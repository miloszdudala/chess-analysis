"""Training: positions from your own games, judged and scheduled."""
import pytest

from chessanalysis import store, training

from .conftest import GAME_SANS, store_game

# White's fourth move (ply 7, 4.c3) drops the eval from 0 to -3.00
MISTAKE = [0] * 7 + [-300] * 14


def _game(user="me", evals=MISTAKE, opp="opp", date="2026.10.01", result="0-1"):
    gid = store_game(user, opp, 2000, 2000, GAME_SANS, source="own", evals=evals,
                     depth=15, top=True, date=date, result=result)
    raw = store.load_analysis(gid, 15)
    # the engine wanted 4.d4; 4.Nc3 was clearly worse; 4.c3 (played) worse still
    raw["top_moves"][6] = [{"uci": "d2d4", "cp": 0}, {"uci": "b1c3", "cp": -150}]
    store.save_analysis(gid, 15, raw, multipv=3, engine="test")
    return gid


def test_a_costly_move_becomes_a_position_to_solve():
    gid = _game()
    found = training.candidates("me")
    assert [p["kind"] for p in found] == ["mistake"]
    p = found[0]
    assert p["id"] == f"{gid}:7" and p["solution"] == "d2d4"
    assert [b["uci"] for b in p["data"]["best"]] == ["d2d4"]      # 4.Nc3 is not good enough
    assert p["data"]["played"]["san"] == "c3" and p["data"]["played"]["loss"] > 20
    assert p["data"]["themes"][0] == "Opening"


def test_a_habit_repeated_in_the_opening_becomes_an_opening_fix():
    _game(date="2026.10.01")
    _game(date="2026.10.02", opp="opp2")
    kinds = sorted(p["kind"] for p in training.candidates("me"))
    assert kinds == ["mistake", "mistake", "opening"]


def test_an_unpunished_gift_is_a_missed_chance():
    # Black's 4...Nf6 throws 3 pawns away (ply 8), White's 5.d3 hands most back
    evals = [0] * 8 + [300, 60] + [60] * 11
    gid = store_game("me", "opp", 2000, 2000, GAME_SANS, source="own", evals=evals,
                     depth=15, top=True, result="1-0")
    found = {p["id"]: p for p in training.candidates("me")}
    assert found[f"{gid}:9"]["kind"] == "missed"
    assert found[f"{gid}:9"]["data"]["gift"] >= 15


def test_judging_a_move():
    _game()
    training.sync("me")
    pid = training.candidates("me")[0]["id"]
    assert training.attempt("me", pid, "d2d4")["solved"]
    wrong = training.attempt("me", pid, "b1c3")
    assert not wrong["solved"] and wrong["loss"] > 10 and wrong["source"] == "analysis"
    # a move the stored analysis never considered goes to the live engine
    assert training.attempt("me", pid, "a2a3", live=lambda fen, uci: {"cp": -10})["solved"]
    assert not training.attempt("me", pid, "a2a3", live=lambda fen, uci: {"cp": -500})["solved"]
    assert training.attempt("me", pid, "a2a5") == {"legal": False}


def test_the_schedule():
    _game()
    training.sync("me")
    pid = training.candidates("me")[0]["id"]
    day = training.DAY
    assert training.grade("me", pid, "good", now=0)["interval"] == 1.0
    assert training.grade("me", pid, "good", now=day)["interval"] == 3.0
    third = training.grade("me", pid, "good", now=4 * day)
    assert third["interval"] > 3.0 and third["due"] == pytest.approx(4 * day + third["interval"] * day)
    failed = training.grade("me", pid, "fail", now=10 * day)
    assert failed["interval"] == 0 and failed["due"] == 10 * day + training.RELEARN
    assert training.get("me", pid)["lapses"] == 1


def test_next_serves_new_positions_then_due_ones():
    _game()
    s = training.sync("me")
    assert s["total"] == 1 and s["new"] == 1
    p = training.next_puzzle("me")
    assert p["status"] == "new" and "solution" not in p and p["played_san"] == "c3"
    training.grade("me", p["id"], "fail")
    assert training.next_puzzle("me")["status"] == "ahead"      # due in ten minutes
    assert training.next_puzzle("me", kind="missed") is None


def test_a_position_that_stops_qualifying_is_retired():
    gid = _game()
    training.sync("me")
    raw = store.load_analysis(gid, 15)
    raw["evals"] = [0] * 21                     # a deeper look: 4.c3 was fine
    store.save_analysis(gid, 15, raw, multipv=3, engine="test")
    assert training.sync("me")["total"] == 0
