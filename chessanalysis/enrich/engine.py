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


@dataclass
class GameAnalysis:
    depth: int
    engine_name: str
    evals: list[int]            # white-POV centipawns, len = plies + 1
    moves: list[MoveEval] = field(default_factory=list)
    accuracy: dict = field(default_factory=dict)   # {"white":.., "black":..}
    acpl: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)      # per side: inaccuracy/mistake/blunder

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
                "fens": []}

    evals, best_uci, moves_san, moves_uci, fens = [], [], [], [], []

    def eval_position(b: chess.Board) -> tuple[int, str]:
        if b.is_game_over():
            if b.is_checkmate():
                # side to move is mated
                cp = -MATE_CP if b.turn == chess.WHITE else MATE_CP
            else:
                cp = 0  # stalemate / draw
            return cp, ""
        info = engine.analyse(b, chess.engine.Limit(depth=depth))
        cp = info["score"].white().score(mate_score=MATE_CP)
        pv = info.get("pv")
        return cp, (pv[0].uci() if pv else "")

    for mv in moves:
        cp, best = eval_position(board)
        evals.append(cp)
        best_uci.append(best)
        fens.append(board.fen())
        moves_san.append(board.san(mv))
        moves_uci.append(mv.uci())
        board.push(mv)
    # final position
    cp, _ = eval_position(board)
    evals.append(cp)
    fens.append(board.fen())
    return {"evals": evals, "best_uci": best_uci, "moves_san": moves_san,
            "moves_uci": moves_uci, "fens": fens}


def _derive(raw: dict, depth: int, engine_name: str) -> GameAnalysis:
    evals = raw["evals"]
    moves_san = raw["moves_san"]
    best_uci = raw["best_uci"]
    fens = raw["fens"]
    moves_uci = raw.get("moves_uci", [])

    move_evals: list[MoveEval] = []
    acc_sum = {"white": 0.0, "black": 0.0}
    cpl_sum = {"white": 0, "black": 0}
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

        move_evals.append(MoveEval(
            ply=i + 1, color=color, san=san, best_san=best_san,
            cp_loss=cp_loss, wp_loss=wp_loss, accuracy=acc, label=label,
            fen_before=fens[i] if i < len(fens) else "",
            move_uci=moves_uci[i] if i < len(moves_uci) else "",
        ))
        acc_sum[color] += acc
        cpl_sum[color] += cp_loss
        n[color] += 1
        if label in counts[color]:
            counts[color][label] += 1

    accuracy = {c: round(acc_sum[c] / n[c], 1) if n[c] else None for c in n}
    acpl = {c: round(cpl_sum[c] / n[c]) if n[c] else None for c in n}
    return GameAnalysis(depth=depth, engine_name=engine_name, evals=evals,
                        moves=move_evals, accuracy=accuracy, acpl=acpl,
                        counts=counts)


def analyse_game(game, depth: int | None = None, engine=None) -> GameAnalysis:
    """Analyse one Game. Uses the disk cache; opens an engine if not given."""
    if depth is None:
        depth = int(config.get("ENGINE_DEPTH", "15"))

    cached = cache.load("engine", f"{game.game_id}_d{depth}")
    if cached and cached.get("evals"):
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
