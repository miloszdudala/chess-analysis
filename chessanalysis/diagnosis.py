"""Heuristic "why did I win / lose this game?" diagnosis.

Turns one game's engine analysis + clocks into a plain-language reason for the
result: a single blunder, a slow drift, time pressure, an opponent's gift, a
throw-away of a winning position, or simply being out- (or under-) played.

Shared by two views:
  * the single-game review — one verdict, with concrete move numbers and evals;
  * the player report — the *distribution* of reasons across many games, so you
    see what actually decides your wins and losses.

The result also carries secondary `factors`, because a loss is often more than
one thing at once (a blunder *in time trouble*, a drift that ended in a slip).
Everything is from the analysed player's point of view.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clocks import TIME_TROUBLE_FRAC, clock_profile, other_color
from .enrich.engine import MATE_CP

# Move-quality thresholds, in win% lost (à la engine.BLUNDER / MISTAKE).
BLUNDER_WP, MISTAKE_WP = 20.0, 10.0
# Positional-drift band: per-move centipawn loss that counts as a "small bleed",
# and how many in a row make a drift episode (mirrors metrics.game.review).
DRIFT_LO, DRIFT_HI, DRIFT_MIN = 15, 90, 4
# A single move must own at least this share of the total win% you lost to be
# called *the* blunder rather than one error among several.
DOMINATE = 0.45
# Fraction of plies you must lead for a win to read as "wire-to-wire".
STEADY_FRAC = 0.6

LOSS_REASONS = {
    "blunder": "One costly blunder",
    "errors": "A handful of errors",
    "drift": "Slow positional drift",
    "time": "Time pressure",
    "flagged": "Lost on the clock",
    "threw_away": "Let a winning position slip",
    "outplayed": "Simply outplayed",
}
WIN_REASONS = {
    "opp_blunder": "Opponent blundered",
    "comeback": "Comeback from behind",
    "steady": "Steady, wire-to-wire",
    "flag_win": "Won on the clock",
    "scramble": "Won a messy scramble",
}
DRAW_REASONS = {
    "saved": "Saved a worse position",
    "let_slip": "Let a win slip to a draw",
    "balanced": "A balanced draw",
}
# Labels for the secondary contributing factors (a superset of the primaries).
FACTOR_LABELS = {
    "time": "time pressure",
    "drift": "positional drift",
    "opp_blunder": "an opponent blunder",
    "opp_time": "the opponent's time trouble",
}


@dataclass
class Diagnosis:
    outcome: str            # "win" | "loss" | "draw"
    primary: str            # reason key (see *_REASONS above)
    headline: str           # short label, e.g. "One costly blunder"
    detail: str             # a full sentence or two, with concrete specifics
    factors: list = field(default_factory=list)   # secondary factor keys


def reason_label(outcome: str, key: str) -> str:
    table = (WIN_REASONS if outcome == "win"
             else LOSS_REASONS if outcome == "loss" else DRAW_REASONS)
    return table.get(key, key)


def factor_label(key: str) -> str:
    return FACTOR_LABELS.get(key, key)


# --- small helpers ----------------------------------------------------------

def _drift_runs(moves):
    """Maximal runs of consecutive small-loss moves (>= DRIFT_MIN long)."""
    runs, cur = [], []
    for m in moves:
        if DRIFT_LO <= m.cp_loss <= DRIFT_HI:
            cur.append(m)
        else:
            if len(cur) >= DRIFT_MIN:
                runs.append(cur)
            cur = []
    if len(cur) >= DRIFT_MIN:
        runs.append(cur)
    return runs


def _mv(m) -> str:
    """A move reference like '24. Qxf7' or '24… Qxf7'."""
    return f"{(m.ply + 1) // 2}{'.' if m.ply % 2 else '…'} {m.san}"


def _pawns(cp: int) -> str:
    """White/user-POV centipawns -> a human eval string."""
    if cp >= MATE_CP - 1000:
        return "a winning position"
    if cp <= -(MATE_CP - 1000):
        return "a lost position"
    return f"{cp / 100:+.1f}"


def _clock_ctx(game, color):
    """Returns (low_at(ply) -> bool, hit_time_trouble: bool) for `color`.

    Defensive: games without clocks / time control yield (always-False, False).
    """
    try:
        pp = clock_profile(game, color)
    except Exception:                       # noqa: BLE001 — missing fields on stubs
        pp = None
    base = pp.base if pp else None
    clock_at = {}
    try:
        for m in game.moves:
            if m.color == color and m.clock is not None:
                clock_at[m.ply] = m.clock
    except Exception:                       # noqa: BLE001
        pass

    def low_at(ply: int) -> bool:
        c = clock_at.get(ply)
        return base is not None and c is not None and c / base < TIME_TROUBLE_FRAC

    return low_at, bool(pp and pp.min_frac < TIME_TROUBLE_FRAC)


# --- the diagnosis ----------------------------------------------------------

def diagnose(game, analysis, cp: int = 200):
    """Classify why `game` ended the way it did. Returns a Diagnosis or None.

    None when there's nothing to reason about (no engine evals / no moves) or no
    bound outcome.
    """
    a = analysis
    outcome = getattr(game, "outcome", "")
    color = getattr(game, "color", "")
    if not a or not a.evals or not a.moves or outcome not in ("win", "loss", "draw"):
        return None

    sgn = 1 if color == "white" else -1
    user_evals = [sgn * e for e in a.evals]
    mine = [m for m in a.moves if m.color == color]
    theirs = [m for m in a.moves if m.color != color]
    if not mine:
        return None

    lead = cp // 2
    peak = max(user_evals)
    trough = min(user_evals)
    peak_i = user_evals.index(peak)
    trough_i = user_evals.index(trough)
    final = user_evals[-1]

    worst = max(mine, key=lambda m: m.wp_loss)
    total_wp = sum(m.wp_loss for m in mine) or 1.0
    sig = sorted((m for m in mine if m.wp_loss >= MISTAKE_WP),
                 key=lambda m: -m.wp_loss)
    runs = _drift_runs(mine)

    low_at, hit_tt = _clock_ctx(game, color)
    on_time = "time" in (getattr(game, "termination", "") or "").lower()
    sig_in_tt = [m for m in sig if low_at(m.ply)]

    if outcome == "loss":
        return _loss(user_evals, mine, worst, total_wp, sig, runs, peak, peak_i,
                     final, cp, lead, on_time, hit_tt, low_at, sig_in_tt, a, color)
    if outcome == "win":
        return _win(user_evals, theirs, trough, trough_i, peak, final, cp, lead,
                    on_time, hit_tt, a, color, game)
    return _draw(peak, peak_i, trough, trough_i, cp)


def _loss(user_evals, mine, worst, total_wp, sig, runs, peak, peak_i, final,
          cp, lead, on_time, hit_tt, low_at, sig_in_tt, a, color):
    factors = []
    if runs:
        factors.append("drift")

    # 1) You had a clearly winning position and lost it.
    if peak >= cp:
        downfall = ""
        after_peak = [m for m in mine if m.ply > peak_i and m.wp_loss >= MISTAKE_WP]
        if after_peak:
            big = max(after_peak, key=lambda m: m.wp_loss)
            downfall = f" It unravelled at {_mv(big)} (−{big.wp_loss:.0f}% win)."
        elif runs:
            downfall = " It slipped away gradually rather than in one move."
        detail = (f"You were on top — up to {_pawns(peak)} around move "
                  f"{(peak_i + 1) // 2} — but couldn't bring it home.{downfall}")
        if hit_tt and any(low_at(m.ply) for m in sig):
            factors = _add(factors, "time")
        return Diagnosis("loss", "threw_away", LOSS_REASONS["threw_away"],
                         detail, _dedupe(factors))

    # 2) Flag fell while the position was still playable.
    if on_time and final > -cp:
        return Diagnosis("loss", "flagged", LOSS_REASONS["flagged"],
                         f"The position was still holdable ({_pawns(final)}) when "
                         f"your flag fell — a clock loss, not a positional one.",
                         _dedupe(factors))

    # 3) Your decisive error came in time trouble — blame the clock.
    if hit_tt and worst.wp_loss >= MISTAKE_WP and low_at(worst.ply):
        return Diagnosis("loss", "time", LOSS_REASONS["time"],
                         f"Your costliest slip, {_mv(worst)} (−{worst.wp_loss:.0f}% "
                         f"win), came with under {int(TIME_TROUBLE_FRAC * 100)}% of "
                         f"your clock left — time pressure did the damage.",
                         _dedupe(factors))

    # 4) One dominant blunder.
    if (worst.wp_loss >= BLUNDER_WP and worst.wp_loss >= DOMINATE * total_wp):
        before = user_evals[worst.ply - 1]
        after = user_evals[worst.ply]
        if hit_tt and low_at(worst.ply):
            factors = _add(factors, "time")
        return Diagnosis("loss", "blunder", LOSS_REASONS["blunder"],
                         f"One move decided it: {_mv(worst)} threw away "
                         f"{worst.wp_loss:.0f}% win probability, swinging the game "
                         f"from {_pawns(before)} to {_pawns(after)}. The rest of "
                         f"your play was sound.",
                         _dedupe(factors))

    # 5) Several errors adding up.
    if len(sig) >= 2:
        names = ", ".join(_mv(m) for m in sig[:3])
        if hit_tt and sig_in_tt:
            factors = _add(factors, "time")
        return Diagnosis("loss", "errors", LOSS_REASONS["errors"],
                         f"No single catastrophe — {len(sig)} mistakes "
                         f"({names}{'…' if len(sig) > 3 else ''}) accumulated into "
                         f"the loss.",
                         _dedupe(factors))

    # 6) A slow positional drift.
    if runs:
        worst_run = max(runs, key=lambda r: sum(m.cp_loss for m in r))
        lost = sum(m.cp_loss for m in worst_run)
        detail = (f"A slow bleed rather than one blunder: {_mv(worst_run[0])}–"
                  f"{_mv(worst_run[-1])} leaked {lost}cp over {len(worst_run)} "
                  f"moves with no obvious mistake.")
        factors = [f for f in factors if f != "drift"]
        return Diagnosis("loss", "drift", LOSS_REASONS["drift"], detail,
                         _dedupe(factors))

    # 7) No real error of your own — outplayed.
    acc = a.accuracy.get(color)
    opp_acc = a.accuracy.get(other_color(color))
    cmp = ""
    if acc is not None and opp_acc is not None:
        cmp = f" ({opp_acc:.0f}% to your {acc:.0f}% accuracy)"
    return Diagnosis("loss", "outplayed", LOSS_REASONS["outplayed"],
                     f"You made no major error (worst move just "
                     f"−{worst.wp_loss:.0f}% win); your opponent simply played more "
                     f"accurately{cmp} and ground you down.",
                     _dedupe(factors))


def _win(user_evals, theirs, trough, trough_i, peak, final, cp, lead, on_time,
         hit_tt, a, color, game):
    factors = []
    opp_worst = max(theirs, key=lambda m: m.wp_loss) if theirs else None
    opp_total = sum(m.wp_loss for m in theirs) or 1.0
    _, opp_tt = _clock_ctx(game, other_color(color))
    if opp_tt:
        factors.append("opp_time")
    if opp_worst and opp_worst.wp_loss >= BLUNDER_WP:
        factors.append("opp_blunder")

    # 1) Won on time while the position itself wasn't won — the clock decided it,
    #    judged by the *final* eval (a comeback must recover on the board, not just
    #    flag the opponent from a worse position).
    if on_time and final < cp:
        # the opponent's clock IS the story here, so don't also list it as a factor
        factors = [f for f in factors if f != "opp_time"]
        if final <= -cp:
            where = f"a losing position ({_pawns(final)})"
        elif final < -lead:
            where = f"a worse position ({_pawns(final)})"
        elif final < lead:
            where = f"a level position ({_pawns(final)})"
        else:
            where = f"a better but not yet winning position ({_pawns(final)})"
        return Diagnosis("win", "flag_win", WIN_REASONS["flag_win"],
                         f"You won on the clock — your opponent flagged with you in "
                         f"{where} on the board.",
                         _dedupe(factors))

    # 2) Comeback — you were clearly losing and turned it around *on the board*
    #    (ended winning, not merely survived to flag them).
    if trough <= -cp and final >= cp:
        return Diagnosis("win", "comeback", WIN_REASONS["comeback"],
                         f"A comeback: you were losing — down to {_pawns(trough)} "
                         f"around move {(trough_i + 1) // 2} — and turned it around.",
                         _dedupe(factors))

    # 3) A single opponent blunder handed it to you.
    if opp_worst and opp_worst.wp_loss >= BLUNDER_WP and \
            opp_worst.wp_loss >= DOMINATE * opp_total:
        factors = [f for f in factors if f != "opp_blunder"]
        return Diagnosis("win", "opp_blunder", WIN_REASONS["opp_blunder"],
                         f"Your opponent handed it over: {_mv(opp_worst)} dropped "
                         f"{opp_worst.wp_loss:.0f}% win chance, and you took it.",
                         _dedupe(factors))

    # 4) Steady, wire-to-wire pressure.
    ahead = sum(1 for v in user_evals if v >= lead) / len(user_evals)
    acc = a.accuracy.get(color)
    if ahead >= STEADY_FRAC and (acc is None or acc >= 70):
        acc_txt = f" with {acc:.0f}% accuracy" if acc is not None else ""
        return Diagnosis("win", "steady", WIN_REASONS["steady"],
                         f"A wire-to-wire win — you led for "
                         f"{round(100 * ahead)}% of the game and converted{acc_txt}.",
                         _dedupe(factors))

    # 5) A messy, double-edged scramble.
    opp_acc = a.accuracy.get(other_color(color))
    cmp = ""
    if acc is not None and opp_acc is not None:
        cmp = f" ({acc:.0f}% to {opp_acc:.0f}%)"
    return Diagnosis("win", "scramble", WIN_REASONS["scramble"],
                     f"A messy, double-edged game{cmp} that swung both ways before "
                     f"falling your way.",
                     _dedupe(factors))


def _draw(peak, peak_i, trough, trough_i, cp):
    if peak >= cp:
        return Diagnosis("draw", "let_slip", DRAW_REASONS["let_slip"],
                         f"You reached {_pawns(peak)} around move "
                         f"{(peak_i + 1) // 2} but couldn't convert, settling for a "
                         f"draw.", [])
    if trough <= -cp:
        return Diagnosis("draw", "saved", DRAW_REASONS["saved"],
                         f"You were worse — down to {_pawns(trough)} around move "
                         f"{(trough_i + 1) // 2} — but held the draw.", [])
    return Diagnosis("draw", "balanced", DRAW_REASONS["balanced"],
                     "A level game throughout that ended in a fair draw.", [])


def _add(factors, key):
    return factors + [key]


def _dedupe(factors):
    seen, out = set(), []
    for f in factors:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out
