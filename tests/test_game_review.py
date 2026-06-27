"""The game-review metrics, especially the interactive board explorer."""
from __future__ import annotations

import types

import chess

from chessanalysis.contexts import GameContext
from chessanalysis.enrich import engine as eng
from chessanalysis.enrich.engine import GameAnalysis, MoveEval
from chessanalysis.metrics.game.review import (
    _drift_runs, _quality_counts, board_explorer, conversion, depth_delta,
    error_profile, eval_graph, move_quality, summary,
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


def test_summary(sample_analysis):
    cards = summary(_ctx(sample_analysis))
    assert cards["type"] == "cards" and len(cards["items"]) == 7
    labels = [c["label"] for c in cards["items"]]
    assert "White top-3 match" in labels and "Black top-3 match" in labels


def test_move_quality_chart_then_table(sample_analysis):
    chart, table = move_quality(_ctx(sample_analysis))
    assert chart["type"] == "barstack"
    assert table["type"] == "table" and [r[0] for r in table["rows"]] == ["White", "Black"]
    # the chart's white bar must sum to white's move count
    rows = {r["label"]: r for r in chart["rows"]}
    wsum = sum(s["value"] for s in rows["White"]["segments"])
    assert wsum == len([m for m in sample_analysis.moves if m.color == "white"])


def test_quality_counts(sample_analysis):
    c = _quality_counts(sample_analysis, "black")
    assert c["blunder"] == 1                       # black's 570cp move
    assert sum(c.values()) == 2                    # black made two moves


def test_drift_runs():
    mk = lambda cp: types.SimpleNamespace(cp_loss=cp, ply=1, color="white")
    assert len(_drift_runs([mk(20), mk(30), mk(40), mk(50)])) == 1
    # a big swing breaks the run; only the trailing 4-long run survives
    runs = _drift_runs([mk(20), mk(30), mk(200), mk(40), mk(50), mk(60), mk(70)])
    assert len(runs) == 1 and len(runs[0]) == 4
    assert _drift_runs([mk(20), mk(30), mk(40)]) == []        # below DRIFT_MIN


def test_error_profile_flags_tactical_miss(sample_analysis):
    explain, table, note = error_profile(_ctx(sample_analysis))
    assert explain["type"] == "text" and note["type"] == "text"
    by_side = {r[0]: r for r in table["rows"]}
    assert by_side["Black"][1] >= 1               # the 570cp drop is a tactical miss


def test_depth_delta_flags_shallow_only_moves(monkeypatch):
    def m(ply, color, label, san="x"):
        return MoveEval(ply=ply, color=color, san=san, best_san="", cp_loss=0,
                        wp_loss=0.0, accuracy=100.0, label=label, fen_before="", move_uci="")
    # high (review) depth flags white's Qh5 as a blunder; the shallow pass calls it ok
    hi = GameAnalysis(depth=18, engine_name="x", evals=[0] * 4,
                      moves=[m(1, "white", "blunder", "Qh5"), m(2, "black", "ok"),
                             m(3, "white", "ok")])
    lo = GameAnalysis(depth=12, engine_name="x", evals=[0] * 4,
                      moves=[m(1, "white", "ok", "Qh5"), m(2, "black", "ok"),
                             m(3, "white", "ok")])
    monkeypatch.setattr(eng, "analyse_game", lambda game, depth: lo)
    explain, table, note = depth_delta(
        GameContext(game=FakeGame(color="white"), analysis=hi, player="me"))
    assert table["rows"][0] == ["White", 1]       # one shallow-only error for white
    assert "Qh5" in note["body"]


def test_eval_graph_plies_align(sample_analysis):
    w = eval_graph(_ctx(sample_analysis))
    assert w["type"] == "eval"
    # one ply entry per position; SAN list aligned to the moves
    assert len(w["plies"]) == len(sample_analysis.evals)
    assert len(w["moves"]) == len(sample_analysis.moves)


def test_conversion_metric_returns_cards(sample_analysis):
    w = conversion(_ctx(sample_analysis))
    assert w["type"] == "cards"
