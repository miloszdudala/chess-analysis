"""Time-aware stats: how results and clock habits change under time pressure.

Engine-free — these read only the per-move clocks in the PGN, so they cover the
whole library cheaply. Games without usable clock data are skipped.
"""
from ...registry import metric
from ... import widgets as W
from ...util import WDL
from ...clocks import (
    PRESSURE_BUCKETS, TIME_TROUBLE_FRAC, clock_profile, other_color,
    pressure_bucket,
)


def _fmt_s(sec: float) -> str:
    sec = round(sec)
    return f"{sec}s" if sec < 60 else f"{sec // 60}:{sec % 60:02d}"


def _ordered_rows(buckets: dict) -> list:
    """Bucket WDLs -> wdl_table rows in fixed worst→best order, dropping empties."""
    return [{"label": lbl, "win": buckets[lbl].win,
             "draw": buckets[lbl].draw, "loss": buckets[lbl].loss}
            for _, lbl in PRESSURE_BUCKETS if buckets[lbl].total]


@metric("player", title="Time pressure", order=50, category="Time management")
def time_pressure(ctx):
    """Win/draw/loss bucketed by how low the clock dropped — yours and theirs."""
    you = {lbl: WDL() for _, lbl in PRESSURE_BUCKETS}
    opp = {lbl: WDL() for _, lbl in PRESSURE_BUCKETS}
    seen = False
    for g in ctx.games:
        pp = clock_profile(g, g.color)
        if pp:
            you[pressure_bucket(pp.min_frac)].add(g.outcome)
            seen = True
        op = clock_profile(g, other_color(g.color))
        if op:
            opp[pressure_bucket(op.min_frac)].add(g.outcome)
            seen = True
    if not seen:
        return None
    return [
        W.text("Your results grouped by the lowest fraction of the starting "
               "clock each side reached during the game."),
        W.wdl_table("When your clock got to", _ordered_rows(you)),
        W.wdl_table("When opponent's clock got to", _ordered_rows(opp)),
    ]


@metric("player", title="Clock management", order=51, category="Time management")
def clock_management(ctx):
    """Headline clock habits: time left at the finish, move pace, flag record."""
    you_end, you_frac, you_move = [], [], []
    opp_end, opp_move = [], []
    trouble = nprof = won_on_time = lost_on_time = 0
    for g in ctx.games:
        pp = clock_profile(g, g.color)
        if pp:
            nprof += 1
            you_end.append(pp.end_clock)
            you_frac.append(pp.end_frac)
            you_move.append(pp.avg_move_time)
            if pp.min_frac < TIME_TROUBLE_FRAC:
                trouble += 1
        op = clock_profile(g, other_color(g.color))
        if op:
            opp_end.append(op.end_clock)
            opp_move.append(op.avg_move_time)
        if "time" in g.termination.lower():
            if g.outcome == "win":
                won_on_time += 1
            elif g.outcome == "loss":
                lost_on_time += 1
    if not nprof:
        return None

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    return W.cards([
        W.card(_fmt_s(avg(you_end)), "Your time left at finish",
               sub=f"{100 * avg(you_frac):.0f}% of the clock"),
        W.card(_fmt_s(avg(opp_end)), "Opponent time left at finish"),
        W.card(f"{100 * trouble / nprof:.0f}%", "Games you hit time trouble",
               sub=f"clock dropped below {int(TIME_TROUBLE_FRAC * 100)}%"),
        W.card(f"{avg(you_move):.1f}s", "Your avg move time",
               sub=f"opponent {avg(opp_move):.1f}s"),
        W.card(f"{won_on_time} / {lost_on_time}", "Won / lost on time"),
    ])
