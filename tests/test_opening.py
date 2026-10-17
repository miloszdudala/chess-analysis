"""Opening strength and repertoire statistics.

The statistics are checked on synthetic corpora built so the right answer is
known: a conversion slope planted in the results, a theory edge planted inside
each player's games behind a confound that fools a pooled comparison, real
between-player differences planted under game-to-game noise.
"""
import random

import pytest

from chessanalysis import opening as op
from chessanalysis.enrich.engine import win_prob

from .conftest import parsed_game as game

pytestmark = pytest.mark.usefixtures("tiny_book")


# --- records ----------------------------------------------------------------------

def test_record_splits_the_opening_between_both_sides():
    g = game("1. e4 e5 2. Nf3 Qh4 3. Nxh4", result="1-0")
    evals = [20, 30, 25, 30, 900, 900]       # 2...Qh4 drops the queen
    white, black = op.record(g, "white", evals), op.record(g, "black", evals)
    assert black["own_op"] > 40 > abs(white["own_op"])
    assert black["opp_op"] == pytest.approx(white["own_op"])   # one game, two views
    for rec, start in ((white, win_prob(20)), (black, win_prob(-20))):
        # what the opening handed you = their errors minus yours, exactly
        assert rec["opp_op"] - rec["own_op"] == pytest.approx(rec["wp24"] - start)
    assert black["left"] and white["opp_left"] and black["cost"] == 870
    assert (white["result"], black["result"]) == (1.0, 0.0)


def test_record_without_evals_keeps_the_book_facts():
    r = op.record(game("1. e4 e5"), "black", None)
    assert r["book"] == 1 and r["own_op"] is None and r["cost"] is None


def _shuffle(plies=24, step=5):
    """Knights out and back, with a clock that loses `step` seconds a move."""
    out = []
    for i in range(plies):
        san = (("Nf3", "Ng1") if i % 2 == 0 else ("Nf6", "Ng8"))[(i // 2) % 2]
        clock = 600 - step * (i // 2 + 1)
        prefix = f"{i // 2 + 1}. " if i % 2 == 0 else ""
        out.append(f"{prefix}{san} {{[%clk 0:{clock // 60:02d}:{clock % 60:02d}]}}")
    return game(" ".join(out), result="1/2-1/2", headers='[TimeControl "600"]\n')


def test_record_reads_the_clock_and_the_moves_you_chose():
    r = op.record(_shuffle(), "white", None)
    assert r["clock12"] == 60
    assert r["first"] == "Nf3" and r["moves"] == frozenset({"Nf3", "Ng1"})
    assert r["opp_first"] == "Nf6"
    assert op.record(_shuffle(plies=20), "white", None)["clock12"] is None


@pytest.mark.parametrize("san, norm", [("Nbxd2+", "Nd2"), ("exd5", "Pd5"),
                                       ("e8=Q#", "Pe8"), ("O-O-O+", "O-O-O")])
def test_a_move_is_a_piece_and_a_square(san, norm):
    assert op._norm(san) == norm


# --- theory depth --------------------------------------------------------------------

def test_theory_depth_does_not_count_the_opponents_departure_as_yours():
    # Two games you left at your 3rd move; six where the opponent left after
    # your first. A plain average says 1.25 book moves; you were never caught
    # out before move 3 in any game where the book went on that long.
    recs = [{"left": True, "book": 2}] * 2 + [{"left": False, "book": 1}] * 6
    assert op.theory_depth(recs)["median"] == 3


def test_theory_depth_median_where_half_have_left():
    recs = [{"left": True, "book": 2}] * 4 + [{"left": False, "book": 5}] * 4
    d = op.theory_depth(recs)
    assert d["median"] == 3 and d["survival"][1] == 1.0 and d["survival"][2] == 0.5


# --- repertoire --------------------------------------------------------------------

def _rep(color="white", opp_first="c5", moves=("Nc3", "Pg3"), pawns=None, i=0):
    return {"color": color, "opp_first": opp_first, "moves": frozenset(moves),
            "pawns": pawns, "sort_key": f"{i:03d}"}


def test_similarity_compares_only_games_that_started_alike():
    recs = [_rep(), _rep(),                                  # same setup vs 1...c5
            _rep(opp_first="e5", moves=("Pd4",)),            # a different reply
            _rep(color="black", opp_first="c5")]             # the other colour
    s = op.similarity(recs)
    assert s == {"moves": 1.0, "pawns": None, "pairs": 1}
    recs.append(_rep(moves=("Nc3", "Pf4")))                  # overlaps 1 of 3 moves
    assert op.similarity(recs, "white")["moves"] == pytest.approx((1 + 1 / 3 + 1 / 3) / 3)


def test_windowed_similarity_is_on_the_corpus_players_footing():
    same = [_rep(i=i) for i in range(10)]
    assert op.windowed_similarity(same)["moves"] == 1.0
    assert op.windowed_similarity(same[:9]) is None          # fewer than ten games


# --- synthetic corpora ---------------------------------------------------------------

def _corpus(n_players, games=10, seed=0, wp24=lambda p, g, rng: 50.0, **extra):
    """Records shaped like `op.record`'s, for players p0..pN with `games` each.
    The result is the expected score at move 12 at a planted 0.8 slope."""
    rng = random.Random(seed)
    out = []
    for p in range(n_players):
        for g in range(games):
            w = wp24(p, g, rng)
            rec = {"player": f"p{p}", "sort_key": f"{g:03d}", "elo": 2000,
                   "color": "white" if g % 2 else "black", "plies": 80,
                   "wp24": w, "wp64": w, "result": 0.5 + 0.008 * (w - 50),
                   "left": False, "opp_left": False, "family": "F",
                   "own_op": 25.0, "opp_op": 25.0, "clock12": None,
                   "own_rest": 50.0, "rest_moves": 20}
            for k, f in extra.items():
                rec[k] = f(p, g, rng, rec)
            out.append(rec)
    return out


def test_calibration_recovers_the_planted_conversion():
    corpus = _corpus(60, wp24=lambda p, g, rng: rng.uniform(30, 70))
    cal = op.calibration(corpus)
    assert cal["k"][op.CHECK] == pytest.approx(0.8)
    assert cal["k_within"] == pytest.approx(0.8)


def test_theory_contrast_holds_the_player_fixed():
    # Weak players (skill -10) meet opponents who leave the book first in 8 of
    # 10 games; strong ones (+10) in 2 of 10. Inside every player's games,
    # being in book longer is worth +5 points of win chance at move 12, i.e.
    # 4 score points at the planted 0.8. Pooled, the confound swamps it.
    def skill(p):
        return -10 if p % 2 else 10

    def plus(p, g):
        return g < (8 if skill(p) < 0 else 2)

    corpus = _corpus(40, wp24=lambda p, g, rng: 50 + skill(p) + (5 if plus(p, g) else 0),
                     opp_left=lambda p, g, rng, rec: plus(p, g),
                     left=lambda p, g, rng, rec: not plus(p, g))
    c = op.theory_contrast(corpus)
    assert c["players"] == 40
    assert c["op"][0] == pytest.approx(4.0)
    assert c["result"][0] == pytest.approx(4.0)
    assert c["mg"][0] == pytest.approx(0.0, abs=1e-9)
    pooled = (sum(100 * r["result"] for r in corpus if r["opp_left"]) / 200
              - sum(100 * r["result"] for r in corpus if r["left"]) / 200)
    assert pooled < 0                           # the comparison the design avoids


def test_spreads_separate_real_differences_from_luck():
    def noisy(true_sd):
        return _corpus(200, seed=1, own_op=lambda p, g, rng, rec:
                       25 + (true_sd if p % 2 else -true_sd) + rng.gauss(0, 10),
                       opp_op=lambda p, g, rng, rec: 25 + rng.gauss(0, 10))
    real = op.spreads(noisy(4.0))["own_op"]
    luck = op.spreads(noisy(0.0))["own_op"]
    assert 2.5 < real[0] < 5.5 and real[1] < 4.0 < real[2]
    assert luck[0] < 2.0


def test_reliability_says_how_far_ten_games_pin_a_player_down():
    steady = _corpus(40, own_rest=lambda p, g, rng, rec: 20.0 + 3 * p)
    r = op.reliability(steady)
    assert r["split"] == pytest.approx(1.0) and r["games_for_06"] < 10
    noise = _corpus(40, seed=2, own_rest=lambda p, g, rng, rec: rng.uniform(0, 100))
    assert op.reliability(noise)["full"] < 0.5


def test_popularity_buckets_by_share_of_games():
    corpus = ([{"family": "Big", "color": "white"}] * 60
              + [{"family": "Mid", "color": "white"}] * 39
              + [{"family": "Rare", "color": "white"}]
              + [{"family": "Big", "color": "black"}] * 50)
    assert op.popularity(corpus) == {"Big": "Mainstream", "Mid": "Uncommon",
                                     "Rare": "Uncommon"}
    corpus += [{"family": "Mid", "color": "white"}] * 300
    assert op.popularity(corpus)["Rare"] == "Niche"
