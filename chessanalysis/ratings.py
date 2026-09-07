"""Undoing a cheated game's effect on the rating curve.

Chess.com PGN headers carry the rating *after* each game, so a series of games
in one time class is a rating curve sampled per game. When an opponent is later
closed for cheating, Chess.com gives back the points that game cost — but not
at the time it was played: the refund lands days later, silently, as a jump in
the curve. Left alone that produces two artefacts in every rating stat: a dip
that shouldn't be there, then a jump that shouldn't be there either.

`correct` removes both. It adds the lost points back over exactly the stretch
between the cheated game and the refund, leaving the curve continuous and every
rating change attributable to a real game.

Two things make the correction well defined without the player telling us:

*How much* is model-free — a game's cost is the drop it produced, and the
refund restores precisely that. Only games that *cost* points are refunded: a
win or a draw against someone later banned keeps its gain, so those get no
correction at all.

*When* is model-free too. A loss always lowers your rating and a win always
raises it, so a loss whose change is >= 0 (or a win whose change is <= 0) is
arithmetically impossible — the only thing that can produce one is an
adjustment landing on top of that game. The first such game after the cheated
one is where the refund arrived. If none is found the refund hasn't landed yet
and the correction simply runs to the end of the series.
"""
from __future__ import annotations

# a result whose rating moved the wrong way (or not at all) can only be an
# adjustment landing on top of the game
_WRONG_WAY = {"loss": lambda d: d >= 0, "win": lambda d: d <= 0}


def _series(games):
    """Games with a usable rating, grouped by time class (ratings are per
    format — a blitz loss says nothing about the rapid curve)."""
    out: dict[str, list] = {}
    for g in games:
        if g.user_elo is not None:
            out.setdefault(g.time_class, []).append(g)
    return out


def _refund_index(series, start):
    """Index of the game the refund landed on, or None if it hasn't yet."""
    for j in range(start + 1, len(series)):
        delta = series[j].user_elo - series[j - 1].user_elo
        impossible = _WRONG_WAY.get(series[j].outcome)
        if impossible and impossible(delta):
            return j
    return None


def corrections(games, cheated_ids) -> dict[str, int]:
    """{game_id: points to add to that game's rating}, for cheated losses.

    `games` must be the full chronological history — the cheated games
    included, since the curve is only readable with every sample present.
    """
    fix: dict[str, int] = {}
    for series in _series(games).values():
        for i, g in enumerate(series):
            if i == 0 or str(g.game_id) not in cheated_ids:
                continue
            lost = g.user_elo - series[i - 1].user_elo
            if lost >= 0:
                continue                  # a win or draw: the gain is kept
            back = -lost
            end = _refund_index(series, i)
            # from the cheated game itself (the refund undoes its own drop too)
            # up to, but not including, the game the refund landed on — from
            # there the points are already back in the recorded rating
            for j in range(i, end if end is not None else len(series)):
                fix[str(series[j].game_id)] = fix.get(str(series[j].game_id), 0) + back
    return fix


def apply(games, cheated_ids) -> None:
    """Rebase `user_elo` in place over the whole history, keeping the rating as
    Chess.com recorded it in `user_elo_raw`."""
    fix = corrections(games, cheated_ids)
    for g in games:
        g.user_elo_raw = g.user_elo
        if g.user_elo is not None:
            g.user_elo += fix.get(str(g.game_id), 0)
