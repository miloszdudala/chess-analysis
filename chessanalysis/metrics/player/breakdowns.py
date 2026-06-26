"""Results & form: W/D/L split by color, recent form, and game length."""
from ...registry import metric
from ... import widgets as W
from ...util import WDL, tally, wdl_rows

CAT = "Results & form"


@metric("player", title="By color", order=20, category=CAT)
def by_color(ctx):
    return W.wdl_table("Color", wdl_rows(tally(ctx.games, lambda g: g.color.title())))


@metric("player", title="Form & momentum", order=22, category=CAT)
def momentum(ctx):
    """How you do depending on the previous game's result — a tilt check.

    Games are chronological, so we tally each game's outcome against the result
    of the one before it, plus a 'on a losing streak' bucket (2+ losses deep).
    """
    after = {"win": WDL(), "draw": WDL(), "loss": WDL()}
    streak = WDL()
    prev, losses_in_row = None, 0
    for g in ctx.games:
        if prev is not None:
            after[prev].add(g.outcome)
        if losses_in_row >= 2:
            streak.add(g.outcome)
        losses_in_row = losses_in_row + 1 if g.outcome == "loss" else 0
        prev = g.outcome

    rows = []
    for key, label in (("win", "After a win"), ("draw", "After a draw"),
                       ("loss", "After a loss")):
        w = after[key]
        if w.total:
            rows.append({"label": label, "win": w.win, "draw": w.draw, "loss": w.loss})
    if streak.total:
        rows.append({"label": "On a 2+ loss streak", "win": streak.win,
                     "draw": streak.draw, "loss": streak.loss})
    if len(rows) < 2:
        return None
    return W.wdl_table("Previous game", rows)


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
    return W.wdl_table("Game length", rows)
