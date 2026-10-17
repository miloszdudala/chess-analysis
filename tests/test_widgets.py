"""Widget builders — the backend↔frontend JSON contract."""
from __future__ import annotations

from chessanalysis import widgets as W


def test_review_widget_shape():
    positions = [{"fen": "x", "cp": 12, "best": [{"uci": "e2e4", "san": "e4", "cp": 12}]}]
    moves = [{"san": "e4", "uci": "e2e4", "label": "ok",
              "cp_loss": 0, "wp_loss": 0.0, "best_san": "e4"}]
    w = W.review(positions, moves, orientation="white", white="A", black="B")
    assert w["type"] == "review"
    assert w["positions"] is positions and w["moves"] is moves
    assert w["orientation"] == "white"
    assert w["white"] == "A" and w["black"] == "B"


def test_evalbar_widget():
    w = W.evalbar([{"ply": 0, "cp": 0, "label": "ok"}], ["e4"])
    assert w["type"] == "eval"
    assert w["plies"] and w["moves"] == ["e4"]


def test_actions_and_focus_widgets():
    a = W.actions([{"label": "Train", "route": "#/train"}])
    assert a["type"] == "actions" and a["items"][0]["route"] == "#/train"
    f = W.focus([{"tone": "leak", "title": "t", "body": "b", "action": None}])
    assert f["type"] == "focus" and f["items"][0]["tone"] == "leak"


def test_wdl_barstack_shape_and_note():
    w = W.wdl_barstack([{"label": "White", "win": 6, "draw": 2, "loss": 2}])
    assert w["type"] == "barstack" and w["palette"] == W.WDL_PALETTE
    row = w["rows"][0]
    assert {s["name"]: s["value"] for s in row["segments"]} == {"win": 6, "draw": 2, "loss": 2}
    assert row["note"] == "60% · 10g"            # 6/10 wins over 10 games


def test_gapchart_widget():
    w = W.gapchart([{"label": "Opening", "gap": 0.1, "lo": 0.02, "hi": 0.2,
                     "verdict": "leak"}])
    assert w["type"] == "gapchart" and w["unit"] == "%"


def test_timeline_widget():
    w = W.timeline([{"outcome": "win", "label": "x"}, {"outcome": "loss"}], title="Form")
    assert w["type"] == "timeline" and len(w["items"]) == 2


def test_cards_and_table():
    cards = W.cards([W.card("99%", "Accuracy", sub="white")])
    assert cards["type"] == "cards"
    assert cards["items"][0] == {"value": "99%", "label": "Accuracy", "sub": "white"}
    tbl = W.table(["A", "B"], [[1, 2]])
    assert tbl["type"] == "table" and tbl["columns"] == ["A", "B"]
