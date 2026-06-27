"""Heuristic win/loss diagnosis (diagnosis.diagnose + insights.outcome_reasons)."""
from __future__ import annotations

from chessanalysis import diagnosis as dx
from chessanalysis import insights
from chessanalysis.enrich.engine import GameAnalysis, MoveEval
from chessanalysis.model import Move


def mev(ply, color, label="ok", wp=0.0, cpl=0, san="x"):
    return MoveEval(ply=ply, color=color, san=san, best_san="", cp_loss=cpl,
                    wp_loss=wp, accuracy=100.0, label=label, fen_before="", move_uci="")


def analysis(moves, evals, acc=None):
    a = GameAnalysis(depth=12, engine_name="x", evals=evals, moves=moves)
    a.accuracy = acc or {"white": 85.0, "black": 85.0}
    return a


class DGame:
    """A minimal Game stand-in: just what diagnose() / clock_profile read."""
    def __init__(self, outcome, color="white", termination="Normal",
                 moves=None, tc="600"):
        self.outcome, self.color, self.termination = outcome, color, termination
        self.moves = moves or []
        self.time_control = tc


# --- losses -----------------------------------------------------------------

def test_one_blunder_loss():
    moves = [mev(1, "white"), mev(2, "black"),
             mev(3, "white", "blunder", wp=40.0, cpl=420), mev(4, "black")]
    a = analysis(moves, [20, 20, 20, -400, -400])
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "blunder"
    assert "2." in dg.detail          # ply 3 == White's move 2


def test_several_errors_loss():
    moves = [mev(1, "white", "mistake", wp=12.0, cpl=120),
             mev(2, "black"),
             mev(3, "white", "mistake", wp=11.0, cpl=110)]
    a = analysis(moves, [20, -100, -100, -260])
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "errors"


def test_drift_loss():
    # four small consecutive bleeds, no mistake-level move
    moves = [mev(p, "white", wp=2.0, cpl=40) for p in (1, 3, 5, 7)]
    a = analysis(moves, [20, 0, -20, -60, -100, -140, -180, -240])
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "drift"


def test_threw_away_loss():
    # white climbs to +3 then loses
    moves = [mev(1, "white"), mev(2, "black"),
             mev(3, "white", "blunder", wp=50.0, cpl=600), mev(4, "black")]
    a = analysis(moves, [50, 300, 300, -300, -300])
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "threw_away"
    assert "couldn't bring it home" in dg.detail


def test_flagged_loss():
    moves = [mev(1, "white"), mev(2, "black")]
    a = analysis(moves, [20, 10, -40])
    dg = dx.diagnose(DGame("loss", termination="Bob won on time"), a)
    assert dg.primary == "flagged"


def test_outplayed_loss():
    moves = [mev(1, "white", wp=4.0, cpl=40), mev(2, "black")]
    a = analysis(moves, [10, -60, -260], acc={"white": 88.0, "black": 96.0})
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "outplayed"
    assert "96%" in dg.detail and "88%" in dg.detail


def test_time_pressure_loss_and_factor():
    # decisive blunder played with 30s of a 600s clock left -> time pressure
    gmoves = [Move(ply=1, color="white", san="a", clock=500.0),
              Move(ply=3, color="white", san="b", clock=30.0)]
    moves = [mev(1, "white"), mev(2, "black"),
             mev(3, "white", "blunder", wp=40.0, cpl=420), mev(4, "black")]
    a = analysis(moves, [20, 20, 20, -400, -400])
    dg = dx.diagnose(DGame("loss", moves=gmoves), a)
    assert dg.primary == "time"
    assert "clock" in dg.detail.lower()


def test_drift_is_a_secondary_factor_of_a_blunder_loss():
    # one decisive blunder, but also a 4-move drift earlier -> drift as a factor
    drift = [mev(p, "white", wp=2.0, cpl=40) for p in (1, 3, 5, 7)]
    moves = drift + [mev(9, "white", "blunder", wp=45.0, cpl=500), mev(10, "black")]
    a = analysis(moves, [20, 0, -20, -60, -100, -140, -180, -200, -200, -600, -600])
    dg = dx.diagnose(DGame("loss"), a)
    assert dg.primary == "blunder" and "drift" in dg.factors


# --- wins -------------------------------------------------------------------

def test_opponent_blunder_win():
    moves = [mev(1, "white"), mev(2, "black", "blunder", wp=45.0, cpl=500),
             mev(3, "white")]
    a = analysis(moves, [20, 20, 600, 600])
    dg = dx.diagnose(DGame("win"), a)
    assert dg.primary == "opp_blunder"


def test_comeback_win():
    moves = [mev(1, "white", "blunder", wp=40.0, cpl=400), mev(2, "black"),
             mev(3, "white")]
    a = analysis(moves, [20, -400, -400, 600])
    dg = dx.diagnose(DGame("win"), a)
    assert dg.primary == "comeback"


def test_steady_win():
    moves = [mev(p, "white") for p in (1, 3, 5)] + [mev(p, "black") for p in (2, 4, 6)]
    a = analysis(moves, [150, 160, 170, 180, 190, 200, 210],
                 acc={"white": 92.0, "black": 70.0})
    dg = dx.diagnose(DGame("win"), a)
    assert dg.primary == "steady"


def test_flag_win():
    moves = [mev(1, "white"), mev(2, "black")]
    a = analysis(moves, [20, 10, -30])
    dg = dx.diagnose(DGame("win", termination="Alice won on time"), a)
    assert dg.primary == "flag_win"


def test_won_on_time_from_worse_position_is_not_a_comeback():
    # peaked at +3, but ended losing and flagged the opponent -> clock, not comeback
    moves = [mev(1, "white"), mev(2, "black"), mev(3, "white"), mev(4, "black")]
    a = analysis(moves, [20, 300, 300, -900, -700])
    dg = dx.diagnose(DGame("win", termination="md won on time"), a)
    assert dg.primary == "flag_win"
    assert "losing position" in dg.detail and "opp_time" not in dg.factors


def test_comeback_requires_recovering_on_the_board():
    # was lost, recovered to a winning position by the end -> genuine comeback,
    # even though the game happened to end on time
    moves = [mev(1, "white", "blunder", wp=40.0, cpl=400), mev(2, "black"),
             mev(3, "white")]
    a = analysis(moves, [20, -400, -400, 600])
    dg = dx.diagnose(DGame("win", termination="md won on time"), a)
    assert dg.primary == "comeback"


# --- draws ------------------------------------------------------------------

def test_let_slip_draw():
    moves = [mev(1, "white"), mev(2, "black")]
    a = analysis(moves, [300, 300, 20])
    dg = dx.diagnose(DGame("draw"), a)
    assert dg.primary == "let_slip"


def test_saved_draw():
    moves = [mev(1, "white"), mev(2, "black")]
    a = analysis(moves, [-300, -300, 20])
    dg = dx.diagnose(DGame("draw"), a)
    assert dg.primary == "saved"


# --- guards & aggregation ---------------------------------------------------

def test_none_when_no_data():
    assert dx.diagnose(DGame("loss"), analysis([], [])) is None
    assert dx.diagnose(DGame(""), analysis([mev(1, "white")], [0, 0])) is None


def test_outcome_reasons_aggregation():
    blunder = analysis([mev(1, "white", "blunder", wp=40.0, cpl=420)], [20, -400])
    steady = analysis([mev(1, "white")], [200, 210],
                      acc={"white": 90.0, "black": 70.0})
    pairs = [(DGame("loss"), blunder), (DGame("win"), steady)]
    out = insights.outcome_reasons(pairs)
    assert out and out[0]["title"] == "Why you win & lose"
    labels = {c["label"]: c["value"]
              for w in out[0]["widgets"] if w["type"] == "cards" for c in w["items"]}
    assert labels["Top reason you lose"] == dx.LOSS_REASONS["blunder"]
    assert labels["Top reason you win"] == dx.WIN_REASONS["steady"]
    # drill-down: a "reasons" widget per outcome, each group carrying its games
    reasons = [w for w in out[0]["widgets"] if w["type"] == "reasons"]
    by_label = {w["label"]: w for w in reasons}
    loss_grp = by_label["Why you lose"]["groups"][0]
    assert loss_grp["label"] == dx.LOSS_REASONS["blunder"]
    assert loss_grp["count"] == 1 and "100% of losses" in loss_grp["sub"]
    assert loss_grp["games"][0]["outcome"] == "loss" and loss_grp["games"][0]["detail"]


def test_outcome_reasons_empty():
    assert insights.outcome_reasons([]) == []
