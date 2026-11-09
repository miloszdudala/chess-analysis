"""Rebasing the rating curve around a game against a banned opponent."""
from __future__ import annotations

import pytest

from chessanalysis import ratings


class FakeGame:
    """Just the fields `ratings` reads: identity, rating, result, format."""

    def __init__(self, gid, elo, outcome, time_class="rapid", opp_elo=None):
        self.game_id = gid
        self.user_elo = elo
        self.user_elo_raw = elo
        self.outcome = outcome
        self.time_class = time_class
        self.opp_elo = opp_elo


def series(*rows, time_class="rapid"):
    return [FakeGame(f"g{i}", elo, out, time_class)
            for i, (elo, out) in enumerate(rows)]


def elos(games):
    return [g.user_elo for g in games]


# --- the real shape of the bug ---------------------------------------------
# 1970 -> loss to a cheat (-12) -> three honest games -> the refund lands on a
# loss that therefore appears to cost nothing.

REAL = [(1970, "win"), (1958, "loss"), (1946, "loss"), (1957, "win"),
        (1946, "loss"), (1954, "win"), (1954, "loss"), (1967, "win")]


def test_refund_is_spread_over_the_stretch_it_was_missing():
    games = series(*REAL)
    ratings.apply(games, {"g1"})
    # the cheated game and everything up to the refund gets its 12 points back;
    # the refund game itself already has them
    assert elos(games) == [1970, 1970, 1958, 1969, 1958, 1966, 1954, 1967]


def test_corrected_curve_has_no_impossible_rating_change():
    """The point of the whole exercise: once the cheated game is dropped (as
    `load_games` drops it), every remaining rating change moves the way its
    result says it should. The cheated game itself nets zero — that *is* what a
    refunded loss costs — so it is excluded here exactly as it is in the app."""
    games = series(*REAL)
    ratings.apply(games, {"g1"})
    games = [g for g in games if g.game_id != "g1"]
    for prev, g in zip(games, games[1:]):
        delta = g.user_elo - prev.user_elo
        if g.outcome == "win":
            assert delta > 0, f"{g.game_id} is a win that lost rating"
        elif g.outcome == "loss":
            assert delta < 0, f"{g.game_id} is a loss that gained rating"


def test_raw_rating_is_kept_alongside_the_corrected_one():
    games = series(*REAL)
    ratings.apply(games, {"g1"})
    assert elos(games) != [g.user_elo_raw for g in games]
    assert [g.user_elo_raw for g in games] == [e for e, _ in REAL]


# --- a win or draw against a cheat keeps its points ------------------------

@pytest.mark.parametrize("outcome, elo", [("win", 1982), ("draw", 1974)])
def test_beating_a_cheat_is_not_refunded(outcome, elo):
    """Chess.com only gives back rating a game *cost*: a win (or a draw that
    gained points) against someone later banned keeps its gain."""
    games = series((1970, "win"), (elo, outcome), (1960, "loss"))
    ratings.apply(games, {"g1"})
    assert elos(games) == [1970, elo, 1960]


def test_a_draw_that_cost_points_is_refunded():
    games = series((1970, "win"), (1962, "draw"), (1950, "loss"), (1950, "loss"))
    ratings.apply(games, {"g1"})
    assert elos(games) == [1970, 1970, 1958, 1950]


# --- a refund landing on a win ---------------------------------------------
# A win can't move the wrong way, so here the refund only shows as a win worth
# more than its neighbours. Evenly matched opponents, K = 16: an honest game is
# +-8, and the win carrying the 8-point refund is +16.

def test_refund_landing_on_a_win_is_found_by_its_excess():
    rows = [(2000, "win"), (1992, "loss"), (2000, "win"), (2008, "win"),
            (2000, "loss"), (2016, "win"), (2024, "win"), (2016, "loss")]
    games = series(*rows)
    for prev, g in zip(games, games[1:]):
        g.opp_elo = prev.user_elo          # an even game: expected score 0.5
    ratings.apply(games, {"g1"})
    # corrected up to the refund game only — the present rating is untouched
    assert elos(games) == [2000, 2000, 2008, 2016, 2008, 2016, 2024, 2016]


# --- edges -----------------------------------------------------------------

def test_refund_not_landed_yet_corrects_to_the_end():
    games = series((1970, "win"), (1958, "loss"), (1948, "loss"), (1960, "win"))
    ratings.apply(games, {"g1"})
    assert elos(games) == [1970, 1970, 1960, 1972]


def test_other_time_classes_are_untouched():
    rapid = series((1970, "win"), (1958, "loss"), time_class="rapid")
    blitz = series((1200, "loss"), (1190, "loss"), time_class="blitz")
    for i, g in enumerate(blitz):
        g.game_id = f"b{i}"
    ratings.apply(rapid + blitz, {"g1"})
    assert elos(blitz) == [1200, 1190]


def test_a_cheated_first_game_has_no_previous_rating_to_measure_against():
    games = series((1958, "loss"), (1946, "loss"))
    ratings.apply(games, {"g0"})
    assert elos(games) == [1958, 1946]


def test_no_cheated_games_changes_nothing():
    games = series(*REAL)
    ratings.apply(games, set())
    assert elos(games) == [e for e, _ in REAL]


def test_games_without_a_rating_are_skipped():
    games = series((1970, "win"), (1958, "loss"))
    games.insert(1, FakeGame("unrated", None, "win"))
    ratings.apply(games, {"g1"})
    assert games[1].user_elo is None


# --- a refund that never comes ----------------------------------------------
# Chess.com doesn't refund every game against a closed account. Once games
# played well after the ban still show no refund, the loss stands.

def _dated(games, start_day):
    for i, g in enumerate(games):
        g.sort_key = f"2026.10.{start_day + i:02d} 12:00:00"
    return games


NO_REFUND = [(2055, "draw"), (2050, "loss"), (2058, "win"), (2053, "loss"),
             (2061, "win"), (2056, "loss"), (2064, "win")]


def test_missing_refund_long_after_the_ban_is_not_corrected():
    games = _dated(series(*NO_REFUND), 1)
    seen = ratings._epoch(games[1])               # ban seen the day after the game
    ratings.apply(games, {"g1"}, {"g1": seen})    # last game is 5 days later...
    assert elos(games)[-1] == 2069                # ...so still waiting: corrected
    games = _dated(series(*NO_REFUND), 1)
    ratings.apply(games, {"g1"}, {"g1": seen - 3 * 86400})   # 8 days: gave up
    assert elos(games) == [e for e, _ in NO_REFUND]
