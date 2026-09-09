"""How many of your games land in each accuracy band.

A plain frequency count: group your games by the accuracy they scored and say
how many fell in each bucket. The band's share sits alongside as context —
raw counts could not, since it holds a thousand games to your handful — so a
bucket that is over- or under-represented in your play is visible without
having to hold two averages in your head.
"""
from ... import widgets as W
from ...registry import metric

STEP = 5
FLOOR = 45          # below this it is a rout; one bucket is enough


def _bucket(v):
    return FLOOR - STEP if v < FLOOR else int(v // STEP * STEP)


def _label(b):
    return "under 45" if b < FLOOR else f"{b}–{b + STEP - 1}"


def _counts(values):
    out = {}
    for v in values:
        out[_bucket(v)] = out.get(_bucket(v), 0) + 1
    return out


@metric("brackets", title="Your games by accuracy", order=25)
def distribution(ctx):
    from ... import corpus

    if ctx.scope != "peers" or not ctx.user:
        return None
    mine = corpus.my_accuracy_values(ctx.user, ctx.depth)
    band = corpus.accuracy_values(ctx.lo, ctx.hi, ctx.depth)
    if len(mine) < 5 or len(band) < 100:
        return None

    mc, bc = _counts(mine), _counts(band)
    rows = []
    for b in sorted(set(mc) | set(bc), reverse=True):     # best games first
        n = mc.get(b, 0)
        mine_pct = 100 * n / len(mine)
        band_pct = 100 * bc.get(b, 0) / len(band)
        rows.append([_label(b), n, f"{mine_pct:.0f}%", f"{band_pct:.0f}%",
                     f"{mine_pct - band_pct:+.0f}"])
    # No chart underneath: it plotted the column beside it and nothing more.
    return [
        W.text(f"Your {len(mine)} games grouped by the accuracy each one "
               f"scored, against how the band's {len(band)} games fall. The "
               f"band column is a share rather than a count — it holds a "
               f"thousand games to your handful."),
        W.table(["Accuracy", "Your games", "Share of yours", "Your band", "Gap"],
                rows),
    ]
