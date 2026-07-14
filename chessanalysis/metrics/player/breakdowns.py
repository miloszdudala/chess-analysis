"""Results: W/D/L split by color and by game length.

(Form/momentum moved to the FIDE-performance Form section in Overview.)
"""
from ...registry import metric
from ... import widgets as W
from ...util import WDL, tally, wdl_rows

CAT = "Results & form"


@metric("player", title="By color", order=20, category=CAT)
def by_color(ctx):
    return W.wdl_barstack(wdl_rows(tally(ctx.games, lambda g: g.color.title())))


# (label, predicate on full-move count) — short games are usually decided in the
# opening/early tactics; long ones in the endgame, so this localises weak phases.
LENGTH_BUCKETS = [
    ("Short (< 20 moves)", lambda m: m < 20),
    ("Medium (20–40)", lambda m: 20 <= m <= 40),
    ("Long (> 40 moves)", lambda m: m > 40),
]


@metric("player", title="By game length", order=24, category=CAT)
def by_game_length(ctx):
    agg = {lbl: WDL() for lbl, _ in LENGTH_BUCKETS}
    for g in ctx.games:
        full_moves = (len(g.moves) + 1) // 2
        for lbl, test in LENGTH_BUCKETS:
            if test(full_moves):
                agg[lbl].add(g.outcome)
                break
    rows = [{"label": lbl, "win": agg[lbl].win, "draw": agg[lbl].draw,
             "loss": agg[lbl].loss}
            for lbl, _ in LENGTH_BUCKETS if agg[lbl].total]
    if not rows:
        return None
    return W.wdl_barstack(rows)

