"""You against your rating band, in the same currency: same engine, same depth."""
from ... import widgets as W
from ...corpus import PHASES
from ...registry import metric


def _d(a, b, digits=1, invert=False):
    """Signed gap, phrased so a positive number always means 'better'."""
    if a is None or b is None:
        return "—"
    gap = (b - a) if invert else (a - b)
    return f"{gap:+.{digits}f}"


@metric("peers", title=None, order=10)
def headline(ctx):
    me, co, pc = ctx.me, ctx.cohort, ctx.percentile
    def blun(d):
        n = (d["op_n"] or 0) + (d["mg_n"] or 0) + (d["eg_n"] or 0)
        return None if not n else 100.0 * (d["inacc"] * 0 + d["blun"]) / n
    return W.cards([
        W.card(f"{me['acc']:.1f}", "Your accuracy",
               f"peers {co['acc']:.1f} · {_d(me['acc'], co['acc'])}"),
        W.card(f"{pc}th" if pc is not None else "—", "Percentile in your band",
               f"of {int(co['n'])} peer games"),
        W.card(f"{me['acpl']:.0f}", "Your ACPL",
               f"peers {co['acpl']:.0f} · {_d(me['acpl'], co['acpl'], 0, invert=True)}"),
        W.card(f"{me['plies'] / 2:.0f}", "Moves per game",
               f"peers {co['plies'] / 2:.0f}"),
    ])


@metric("peers", title="Where the gap is", order=20)
def by_phase(ctx):
    """Accuracy alone can hide the diagnosis: cleaner average play and more
    catastrophes net out to one number. Split by phase, and by error severity,
    they separate."""
    me, co = ctx.me, ctx.cohort
    rows = []
    for key, label in PHASES:
        rows.append([
            label,
            f"{me[key + '_acc']:.1f}" if me[key + "_acc"] else "—",
            f"{co[key + '_acc']:.1f}" if co[key + "_acc"] else "—",
            _d(me[key + "_acc"], co[key + "_acc"]),
            f"{me[key + '_bl']:.2f} / {co[key + '_bl']:.2f}",
            f"{me[key + '_mi']:.2f} / {co[key + '_mi']:.2f}",
        ])
    return [
        W.text("Same engine, same depth, same phase boundaries on both sides. "
               "A negative gap marks the phase where your band pulls ahead of you."),
        W.table(["Phase", "You", "Peers", "Gap",
                 "Blunders/100 (you / them)", "Mistakes/100 (you / them)"], rows),
    ]


@metric("peers", title="How your band scores", order=30)
def distribution(ctx):
    """Where your average sits in the spread of individual peer games."""
    if not ctx.hist:
        return None
    total = sum(n for _, n in ctx.hist)
    mine = ctx.me["acc"]
    rows = []
    for bucket, n in ctx.hist:
        here = bucket <= mine < bucket + 5
        rows.append({
            "label": f"{bucket}–{bucket + 4}" + (" ← you" if here else ""),
            "segments": [{"name": "you" if here else "games", "value": n}],
            "note": f"{100 * n / total:.0f}%",
        })
    return W.barstack(rows, {"games": "#8aa4b8", "you": "#3f7d5a"},
                      title=f"Accuracy of {total} peer games")


@metric("peers", title="Turning an advantage into a point", order=40)
def conversion(ctx):
    me, co = ctx.me, ctx.cohort
    return W.table(
        ["", "You", "Peers", "Gap"],
        [["Games that reached ±2.00", f"{me['decisive']:.0f}%",
          f"{co['decisive']:.0f}%", _d(me["decisive"], co["decisive"], 0)],
         ["...and held it to the end",
          f"{me['held']:.0f}%" if me["held"] is not None else "—",
          f"{co['held']:.0f}%" if co["held"] is not None else "—",
          _d(me["held"], co["held"], 0)],
         ["Won", f"{me['winpct']:.0f}%", f"{co['winpct']:.0f}%",
          _d(me["winpct"], co["winpct"], 0)]])
