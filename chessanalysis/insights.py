"""Aggregate conversion / stage analysis over many analysed games.

Answers "where do I perform well or poorly?" along several axes:
  * outcome-level conversion and save rates
  * where games are decided — the phase at the point of no return, for wins vs losses
  * accuracy by game phase (opening / middlegame / endgame)
  * accuracy by position state when it's my move (winning / equal / losing)
"""
from __future__ import annotations

import statistics
from collections import Counter

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
    won_phase, lost_phase = Counter(), Counter()
    won_moves, lost_moves = [], []

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

        # Point of no return: the move after which you hold a real lead (win) or
        # stay behind (loss) for the rest of the game — where it was really decided.
        # "Lead" = at least half the decisive threshold (e.g. +/-1 pawn).
        lead = cp // 2
        if g.outcome == "win":
            idx = max((i for i, v in enumerate(user_evals) if v < lead), default=-1)
            mv = max(1, (idx + 2) // 2)
            won_phase[_phase(mv)] += 1
            won_moves.append(mv)
        elif g.outcome == "loss":
            idx = max((i for i, v in enumerate(user_evals) if v > -lead), default=-1)
            mv = max(1, (idx + 2) // 2)
            lost_phase[_phase(mv)] += 1
            lost_moves.append(mv)

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

    def top_phase(counter):
        total = sum(counter.values())
        if not total:
            return "—", ""
        ph, c = counter.most_common(1)[0]
        return ph, f"{round(100 * c / total)}% of {total}"

    won_top, lost_top = top_phase(won_phase), top_phase(lost_phase)
    decided_cards = W.cards([
        W.card(won_top[0], "Wins decided in", sub=won_top[1]),
        W.card(lost_top[0], "Losses decided in", sub=lost_top[1]),
        W.card(f"move {round(sum(won_moves) / len(won_moves))}" if won_moves else "—",
               "Avg move you win"),
        W.card(f"move {round(sum(lost_moves) / len(lost_moves))}" if lost_moves else "—",
               "Avg move you lose"),
    ])
    decided_table = W.table(
        ["Phase", "Wins decided here", "Losses decided here"],
        [[ph, won_phase.get(ph, 0), lost_phase.get(ph, 0)] for ph in PHASE_ORDER],
    )

    return [
        {"title": "Outcomes", "widgets": [cards]},
        {"title": "Where games are decided", "widgets": [decided_cards, decided_table]},
        {"title": "Accuracy by phase", "widgets": [table(phase_agg, PHASE_ORDER, "Phase")]},
        {"title": "Accuracy by position (your move)",
         "widgets": [table(state_agg, [s[0] for s in STATES], "Position")]},
    ]


def form_report(pairs) -> list[dict]:
    """Test the "I have good/bad periods" theory on per-DAY accuracy.

    Aggregating to one value per day first is important: many games on a single
    bad day are correlated, so a per-game test would fake clustering. We average
    accuracy per day, then look for streaks/cycles across days.

    * runs test — do good/bad days cluster into streaks more than chance?
    * autocorrelation — is there a repeating cycle length (in active days)?
    * a rolling daily-accuracy chart to see the waves.
    pairs must be in chronological order.
    """
    day_acc: dict = {}
    for g, a in pairs:
        v = a.accuracy.get(g.color)
        if v is not None:
            day_acc.setdefault(g.date, []).append(v)

    days = sorted(day_acc)                       # "YYYY.MM.DD" sorts chronologically
    accs = [sum(day_acc[d]) / len(day_acc[d]) for d in days]   # mean accuracy per day
    games_per_day = sum(len(v) for v in day_acc.values()) / len(days) if days else 0
    dates = days
    n = len(accs)
    if n < 8:
        return [{"title": "Form & cycles", "widgets": [W.text(
            f"Only {n} active day(s) of games — need more days to test for cycles.")]}]

    # rolling average over days (visual)
    win = max(3, n // 10)
    roll = []
    for i in range(n):
        seg = accs[max(0, i - win + 1):i + 1]
        roll.append({"x": dates[i], "y": round(sum(seg) / len(seg), 1)})
    line = W.line([{"name": f"Rolling daily accuracy (window {win} days)", "points": roll}],
                  y_label="Accuracy")
    line["toolbar"] = False

    # autocorrelation: peak positive acf over candidate cycle lengths
    mean = sum(accs) / n
    var = sum((x - mean) ** 2 for x in accs)

    def acf(lag):
        return (sum((accs[i] - mean) * (accs[i + lag] - mean)
                    for i in range(n - lag)) / var) if var else 0.0

    best_lag, best = 0, 0.0
    for lag in range(2, min(25, n // 2) + 1):
        r = acf(lag)
        if r > best:
            best, best_lag = r, lag
    sig = 2 / (n ** 0.5)   # ~95% significance band for autocorrelation

    # runs test on above/below median accuracy (Wald–Wolfowitz)
    med = statistics.median(accs)
    b = [1 if x >= med else 0 for x in accs]
    n1, n2 = sum(b), n - sum(b)
    runs = 1 + sum(1 for i in range(1, n) if b[i] != b[i - 1])
    z = 0.0
    if n1 and n2:
        exp = 2 * n1 * n2 / n + 1
        v = 2 * n1 * n2 * (2 * n1 * n2 - n) / (n * n * (n - 1))
        if v > 0:
            z = (runs - exp) / (v ** 0.5)

    if z <= -1.96:
        pattern, psub = "Streaky", f"good & bad days cluster (z={z:.1f})"
    elif z >= 1.96:
        pattern, psub = "Alternating", f"good/bad days alternate (z={z:.1f})"
    else:
        pattern, psub = "Random", f"no clustering (z={z:.1f})"
    cyc = f"~{best_lag} days" if best > sig else "none clear"

    cards = W.cards([
        W.card(pattern, "Form pattern", sub=psub),
        W.card(cyc, "Strongest cycle", sub=f"autocorr {best:.2f} (sig > {sig:.2f})"),
        W.card(f"{n} days", "Active days", sub=f"~{games_per_day:.1f} games/day"),
        W.card(f"{round(roll[-1]['y'])}% vs {round(mean)}%", "Recent vs overall",
               sub="rolling now vs your mean"),
    ])

    if z <= -1.96:
        verdict = (f"Your form is streaky day-to-day: good and bad days cluster more than "
                   f"chance (runs test z={z:.1f}). That backs up your theory of better/worse periods.")
    elif z >= 1.96:
        verdict = (f"Your days tend to alternate rather than cluster (z={z:.1f}) — "
                   f"the opposite of sustained cycles.")
    else:
        verdict = (f"Day-to-day form looks essentially random (runs test z={z:.1f}): "
                   f"no statistical evidence of sustained good/bad periods in this window.")
    verdict += (f" Strongest repeating period ≈ {best_lag} active days (autocorrelation {best:.2f})."
                if best > sig else
                " No clear fixed-length cycle stands out in the autocorrelation.")
    verdict += f" Based on {n} active days (~{games_per_day:.1f} games/day)."

    return [{"title": "Form & cycles", "widgets": [cards, line, W.text(verdict)]}]
