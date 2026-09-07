"""Shared fixtures and helpers for the test suite.

Most tests avoid invoking a real engine: they feed `engine._derive` a
cache-shaped `raw` dict built from a real move sequence (so FENs/SAN are valid)
with synthetic evals and top-3 moves. Stockfish-backed tests live in
test_integration_stockfish.py and skip themselves when no engine is installed.
"""
from __future__ import annotations

import chess
import pytest

from chessanalysis import cache, store
from chessanalysis.enrich import engine as eng


# --- a fake Game good enough for the engine + game-review code paths --------

class FakeGame:
    def __init__(self, game_id="testgame", color="white",
                 white="Alice", black="Bob", pgn=""):
        self._id = game_id
        self.color = color
        self.pgn = pgn
        self._h = {"White": white, "Black": black}

    @property
    def game_id(self):
        return self._id

    def h(self, key, default=""):
        return self._h.get(key, default)


# --- build a cache-shaped raw dict from a UCI move list ---------------------

def build_raw(uci_moves, evals, engine_name="TestFish"):
    """Construct what `engine._raw_evals` would cache for a move sequence.

    `evals` is the white-POV centipawn list (len == len(uci_moves) + 1).
    FENs and SAN are derived from a real board so they're always valid; the
    per-position top-3 moves are the first 3 legal moves with synthetic evals.
    """
    assert len(evals) == len(uci_moves) + 1, "evals must be plies + 1"
    board = chess.Board()
    fens, moves_san, moves_uci, best_uci, top_moves = [], [], [], [], []
    for u in uci_moves:
        mv = chess.Move.from_uci(u)
        fens.append(board.fen())
        moves_san.append(board.san(mv))
        moves_uci.append(u)
        legal = list(board.legal_moves)[:3]
        top = [{"uci": m.uci(), "cp": 30 - 10 * i} for i, m in enumerate(legal)]
        top_moves.append(top)
        best_uci.append(top[0]["uci"] if top else "")
        board.push(mv)
    fens.append(board.fen())                        # final position
    legal = list(board.legal_moves)[:3]
    top_moves.append([{"uci": m.uci(), "cp": 0} for m in legal])
    return {
        "evals": list(evals), "best_uci": best_uci, "moves_san": moves_san,
        "moves_uci": moves_uci, "fens": fens, "top_moves": top_moves,
        "engine_name": engine_name,
    }


# 1.e4 e5 2.Nf3 Nc6 — white drifts then blunders on move 2 (black's reply great)
SAMPLE_UCI = ["e2e4", "e7e5", "g1f3", "b8c6"]
SAMPLE_EVALS = [20, 18, 35, 30, 600]   # last jump => white's 2nd move is a blunder


@pytest.fixture
def sample_raw():
    return build_raw(SAMPLE_UCI, SAMPLE_EVALS)


@pytest.fixture
def sample_analysis(sample_raw):
    return eng._derive(sample_raw, depth=12, engine_name="TestFish")


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a temp dir so tests never touch real caches."""
    monkeypatch.setattr(cache, "CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Every test gets its own empty store.

    Autouse on purpose: the store holds real games and real engine analyses,
    and a test that wrote into it would corrupt them silently.
    """
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test-chess.db"))
    store.reset()
    yield store
    store.reset()
