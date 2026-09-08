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
    me, co = ctx.me, ctx.cohort
    n, cn = me["moves"] or 0, co["moves"] or 0
    cards = [
        W.card(f"{me['acc']:.1f}", "Your accuracy",
               f"peers {co['acc']:.1f} · {_gap(me['acc'], co['acc'])}"),
        W.card(f"{me['acpl']:.0f}", "Your ACPL",
               f"peers {co['acpl']:.0f} · "
               f"{_gap(me['acpl'], co['acpl'], 0, lower_is_better=True)}"),
        W.card(f"{100 * me['blunders'] / n:.1f}" if n else "—",
               "Blunders / 100 moves",
               f"peers {100 * co['blunders'] / cn:.1f}" if cn else ""),
    ]
    # Win rate is deliberately absent: both sides of every corpus game are
    # counted, so the band's wins equal its losses by construction and the
    # figure is pinned near (100 - draws)/2 whatever the players did. There is
    # nothing there to compare against.
    if ctx.percentile:
        pc, players = ctx.percentile
        suffix = "th" if 10 <= pc % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(pc % 10, "th")
        cards.append(W.card(f"{pc}{suffix}", "Percentile in your band",
                            f"among {players} players' averages"))
    return W.cards(cards)


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
    note = ("Same engine, same depth, same phase boundaries on both sides. "
            "A negative gap marks the phase where your band pulls ahead of you.")
    if me["acc"] < co["acc"] and all(
            (me[k + "_acc"] or 0) >= (co[k + "_acc"] or 0) for k, _ in PHASES):
        note += (" Note the shape here: your accuracy is higher in every phase "
                 "yet lower overall. Game accuracy punishes catastrophes, and "
                 "the blunder columns are where that shows.")
    if me["dec_move"] and co["dec_move"]:
        note += (f" Your games are decided around move {me['dec_move']:.0f}, "
                 f"your band's around move {co['dec_move']:.0f}.")
    return [
        W.text(note),
        W.table(["Phase", "You", "Peers", "Gap",
                 "Blunders/100 (you / them)", "Mistakes/100 (you / them)"], rows),
    ]
