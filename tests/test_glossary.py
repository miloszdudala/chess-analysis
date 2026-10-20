"""The units every page uses (glossary) and the Guide built from them."""
import pytest

from chessanalysis import glossary as G
from chessanalysis.enrich.engine import win_prob


@pytest.mark.parametrize("cp", [-500, -100, 0, 37, 200, 900])
def test_pawns_for_inverts_win_chance(cp):
    assert G.pawns_for(win_prob(cp)) == pytest.approx(cp / 100, abs=1e-6)


def test_win_chance_edge_reads_as_pawns_near_level():
    # 2% of win chance around 50% is a little over a fifth of a pawn
    assert 0.2 < G.win_chance_edge_in_pawns(2.0) < 0.25


def test_expected_score_is_the_elo_formula():
    assert G.expected_score(2000, 2000) == 0.5
    assert G.expected_score(2100, 2000) == pytest.approx(0.640, abs=1e-3)


@pytest.mark.parametrize("tc,label", [("600", "10-minute"), ("600+5", "10+5"),
                                       ("180+2", "3+2"), ("1/86400", "daily"), (None, "daily")])
def test_time_control_label(tc, label):
    assert G.time_control_label(tc) == label


def test_more_or_less_says_which_way_and_when_it_is_nothing():
    assert G.more_or_less(0.37) == "37% more"
    assert G.more_or_less(-0.14) == "14% less"
    assert G.more_or_less(0.002) == "about the same"


def test_guide_examples_come_from_the_formulas():
    sections = {sid: widgets for sid, _, widgets in G.guide_sections({"depth": 10})}
    assert {"win-chance", "win-chance-lost", "score", "range", "control"} <= set(sections)
    table = next(w for w in sections["win-chance"] if w["type"] == "table")
    assert ["+1.00", f"{win_prob(100):.0f}%"] in table["rows"]
