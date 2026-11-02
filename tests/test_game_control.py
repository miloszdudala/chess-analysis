"""Average win chance: who had the better of a game, not who made fewer errors."""
from __future__ import annotations

import pytest

from chessanalysis.contexts import GameContext
from chessanalysis.enrich.engine import win_prob
from chessanalysis.metrics.game.control import SETTLED, control
from chessanalysis.metrics.game.review import summary

from .conftest import FakeGame


def test_a_pawn_down_draw_reads_below_half():
    # level, then a pawn down for a long stretch, then back to level: a draw
    evals = [0, 0] + [-100] * 20 + [0, 0]
    c = control(evals, "white")
    assert c["counted"] == c["total"] == 23           # never settled: every move counts
    assert c["avg"] < 50
    assert control(evals, "black")["avg"] == pytest.approx(100 - c["avg"])


def test_counting_stops_where_the_game_was_settled():
    # a piece up at move 6, then a long mop-up, or a quick resignation
    decided = [0, 20, -10, 30, 0, 300]
    long = control(decided + [400, 600, 800] + [900] * 30, "white")
    short = control(decided + [400, 600, 800], "white")
    first = next(i for i, cp in enumerate(decided + [400, 600, 800]) if win_prob(cp) >= SETTLED)
    assert long["counted"] == short["counted"] == first   # up to the settling move
    assert long["avg"] == pytest.approx(short["avg"])


def test_a_swing_back_resets_the_settled_point():
    # winning, thrown away, then won again: only the last winning run is the tail
    evals = [0, 900, 900, 0, -50, 900, 900]
    c = control(evals, "white")
    assert c["counted"] == 5


def test_shown_as_one_card_in_the_game_in_numbers(sample_analysis):
    out = summary(GameContext(game=FakeGame(color="white"),
                              analysis=sample_analysis, player="Alice"))
    cards = {c["label"]: c for c in out[0]["items"]}
    assert cards["Your average win chance"]["value"].endswith("%")
