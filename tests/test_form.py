"""FIDE performance / form tracking (form.py + the Form player section)."""
from __future__ import annotations

from chessanalysis import form as F
from chessanalysis.contexts import PlayerContext
from chessanalysis.metrics.player.form import form as form_metric


class FGame:
    def __init__(self, outcome, opp_elo=1500, date="2026.01.01", opponent="opp"):
        self.outcome, self.opp_elo, self.date = outcome, opp_elo, date
        self.opponent = opponent


# --- the FIDE dp table & performance -----------------------------------------

def test_dp_table_endpoints():
    assert F.dp(0.5) == 0
    assert F.dp(1.0) == 800
    assert F.dp(0.0) == -800
    assert F.dp(0.75) == 193          # straight from the FIDE table
    assert F.dp(0.25) == -193         # mirrored below 50%


def test_performance_fifty_percent_equals_avg_opposition():
    games = [FGame("win"), FGame("loss")] * 3          # 50% vs 1500 average
    p = F.performance(games)
    assert p["perf"] == 1500 and p["score"] == 0.5 and p["n"] == 6


def test_performance_perfect_score_is_plus_800():
    p = F.performance([FGame("win", opp_elo=1400)] * 5)
    assert p["perf"] == 2200


def test_performance_skips_unrated_and_gates_sample():
    rated = [FGame("win"), FGame("loss")] * 3
    unrated = [FGame("win", opp_elo=None)] * 4
    p = F.performance(rated + unrated)
    assert p["n"] == 6                                  # unrated games ignored
    assert F.performance(rated[:4]) is None             # below MIN_RATED


# --- rolling windows, peaks, streaks -----------------------------------------

def _era(outcome, n, date, elo=1500):
    return [FGame(outcome, opp_elo=elo, date=date) for _ in range(n)]


def test_rolling_series_tracks_form_change():
    games = _era("loss", 10, "2026.01.01") + _era("win", 10, "2026.02.01")
    pts = F.rolling(games, window=10)
    assert len(pts) == 11                     # one point per game after fill
    assert pts[0]["y"] == 700                 # all losses: 1500 - 800
    assert pts[-1]["y"] == 2300               # all wins: 1500 + 800
    assert pts[-1]["x"] == "2026.02.01"
    # each point maps back to its window's games in rated(games)
    assert (pts[0]["i0"], pts[0]["i1"]) == (0, 10)
    assert (pts[-1]["i0"], pts[-1]["i1"]) == (10, 20)
    window = F.rated(games)[pts[-1]["i0"]:pts[-1]["i1"]]
    assert all(g.outcome == "win" for g in window)


def test_peaks_are_non_overlapping_and_best_first():
    games = (_era("win", 10, "2026.01.01") + _era("loss", 10, "2026.02.01")
             + _era("win", 5, "2026.03.01") + _era("loss", 5, "2026.03.15"))
    best = F.peaks(games, window=10, k=3)
    assert best[0]["perf"] == 2300            # the pure-win decade
    assert best[0]["start"] == "2026.01.01" and best[0]["end"] == "2026.01.01"
    # subsequent picks may not overlap the first window
    assert all(p["start"] >= "2026.02.01" for p in best[1:])
    assert F.slump(games, window=10)["perf"] < best[0]["perf"]


def test_streak():
    games = _era("win", 3, "2026.01.01") + _era("loss", 2, "2026.01.02")
    assert F.streak(games) == {"outcome": "loss", "n": 2}
    assert F.streak([]) is None


# --- the Form section ---------------------------------------------------------

def test_form_metric_builds_cards_chart_and_timeline():
    games = (_era("loss", 15, "2026.01.01", elo=1400)
             + _era("win", 25, "2026.02.01", elo=1500))
    out = form_metric(PlayerContext(player="me", games=games))
    types = [w["type"] for w in out]
    assert "cards" in types and "line" in types and "timeline" in types
    line = next(w for w in out if w["type"] == "line")
    labels = [v["label"] for v in line["variants"]]
    assert labels == ["10 games", "20 games", "30 games"]
    assert any(v.get("default") for v in line["variants"])
    # the roster behind the click-through: one entry per rated game, aligned
    # with each point's i0/i1 window indices
    assert len(line["games"]) == 40
    pt = line["variants"][0]["points"][-1]
    assert line["games"][pt["i1"] - 1]["outcome"] == "win"
    cards = {c["label"]: c["value"]
             for w in out if w["type"] == "cards" for c in w["items"]}
    assert cards["Current form (last 20)"] == 2300      # 20 straight wins vs 1500
    assert cards["Current streak"] == "W25"


def test_form_metric_needs_rated_games():
    games = [FGame("win", opp_elo=None)] * 10
    assert form_metric(PlayerContext(player="me", games=games)) is None
