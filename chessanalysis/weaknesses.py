"""Weakness-finding diagnostics over many analysed games.

Three views, all purely descriptive (numbers, not advice), each built to give a
fair baseline rather than a confounded one:

  * phase parity     — you vs your opponents in the SAME games, phase by phase,
                       so "middlegames are just harder" cancels out;
  * think time       — move quality by seconds spent and by clock remaining;
  * opening leaks    — exact recurring positions where you repeat a move that
                       loses evaluation.

Fed by the same per-game analyses (and cache) as insights.py; served with the
conversion report via /api/insights.
"""
from __future__ import annotations

from collections import Counter


from . import widgets as W
from .clocks import clock_profile
from .diagnosis import _mv
from .enrich.engine import MATE_CP
from .phases import ORDER as PHASE_ORDER


# --- 1) you vs your opponents, phase by phase --------------------------------

def phase_parity(pairs) -> list[dict]:
    """Accuracy/error rates per phase for you AND your opponents in the same
    games. Raw per-phase accuracy is confounded (middlegames are harder for
    everyone); the you-minus-opponent gap in identical games is not."""
    agg = {p: {"mine": [0, 0.0, 0, 0], "theirs": [0, 0.0, 0, 0]}
           for p in PHASE_ORDER}          # [n, acc_sum, mistakes, blunders]
    for g, a in pairs:
        for m in a.moves:
            side = "mine" if m.color == g.color else "theirs"
            b = agg[a.phase_of(m.ply)][side]
            b[0] += 1
            b[1] += m.accuracy
            b[2] += (m.label == "mistake")
            b[3] += (m.label == "blunder")

    rows = []
    for p in PHASE_ORDER:
        mi, th = agg[p]["mine"], agg[p]["theirs"]
        if mi[0] < 50 or th[0] < 50:
            continue
        my_acc, opp_acc = mi[1] / mi[0], th[1] / th[0]
        rows.append([
            p, f"{my_acc:.1f}%", f"{opp_acc:.1f}%",
            f"{my_acc - opp_acc:+.1f}".replace("-", "−"),
            f"{100 * mi[3] / mi[0]:.1f} / {100 * th[3] / th[0]:.1f}",
            f"{100 * mi[2] / mi[0]:.1f} / {100 * th[2] / th[0]:.1f}",
        ])
    if not rows:
        return []
    return [{"title": "You against your opponents, phase by phase", "widgets": [
        W.text("Your accuracy and your opponents' in the same games, so how hard each "
               "phase is affects both sides alike. The difference is yours minus "
               "theirs: negative marks the phase where the people you actually play "
               "do better than you."),
        W.table(["Phase", "Your accuracy", "Their accuracy", "Difference",
                 "Blunders per 100 moves (you / them)",
                 "Mistakes per 100 moves (you / them)"], rows),
    ]}]


# Blunder anatomy used to live here: blunders grouped by the tactic the
# engine's refutation exploited. It was removed rather than repaired. Material
# and checks a rule can settle — exchange evaluation says whether a capture
# actually wins something — but the motifs worth naming are pins, discovered
# attacks, deflection, an overloaded defender, a king gone quietly unsafe, and
# none of those follow from the position by any arrangement of if-statements.
# Measured against exchange evaluation, its largest bucket was 45% wrong. A
# taxonomy that is confidently wrong about half its rows is worse than no
# taxonomy: the blunder counts and the phase split say what happened without
# claiming to know why.

# --- 3) think time vs move quality --------------------------------------------

TIME_BUCKETS = [(5, "Instant (<5s)"), (15, "Quick (5–15s)"),
                (45, "Normal (15–45s)"), (float("inf"), "Long think (>45s)")]
CLOCK_BUCKETS = [(0.10, "<10% clock left"), (0.25, "10–25%"),
                 (0.50, "25–50%"), (float("inf"), ">50% clock left")]


def _bucket(value, buckets):
    return next(label for thr, label in buckets if value < thr)


def think_time(pairs) -> list[dict]:
    """Move quality split by seconds spent on the move and by clock remaining."""
    def blank():
        return {"n": 0, "acc": 0.0, "mi": 0, "bl": 0}
    by_time = {lbl: blank() for _, lbl in TIME_BUCKETS}
    by_clock = {lbl: blank() for _, lbl in CLOCK_BUCKETS}
    bl_total = bl_instant = bl_lowclock = 0

    for g, a in pairs:
        pp = clock_profile(g, g.color)
        if pp is None:
            continue
        # spent seconds / clock fraction per ply of mine (aligned with pp lists)
        plies = [m.ply for m in g.moves if m.color == g.color and m.clock is not None]
        spent = dict(zip(plies, pp.move_times))
        frac = dict(zip(plies, (c / pp.base for c in pp.clocks)))
        for m in a.moves:
            if m.color != g.color or m.ply not in spent:
                continue
            for b in (by_time[_bucket(spent[m.ply], TIME_BUCKETS)],
                      by_clock[_bucket(frac[m.ply], CLOCK_BUCKETS)]):
                b["n"] += 1
                b["acc"] += m.accuracy
                b["mi"] += (m.label == "mistake")
                b["bl"] += (m.label == "blunder")
            if m.label == "blunder":
                bl_total += 1
                bl_instant += (spent[m.ply] < 5)
                bl_lowclock += (frac[m.ply] < 0.25)

    def table(agg, order, col):
        rows = [[lbl, b["n"], f"{b['acc'] / b['n']:.1f}%",
                 round(100 * b["mi"] / b["n"], 1), round(100 * b["bl"] / b["n"], 1)]
                for _, lbl in order if (b := agg[lbl])["n"] >= 30]
        return W.table([col, "Moves", "Accuracy",
                        "Mistakes per 100", "Blunders per 100"], rows) if rows else None

    tt = table(by_time, TIME_BUCKETS, "Time spent")
    tc = table(by_clock, CLOCK_BUCKETS, "Clock remaining")
    if not (tt or tc):
        return []
    widgets = [W.text("Where your errors sit on the clock: by how long you "
                      "thought about the move itself, and by how much time you "
                      "had left when you played it. Long thinks look worse for "
                      "everyone, because the hardest positions are where people "
                      "think longest; the quick-move rows are the cleaner signal, "
                      "since errors there were played without much looking.")]
    if bl_total >= 10:
        widgets.append(W.cards([
            W.card(f"{round(100 * bl_instant / bl_total)}%", "Blunders played instantly",
                   sub=f"{bl_instant} of your {bl_total} blunders took under 5 seconds"),
            W.card(f"{round(100 * bl_lowclock / bl_total)}%", "Blunders with the clock low",
                   sub=f"{bl_lowclock} of {bl_total} came with under 25% of your time left"),
        ]))
    widgets += [w for w in (tt, tc) if w]
    return [{"title": "Think time & move quality", "widgets": widgets}]


# --- 4) recurring opening leaks -----------------------------------------------

LEAK_MAX_PLY = 24        # first ~12 moves
LEAK_MIN_TIMES = 3       # a position+move must recur to be a habit, not a game
LEAK_MIN_CPL = 40        # average eval cost that makes the habit a leak


def _book_move(m) -> bool:
    """Whether strong players play this move here. The same position is scored
    the same way every time it recurs, so recurrence does not average out the
    engine's error at a shallow depth — and a line strong players choose is not
    a habit to fix, whatever a depth-10 search makes of it."""
    import chess

    from . import book
    try:
        return book.is_book(chess.Board(m.fen_before), m.move_uci)
    except ValueError:
        return False


def opening_leaks(pairs) -> list[dict]:
    """Positions you keep reaching where you keep playing the same
    eval-losing move — the concrete repertoire habits that cost you."""
    spots: dict = {}     # (fen-key, san) -> stats
    for g, a in pairs:
        for m in a.moves:
            if m.color != g.color or m.ply > LEAK_MAX_PLY or not m.fen_before:
                continue
            if _book_move(m):
                continue
            key = (" ".join(m.fen_before.split()[:4]), m.san)
            s = spots.setdefault(key, {
                "n": 0, "cpl": 0, "move_no": (m.ply + 1) // 2, "san": m.san,
                "ply": m.ply, "best": Counter(), "prev": Counter(),
                "wdl": Counter(), "games": [],
            })
            s["n"] += 1
            s["cpl"] += m.cp_loss
            if m.best_san:
                s["best"][m.best_san] += 1
            prev = next((mv.san for mv in g.moves if mv.ply == m.ply - 1), None)
            s["prev"][prev or "start"] += 1
            s["wdl"][g.outcome] += 1
            s["games"].append({
                "id": getattr(g, "game_id", ""),
                "ply": m.ply - 1,                 # the position before your move
                "date": getattr(g, "date", ""),
                "opponent": getattr(g, "opponent", "?"),
                "outcome": getattr(g, "outcome", ""),
                "note": f"−{m.cp_loss / 100:.1f} pawns"
                        + (f", engine wanted {m.best_san}" if m.best_san else ""),
            })

    leaks = [s for s in spots.values()
             if s["n"] >= LEAK_MIN_TIMES and s["cpl"] / s["n"] >= LEAK_MIN_CPL]
    if not leaks:
        return []
    leaks.sort(key=lambda s: -(s["n"] * s["cpl"] / s["n"]))
    rows = []
    for s in leaks[:10]:
        no, white_mv = s["move_no"], s["ply"] % 2 == 1
        after = s["prev"].most_common(1)[0][0]
        # the move before a White move is Black's previous one, a number lower
        ctx = ("from the start" if after == "start" else
               f"after {no - 1}…{after}" if white_mv else f"after {no}.{after}")
        best = s["best"].most_common(1)[0][0] if s["best"] else "—"
        w, d, l = s["wdl"]["win"], s["wdl"]["draw"], s["wdl"]["loss"]
        rows.append({
            "cells": [f"{no}{'.' if white_mv else '…'} {s['san']}", ctx, s["n"],
                      f"{s['cpl'] / s['n'] / 100:.1f}", best, f"{w}-{d}-{l}"],
            "games": sorted(s["games"], key=lambda e: e["date"], reverse=True),
        })
    return [{"title": "Recurring opening mistakes", "widgets": [
        W.text(f"Exact positions you reached at least {LEAK_MIN_TIMES} times in "
               f"the first {LEAK_MAX_PLY // 2} moves and answered with the same "
               f"move, losing {LEAK_MIN_CPL / 100:.1f} pawns of evaluation or more on "
               f"average — habits, not one-off slips. Book moves (what strong players "
               f"play there) are left out however the engine scores them. Click a row "
               f"to open the games at that position, with the engine's move arrowed."),
        W.drilltable(["You play", "Position", "Times", "Avg pawns lost",
                      "Engine prefers", "Your score (W-D-L)"], rows),
    ]}]


def report(pairs) -> list[dict]:
    """All three weakness diagnostics, in reading order."""
    return phase_parity(pairs) + think_time(pairs) + opening_leaks(pairs)
