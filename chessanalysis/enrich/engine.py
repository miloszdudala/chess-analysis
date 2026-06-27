"""Stockfish-backed per-move analysis: evals, centipawn loss, accuracy.

Caches raw engine output (evals + best moves) per game on disk, so re-runs are
instant and tweaking the classification thresholds never needs a re-run.
"""
from __future__ import annotations

import io
import math
import os
import shutil
from dataclasses import dataclass, field

import chess
import chess.engine
import chess.pgn

from .. import cache, config

MATE_CP = 10000
# win%-drop thresholds (percentage points), à la Lichess.
BLUNDER, MISTAKE, INACCURACY = 20.0, 10.0, 5.0


def find_engine() -> str:
    path = config.get("STOCKFISH_PATH")
    if path and os.path.exists(path):
        return path
    found = shutil.which("stockfish")
    if found:
        return found
    raise FileNotFoundError(
        "No UCI engine found. Set STOCKFISH_PATH in .env or install one "
        "(`brew install stockfish`)."
    )


def win_prob(cp: float) -> float:
    """Centipawns (one side's POV) -> win probability in [0,100]."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def _move_accuracy(wp_loss: float) -> float:
    acc = 103.1668 * math.exp(-0.04354 * wp_loss) - 3.1669
    return max(0.0, min(100.0, acc))


def _classify(wp_loss: float) -> str:
    if wp_loss >= BLUNDER:
        return "blunder"
    if wp_loss >= MISTAKE:
        return "mistake"
    if wp_loss >= INACCURACY:
        return "inaccuracy"
    return "ok"


def _stddev(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


WEIGHT_FLOOR = 0.5          # a quiet, accurate move still counts a little
MAX_WEIGHT_SHARE = 0.25     # no single move may own more than this of the total


def _capped_weighted_mean(values, weights) -> float:
    """Weighted mean, but iteratively cap each weight at MAX_WEIGHT_SHARE of the
    running total — so one wild swing can't single-handedly define the score."""
    w = list(weights)
    for _ in range(6):
        cap = sum(w) * MAX_WEIGHT_SHARE
        capped = [min(x, cap) for x in w]
        if capped == w:
            break
        w = capped
    total = sum(w) or 1.0
    return sum(v * x for v, x in zip(values, w)) / total


def _game_accuracy(evals, moves) -> dict:
    """Per-colour game accuracy, robust to a single catastrophic move.

    Blends two views of the per-move accuracies (each from the Lichess win%
    model):
      * the plain mean — every move counts equally;
      * a *criticality-weighted* mean — each move weighted by how volatile the
        position was (stddev of the white win% over a sliding window), so the
        moments that actually decided the game count more.
    Weights are floored (quiet moves still count) and capped so no single move
    owns more than a quarter of the total — a lone game-ending blunder dents the
    score without collapsing it (an unweighted/harmonic mean would zero out on
    one 0% move). The two views are averaged.
    """
    out = {"white": None, "black": None}
    if not moves:
        return out
    wp = [win_prob(e) for e in evals]              # white-POV win%, len = plies+1
    window = max(2, min(8, len(wp) // 10))
    weights = []                                   # one per played move (by ply)
    for i in range(1, len(wp)):
        lo = max(0, i - window + 1)
        weights.append(max(_stddev(wp[lo:i + 1]), WEIGHT_FLOOR))
    acc = {"white": [], "black": []}
    wts = {"white": [], "black": []}
    for m in moves:
        i = m.ply - 1
        if 0 <= i < len(weights):
            acc[m.color].append(m.accuracy)
            wts[m.color].append(weights[i])
    for c in ("white", "black"):
        if not acc[c]:
            continue
        plain = sum(acc[c]) / len(acc[c])
        weighted = _capped_weighted_mean(acc[c], wts[c])
        out[c] = round((plain + weighted) / 2, 1)
    return out


@dataclass
class MoveEval:
    ply: int
    color: str          # "white" | "black"
    san: str
    best_san: str
    cp_loss: int        # centipawns lost vs best (mover POV)
    wp_loss: float      # win% lost (mover POV)
    accuracy: float
    label: str          # ok / inaccuracy / mistake / blunder
    fen_before: str
    move_uci: str
    top3: bool = False  # the move was among the engine's top-3 candidates


@dataclass
class GameAnalysis:
    depth: int
    engine_name: str
    evals: list[int]            # white-POV centipawns, len = plies + 1
    moves: list[MoveEval] = field(default_factory=list)
    accuracy: dict = field(default_factory=dict)   # {"white":.., "black":..}
    top3: dict = field(default_factory=dict)        # % of moves in engine's top-3
    acpl: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)      # per side: inaccuracy/mistake/blunder
    fens: list = field(default_factory=list)        # FEN per position, len = plies + 1
    top_moves: list = field(default_factory=list)   # per position: [{"uci","cp"},..] (white POV)

    def blunders(self, color: str | None = None) -> list[MoveEval]:
        return [m for m in self.moves
                if m.label == "blunder" and (color is None or m.color == color)]

    def key_moments(self, n: int = 6) -> list[MoveEval]:
        flagged = [m for m in self.moves if m.label in ("blunder", "mistake")]
        return sorted(flagged, key=lambda m: -m.wp_loss)[:n]

    def decisive(self, cp: int = 200) -> dict:
        """First moment the eval crosses +/-cp, which side, and whether it held.

        held = the advantage never dropped back below the threshold afterwards
        (it stayed at least that decisive, or grew). Returns reached=False if the
        game never became decisive by this threshold.
        """
        evals = self.evals
        first, side = None, None
        for i, e in enumerate(evals):
            if e >= cp:
                first, side = i, "white"
                break
            if e <= -cp:
                first, side = i, "black"
                break
        if first is None:
            return {"reached": False, "cp": cp}
        rest = evals[first:]
        held = (min(rest) >= cp) if side == "white" else (max(rest) <= -cp)
        return {"reached": True, "cp": cp, "ply": first,
                "move_no": (first + 1) // 2, "side": side, "held": held}


def _read_board_moves(pgn_text: str):
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None, []
    board = game.board()
    return board, list(game.mainline_moves())


def _raw_evals(pgn_text: str, depth: int, engine) -> dict:
    """Run the engine over every position; return cached-shaped raw output."""
    board, moves = _read_board_moves(pgn_text)
    if board is None:
        return {"evals": [], "best_uci": [], "moves_san": [], "moves_uci": [],
                "fens": [], "top_moves": []}

    evals, best_uci, moves_san, moves_uci, fens, top_moves = [], [], [], [], [], []

    def eval_position(b: chess.Board) -> tuple[int, str, list]:
        """Returns (white-POV cp, best move uci, top-3 [{"uci","cp"}])."""
        if b.is_game_over():
            if b.is_checkmate():
                # side to move is mated
                cp = -MATE_CP if b.turn == chess.WHITE else MATE_CP
            else:
                cp = 0  # stalemate / draw
            return cp, "", []
        infos = engine.analyse(b, chess.engine.Limit(depth=depth), multipv=3)
        if isinstance(infos, dict):              # engine without MultiPV support
            infos = [infos]
        top = []
        for it in infos:
            pv = it.get("pv")
            if not pv:
                continue
            top.append({"uci": pv[0].uci(),
                        "cp": it["score"].white().score(mate_score=MATE_CP)})
        cp = top[0]["cp"] if top else infos[0]["score"].white().score(mate_score=MATE_CP)
        return cp, (top[0]["uci"] if top else ""), top

    for mv in moves:
        cp, best, top = eval_position(board)
        evals.append(cp)
        best_uci.append(best)
        top_moves.append(top)
        fens.append(board.fen())
        moves_san.append(board.san(mv))
        moves_uci.append(mv.uci())
        board.push(mv)
    # final position
    cp, _, top = eval_position(board)
    evals.append(cp)
    top_moves.append(top)
    fens.append(board.fen())
    return {"evals": evals, "best_uci": best_uci, "moves_san": moves_san,
            "moves_uci": moves_uci, "fens": fens, "top_moves": top_moves}


def _derive(raw: dict, depth: int, engine_name: str) -> GameAnalysis:
    evals = raw["evals"]
    moves_san = raw["moves_san"]
    best_uci = raw["best_uci"]
    fens = raw["fens"]
    moves_uci = raw.get("moves_uci", [])
    top_moves = raw.get("top_moves", [])

    move_evals: list[MoveEval] = []
    cpl_sum = {"white": 0, "black": 0}
    top3_sum = {"white": 0, "black": 0}
    n = {"white": 0, "black": 0}
    counts = {"white": {"inaccuracy": 0, "mistake": 0, "blunder": 0},
              "black": {"inaccuracy": 0, "mistake": 0, "blunder": 0}}

    for i, san in enumerate(moves_san):
        white_to_move = (i % 2 == 0)
        color = "white" if white_to_move else "black"
        cp_before_w, cp_after_w = evals[i], evals[i + 1]

        if white_to_move:
            cp_loss = max(0, cp_before_w - cp_after_w)
            wp_before = win_prob(cp_before_w)
            wp_after = win_prob(cp_after_w)
        else:
            cp_loss = max(0, cp_after_w - cp_before_w)
            wp_before = win_prob(-cp_before_w)
            wp_after = win_prob(-cp_after_w)

        wp_loss = max(0.0, wp_before - wp_after)
        acc = _move_accuracy(wp_loss)
        label = _classify(wp_loss)

        best_san = ""
        if best_uci[i] and i < len(fens):
            try:
                b = chess.Board(fens[i])
                best_san = b.san(chess.Move.from_uci(best_uci[i]))
            except (ValueError, AssertionError):
                best_san = ""

        move_uci = moves_uci[i] if i < len(moves_uci) else ""
        cand = [t["uci"] for t in (top_moves[i] if i < len(top_moves) else [])][:3]
        in_top3 = bool(move_uci) and move_uci in cand

        move_evals.append(MoveEval(
            ply=i + 1, color=color, san=san, best_san=best_san,
            cp_loss=cp_loss, wp_loss=wp_loss, accuracy=acc, label=label,
            fen_before=fens[i] if i < len(fens) else "",
            move_uci=move_uci, top3=in_top3,
        ))
        cpl_sum[color] += cp_loss
        top3_sum[color] += in_top3
        n[color] += 1
        if label in counts[color]:
            counts[color][label] += 1

    accuracy = _game_accuracy(evals, move_evals)
    top3 = {c: round(100 * top3_sum[c] / n[c], 1) if n[c] else None for c in n}
    acpl = {c: round(cpl_sum[c] / n[c]) if n[c] else None for c in n}
    return GameAnalysis(depth=depth, engine_name=engine_name, evals=evals,
                        moves=move_evals, accuracy=accuracy, top3=top3, acpl=acpl,
                        counts=counts, fens=fens, top_moves=top_moves)


def analyse_game(game, depth: int | None = None, engine=None) -> GameAnalysis:
    """Analyse one Game. Uses the disk cache; opens an engine if not given."""
    if depth is None:
        depth = int(config.get("ENGINE_DEPTH", "15"))

    cached = cache.load("engine", f"{game.game_id}_d{depth}")
    # `top_moves` was added later; recompute caches that predate it so the
    # board explorer always has engine arrows.
    if cached and cached.get("evals") and cached.get("top_moves"):
        return _derive(cached, depth, cached.get("engine_name", "cache"))

    own_engine = engine is None
    if own_engine:
        engine = chess.engine.SimpleEngine.popen_uci(find_engine())
    try:
        engine_name = engine.id.get("name", "Stockfish")
        raw = _raw_evals(game.pgn, depth, engine)
    finally:
        if own_engine:
            engine.quit()

    raw["engine_name"] = engine_name
    cache.save("engine", f"{game.game_id}_d{depth}", raw)
    return _derive(raw, depth, engine_name)
