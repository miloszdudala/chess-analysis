"""Scope "peers": you against players at your rating."""
from ... import widgets as W
from ...corpus import PHASES
from ...registry import metric


def _peers(ctx):
    return ctx.scope == "peers" and ctx.me and ctx.cohort


def _gap(a, b, digits=1, lower_is_better=False):
    """Signed gap phrased so a positive number always means you are ahead."""
    if a is None or b is None:
        return "—"
    return f"{(b - a) if lower_is_better else (a - b):+.{digits}f}".replace("-", "−")


@metric("brackets", title=None, order=10)
def headline(ctx):
    if not _peers(ctx):
        return None
    me, co = ctx.me, ctx.cohort
    n, cn = me["moves"] or 0, co["moves"] or 0
    cards = [
        W.card(f"{me['acc']:.1f}", "Your accuracy",
               f"theirs {co['acc']:.1f} · higher is better"),
        W.card(f"{me['acpl']:.0f}", "Your average centipawn loss",
               f"theirs {co['acpl']:.0f} · lower is better"),
        W.card(f"{100 * me['blunders'] / n:.1f}" if n else "—",
               "Your blunders per 100 moves",
               f"theirs {100 * co['blunders'] / cn:.1f}" if cn else ""),
    ]
    # Win rate is deliberately absent: both sides of every corpus game are
    # counted, so the band's wins equal its losses by construction and the
    # figure is pinned near (100 - draws)/2 whatever the players did. There is
    # nothing there to compare against.
    if ctx.percentile:
        pc, players = ctx.percentile
        suffix = "th" if 10 <= pc % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(pc % 10, "th")
        cards.append(W.card(f"{pc}{suffix}", "Accuracy percentile",
                            f"among {players} {ctx.who} with enough games"))
    return [W.cards(cards),
            W.text(f"\"Theirs\" is {ctx.who}, measured by the same engine at the same "
                   f"depth as your games.", guide="win-chance-lost",
                   label="What accuracy and centipawn loss are")]


@metric("brackets", title="Accuracy and blunders by phase", order=20)
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
    note = (f"Accuracy by phase, you against {ctx.who}, with the same phase "
            f"boundaries on both sides. The difference is your accuracy minus "
            f"theirs: positive means yours is higher.")
    if me["acc"] < co["acc"] and all(
            (me[k + "_acc"] or 0) >= (co[k + "_acc"] or 0) for k, _ in PHASES):
        note += (" Your accuracy is higher in every phase and lower overall: a "
                 "phase figure is the plain average of its moves' accuracy, while "
                 "game accuracy (the Lichess method) is half a harmonic mean, which "
                 "pulls toward a game's worst moves.")
    if me["dec_move"] and co["dec_move"]:
        note += (f" The evaluation first reaches ±2.00 around move "
                 f"{me['dec_move']:.0f} in your games and around move "
                 f"{co['dec_move']:.0f} in theirs.")
    return [
        W.text(note),
        W.table(["Phase", "Your accuracy", "Their accuracy", "Difference",
                 "Blunders per 100 moves (you / them)",
                 "Mistakes per 100 moves (you / them)"], rows),
    ]
