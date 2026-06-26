"""Clock / time-pressure helpers derived from per-move %clk data.

A game's PGN carries the seconds left on each mover's clock after their move.
From that, per side, we reconstruct how low the clock got, how much was left at
the finish, and how long each move took — the raw material for time-aware stats.

Games without a numeric time control (e.g. daily/correspondence) or without any
clock annotations yield no profile and are simply skipped by callers.
"""
from __future__ import annotations

from dataclasses import dataclass


def parse_time_control(tc: str):
    """'600' -> (600, 0); '180+2' -> (180, 2); daily/empty/odd -> None."""
    if not tc or "/" in tc:                 # '/' marks daily (e.g. '1/259200')
        return None
    base, _, inc = tc.partition("+")
    try:
        b, i = int(base), int(inc or 0)
    except ValueError:
        return None
    return (b, i) if b > 0 else None


def other_color(color: str) -> str:
    return "black" if color == "white" else "white"


@dataclass
class ClockProfile:
    """One side's clock story through a game."""
    base: int                  # starting seconds
    inc: int                   # increment per move
    clocks: list               # seconds left after each of this side's moves
    move_times: list           # seconds spent on each move

    @property
    def min_clock(self) -> float:
        return min(self.clocks)

    @property
    def min_frac(self) -> float:
        return self.min_clock / self.base

    @property
    def end_clock(self) -> float:
        return self.clocks[-1]

    @property
    def end_frac(self) -> float:
        return self.end_clock / self.base

    @property
    def avg_move_time(self) -> float:
        return sum(self.move_times) / len(self.move_times) if self.move_times else 0.0


def clock_profile(game, color: str):
    """Build a ClockProfile for `color` in `game`, or None if unavailable."""
    tc = parse_time_control(game.time_control)
    if tc is None:
        return None
    clocks = [m.clock for m in game.moves
              if m.color == color and m.clock is not None]
    if not clocks:
        return None
    base, inc = tc
    times, prev = [], float(base)
    for c in clocks:
        # clock_after = clock_before - spent + inc  =>  spent = before - after + inc
        times.append(max(0.0, prev - c + inc))
        prev = c
    return ClockProfile(base=base, inc=inc, clocks=clocks, move_times=times)


# severity buckets by the lowest fraction of the starting clock a side reached.
# kept in worst→best order so tables read top-down by pressure.
PRESSURE_BUCKETS = [
    (0.10, "Severe (<10% left)"),
    (0.25, "Time trouble (10–25%)"),
    (0.50, "Some pressure (25–50%)"),
    (float("inf"), "Comfortable (>50%)"),
]
TIME_TROUBLE_FRAC = 0.10       # threshold for "reached time trouble"


def pressure_bucket(frac: float) -> str:
    for thr, label in PRESSURE_BUCKETS:
        if frac < thr:
            return label
    return PRESSURE_BUCKETS[-1][1]
