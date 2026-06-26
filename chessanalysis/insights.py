"""Aggregate conversion / stage analysis over many analysed games.

Answers "where do I perform well or poorly?" along two axes:
  * game phase   — opening / middlegame / endgame
  * position state when it's my move — winning / equal / losing (the conversion lens)
plus outcome-level conversion and save rates.
"""
from __future__ import annotations

from . import widgets as W

PHASE_ORDER = ["Opening", "Middlegame", "Endgame"]

# (label, predicate on user-perspective centipawns before the move)
STATES = [
    ("Winning (≥ +2)", lambda c: c >= 200),
    ("Better (+0.8…+2)", lambda c: 80 <= c < 200),
    ("Equal (±0.8)", lambda c: -80 < c < 80),
    ("Worse (−2…−0.8)", lambda c: -200 < c <= -80),
    ("Losing (≤ −2)", lambda c: c <= -200),
]


def _phase(move_no: int) -> str:
    if move_no <= 12:
        return "Opening"
    if move_no <= 32:
        return "Middlegame"
    return "Endgame"


def _blank():
    return {"n": 0, "acc": 0.0, "bl": 0, "mi": 0}


def conversion_report(pairs, cp: int = 200) -> list[dict]:
    """pairs: list of (Game, GameAnalysis). Returns a list of {title, widgets}."""
    phase_agg = {p: _blank() for p in PHASE_ORDER}
    state_agg = {s[0]: _blank() for s in STATES}
    reached_win = won = reached_loss = saved = decisive = 0

    for g, a in pairs:
        evals = a.evals
        if not evals:
            continue
        user_evals = [e if g.color == "white" else -e for e in evals]
        if max(user_evals) >= cp:
            reached_win += 1
            won += (g.outcome == "win")
        if min(user_evals) <= -cp:
            reached_loss += 1
            saved += (g.outcome in ("win", "draw"))
        if max(abs(e) for e in evals) >= cp:
            decisive += 1

        for m in a.moves:
            if m.color != g.color:
                continue
            move_no = (m.ply + 1) // 2
            cp_white = evals[m.ply - 1] if 0 <= m.ply - 1 < len(evals) else 0
            cp_user = cp_white if g.color == "white" else -cp_white
            state = next(s[0] for s in STATES if s[1](cp_user))
            for bucket in (phase_agg[_phase(move_no)], state_agg[state]):
                bucket["n"] += 1
                bucket["acc"] += m.accuracy
                bucket["bl"] += (m.label == "blunder")
                bucket["mi"] += (m.label == "mistake")

    def table(agg, order, label_col):
        rows = []
        for key in order:
            b = agg[key]
            if not b["n"]:
                continue
            rows.append([
                key, b["n"], f"{b['acc'] / b['n']:.1f}%",
                round(100 * b["mi"] / b["n"], 1), round(100 * b["bl"] / b["n"], 1),
            ])
        return W.table([label_col, "Moves", "Avg accuracy", "Mistakes/100", "Blunders/100"], rows)

    thr = f"{cp / 100:.0f}"
    cards = W.cards([
        W.card(f"{round(100 * won / reached_win)}%" if reached_win else "—",
               "Conversion", sub=f"{won}/{reached_win} winning games won"),
        W.card(f"{round(100 * saved / reached_loss)}%" if reached_loss else "—",
               "Save rate", sub=f"{saved}/{reached_loss} losing games saved"),
        W.card(f"{round(100 * decisive / len(pairs))}%" if pairs else "—",
               "Decisive games", sub=f"reached ±{thr}"),
    ])
    return [
        {"title": "Outcomes", "widgets": [cards]},
        {"title": "Accuracy by phase", "widgets": [table(phase_agg, PHASE_ORDER, "Phase")]},
        {"title": "Accuracy by position (your move)",
         "widgets": [table(state_agg, [s[0] for s in STATES], "Position")]},
    ]
