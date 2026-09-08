"""Your accuracy against your band's — as two distributions, not two averages.

An average hides the thing that actually distinguishes players at one rating:
not where the middle of their play sits, which barely moves across a band, but
how wide the tail of bad games is. Two players averaging 80 are different
players if one ranges 76-84 and the other 60-95.

Both sides are binned the same way and normalised to their own game count, so a
16-game history and a 1254-game cohort are directly readable against each other.
"""
from ... import widgets as W
from ...registry import metric

STEP = 5
FLOOR = 45          # everything below this is one bucket: a rout is a rout
QS = (10, 25, 50, 75, 90)


def _bucket(v):
    return FLOOR - STEP if v < FLOOR else int(v // STEP * STEP)


def _hist(values):
    """{bucket: share of this side's games}, as percentages."""
    out = {}
    for v in values:
        out[_bucket(v)] = out.get(_bucket(v), 0) + 1
    return {b: 100 * n / len(values) for b, n in out.items()}


@metric("brackets", title="Accuracy spread — you against your band", order=25)
def distribution(ctx):
    from ... import corpus

    if ctx.scope != "peers" or not ctx.user:
        return None
    mine = corpus.my_accuracy_values(ctx.user, ctx.depth)
    band = corpus.accuracy_values(ctx.lo, ctx.hi, ctx.depth)
    if len(mine) < 5 or len(band) < 100:
        return None

    mh, bh = _hist(mine), _hist(band)
    buckets = sorted(set(mh) | set(bh))
    label = {b: ("<45" if b < FLOOR else f"{b}–{b + STEP - 1}") for b in buckets}

    curves = W.xyline(
        [{"name": f"You ({len(mine)} games)", "color": "#c1573f",
          "points": [{"x": b, "y": round(mh.get(b, 0), 1)} for b in buckets]},
         {"name": f"Your band ({len(band)})", "color": "#8aa4b8",
          "points": [{"x": b, "y": round(bh.get(b, 0), 1)} for b in buckets]}],
        y_label="% of that side's games", x_label="Game accuracy", y_zero=True)

    mq, bq = corpus.quantiles(mine, QS), corpus.quantiles(band, QS)
    rows = [[f"{q}th percentile", f"{mq[q]:.1f}", f"{bq[q]:.1f}",
             f"{mq[q] - bq[q]:+.1f}"] for q in QS]
    rows.append(["Spread (10th→90th)", f"{mq[90] - mq[10]:.1f}",
                 f"{bq[90] - bq[10]:.1f}", f"{(mq[90] - mq[10]) - (bq[90] - bq[10]):+.1f}"])

    bars = W.barstack(
        [{"label": label[b],
          "segments": [{"name": "you", "value": round(mh.get(b, 0), 1)},
                       {"name": "band", "value": round(bh.get(b, 0), 1)}],
          "note": f"you {mh.get(b, 0):.0f}% · band {bh.get(b, 0):.0f}%"}
         for b in buckets],
        {"you": "#c1573f", "band": "#8aa4b8"})

    return [
        W.text("Each side is binned the same way and shown as a share of its "
               "own games, so a short history reads against a large cohort. "
               "The percentile table is the robust summary — with few games "
               "the curve is spiky, but its quartiles still mean something."),
        curves,
        W.table(["", "You", "Your band", "Gap"], rows),
        bars,
    ]
