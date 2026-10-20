"""Heuristic "why did I win / lose this game?" diagnosis.

Turns one game's engine analysis + clocks into a plain-language reason for the
result. A decisive game is decided by what the LOSING side did (or failed to
do), so wins and losses share one classifier run from the loser's perspective:
a loss is diagnosed on your play, a win on the opponent's — the same reason
categories with the roles swapped (your "One costly blunder" is their
"One opponent blunder", your "Let a winning position slip" is their
"Comeback from behind", and so on). Draws keep their own three reasons.

Shared by two views:
  * the single-game review — one verdict, with concrete move numbers and evals;
  * the player report — the *distribution* of reasons across many games, so you
    see what actually decides your wins and losses.

The result also carries secondary `factors`, because a loss is often more than
one thing at once (a blunder *in time trouble*, a drift that ended in a slip).
Detail sentences are always phrased from the analysed player's point of view.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clocks import TIME_TROUBLE_FRAC, clock_profile, other_color
from .enrich.engine import MATE_CP

# Move-quality thresholds, in win% lost (à la engine.BLUNDER / MISTAKE).
BLUNDER_WP, MISTAKE_WP = 20.0, 10.0
# Positional-drift band: per-move centipawn loss that counts as a "small bleed",
# and how many in a row make a drift episode (mirrors metrics.game.review).
DRIFT_LO, DRIFT_HI, DRIFT_MIN = 30, 90, 4
# A single move must own at least this share of the loser's *significant*
# win%-loss (mistake-level and worse) to be called *the* blunder. Measured
# against real errors only: in a long game the background noise of dozens of
# 1–2% inaccuracies would otherwise swamp a genuinely decisive move.
DOMINATE = 0.55

# One key set for every decisive game, labelled from each side of the board.
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
    "blunder": "One opponent blunder",
    "errors": "Opponent errors added up",
    "drift": "A slow squeeze",
    "time": "Opponent cracked in time trouble",
    "flagged": "Won on the clock",
    "threw_away": "Comeback from behind",
    "outplayed": "You outplayed them",
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
    "blunder": "a costly blunder",
    "opp_time": "the opponent's time trouble",
    "opp_drift": "the opponent's positional drift",
    "opp_blunder": "an opponent blunder",
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

    None when there's nothing to reason about (no engine evals / no moves for
    the relevant side) or no bound outcome.
    """
    a = analysis
    outcome = getattr(game, "outcome", "")
    color = getattr(game, "color", "")
    if not a or not a.evals or not a.moves or outcome not in ("win", "loss", "draw"):
        return None

    sgn = 1 if color == "white" else -1
    user_evals = [sgn * e for e in a.evals]
    if outcome == "draw":
        peak, trough = max(user_evals), min(user_evals)
        return _draw(peak, user_evals.index(peak),
                     trough, user_evals.index(trough), cp)

    # A decisive game is one story told from two sides — diagnose the loser.
    loser = color if outcome == "loss" else other_color(color)
    loser_evals = user_evals if outcome == "loss" else [-e for e in user_evals]
    loser_moves = [m for m in a.moves if m.color == loser]
    if not loser_moves:
        return None
    on_time = "time" in (getattr(game, "termination", "") or "").lower()
    return _decisive(game, a, outcome, loser, loser_evals, loser_moves, cp, on_time)


def _decisive(game, a, outcome, loser, evals, moves, cp, on_time):
    """Classify a decisive game from the loser's perspective.

    `evals` and `moves` belong to the losing side; `outcome` only flips the
    phrasing (and the factor keys) between "why you lost" and "why your
    opponent lost", so wins and losses always mirror each other.
    """
    won = outcome == "win"
    reasons = WIN_REASONS if won else LOSS_REASONS
    lead = cp // 2

    peak = max(evals)
    peak_i = evals.index(peak)
    final = evals[-1]
    worst = max(moves, key=lambda m: m.wp_loss)
    sig = sorted((m for m in moves if m.wp_loss >= MISTAKE_WP),
                 key=lambda m: -m.wp_loss)
    sig_total = sum(m.wp_loss for m in sig)
    runs = _drift_runs(moves)
    low_at, hit_tt = _clock_ctx(game, loser)
    sig_in_tt = [m for m in sig if low_at(m.ply)]

    def result(key, detail):
        factors = []
        if runs and key != "drift":
            factors.append("opp_drift" if won else "drift")
        # for "flagged" (and "time") the clock IS the story, not a side note
        if hit_tt and sig_in_tt and key not in ("time", "flagged"):
            factors.append("opp_time" if won else "time")
        if worst.wp_loss >= BLUNDER_WP and key != "blunder":
            factors.append("opp_blunder" if won else "blunder")
        return Diagnosis(outcome, key, reasons[key], detail, factors)

    # 1) The loser's flag fell while the board was still alive — the clock,
    #    not the position, decided it.
    if on_time and final > -cp:
        if won:
            uf = -final                     # user POV
            if uf <= -cp:
                where = f"a losing position ({_pawns(uf)})"
            elif uf < -lead:
                where = f"a worse position ({_pawns(uf)})"
            elif uf < lead:
                where = f"a level position ({_pawns(uf)})"
            else:
                where = f"a better but not yet winning position ({_pawns(uf)})"
            detail = (f"You won on the clock — your opponent flagged with you "
                      f"in {where} on the board.")
        else:
            detail = (f"The position was still holdable ({_pawns(final)}) when "
                      f"your flag fell — a clock loss, not a positional one.")
        return result("flagged", detail)

    # 2) The loser was clearly winning and let it slip.
    if peak >= cp:
        after_peak = [m for m in moves
                      if m.ply > peak_i and m.wp_loss >= MISTAKE_WP]
        big = max(after_peak, key=lambda m: m.wp_loss) if after_peak else None
        if won:
            turn = (f" It turned at {_mv(big)}, which cost them {big.wp_loss:.0f}% win chance."
                    if big else
                    (" It slipped away from them gradually rather than in one move."
                     if runs else ""))
            detail = (f"A comeback: you were losing — down to {_pawns(-peak)} "
                      f"around move {(peak_i + 1) // 2} — and turned it around."
                      f"{turn}")
        else:
            downfall = (f" It unravelled at {_mv(big)}, which cost {big.wp_loss:.0f}% win chance."
                        if big else
                        (" It slipped away gradually rather than in one move."
                         if runs else ""))
            detail = (f"You were on top — up to {_pawns(peak)} around move "
                      f"{(peak_i + 1) // 2} — but couldn't bring it home."
                      f"{downfall}")
        return result("threw_away", detail)

    # 3) The loser's decisive error came in time trouble — blame the clock.
    if hit_tt and worst.wp_loss >= MISTAKE_WP and low_at(worst.ply):
        pct = int(TIME_TROUBLE_FRAC * 100)
        if won:
            detail = (f"Your opponent cracked on the clock: their costliest "
                      f"move, {_mv(worst)} (−{worst.wp_loss:.0f}% win chance), came "
                      f"with under {pct}% of their time left.")
        else:
            detail = (f"Your costliest move, {_mv(worst)} "
                      f"(−{worst.wp_loss:.0f}% win chance), came with under {pct}% of "
                      f"your clock left — time pressure did the damage.")
        return result("time", detail)

    # 4) One dominant blunder decided it.
    if worst.wp_loss >= BLUNDER_WP and worst.wp_loss >= DOMINATE * sig_total:
        before, after = evals[worst.ply - 1], evals[worst.ply]
        if won:
            detail = (f"Your opponent handed it over: {_mv(worst)} threw away "
                      f"{worst.wp_loss:.0f}% win chance, swinging the game "
                      f"from {_pawns(-before)} to {_pawns(-after)} in your "
                      f"favour, and you took it.")
        else:
            detail = (f"One move decided it: {_mv(worst)} threw away "
                      f"{worst.wp_loss:.0f}% win chance, swinging the game "
                      f"from {_pawns(before)} to {_pawns(after)}. The rest of "
                      f"your play was sound.")
        return result("blunder", detail)

    # 5) Several errors adding up.
    if len(sig) >= 2:
        names = ", ".join(_mv(m) for m in sig[:3])
        more = "…" if len(sig) > 3 else ""
        if won:
            detail = (f"No single catastrophe from your opponent — {len(sig)} "
                      f"mistakes ({names}{more}) accumulated into your win.")
        else:
            detail = (f"No single catastrophe — {len(sig)} mistakes "
                      f"({names}{more}) accumulated into the loss.")
        return result("errors", detail)

    # 6) A slow positional drift.
    if runs:
        worst_run = max(runs, key=lambda r: sum(m.cp_loss for m in r))
        lost = sum(m.cp_loss for m in worst_run)
        span = f"{_mv(worst_run[0])}–{_mv(worst_run[-1])}"
        if won:
            detail = (f"A slow squeeze rather than one blunder: your opponent "
                      f"gave away {lost / 100:.1f} pawns over {len(worst_run)} moves "
                      f"({span}) with no single obvious mistake.")
        else:
            detail = (f"A slow bleed rather than one blunder: {span} gave away "
                      f"{lost / 100:.1f} pawns over {len(worst_run)} moves with no "
                      f"obvious mistake.")
        return result("drift", detail)

    # 7) No real error from the loser — the winner was simply better.
    w_acc = a.accuracy.get(other_color(loser))
    l_acc = a.accuracy.get(loser)
    if won:
        cmp = (f" ({w_acc:.0f}% to {l_acc:.0f}% accuracy)"
               if w_acc is not None and l_acc is not None else "")
        detail = (f"Your opponent made no major error (their worst move cost "
                  f"{worst.wp_loss:.0f}% win chance); you simply played more "
                  f"accurately{cmp} and ground them down.")
    else:
        cmp = (f" ({w_acc:.0f}% to your {l_acc:.0f}% accuracy)"
               if w_acc is not None and l_acc is not None else "")
        detail = (f"You made no major error (your worst move cost "
                  f"{worst.wp_loss:.0f}% win chance); your opponent simply played "
                  f"more accurately{cmp} and ground you down.")
    return result("outplayed", detail)


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
