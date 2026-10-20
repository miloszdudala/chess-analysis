"""Advanced engine-derived diagnostics (insights.advanced_report)."""
from __future__ import annotations

from chessanalysis import insights
from chessanalysis.enrich.engine import GameAnalysis, MoveEval

from .conftest import FakeGame


def mev(ply, color, label="ok", cp_loss=0, fen="", uci="", best_san="", san="x", wp_loss=0.0):
    return MoveEval(ply=ply, color=color, san=san, best_san=best_san, cp_loss=cp_loss,
                    wp_loss=wp_loss, accuracy=100.0, label=label, fen_before=fen, move_uci=uci)


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


def _ec_pair(color, outcome, evals):
    g = FakeGame(color=color)
    g.outcome = outcome
    return (g, _analysis([], evals))


def _eval_curve_widget(pairs):
    out = insights.eval_curve(pairs)
    assert out and out[0]["title"] == "Average evaluation by move"
    return [w for w in out[0]["widgets"] if w["type"] == "evalcurve"][0]


def _grouping(curve, key):
    return next(g for g in curve["groupings"] if g["key"] == key)


def test_eval_curve_splits_by_color_and_clamps_mate_scores():
    # 5 games each colour so the per-move coverage floor is cleared
    wpairs = [_ec_pair("white", "win", [0, 100, 200, 9000, 9000]) for _ in range(5)]
    # white-POV evals positive -> Black (the user here) is worse -> negative POV
    bpairs = [_ec_pair("black", "loss", [0, 100, 200, 300, 300]) for _ in range(5)]
    curve = _eval_curve_widget(wpairs + bpairs)
    series = {s["name"]: s["points"] for s in _grouping(curve, "color")["series"]}
    assert set(series) == {"As White", "As Black"}
    assert series["As White"][0]["y"] > 0 and series["As Black"][0]["y"] < 0
    # the 9000cp (≈mate) eval must be clamped, never reaching ±90 pawns
    assert all(abs(p["y"]) <= 10 for pts in series.values() for p in pts)


def test_eval_curve_splits_by_result():
    # enough games per result bucket to clear the coverage floor
    won = [_ec_pair("white", "win", [0, 100, 250, 400, 600]) for _ in range(5)]
    lost = [_ec_pair("white", "loss", [0, -50, -200, -400, -600]) for _ in range(5)]
    curve = _eval_curve_widget(won + lost)
    by_result = {s["name"]: s["points"] for s in _grouping(curve, "result")["series"]}
    assert {"Won", "Lost"} <= set(by_result)
    assert by_result["Won"][-1]["y"] > by_result["Lost"][-1]["y"]
    # also exposes an overall-average grouping; default is the colour split
    assert {g["key"] for g in curve["groupings"]} >= {"all", "color", "result"}


def test_eval_curve_colour_times_result():
    pairs = []
    for color in ("white", "black"):
        for outcome, ev in (("win", [0, 100, 250, 400, 600]),
                            ("loss", [0, -50, -200, -400, -600])):
            pairs += [_ec_pair(color, outcome, ev) for _ in range(5)]
    curve = _eval_curve_widget(pairs)
    colres = _grouping(curve, "colres")
    by_name = {s["name"]: s for s in colres["series"]}
    assert {"White · Won", "White · Lost", "Black · Won", "Black · Lost"} <= set(by_name)
    # Black series are dashed, White solid
    assert by_name["Black · Won"]["dash"] is True
    assert by_name["White · Won"]["dash"] is False


def test_eval_curve_empty():
    assert insights.eval_curve([]) == []


def test_cascading_error_probability():
    # white errors on plies 1 and 3 (consecutive own moves), ok on 5
    moves = [mev(1, "white", "blunder"), mev(2, "black"),
             mev(3, "white", "blunder"), mev(4, "black"), mev(5, "white", "ok")]
    a = _analysis(moves, evals=[0] * 6)
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    # of 2 errors with a following move, 1 was followed by an error
    assert cards["A mistake straight after a mistake"] == "50%"


def test_opponent_mistakes_punished():
    # black (opponent) gives away 17% on ply 2; white answers with the best move,
    # and a 4% inaccuracy on ply 4 is not a mistake, so it is no chance at all
    moves = [mev(1, "white"),
             mev(2, "black", label="mistake", wp_loss=17.0),
             mev(3, "white", san="Nf3", best_san="Nf3"),       # played the engine's #1
             mev(4, "black", wp_loss=4.0),
             mev(5, "white", san="a3", best_san="Nc3")]
    a = _analysis(moves, evals=[0, 0, 200, 200, 230, 230])
    cards = _cards(insights.advanced_report([(FakeGame(color="white"), a)]))
    assert cards["Their mistakes you punished"] == "100%"
    chances = insights.punish_chances(FakeGame(color="white"), a)
    assert [(m.ply, r.ply) for m, r in chances] == [(2, 3)]


def test_advanced_report_trimmed_to_two_cards():
    moves = [mev(1, "white"), mev(2, "black")]
    a = _analysis(moves, evals=[0] * 3)
    out = insights.advanced_report([(FakeGame(color="white"), a)])
    assert out[0]["title"] == "Punishing mistakes, and mistakes in a row"
    labels = list(_cards(out))
    assert labels == ["Their mistakes you punished", "A mistake straight after a mistake"]


# --- progress check (recent vs baseline) ------------------------------------

def _prog_pair(outcome, acc, blunder=False):
    g = FakeGame(color="white")
    g.outcome = outcome
    moves = [mev(p, "white", label="blunder" if (blunder and p == 1) else "ok")
             for p in range(1, 40, 2)] + [mev(p, "black") for p in range(2, 41, 2)]
    a = _analysis(moves, evals=[0] * 41)
    a.accuracy = {"white": acc}
    return (g, a)


def test_progress_report_flags_improvement():
    # 30 sloppy baseline games (acc 75, a blunder each), then 10 clean ones
    pairs = ([_prog_pair("loss", 75.0, blunder=True) for _ in range(30)]
             + [_prog_pair("win", 90.0) for _ in range(10)])
    out = insights.progress_report(pairs)
    assert out and out[0]["title"].startswith("Progress check")
    tbl = [w for w in out[0]["widgets"] if w["type"] == "table"][0]
    rows = {r[0]: r for r in tbl["rows"]}
    assert "better" in rows["Accuracy"][3]
    assert "better" in rows["Blunders per 100 moves"][3]


def test_progress_report_gates_small_samples():
    assert insights.progress_report([_prog_pair("win", 90.0)] * 10) == []
