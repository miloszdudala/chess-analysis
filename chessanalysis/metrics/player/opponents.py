"""Opponent-strength stats (aggregate, within the chosen format).

Per-game rating change is approximated from consecutive ratings in the
chronological (single-format) game list: Δ for game i = elo_i − elo_{i-1}.
"""
from ...registry import metric
from ... import widgets as W
from ...util import WDL

# (label, predicate on rating gap = opp_elo - user_elo), strongest first.
BUCKETS = [
    ("Much stronger (≥ +150)", lambda d: d >= 150),
    ("Stronger (+50…+150)", lambda d: 50 <= d < 150),
    ("Similar (−50…+50)", lambda d: -50 < d < 50),
    ("Weaker (−150…−50)", lambda d: -150 < d <= -50),
    ("Much weaker (≤ −150)", lambda d: d <= -150),
]


def _pct(n, t):
    return f"{round(100 * n / t)}%" if t else "—"


@metric("player", title="By opponent strength", order=40)
def by_opponent_strength(ctx):
    agg = {label: {"wdl": WDL(), "dsum": 0, "dn": 0} for label, _ in BUCKETS}
    prev = None
    for g in ctx.games:
        delta = (g.user_elo - prev) if (g.user_elo is not None and prev is not None) else None
        if g.user_elo is not None:
            prev = g.user_elo
        if not (g.user_elo and g.opp_elo):
            continue
        gap = g.opp_elo - g.user_elo
        for label, test in BUCKETS:
            if test(gap):
                bucket = agg[label]
                bucket["wdl"].add(g.outcome)
                if delta is not None:
                    bucket["dsum"] += delta
                    bucket["dn"] += 1
                break

    rows = []
    for label, _ in BUCKETS:
        b = agg[label]
        w = b["wdl"]
        if not w.total:
            continue
        avg_d = f"{b['dsum'] / b['dn']:+.0f}" if b["dn"] else "—"
        rows.append([label, w.total, w.win, w.draw, w.loss,
                     _pct(w.win, w.total), avg_d, {"bar": [w.win, w.draw, w.loss]}])
    if not rows:
        return None
    return W.table(["Opponent", "Games", "W", "D", "L", "Win%", "Avg Δ", ""], rows)


@metric("player", title="Opponent strength by result", order=41)
def strength_by_result(ctx):
    agg = {o: {"opp": [], "gap": []} for o in ("win", "draw", "loss")}
    for g in ctx.games:
        if not g.opp_elo:
            continue
        agg[g.outcome]["opp"].append(g.opp_elo)
        if g.user_elo:
            agg[g.outcome]["gap"].append(g.opp_elo - g.user_elo)

    rows = []
    for outcome, label in (("win", "Won"), ("draw", "Drew"), ("loss", "Lost")):
        opp, gap = agg[outcome]["opp"], agg[outcome]["gap"]
        if not opp:
            continue
        avg_opp = round(sum(opp) / len(opp))
        avg_gap = f"{round(sum(gap) / len(gap)):+d}" if gap else "—"
        rows.append([label, len(opp), avg_opp, avg_gap])
    if not rows:
        return None
    return W.table(["Result", "Games", "Avg opponent Elo", "Avg gap"], rows)
