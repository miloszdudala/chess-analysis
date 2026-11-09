"""You against players at your rating, using the report's own classifiers.

These reuse the same functions the Player report runs — `diagnosis.diagnose`,
the think-time buckets — but tally both sides
and show them together. Running them on the band alone, as an unmodified copy
of the player report would, answers a question nobody asked: it describes 400
strangers under headings that say "you".
"""
from collections import Counter

from ... import diagnosis as dx
from ... import weaknesses as wk
from ... import widgets as W
from ...clocks import clock_profile
from ...registry import metric

REUSE_LIMIT = 400          # cohort games held as full per-move analyses at once
MIN_ROW = 0.02             # hide reasons under 2% on both sides


def _both(ctx):
    """Your pairs and the band's, built once and reused across these metrics."""
    if getattr(ctx, "_pairs_cache", None) is None:
        from ... import corpus
        ctx._pairs_cache = (corpus.my_pairs(ctx.user, ctx.depth),
                            corpus.pairs(ctx.lo, ctx.hi, ctx.depth, REUSE_LIMIT))
    return ctx._pairs_cache


def _peers(ctx):
    return ctx.scope == "peers" and ctx.user


def _pct(n, total):
    return f"{100 * n / total:.0f}%" if total else "—"


def _gap(a, at, b, bt):
    """The difference between two shares, in percentage points."""
    if not at or not bt:
        return "—"
    return f"{100 * a / at - 100 * b / bt:+.0f}".replace("-", "−")


def _rows(mine, theirs, label_of, order=None):
    """Comparison rows for two Counters, commonest-first, rare ones dropped."""
    mt, tt = sum(mine.values()), sum(theirs.values())
    keys = order or sorted(set(mine) | set(theirs),
                           key=lambda k: -(theirs[k] / tt if tt else 0))
    rows = []
    for k in keys:
        m, t = mine.get(k, 0), theirs.get(k, 0)
        if (not mt or m / mt < MIN_ROW) and (not tt or t / tt < MIN_ROW):
            continue
        rows.append([label_of(k), f"{_pct(m, mt)} ({m})", _pct(t, tt), _gap(m, mt, t, tt)])
    return rows


@metric("brackets", title="Win and loss reasons", order=45)
def reasons(ctx):
    """The same one-dominant-reason diagnosis the Player report runs, tallied
    for you and for your band so the two distributions sit side by side."""
    if not _peers(ctx):
        return None
    mine, theirs = _both(ctx)

    def tally(pairs):
        out = {"loss": Counter(), "win": Counter(), "draw": Counter()}
        for g, a in pairs:
            dg = dx.diagnose(g, a, 200)
            if dg:
                out[dg.outcome][dg.primary] += 1
        return out

    mt, tt = tally(mine), tally(theirs)
    widgets = [W.text(
        f"Every game is reduced to one main reason for its result, the same way for "
        f"your games and for those of {ctx.who}. Your column shows the count of games too: "
        f"a share of a handful of games moves a lot with one game more or less. "
        f"The difference is your share minus theirs.")]
    for outcome, label in (("loss", "Why you lose"), ("win", "Why you win"),
                           ("draw", "Your draws")):
        if not sum(mt[outcome].values()):
            continue          # nothing of yours to compare — an empty column
        rows = _rows(mt[outcome], tt[outcome],
                     lambda k, o=outcome: dx.reason_label(o, k))
        if rows:
            widgets.append(W.table(
                [label, f"You ({sum(mt[outcome].values())} games)",
                 ctx.who[0].upper() + ctx.who[1:], "Difference"], rows))
    return widgets if len(widgets) > 1 else None


@metric("brackets", title="Opponent mistakes punished", order=58)
def capitalisation(ctx):
    """When the opponent makes a mistake, how often the engine's move is the
    reply — counted exactly as on the Stats page (`insights.punish_chances`)."""
    from ... import insights
    from ...enrich.engine import MISTAKE

    if not _peers(ctx):
        return None
    mine, theirs = _both(ctx)

    def tally(pairs):
        seen = taken = 0
        for g, a in pairs:
            for _, reply in insights.punish_chances(g, a):
                seen += 1
                taken += insights.punished(reply)
        return taken, seen

    mt, ms = tally(mine)
    tt, ts = tally(theirs)
    if ms < 10 or ts < 50:
        return None
    return [W.text(f"After the opponent's move cost them {MISTAKE:.0f}% win chance or "
                   f"more, how often the reply was the engine's first choice — for you "
                   f"and for {ctx.who}, at the same engine depth."),
            W.cards([
                W.card(f"{100 * mt / ms:.0f}%", "You punish it",
                       f"{mt} of {ms} chances"),
                W.card(f"{100 * tt / ts:.0f}%", "They punish it",
                       f"{tt} of {ts} chances")])]


@metric("brackets", title="Think time and move quality", order=65)
def think(ctx):
    """Error rate by how long the move took, you against players at your rating.

    The raw numbers look backwards — accuracy falls as thinking time rises —
    because players think longest in the hardest positions. The comparison is
    what carries meaning: the same selection effect applies to both columns.
    """
    if not _peers(ctx):
        return None
    mine, theirs = _both(ctx)

    def tally(pairs):
        agg = {lbl: [0, 0, 0.0] for _, lbl in wk.TIME_BUCKETS}   # n, blunders, acc
        for g, a in pairs:
            pp = clock_profile(g, g.color)
            if pp is None:
                continue
            plies = [m.ply for m in g.moves if m.color == g.color and m.clock is not None]
            spent = dict(zip(plies, pp.move_times))
            for m in a.moves:
                if m.color != g.color or m.ply not in spent:
                    continue
                b = agg[wk._bucket(spent[m.ply], wk.TIME_BUCKETS)]
                b[0] += 1
                b[1] += m.label == "blunder"
                b[2] += m.accuracy
        return agg

    ma, ta = tally(mine), tally(theirs)
    rows = []
    for _, lbl in wk.TIME_BUCKETS:
        m, t = ma[lbl], ta[lbl]
        if m[0] < 20 or t[0] < 50:
            continue
        rows.append([lbl, m[0], f"{m[2] / m[0]:.1f}%", f"{t[2] / t[0]:.1f}%",
                     f"{100 * m[1] / m[0]:.1f}", f"{100 * t[1] / t[0]:.1f}"])
    if not rows:
        return None
    return [W.text(f"Accuracy and blunders by how long the move took, you against "
                   f"{ctx.who}. Long thinks look worse for everyone, because hard "
                   f"positions are where people think longest; compare the two "
                   f"columns, not the rows."),
            W.table(["Time spent", "Your moves", "Your accuracy", "Their accuracy",
                     "Your blunders per 100", "Their blunders per 100"], rows)]
