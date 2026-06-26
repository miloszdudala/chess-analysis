"""Results & form: W/D/L split by color, recent form, and game length."""
from ...registry import metric
from ... import widgets as W
from ...util import WDL, tally, wdl_rows

CAT = "Results & form"


@metric("player", title="By color", order=20, category=CAT)
def by_color(ctx):
    return W.wdl_barstack(wdl_rows(tally(ctx.games, lambda g: g.color.title())))


@metric("player", title="Form & momentum", order=22, category=CAT)
def momentum(ctx):
    """Tilt within a session: results vs the *same-day* previous game.

    Momentum only makes sense inside a sitting — a result yesterday shouldn't
    colour today's first game. So a new day resets everything: its first game is
    tallied separately ("First game of the day", a fresh start), and the
    after-a-win/draw/loss and losing-streak buckets only count transitions
    between consecutive games played on the same calendar day.
    """
    after = {"win": WDL(), "draw": WDL(), "loss": WDL()}
    first = WDL()                 # the first game of each day (fresh start)
    streak = WDL()                # games played while 2+ losses deep, same day
    prev_outcome, prev_day, losses_in_row = None, None, 0
    for g in ctx.games:
        same_day = g.date == prev_day
        if not same_day:
            losses_in_row = 0     # a new day breaks any streak / momentum
            first.add(g.outcome)
        else:
            after[prev_outcome].add(g.outcome)
            if losses_in_row >= 2:
                streak.add(g.outcome)
        losses_in_row = losses_in_row + 1 if g.outcome == "loss" else 0
        prev_outcome, prev_day = g.outcome, g.date

    rows = []
    if first.total:
        rows.append({"label": "First game of the day", "win": first.win,
                     "draw": first.draw, "loss": first.loss})
    for key, label in (("win", "After a win (same day)"),
                       ("draw", "After a draw (same day)"),
                       ("loss", "After a loss (same day)")):
        w = after[key]
        if w.total:
            rows.append({"label": label, "win": w.win, "draw": w.draw, "loss": w.loss})
    if streak.total:
        rows.append({"label": "On a 2+ loss streak (same day)", "win": streak.win,
                     "draw": streak.draw, "loss": streak.loss})
    if len(rows) < 2:
        return None

    # the actual result sequence (last 60 games) makes streaks/tilt visible
    recent = ctx.games[-60:]
    strip = W.timeline(
        [{"outcome": g.outcome,
          "label": f"{g.date} vs {g.opponent} · {g.outcome}"} for g in recent],
        title=f"Recent form — last {len(recent)} games (oldest → newest)")
    return [strip, W.wdl_barstack(rows, title="Result vs the same-day previous game")]


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
