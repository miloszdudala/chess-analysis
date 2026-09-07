"""Scope "peers": you against the band you actually play in."""
from ... import widgets as W
from ...corpus import PHASES
from ...registry import metric


def _peers(ctx):
    return ctx.scope == "peers" and ctx.me and ctx.cohort


def _gap(a, b, digits=1, lower_is_better=False):
    """Signed gap phrased so a positive number always means you are ahead."""
    if a is None or b is None:
        return "—"
    return f"{(b - a) if lower_is_better else (a - b):+.{digits}f}"


@metric("brackets", title=None, order=10)
def headline(ctx):
    if not _peers(ctx):
        return None
    me, co, pc = ctx.me, ctx.cohort, ctx.percentile
    return W.cards([
        W.card(f"{me['acc']:.1f}", "Your accuracy",
               f"peers {co['acc']:.1f} · {_gap(me['acc'], co['acc'])}"),
        W.card(f"{pc}th" if pc is not None else "—", "Percentile in your band",
               f"of {int(co['n'])} peer games"),
        W.card(f"{me['acpl']:.0f}", "Your ACPL",
               f"peers {co['acpl']:.0f} · "
               f"{_gap(me['acpl'], co['acpl'], 0, lower_is_better=True)}"),
        W.card(f"{me['winpct']:.0f}%", "Won",
               f"peers {co['winpct']:.0f}%"),
    ])


@metric("brackets", title="Where the gap is", order=20)
def by_phase(ctx):
    """Accuracy alone can hide the diagnosis — cleaner average play and more
    catastrophes net out to one number. Split by phase and by severity, they
    separate."""
    if not _peers(ctx):
        return None
    me, co = ctx.me, ctx.cohort
    rows = [[label,
             f"{me[k + '_acc']:.1f}" if me[k + "_acc"] else "—",
             f"{co[k + '_acc']:.1f}" if co[k + "_acc"] else "—",
             _gap(me[k + "_acc"], co[k + "_acc"]),
             f"{me[k + '_bl']:.2f} / {co[k + '_bl']:.2f}",
             f"{me[k + '_mi']:.2f} / {co[k + '_mi']:.2f}"]
            for k, label in PHASES]
    return [
        W.text("Same engine, same depth, same phase boundaries on both sides. "
               "A negative gap marks the phase where your band pulls ahead of you."),
        W.table(["Phase", "You", "Peers", "Gap",
                 "Blunders/100 (you / them)", "Mistakes/100 (you / them)"], rows),
    ]


@metric("brackets", title="How your band scores", order=30)
def distribution(ctx):
    """Where your average sits in the spread of individual peer games."""
    if not _peers(ctx) or not ctx.hist:
        return None
    total = sum(n for _, n in ctx.hist)
    mine = ctx.me["acc"]
    rows = []
    for bucket, n in ctx.hist:
        here = bucket <= mine < bucket + 5
        rows.append({"label": f"{bucket}–{bucket + 4}" + (" ← you" if here else ""),
                     "segments": [{"name": "you" if here else "games", "value": n}],
                     "note": f"{100 * n / total:.0f}%"})
    return W.barstack(rows, {"games": "#8aa4b8", "you": "#3f7d5a"},
                      title=f"Accuracy of {total} peer games")
