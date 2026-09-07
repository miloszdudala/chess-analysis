"""Opponent-strength stats (aggregate, within the chosen format).

Chess.com PGN headers carry POST-game ratings, so both the per-game rating
change and the strength gap are reconstructed from the chronological
(single-format) game list: your pre-game rating for game i is your post-game
rating from game i-1 (Δ = elo_i − elo_{i-1}), and the opponent's pre-game
rating is approximated by handing back the mirrored exchange (opp_post + Δ).
Classifying by the post-game gap would skew the buckets: winning makes the
opponent look ~2Δ weaker than they actually were, losing ~2Δ stronger.
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


@metric("player", title="By opponent strength", order=30, category="Opponents")
def by_opponent_strength(ctx):
    agg = {label: {"wdl": WDL(), "dsum": 0, "dn": 0} for label, _ in BUCKETS}
    prev = None
    for g in ctx.games:
        delta = (g.user_elo - prev) if (g.user_elo is not None and prev is not None) else None
        user_pre = prev
        if g.user_elo is not None:
            prev = g.user_elo
        if not (g.user_elo and g.opp_elo):
            continue
        if delta is not None:
            # pre-game gap: (opp_post + Δ) − user_pre  (see module docstring)
            gap = (g.opp_elo + delta) - user_pre
        else:
            gap = g.opp_elo - g.user_elo    # first game: post-only fallback
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
