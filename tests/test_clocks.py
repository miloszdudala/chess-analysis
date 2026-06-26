"""Clock helpers + the time-pressure / clock-management player metrics."""
from __future__ import annotations

from chessanalysis import clocks
from chessanalysis.clocks import (
    ClockProfile, clock_profile, other_color, parse_time_control, pressure_bucket,
)
from chessanalysis.contexts import PlayerContext
from chessanalysis.metrics.player.time_pressure import (
    clock_management, time_pressure,
)
from chessanalysis.model import Game, Move


def make_game(tc, color, outcome, white_clocks, black_clocks, termination=""):
    moves, ply = [], 1
    for i in range(max(len(white_clocks), len(black_clocks))):
        if i < len(white_clocks):
            moves.append(Move(ply=ply, color="white", san="x", clock=white_clocks[i]))
            ply += 1
        if i < len(black_clocks):
            moves.append(Move(ply=ply, color="black", san="x", clock=black_clocks[i]))
            ply += 1
    g = Game(headers={"TimeControl": tc, "Termination": termination}, moves=moves)
    g.color, g.outcome = color, outcome
    return g


# --- parse_time_control -----------------------------------------------------

def test_parse_time_control():
    assert parse_time_control("600") == (600, 0)
    assert parse_time_control("180+2") == (180, 2)
    assert parse_time_control("1/259200") is None      # daily
    assert parse_time_control("") is None
    assert parse_time_control("abc") is None
    assert parse_time_control("0") is None


def test_other_color():
    assert other_color("white") == "black"
    assert other_color("black") == "white"


# --- clock_profile ----------------------------------------------------------

def test_clock_profile_math():
    g = make_game("600", "white", "win",
                  white_clocks=[595, 580, 60], black_clocks=[590, 500, 480])
    p = clock_profile(g, "white")
    assert isinstance(p, ClockProfile)
    assert p.base == 600 and p.inc == 0
    assert p.min_clock == 60 and p.min_frac == 0.1
    assert p.end_clock == 60 and p.end_frac == 0.1
    # spent: 600-595, 595-580, 580-60
    assert p.move_times == [5, 15, 520]
    assert p.avg_move_time == 540 / 3


def test_clock_profile_increment_in_spent():
    g = make_game("180+2", "white", "draw", white_clocks=[180, 175], black_clocks=[179])
    p = clock_profile(g, "white")
    # spent = before - after + inc: (180-180+2)=2, (180-175+2)=7
    assert p.move_times == [2, 7]


def test_clock_profile_none_without_clocks_or_tc():
    no_clocks = make_game("600", "white", "win", [None, None], [None])
    assert clock_profile(no_clocks, "white") is None
    daily = make_game("1/259200", "white", "win", [100], [100])
    assert clock_profile(daily, "white") is None


def test_pressure_bucket_boundaries():
    assert pressure_bucket(0.05) == clocks.PRESSURE_BUCKETS[0][1]   # severe
    assert pressure_bucket(0.20) == clocks.PRESSURE_BUCKETS[1][1]   # time trouble
    assert pressure_bucket(0.40) == clocks.PRESSURE_BUCKETS[2][1]   # some
    assert pressure_bucket(0.90) == clocks.PRESSURE_BUCKETS[3][1]   # comfortable


# --- metrics ----------------------------------------------------------------

def _ctx(games):
    return PlayerContext(player="me", games=games)


def test_time_pressure_buckets_by_outcome():
    severe = make_game("600", "white", "win", [595, 30], [590, 580])   # min 30/600=.05
    comfy = make_game("600", "white", "loss", [595, 400], [590, 580])  # min 400/600=.67
    widgets = time_pressure(_ctx([severe, comfy]))
    assert widgets[0]["type"] == "text"
    you_tbl = widgets[1]
    assert you_tbl["type"] == "wdl_table"
    by_label = {r["label"]: r for r in you_tbl["rows"]}
    assert by_label["Severe (<10% left)"]["win"] == 1
    assert by_label["Comfortable (>50%)"]["loss"] == 1


def test_time_pressure_opponent_table_uses_opponent_clock():
    # opponent (black) crashes to 20/600 = .03 severe; player (white) wins
    g = make_game("600", "white", "win", [595, 500], [590, 20])
    opp_tbl = time_pressure(_ctx([g]))[2]
    assert opp_tbl["label_col"] == "When opponent's clock got to"
    by_label = {r["label"]: r for r in opp_tbl["rows"]}
    assert by_label["Severe (<10% left)"]["win"] == 1


def test_time_pressure_none_without_clock_data():
    no_data = make_game("1/259200", "white", "win", [100], [100])
    assert time_pressure(_ctx([no_data])) is None


def test_clock_management_cards():
    won = make_game("600", "white", "win", [595, 300], [590, 580],
                    termination="me won on time")
    lost = make_game("600", "white", "loss", [595, 40], [590, 580])  # time trouble
    w = clock_management(_ctx([won, lost]))
    assert w["type"] == "cards"
    labels = {c["label"]: c["value"] for c in w["items"]}
    assert "Your time left at finish" in labels
    assert labels["Won / lost on time"] == "1 / 0"
    # one of two games dropped below 10% -> 50%
    assert labels["Games you hit time trouble"] == "50%"
