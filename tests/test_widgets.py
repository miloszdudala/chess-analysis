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


def test_board_widget_optional_svg():
    w = W.board("fen-string", caption="cap", lastmove="e2e4", svg="<svg/>")
    assert w["type"] == "board"
    assert w["fen"] == "fen-string" and w["svg"] == "<svg/>"
    assert w["caption"] == "cap" and w["lastmove"] == "e2e4"


def test_cards_and_table():
    cards = W.cards([W.card("99%", "Accuracy", sub="white")])
    assert cards["type"] == "cards"
    assert cards["items"][0] == {"value": "99%", "label": "Accuracy", "sub": "white"}
    tbl = W.table(["A", "B"], [[1, 2]])
    assert tbl["type"] == "table" and tbl["columns"] == ["A", "B"]
