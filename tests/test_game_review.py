"""The game-review metrics, especially the interactive board explorer."""
from __future__ import annotations

import chess

from chessanalysis.contexts import GameContext
from chessanalysis.enrich import engine as eng
from chessanalysis.metrics.game.review import (
    _quality_counts, board_explorer, eval_graph, key_moments, move_quality, summary,
)

from .conftest import FakeGame, build_raw


def _ctx(analysis, color="white"):
    return GameContext(game=FakeGame(color=color), analysis=analysis, player="Alice")


def test_board_explorer_widget_shape(sample_analysis):
    w = board_explorer(_ctx(sample_analysis))
    assert w["type"] == "review"
    assert w["orientation"] == "white"
    assert w["white"] == "Alice" and w["black"] == "Bob"
    # one position per FEN, one move per played move
    assert len(w["positions"]) == len(sample_analysis.fens)
    assert len(w["moves"]) == len(sample_analysis.moves)


def test_board_explorer_positions_have_eval_and_arrows(sample_analysis):
    w = board_explorer(_ctx(sample_analysis))
    p0 = w["positions"][0]
    assert "fen" in p0 and isinstance(p0["cp"], int)
    # top-3 engine moves resolved to SAN for the arrows
    assert 1 <= len(p0["best"]) <= 3
    for b in p0["best"]:
        assert set(b) == {"uci", "san", "cp"}
        assert b["san"]                      # UCI was converted to SAN
    # arrows must reference legal moves for that position
    board = chess.Board(p0["fen"])
    assert chess.Move.from_uci(p0["best"][0]["uci"]) in board.legal_moves


def test_board_explorer_move_fields(sample_analysis):
    w = board_explorer(_ctx(sample_analysis))
    m = w["moves"][0]
    assert set(m) == {"san", "uci", "label", "cp_loss", "wp_loss", "best_san"}
    assert m["san"] == "e4"


def test_board_explorer_orientation_follows_player_color(sample_analysis):
    assert board_explorer(_ctx(sample_analysis, color="black"))["orientation"] == "black"


def test_board_explorer_none_when_no_positions():
    empty = eng.GameAnalysis(depth=12, engine_name="x", evals=[], fens=[])
    assert board_explorer(_ctx(empty)) is None


def test_board_explorer_carries_the_phases(sample_analysis):
    w = board_explorer(_ctx(sample_analysis))
    assert set(w["division"]) == {"mid", "end", "plies"}
    assert w["division"]["plies"] == len(sample_analysis.moves)


def test_summary_cards_table_and_note(sample_analysis):
    cards, table, note = summary(_ctx(sample_analysis))
    assert cards["type"] == "cards"
    labels = [c["label"] for c in cards["items"]]
    assert "White accuracy" in labels and "Black accuracy" in labels
    assert any(lbl.startswith("Decisive") for lbl in labels)
    assert [r[0] for r in table["rows"]] == ["White", "Black"]
    assert table["columns"][4:7] == ["Opening", "Middlegame", "Endgame"]
    assert note["type"] == "text"


def test_move_quality_chart(sample_analysis):
    chart = move_quality(_ctx(sample_analysis))
    assert chart["type"] == "barstack"
    # the chart's white bar must sum to white's move count
    rows = {r["label"]: r for r in chart["rows"]}
    wsum = sum(s["value"] for s in rows["White"]["segments"])
    assert wsum == len([m for m in sample_analysis.moves if m.color == "white"])


def test_quality_counts(sample_analysis):
    c = _quality_counts(sample_analysis, "black")
    assert c["blunder"] == 1                       # black's 570cp move
    assert sum(c.values()) == 2                    # black made two moves


def test_key_moments_jump_to_their_ply(sample_analysis):
    out = key_moments(_ctx(sample_analysis))
    moments = out[0]
    assert moments["type"] == "moments"
    item = moments["items"][0]
    assert item["kind"] == "blunder" and item["ply"] == 4 and not item["mine"]


def test_eval_graph_plies_align(sample_analysis):
    w = eval_graph(_ctx(sample_analysis))
    assert w["type"] == "eval"
    # one ply entry per position; SAN list aligned to the moves
    assert len(w["plies"]) == len(sample_analysis.evals)
    assert len(w["moves"]) == len(sample_analysis.moves)
    assert "division" in w
