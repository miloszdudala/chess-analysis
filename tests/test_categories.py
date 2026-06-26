"""Section categorisation plumbing + the new actionable player metrics."""
from __future__ import annotations

from chessanalysis.contexts import PlayerContext
from chessanalysis.document import Document
from chessanalysis.metrics.player.breakdowns import by_game_length, momentum
from chessanalysis.metrics.player.openings import _opening_family, opening_repertoire
from chessanalysis.model import Game, Move
from chessanalysis.registry import metrics_for


def make_game(outcome, color="white", plies=10, eco="C50", ecourl=""):
    headers = {"ECO": eco, "TimeControl": "600"}
    if ecourl:
        headers["ECOUrl"] = ecourl
    moves = [Move(ply=i + 1, color="white" if i % 2 == 0 else "black", san="x")
             for i in range(plies)]
    g = Game(headers=headers, moves=moves)
    g.color, g.outcome = color, outcome
    return g


def _ctx(games):
    return PlayerContext(player="me", games=games)


# --- category plumbing ------------------------------------------------------

def test_document_add_stores_and_serialises_category():
    d = Document(mode="player", title="t")
    d.add("Sec", {"type": "text", "body": "x"}, category="Cat")
    assert d.sections[0].category == "Cat"
    assert d.to_dict()["sections"][0]["category"] == "Cat"


def test_every_player_metric_is_categorised():
    for m in metrics_for("player"):
        assert m.category, f"player metric {m.id!r} has no category"


# --- momentum / tilt --------------------------------------------------------

def _wdl_by_label(barstack):
    """{label: {win/draw/loss: n}} from a W/D/L barstack widget."""
    return {r["label"]: {s["name"]: s["value"] for s in r["segments"]}
            for r in barstack["rows"]}


def test_momentum_same_day_buckets():
    # all same (empty) date: g1 is first-of-day, then same-day transitions
    # W, L, L, W : after-win->loss; after-loss->{loss,win}; streak(2+)->final win
    games = [make_game(o) for o in ("win", "loss", "loss", "win")]
    strip, chart = momentum(_ctx(games))
    assert strip["type"] == "timeline" and len(strip["items"]) == 4
    rows = _wdl_by_label(chart)
    assert rows["First game of the day"]["win"] == 1
    assert rows["After a win (same day)"]["loss"] == 1
    assert rows["After a loss (same day)"]["loss"] == 1
    assert rows["After a loss (same day)"]["win"] == 1
    assert rows["On a 2+ loss streak (same day)"]["win"] == 1


def test_momentum_resets_across_days():
    # day 1: win ; day 2: loss then win. The day1->day2 pair must NOT count as
    # 'after a win'; only the same-day day2 loss->win transition does.
    g1 = make_game("win"); g1.headers["Date"] = "2026.01.01"
    g2 = make_game("loss"); g2.headers["Date"] = "2026.01.02"
    g3 = make_game("win"); g3.headers["Date"] = "2026.01.02"
    rows = _wdl_by_label(momentum(_ctx([g1, g2, g3]))[1])
    assert rows["First game of the day"]["win"] == 1 and rows["First game of the day"]["loss"] == 1
    assert "After a win (same day)" not in rows          # cross-day pair excluded
    assert rows["After a loss (same day)"]["win"] == 1   # the same-day pair counts


# --- game length ------------------------------------------------------------

def test_game_length_buckets():
    games = [make_game("win", plies=10), make_game("loss", plies=90)]
    rows = _wdl_by_label(by_game_length(_ctx(games)))
    assert rows["Short (< 20 moves)"]["win"] == 1
    assert rows["Long (> 40 moves)"]["loss"] == 1


# --- opening repertoire -----------------------------------------------------

def test_opening_family_keeps_two_word_root():
    assert _opening_family("Giuoco Piano Game Main Line 4...d6") == "Giuoco Piano"
    assert _opening_family("Ruy Lopez Opening Morphy Defense") == "Ruy Lopez"
    assert _opening_family("Slav Defense") == "Slav Defense"


def test_opening_repertoire_groups_scores_and_compares_to_baseline():
    games = [make_game("loss", color="black", ecourl="https://x/Giuoco-Piano-Game-Main")
             for _ in range(6)]
    games += [make_game("win", color="white", ecourl="https://x/Ruy-Lopez-Opening-Morphy")
              for _ in range(6)]
    text, table = opening_repertoire(_ctx(games))
    assert text["type"] == "text"
    by_name = {r[0]: r for r in table["rows"]}
    gp = by_name["Giuoco Piano"]
    assert gp[1] == "Black" and gp[2] == 6
    assert gp[4] == "0%"            # all losses -> 0 score
    assert gp[5] == "-50%"          # overall baseline is 50% (6W/6L)
    assert "Ruy Lopez" in by_name


def test_opening_repertoire_gates_small_samples():
    games = [make_game("win", ecourl="https://x/Sicilian-Defense") for _ in range(3)]
    assert opening_repertoire(_ctx(games)) is None
