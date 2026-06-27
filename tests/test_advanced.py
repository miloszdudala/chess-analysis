"""Advanced engine-derived diagnostics (insights.advanced_report)."""
from __future__ import annotations

from chessanalysis import insights
from chessanalysis.enrich.engine import GameAnalysis, MoveEval

from .conftest import FakeGame


def mev(ply, color, label="ok", cp_loss=0, fen="", uci="", best_san="", san="x"):
    return MoveEval(ply=ply, color=color, san=san, best_san=best_san, cp_loss=cp_loss,
                    wp_loss=0.0, accuracy=100.0, label=label, fen_before=fen, move_uci=uci)


def _analysis(moves, evals, fens=None, top_moves=None):
    return GameAnalysis(depth=12, engine_name="x", evals=evals, moves=moves,
                        fens=fens or [], top_moves=top_moves or [])


def _cards(sections):
    return {c["label"]: c["value"]
            for s in sections for w in s["widgets"] if w["type"] == "cards"
            for c in w["items"]}


def test_empty_report():
    assert insights.advanced_report([]) == []


class _G:
    def __init__(self, date, color):
        self.date, self.color = date, color


def test_accuracy_trend():
    a1 = _analysis([], [0], )
    a1.accuracy = {"white": 90.0}
    a2 = _analysis([], [0])
    a2.accuracy = {"white": 80.0}
    out = insights.accuracy_trend([(_G("2026.01.01", "white"), a1),
                                   (_G("2026.01.02", "white"), a2)])
    line = out[0]["widgets"][0]
    assert out[0]["title"] == "Accuracy over time"
    assert line["type"] == "line" and line["toolbar"] is True and line["agg"] == "mean"
    assert line["series"][0]["points"] == [{"x": "2026.01.01", "y": 90.0},
                                           {"x": "2026.01.02", "y": 80.0}]


def test_accuracy_trend_needs_two_points():
    a = _analysis([], [0])
    a.accuracy = {"white": 90.0}
    assert insights.accuracy_trend([(_G("2026.01.01", "white"), a)]) == []


def test_cascading_error_probability():
    # white errors on plies 1 and 3 (consecutive own moves), ok on 5
    moves = [mev(1, "white", "blunder"), mev(2, "black"),
             mev(3, "white", "blunder"), mev(4, "black"), mev(5, "white", "ok")]
    a = _analysis(moves, evals=[0] * 6)
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    # P(error | prior error): of 2 errors with a following move, 1 was followed by an error
    assert cards["Cascading-error probability"] == "50%"


def test_sharpness_acpl_splits_sharp_vs_calm():
    # ply1 in a sharp position (top1-top2 gap 200) losing 80cp; ply3 calm (gap 10) losing 10cp
    moves = [mev(1, "white", cp_loss=80), mev(2, "black"), mev(3, "white", cp_loss=10)]
    top = [[{"uci": "a2a3", "cp": 300}, {"uci": "b2b3", "cp": 100}],   # idx0: sharp
           [],
           [{"uci": "c2c3", "cp": 50}, {"uci": "d2d3", "cp": 40}]]      # idx2: calm
    a = _analysis(moves, evals=[0] * 4, top_moves=top)
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    assert cards["Sharpness ACPL"] == 80          # only the sharp-position loss


def test_opponent_error_capitalization():
    # black (opponent) hands white +2.0 on ply2; white refutes with the best move on ply3
    moves = [mev(1, "white"),
             mev(2, "black"),                                  # eval jumps for white here
             mev(3, "white", san="Nf3", best_san="Nf3"),       # played the engine's #1
             mev(4, "black")]
    a = _analysis(moves, evals=[0, 0, 200, 200, 200])
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    assert cards["Opponent-error capitalization"] == "100%"


def test_premature_simplification():
    # a position with two pawn captures (exd5 / dxe5); white grabs one but the
    # engine's best is a non-capture (Nf3) — releasing the tension early.
    import chess
    pos = chess.Board("rnbqkbnr/ppp2ppp/8/3pp3/3PP3/8/PPP2PPP/RNBQKBNR w KQkq - 0 1")
    caps = [m for m in pos.legal_moves if pos.is_capture(m)]
    assert len(caps) >= 2
    cap = caps[0]
    moves = [mev(1, "white", fen=pos.fen(), uci=cap.uci())]
    top = [[{"uci": "g1f3", "cp": 30}, {"uci": cap.uci(), "cp": 20}]]   # best is non-capture
    a = _analysis(moves, evals=[0, 0], top_moves=top)
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    assert cards["Premature simplification"] == "100%"
