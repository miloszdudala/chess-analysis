"""Aggregate conversion / stage analysis over many analysed games.

Answers "where do I perform well or poorly?" along several axes:
  * outcome-level conversion and save rates
  * where games are decided — the phase at the point of no return, for wins vs losses
  * accuracy by game phase (opening / middlegame / endgame)
  * accuracy by position state when it's my move (winning / equal / losing)
"""
from __future__ import annotations

from collections import Counter

import chess

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


# --- advanced, engine-derived diagnostics -----------------------------------
OPP_DROP = 150        # cp the opponent must hand you in one move to count as a chance
SHARP_GAP = 150       # cp gap between the engine's #1 and #2 = a "sharp" position
ERROR_LABELS = {"mistake", "blunder"}


def _is_error(label) -> bool:
    return label in ERROR_LABELS


def advanced_report(pairs) -> list[dict]:
    """Five engine-derived diagnostics aggregated over all analysed games.

    Uses each GameAnalysis's per-move evals, multi-PV candidates (top_moves),
    SAN/best-move and the board (fen_before) — so no extra engine work beyond
    the analysis the conversion pass already ran.
    """
    opp_chances = opp_taken = 0                       # opponent-error capitalization
    err_followed = err_then_err = 0                   # cascading errors
    base_moves = base_err = 0
    sharp_cpl, calm_cpl = [], []                      # sharpness vulnerability
    tension_pos = tension_premature = 0               # tension resolution

    for g, a in pairs:
        evals = a.evals
        if not evals:
            continue
        sgn = 1 if g.color == "white" else -1
        moves, tops = a.moves, a.top_moves

        # Opponent error capitalization: opponent hands you ≥OPP_DROP in one move,
        # do you reply with the engine's #1 (the refutation)?
        for i, m in enumerate(moves):
            if m.color == g.color:
                continue
            p = m.ply
            if not (1 <= p < len(evals)):
                continue
            if sgn * evals[p] - sgn * evals[p - 1] >= OPP_DROP:
                opp_chances += 1
                nxt = moves[i + 1] if i + 1 < len(moves) else None
                if nxt and nxt.color == g.color and nxt.best_san and nxt.san == nxt.best_san:
                    opp_taken += 1

        # Cascading error probability: P(error | previous move was an error),
        # over your own consecutive moves.
        mine = [m for m in moves if m.color == g.color]
        for j, m in enumerate(mine):
            base_moves += 1
            base_err += _is_error(m.label)
            if _is_error(m.label) and j + 1 < len(mine):
                err_followed += 1
                err_then_err += _is_error(mine[j + 1].label)

        # Sharpness vulnerability + tension resolution: per own move, look at the
        # multi-PV candidates and the board at that position.
        for m in mine:
            idx = m.ply - 1
            cand = tops[idx] if 0 <= idx < len(tops) else []
            if len(cand) >= 2:
                gap = abs(cand[0]["cp"] - cand[1]["cp"])
                (sharp_cpl if gap >= SHARP_GAP else calm_cpl).append(m.cp_loss)
            if cand and m.fen_before and m.move_uci:
                try:
                    b = chess.Board(m.fen_before)
                    played = chess.Move.from_uci(m.move_uci)
                    best = chess.Move.from_uci(cand[0]["uci"])
                except (ValueError, IndexError):
                    continue
                if sum(b.is_capture(mv) for mv in b.legal_moves) >= 2:
                    tension_pos += 1
                    # you released the tension (captured) but the engine kept it
                    if b.is_capture(played) and not b.is_capture(best):
                        tension_premature += 1

    if not base_moves:
        return []

    pct = lambda n, d: f"{round(100 * n / d)}%" if d else "—"
    mean = lambda xs: round(sum(xs) / len(xs)) if xs else None
    sharp_acpl, calm_acpl = mean(sharp_cpl), mean(calm_cpl)
    casc = pct(err_then_err, err_followed)
    base_rate = pct(base_err, base_moves)

    cards = W.cards([
        W.card(pct(opp_taken, opp_chances), "Opponent-error capitalization",
               sub=f"{opp_taken}/{opp_chances} refuted with the top move"),
        W.card(casc, "Cascading-error probability",
               sub=f"P(error | prior error) · base {base_rate}"),
        W.card(sharp_acpl if sharp_acpl is not None else "—", "Sharpness ACPL",
               sub=f"in sharp spots vs {calm_acpl if calm_acpl is not None else '—'} calm"),
        W.card(pct(tension_premature, tension_pos), "Premature simplification",
               sub=f"{tension_premature}/{tension_pos} tense positions released early"),
    ])
    notes = W.text(
        "Opponent-error capitalization — when the opponent blunders ≥1.5 pawns, how "
        "often you find the engine's refutation (offensive sharpness). "
        "Cascading-error probability — chance your next move is also an error right "
        "after a mistake; well above your base error rate signals tilt. "
        "Sharpness ACPL — average centipawn loss only in positions where the best "
        "move is far ahead of the second-best (calculation under pressure). "
        "Premature simplification — share of multi-capture positions where you "
        "released the tension but the engine preferred to keep it.")
    return [{"title": "Advanced metrics", "widgets": [cards, notes]}]
