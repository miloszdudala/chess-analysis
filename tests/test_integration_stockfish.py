"""End-to-end engine run. Skipped automatically when no UCI engine is present.

Validates the multipv plumbing: a fresh analysis must capture top-3 moves per
position and store them (so the board explorer gets its arrows).
"""
from __future__ import annotations

import pytest

from chessanalysis import store
from chessanalysis.enrich import engine as eng
from chessanalysis.model import Game


def _has_engine():
    try:
        eng.find_engine()
        return True
    except Exception:                       # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _has_engine(), reason="no UCI engine installed")

PGN = '[Event "t"]\n[White "A"]\n[Black "B"]\n[Date "2026.01.01"]\n\n' \
      "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0\n"


def test_analyse_game_captures_top_moves():
    g = Game(headers={"White": "A", "Black": "B", "Date": "2026.01.01"}, pgn=PGN)
    a = eng.analyse_game(g, depth=6)

    assert len(a.top_moves) == len(a.fens)              # one entry per position
    assert len(a.evals) == len(a.fens)
    assert all(isinstance(t, list) for t in a.top_moves)
    # opening position should offer multiple candidate moves
    assert 1 <= len(a.top_moves[0]) <= 3
    for cand in a.top_moves[0]:
        assert "uci" in cand and "cp" in cand

    # stored complete (with top_moves) -> a re-run reads it back instead of
    # paying for the engine again
    cached = store.load_analysis(g.game_id, 6)
    assert cached and cached.get("top_moves")
