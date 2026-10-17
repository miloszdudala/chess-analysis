"""The coach: where win chance goes, against rating-matched corpus players."""
from chessanalysis import coach, phases

from .conftest import GAME_SANS, store_game


def _div(plies, mid=None, end=None):
    return phases.Division(mid, end, plies)


def test_each_partition_adds_up_to_the_total():
    evals = [0, -100, -50, -300, -250, -400, -350]
    led = coach.side_ledger(evals, _div(6, mid=2, end=4), "white",
                            clocks=[590, 50, 40], base=600)
    total = led["total"][0]
    for group in (("op", "mg", "eg"), ("ahead", "level", "behind"),
                  ("comfortable", "low", "trouble")):
        assert abs(sum(led.get(k, [0, 0])[0] for k in group) - total) < 0.01   # stored to 3 dp
    assert led["total"][1] == 3
    assert led["trouble"][1] == 1          # the third move began under 10% of the clock
    assert led["behind"][1] == 1           # ...and at -2.50


def test_black_is_measured_from_blacks_side():
    evals = [0, 0, 100, 100]               # black's move at ply 2 hands white 100cp
    led = coach.side_ledger(evals, _div(3), "black")
    assert led["total"][0] > 5 and led["total"][1] == 1
    assert led.get("trouble") is None      # no clocks, no clock buckets


def test_a_reply_to_the_opponents_mistake_is_its_own_bucket():
    evals = [0, 0, 400, 100]               # black blunders, white gives most back
    led = coach.side_ledger(evals, _div(3), "white")
    assert led["reply"][1] == 1 and led["reply"][0] > 20


def _corpus(n=80):
    oscillate = [0 if i % 2 == 0 else -30 for i in range(len(GAME_SANS) + 1)]
    for k in range(n):
        store_game(f"cw{k}", f"cb{k}", 2000, 2010, GAME_SANS, evals=oscillate)


def test_the_control_cancels_what_both_sides_of_your_games_share():
    _corpus()
    # in your games both sides lose three times what the corpus does
    both_worse = [0 if i % 2 == 0 else -90 for i in range(len(GAME_SANS) + 1)]
    for k in range(8):
        store_game("me", f"opp{k}", 2000, 2000, GAME_SANS, source="own", evals=both_worse)
    res = coach.compare("me")
    total = next(r for r in res["rows"] if r["key"] == "total")
    assert total["gap"] > 0.5 and total["control"] > 0.5
    assert abs(total["net"]) < 0.15 and total["verdict"] == "level"


def test_a_real_leak_is_flagged():
    _corpus()
    # you lose 90cp a move, your opponents 30 — the corpus 30
    evals, e = [0], 0
    for i in range(len(GAME_SANS)):
        e += -90 if i % 2 == 0 else 30
        evals.append(e)
    for k in range(8):
        store_game("me", f"opp{k}", 2000, 2000, GAME_SANS, source="own", evals=evals)
    res = coach.compare("me")
    total = next(r for r in res["rows"] if r["key"] == "total")
    assert total["verdict"] == "leak" and total["net"] > 0.3
    assert res["games"] == 8 and res["elo_range"] == [2000, 2000]
    assert coach.focus(res)["leaks"]


def test_nothing_to_compare_without_a_corpus():
    store_game("me", "x", 2000, 2000, GAME_SANS, source="own", evals=[0] * 21)
    assert coach.compare("me") is None


def test_ledgers_are_stored_and_reused():
    from chessanalysis import store

    gid = store_game("a", "b", 2000, 2000, GAME_SANS, evals=[0] * 21)
    first = coach.ledgers([gid], 10)
    assert (gid, "white") in first and (gid, "black") in first
    n = store.connect().execute("SELECT COUNT(*) FROM ledgers").fetchone()[0]
    assert n == 2 and coach.ledgers([gid], 10) == first
