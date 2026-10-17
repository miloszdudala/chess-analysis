"""One long-lived engine for interactive questions, with a memory.

Exploring a variation on the review board, grading a training move, and
showing the engine's view of an explorer position all ask the same thing —
"what does the engine make of this position?" — a few hundred milliseconds
at a time. Starting Stockfish per request would cost more than the search, so
one process serves them all, a lock serialises it (the web server answers on
several threads), and answers are remembered: the explorer and the trainer
revisit the same positions constantly.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

import chess
import chess.engine

from .enrich.engine import MATE_CP, find_engine

_LOCK = threading.Lock()
_ENGINE = None
_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 4000


def _engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = chess.engine.SimpleEngine.popen_uci(find_engine())
        _ENGINE.configure({"Hash": 64})
    return _ENGINE


def _terminal(board: chess.Board) -> dict:
    cp = 0
    if board.is_checkmate():
        cp = -MATE_CP if board.turn == chess.WHITE else MATE_CP
    return {"cp": cp, "best": [], "depth": 0, "over": True}


def analyse(fen: str, depth: int = 14, multipv: int = 3, pv_len: int = 0) -> dict:
    """{"cp": white-POV centipawns, "best": [{"uci","san","cp","pv"?}], "depth"}.

    `pv_len` > 0 also returns each candidate's principal variation in SAN, up
    to that many plies.
    """
    key = (fen, depth, multipv, pv_len)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    board = chess.Board(fen)
    if board.is_game_over():
        return _terminal(board)
    with _LOCK:
        try:
            infos = _engine().analyse(board, chess.engine.Limit(depth=depth),
                                      multipv=multipv)
        except chess.engine.EngineTerminatedError:
            globals()["_ENGINE"] = None           # restart on the next call
            raise
    if isinstance(infos, dict):
        infos = [infos]
    best = []
    for it in infos:
        pv = it.get("pv")
        if not pv:
            continue
        entry = {"uci": pv[0].uci(), "san": board.san(pv[0]),
                 "cp": it["score"].white().score(mate_score=MATE_CP)}
        if pv_len:
            entry["pv"] = _san_line(board, pv[:pv_len])
        best.append(entry)
    out = {"cp": best[0]["cp"] if best else 0, "best": best, "depth": depth,
           "over": False}
    with _LOCK:
        _CACHE[key] = out
        if len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return out


def _san_line(board: chess.Board, moves) -> list[str]:
    b = board.copy(stack=False)
    out = []
    for mv in moves:
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out


def after_move(fen: str, uci: str, depth: int = 14) -> dict | None:
    """Apply `uci` (a bare pawn move to the last rank becomes a queen) and
    analyse the result. None if the move is illegal."""
    board = chess.Board(fen)
    mv = parse_move(board, uci)
    if mv is None:
        return None
    san = board.san(mv)
    board.push(mv)
    res = analyse(board.fen(), depth=depth, multipv=1, pv_len=8)
    return {"fen": board.fen(), "san": san, "uci": mv.uci(), **res}


def parse_move(board: chess.Board, uci: str):
    try:
        mv = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if mv not in board.legal_moves and len(uci) == 4:
        mv = chess.Move.from_uci(uci + "q")
    return mv if mv in board.legal_moves else None


def close() -> None:
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            try:
                _ENGINE.quit()
            except Exception:                     # noqa: BLE001
                pass
            _ENGINE = None
