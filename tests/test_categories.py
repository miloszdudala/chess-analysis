"""Section categorisation plumbing + the player metrics."""
from __future__ import annotations

from chessanalysis.contexts import PlayerContext
from chessanalysis.document import Document
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


# --- opponent strength ------------------------------------------------------

def test_opponent_strength_uses_pre_game_ratings():
    """Chess.com Elo headers are post-game; the gap must be reconstructed.

    Game 2: you (2000 pre) beat a 2050-pre opponent. Post-game the headers say
    you 2008 vs them 2042 — a +34 gap — but the real pre-game gap was +50.
    Game 3: you (2008 pre) lose to a 2030-pre opponent; post-game they read
    2038, which would put a level game (+22) among the stronger ones (+38).
    """
    from chessanalysis.metrics.player.opponents import by_opponent_strength

    class G:
        def __init__(self, outcome, user_elo, opp_elo):
            self.outcome, self.user_elo, self.opp_elo = outcome, user_elo, opp_elo

    games = [G("win", 2000, 1900),          # baseline: sets your pre for game 2
             G("win", 2008, 2042),          # post ratings after a win (Δ = +8)
             G("loss", 2000, 2038)]         # post ratings after a loss (Δ = −8)
    table = [w for w in by_opponent_strength(_ctx(games)) if w["type"] == "table"][0]
    rows = {r[0]: r for r in table["rows"]}
    stronger, level = rows["Stronger (25–100 above)"], rows["Level (within ±25)"]
    assert stronger[1] == 1 and stronger[3] == 1     # the win, at its pre-game +50
    assert level[1] == 1 and level[5] == 1           # the loss, at its pre-game +22
    assert stronger[8] == "+8.0" and level[8] == "−8.0"
    assert stronger[7] == "43%"                      # Elo expectation at +50
