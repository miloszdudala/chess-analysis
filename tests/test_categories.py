"""Section categorisation plumbing + the new actionable player metrics."""
from __future__ import annotations

from chessanalysis.contexts import PlayerContext
from chessanalysis.document import Document
from chessanalysis.metrics.player.breakdowns import by_game_length
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


def _wdl_by_label(barstack):
    """{label: {win/draw/loss: n}} from a W/D/L barstack widget."""
    return {r["label"]: {s["name"]: s["value"] for s in r["segments"]}
            for r in barstack["rows"]}


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
