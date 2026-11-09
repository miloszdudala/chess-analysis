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

*When* is read off the curve. Every rating change is the game's own result
plus whatever adjustment landed on top of it, and the game's share is
predictable: K * (score - expected), with the expected score from the two
ratings and K read from the neighbouring games (it's the same for every game
in a stretch, bar the provisional start). What's left over is the adjustment.
The first game after the cheated one carrying roughly the lost points extra is
where the refund arrived — a win worth 17 among wins worth 9, or a loss that
cost nothing. Without opponent ratings only the second kind is visible: a loss
whose change is >= 0 (or a win whose change is <= 0) is arithmetically
impossible, so it can only be an adjustment. If no such game is found the
refund hasn't landed yet and the correction runs to the end of the series —
but only for a while. Chess.com doesn't refund every game against a closed
account, and a refund missing from games played `REFUND_DAYS` after the ban
was first seen is not coming: that loss stands, uncorrected, exactly as
Chess.com's own rating keeps it.
"""
from __future__ import annotations

import calendar
import time
from statistics import median

# a result whose rating moved the wrong way (or not at all) can only be an
# adjustment landing on top of the game
_WRONG_WAY = {"loss": lambda d: d >= 0, "win": lambda d: d <= 0}
_SCORE = {"win": 1.0, "draw": 0.5, "loss": 0.0}
_K_WINDOW = 5          # games either side whose K sets a game's expected change
_MIN_SURPRISE = 0.15   # |score - expected| below this says too little about K
REFUND_DAYS = 7        # refunds seen so far land within a day or two of the ban


def _epoch(g) -> int:
    """A game's end as unix time, 0 if unknown."""
    try:
        return calendar.timegm(time.strptime(getattr(g, "sort_key", ""),
                                             "%Y.%m.%d %H:%M:%S"))
    except ValueError:
        return 0


def _series(games):
    """Games with a usable rating, grouped by time class (ratings are per
    format — a blitz loss says nothing about the rapid curve)."""
    out: dict[str, list] = {}
    for g in games:
        if g.user_elo is not None:
            out.setdefault(g.time_class, []).append(g)
    return out


def _surprise(series, j):
    """score - expected for game j, or None without an opponent rating."""
    opp = getattr(series[j], "opp_elo", None)
    if not opp:
        return None
    before = series[j - 1].user_elo
    expected = 1 / (1 + 10 ** ((opp - before) / 400))
    return _SCORE[series[j].outcome] - expected


def _residuals(series):
    """Per game, the rating change its result doesn't explain (None where it
    can't be modelled). K is the median implied by the neighbours, so a
    refund-carrying game never sets its own yardstick."""
    delta = [None] + [series[j].user_elo - series[j - 1].user_elo
                      for j in range(1, len(series))]
    surprise = [None] + [_surprise(series, j) for j in range(1, len(series))]
    implied = [delta[j] / surprise[j]
               if surprise[j] is not None and abs(surprise[j]) >= _MIN_SURPRISE
               else None for j in range(len(series))]
    out = []
    for j in range(len(series)):
        ks = [implied[i] for i in range(max(1, j - _K_WINDOW),
                                        min(len(series), j + _K_WINDOW + 1))
              if i != j and implied[i] is not None]
        if surprise[j] is None or not ks:
            out.append(None)
        else:
            out.append(delta[j] - median(ks) * surprise[j])
    return out


def _refund_index(series, start, back, left):
    """Index of the game the refund of `back` points landed on, or None if it
    hasn't yet. `left` is each game's still-unexplained residual; a claimed
    refund is taken out of it so two refunds can't both land on one jump."""
    tol = max(3, 0.4 * back)
    for j in range(start + 1, len(series)):
        if left[j] is not None:
            if left[j] >= back - tol:
                left[j] -= back
                return j
            continue
        delta = series[j].user_elo - series[j - 1].user_elo
        impossible = _WRONG_WAY.get(series[j].outcome)
        if impossible and impossible(delta):
            return j
    return None


def corrections(games, cheated_ids, banned_at=None) -> dict[str, int]:
    """{game_id: points to add to that game's rating}, for cheated losses.

    `games` must be the full chronological history — the cheated games
    included, since the curve is only readable with every sample present.
    `banned_at` is {game_id: unix time the ban was first seen}; without it a
    refund that never shows up is assumed to be still on its way.
    """
    banned_at = banned_at or {}
    fix: dict[str, int] = {}
    for series in _series(games).values():
        left = _residuals(series)
        for i, g in enumerate(series):
            if i == 0 or str(g.game_id) not in cheated_ids:
                continue
            lost = g.user_elo - series[i - 1].user_elo
            if lost >= 0:
                continue                  # a win or draw: the gain is kept
            back = -lost
            end = _refund_index(series, i, back, left)
            seen = banned_at.get(str(g.game_id))
            if end is None and seen and _epoch(series[-1]) > seen + REFUND_DAYS * 86400:
                continue                  # played on well past the ban: no refund
            # from the cheated game itself (the refund undoes its own drop too)
            # up to, but not including, the game the refund landed on — from
            # there the points are already back in the recorded rating
            for j in range(i, end if end is not None else len(series)):
                fix[str(series[j].game_id)] = fix.get(str(series[j].game_id), 0) + back
    return fix


def apply(games, cheated_ids, banned_at=None) -> None:
    """Rebase `user_elo` in place over the whole history, keeping the rating as
    Chess.com recorded it in `user_elo_raw`."""
    fix = corrections(games, cheated_ids, banned_at)
    for g in games:
        g.user_elo_raw = g.user_elo
        if g.user_elo is not None:
            g.user_elo += fix.get(str(g.game_id), 0)
