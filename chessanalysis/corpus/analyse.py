"""Turning banked games into samples: one shallow engine pass, two data points.

Runs at `corpus.DEPTH` with multipv 1. The depth study behind that choice: at
depth 10 accuracy is unbiased against the depth-15 review setting (-0.2 points,
r=0.989) while running ~17x faster, and multipv 3 costs 3.6x more for candidate
moves no bracket statistic reads. Depth 8 and below is not merely noisier, it
is *biased*: a shallow engine misses the refutation, so a mistake scores as a
fine move (+1.7 accuracy at d8, +2.3 at d6).

Parallelism is independent OS processes, deliberately not a ProcessPoolExecutor:
python-chess drives the engine over asyncio, whose subprocess child-watcher
wants the main thread of the main interpreter. Inside pool workers the run
stalls with live-but-unresponsive engines and never tears down. A shard is a
normal main thread, so the engine behaves, and a shard that dies costs only its
own share of the work.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time

import chess
import chess.engine
import chess.pgn

from .. import store
from ..enrich import engine as eng
from . import DEPTH, MULTIPV

# Non-pawn, non-king material at which the endgame has begun.
ENDGAME_MATERIAL = 13
_VAL = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}

SAMPLE_COLS = (
    "gid,color,depth,elo,opp_elo,band,outcome,plies,acc,acpl,inacc,mist,blun,"
    "op_n,op_acc,op_cpl,op_ia,op_mi,op_bl,"
    "mg_n,mg_acc,mg_cpl,mg_ia,mg_mi,mg_bl,"
    "eg_n,eg_acc,eg_cpl,eg_ia,eg_mi,eg_bl,dec_ply,dec_side,dec_held")


def _phase(move_no: int) -> str:
    """The split the rest of the app uses (weaknesses.py / insights.py)."""
    if move_no <= 12:
        return "op"
    return "mg" if move_no <= 32 else "eg"


def _material(board):
    return sum(_VAL[p] * len(board.pieces(p, c))
               for p in _VAL for c in (chess.WHITE, chess.BLACK))


def analyse_pgn(pgn_text: str, engine, depth: int = DEPTH) -> dict | None:
    """Raw engine output for one game, plus the ply the endgame started."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None
    board = game.board()
    moves = list(game.mainline_moves())
    if not moves:
        return None
    evals, best_uci, san, uci, fens, top = [], [], [], [], [], []
    eg_ply, t0 = None, time.time()

    def ev(b):
        if b.is_game_over():
            if b.is_checkmate():
                return (-eng.MATE_CP if b.turn == chess.WHITE else eng.MATE_CP), "", []
            return 0, "", []
        info = engine.analyse(b, chess.engine.Limit(depth=depth), multipv=MULTIPV)
        if isinstance(info, list):
            info = info[0]
        pv = info.get("pv")
        cp = info["score"].white().score(mate_score=eng.MATE_CP)
        best = pv[0].uci() if pv else ""
        # The principal variation is recorded even at multipv 1. It costs
        # nothing — the engine already searched it — and without it the stats
        # that ask what the refutation *was* (blunder anatomy, opponent-error
        # capitalisation) have nothing to compare the played move against and
        # silently collapse to a single bucket.
        return cp, best, ([{"uci": best, "cp": cp}] if best else [])

    for i, mv in enumerate(moves):
        if eg_ply is None and _material(board) <= ENDGAME_MATERIAL:
            eg_ply = i + 1
        cp, best, tm = ev(board)
        evals.append(cp)
        best_uci.append(best)
        top.append(tm)
        fens.append(board.fen())
        san.append(board.san(mv))
        uci.append(mv.uci())
        board.push(mv)
    cp, _, tm = ev(board)
    evals.append(cp)
    top.append(tm)
    fens.append(board.fen())
    return {"evals": evals, "best_uci": best_uci, "moves_san": san, "moves_uci": uci,
            "fens": fens, "top_moves": top, "eg_ply": eg_ply,
            "secs": round(time.time() - t0, 2)}


def sample_rows(gid, raw, welo, belo, result, depth=DEPTH) -> list[list]:
    """The two sample rows — white's and black's — from one engine pass."""
    a = eng._derive(raw, depth, "sf")
    out = []
    for color in ("white", "black"):
        ms = [m for m in a.moves if m.color == color]
        if not ms:
            continue
        ph = {k: [0, 0.0, 0, 0, 0, 0] for k in ("op", "mg", "eg")}
        for m in ms:
            p = ph[_phase((m.ply + 1) // 2)]
            p[0] += 1
            p[1] += m.accuracy
            p[2] += m.cp_loss
            p[3] += m.label == "inaccuracy"
            p[4] += m.label == "mistake"
            p[5] += m.label == "blunder"
        elo, opp = (welo, belo) if color == "white" else (belo, welo)
        outcome = ("draw" if result == "1/2-1/2" else
                   "win" if (result == "1-0") == (color == "white") else "loss")
        d = a.decisive(200)
        r = [str(gid), color, depth, elo, opp,
             (welo + belo) // 2 // 100 * 100, outcome, len(a.moves),
             a.accuracy[color], a.acpl[color], a.counts[color]["inaccuracy"],
             a.counts[color]["mistake"], a.counts[color]["blunder"]]
        for k in ("op", "mg", "eg"):
            n, acc, cpl, ia, mi, bl = ph[k]
            r += [n, round(acc / n, 2) if n else None, cpl, ia, mi, bl]
        r += [d["ply"], d["side"], int(d["held"])] if d["reached"] else [None, None, None]
        out.append(r)
    return out


def pending(depth: int = DEPTH) -> int:
    return store.connect().execute(
        "SELECT COUNT(*) FROM games g LEFT JOIN analysis a "
        "ON a.gid=g.gid AND a.depth=? WHERE a.gid IS NULL", (depth,)).fetchone()[0]


def shard(i: int, n: int, depth: int = DEPTH) -> None:
    """Analyse every n-th unanalysed game. One plain OS process per shard."""
    conn = store.connect()
    todo = conn.execute(
        "SELECT g.gid, g.pgn, g.welo, g.belo, g.result FROM games g "
        "LEFT JOIN analysis a ON a.gid=g.gid AND a.depth=? WHERE a.gid IS NULL "
        "ORDER BY g.gid", (depth,)).fetchall()[i::n]
    if not todo:
        return
    proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
    proc.configure({"Hash": 16, "Threads": 1})
    try:
        for r in todo:
            raw = analyse_pgn(store.unpack_pgn(r["pgn"]), proc, depth)
            if raw is None:
                continue
            store.save_analysis(r["gid"], depth, raw, multipv=MULTIPV,
                                engine="sf", secs=raw["secs"])
            if r["welo"] is not None and r["belo"] is not None:
                for row in sample_rows(r["gid"], raw, r["welo"], r["belo"], r["result"],
                                       depth):
                    conn.execute(
                        f"INSERT OR REPLACE INTO samples({SAMPLE_COLS}) "
                        f"VALUES({','.join('?' * 34)})", row)
                conn.commit()
    finally:
        proc.close()


def analyse_own(user: str, depth: int = DEPTH, limit: int = 25) -> int:
    """Analyse your own not-yet-covered games, in this process.

    Only ever a handful — the games played since you last opened the tab — so
    one engine and no sharding. Capped so a first run on a long history cannot
    hang a page load; the rest are picked up by the next Expand.
    """
    from .. import corpus

    todo = corpus.pending_own(user, depth)[:limit]
    if not todo:
        return 0
    proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
    proc.configure({"Hash": 16, "Threads": 1})
    conn = store.connect()
    done = 0
    try:
        for g in todo:
            raw = analyse_pgn(g.pgn, proc, depth)
            if raw is None:
                continue
            store.save_analysis(g.game_id, depth, raw, multipv=MULTIPV,
                                engine="sf", secs=raw["secs"])
            welo, belo = g.h("WhiteElo"), g.h("BlackElo")
            if welo.isdigit() and belo.isdigit():
                for row in sample_rows(g.game_id, raw, int(welo), int(belo),
                                       g.result, depth):
                    conn.execute(f"INSERT OR REPLACE INTO samples({SAMPLE_COLS}) "
                                 f"VALUES({','.join('?' * 34)})", row)
            done += 1
        conn.commit()
    finally:
        proc.close()
    return done


def run(workers: int = 3, depth: int = DEPTH) -> int:
    """Analyse everything outstanding across `workers` shards. Returns the count."""
    n = pending(depth)
    if not n:
        return 0
    procs = [subprocess.Popen([sys.executable, "-m", __name__, "shard", str(i),
                               str(workers), str(depth)],
                              cwd=os.getcwd()) for i in range(workers)]
    for p in procs:
        p.wait()
    return n - pending(depth)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "shard":
        shard(int(sys.argv[2]), int(sys.argv[3]),
              int(sys.argv[4]) if len(sys.argv) > 4 else DEPTH)
