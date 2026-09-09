"""Weakness-finding diagnostics (weaknesses.report)."""
from __future__ import annotations

from chessanalysis import weaknesses as wk
from chessanalysis.enrich.engine import GameAnalysis, MoveEval
from chessanalysis.model import Move


def mev(ply, color, label="ok", cpl=0, acc=95.0, san="x", best="", fen="", uci=""):
    return MoveEval(ply=ply, color=color, san=san, best_san=best, cp_loss=cpl,
                    wp_loss=0.0, accuracy=acc, label=label, fen_before=fen,
                    move_uci=uci)


def analysis(moves, evals=None, top_moves=None):
    a = GameAnalysis(depth=12, engine_name="x", evals=evals or [0], moves=moves)
    a.top_moves = top_moves or []
    a.accuracy = {"white": 85.0, "black": 85.0}
    return a


class WGame:
    def __init__(self, outcome="win", color="white", moves=None, tc="600",
                 opponent="opp", date="2026.01.01", opening="Italian Game"):
        self.outcome, self.color, self.opponent = outcome, color, opponent
        self.date, self.opening = date, opening
        self.termination, self.time_control = "Normal", tc
        self.moves = moves or []


# --- phase parity -------------------------------------------------------------

def test_phase_parity_pairs_you_against_opponents():
    # 5 games × 12 opening moves each side: you 90% avg accuracy, them 80%
    moves = ([mev(p, "white", acc=90.0) for p in range(1, 24, 2)]
             + [mev(p, "black", acc=80.0) for p in range(2, 25, 2)])
    out = wk.phase_parity([(WGame(), analysis(moves)) for _ in range(5)])
    rows = out[0]["widgets"][1]["rows"]
    assert rows[0][0] == "Opening"
    assert rows[0][1] == "90.0%" and rows[0][2] == "80.0%" and rows[0][3] == "+10.0%"


def test_phase_parity_needs_sample():
    moves = [mev(1, "white"), mev(2, "black")]
    assert wk.phase_parity([(WGame(), analysis(moves))]) == []


# --- think time ---------------------------------------------------------------

def timed_game():
    # 40 own moves: instant accurate moves, one long-think blunder
    gmoves, amoves, clock = [], [], 600.0
    for i, ply in enumerate(range(1, 80, 2)):
        spend = 60.0 if i == 20 else 2.0
        clock -= spend
        gmoves.append(Move(ply=ply, color="white", san="x", clock=clock))
        amoves.append(mev(ply, "white",
                          label="blunder" if i == 20 else "ok",
                          acc=20.0 if i == 20 else 95.0))
    return WGame(moves=gmoves), analysis(amoves)


def test_think_time_buckets_split_by_seconds_spent():
    pairs = [timed_game() for _ in range(2)]
    out = wk.think_time(pairs)
    tbl = next(w for w in out[0]["widgets"] if w["type"] == "table")
    by_label = {r[0]: r for r in tbl["rows"]}
    inst = by_label["Instant (<5s)"]
    assert inst[1] == 78 and inst[4] == 0.0        # no blunders on instant moves
    # the long-think bucket (n=2) is below the 30-move floor -> not shown
    assert "Long think (>45s)" not in by_label


def test_think_time_skips_games_without_clocks():
    g = WGame(tc="")            # no time control -> no profile
    assert wk.think_time([(g, analysis([mev(1, "white")]))]) == []


# --- opening leaks --------------------------------------------------------------

def leak_game(outcome="loss"):
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    gm = [Move(ply=1, color="white", san="e4", clock=None),
          Move(ply=2, color="black", san="e5", clock=None),
          Move(ply=3, color="white", san="Ke2", clock=None)]
    m = mev(3, "white", "mistake", cpl=90, san="Ke2", best="Nf3", fen=fen, uci="e1e2")
    return WGame(outcome, moves=gm), analysis([m])


def test_opening_leak_needs_repetition():
    assert wk.opening_leaks([leak_game()]) == []
    out = wk.opening_leaks([leak_game() for _ in range(3)])
    tbl = out[0]["widgets"][1]
    assert tbl["type"] == "drilltable"
    row = tbl["rows"][0]
    assert row["cells"][0] == "2. Ke2" and row["cells"][1] == "after 2…e5"
    assert row["cells"][2] == 3 and row["cells"][4] == "Nf3" and row["cells"][5] == "0-0-3"
    # drill-down opens each game at the position *before* the leak move (ply 2)
    assert len(row["games"]) == 3 and all(gm["ply"] == 2 for gm in row["games"])
