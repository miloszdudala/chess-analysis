"""Static renderer: widget dispatch, the review placeholder, and CSS."""
from __future__ import annotations

from chessanalysis import render_html as R


def test_review_handler_registered_and_placeholder():
    assert "review" in R._HANDLERS
    html = R.render_widget({"type": "review", "positions": [], "moves": [],
                            "orientation": "white", "white": "A", "black": "B"})
    assert "unknown widget" not in html
    assert "web app" in html.lower()       # static page points to the interactive view


def test_unknown_widget_is_commented():
    assert "unknown widget" in R.render_widget({"type": "nope"})


def test_barstack_handler():
    assert "barstack" in R._HANDLERS
    html = R.render_widget({
        "type": "barstack", "title": "T",
        "rows": [{"label": "White", "segments": [{"name": "best", "value": 3},
                                                  {"name": "blunder", "value": 1}]}],
        "palette": {"best": "#0a0", "blunder": "#a00"},
    })
    assert "barstack" in html and "bs-seg" in html and "bs-leg" in html


def test_eval_and_board_handlers():
    ev = R.render_widget({"type": "eval",
                          "plies": [{"ply": 0, "cp": 0}, {"ply": 1, "cp": 50}],
                          "moves": ["e4"]})
    assert "<svg" in ev and "polyline" in ev
    bd = R.render_widget({"type": "board", "svg": "<svg id='x'/>", "caption": "hi"})
    assert "figure" in bd and "hi" in bd


def test_css_includes_review_styles():
    css = R.css()
    for token in (".rv-svg", ".rv-evalbar", ".rv-hl-blunder", ".rv-board"):
        assert token in css, f"missing {token} in stylesheet"


def test_css_has_no_chesscom_badge_artifacts():
    """Guard the design decision: no Chess.com-style move-badge classes."""
    css = R.css()
    # the old badge approach left no on-board medallion styling
    assert ".rv-badge" not in css
