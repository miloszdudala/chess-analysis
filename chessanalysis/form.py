"""Form tracking: FIDE performance ratings over sliding windows of games.

Performance rating answers "how strongly did I actually play in this stretch?"
independently of the Elo the rating system happened to show. It uses the
official FIDE method (handbook 8.1a): the average rating of the opposition
plus a conversion of the score percentage into a rating difference (dp).

All functions take chronological Game lists and only count *rated* games
(those with a known opponent Elo); the rest are skipped, not zeroed.
"""
from __future__ import annotations

# FIDE dp table (handbook 8.1a): score fraction p -> rating difference.
# Index = round(100 * p) - 50 for p >= 0.50; mirrored negative below 0.50.
_DP = [
    0, 7, 14, 21, 29, 36, 43, 50, 57, 65,          # .50 - .59
    72, 80, 87, 95, 102, 110, 117, 125, 133, 141,   # .60 - .69
    149, 158, 166, 175, 184, 193, 202, 211, 220, 230,  # .70 - .79
    240, 251, 262, 273, 284, 296, 309, 322, 336, 351,  # .80 - .89
    366, 383, 401, 422, 444, 470, 501, 538, 589, 677,  # .90 - .99
    800,                                               # 1.00
]

MIN_RATED = 5          # fewer rated games than this -> no honest performance
SCORE = {"win": 1.0, "draw": 0.5, "loss": 0.0}


def dp(p: float) -> int:
    """FIDE rating-difference for a score fraction p in [0, 1]."""
    i = round(100 * p)
    return _DP[i - 50] if i >= 50 else -_DP[50 - i]


def rated(games) -> list:
    """The games that count toward performance: known opponent Elo + a result.

    Shared by every calculation here AND by callers that need indices into the
    same list (e.g. mapping a rolling-chart point back to its window's games).
    """
    return [g for g in games if g.opp_elo and g.outcome in SCORE]


def performance(games) -> dict | None:
    """FIDE performance over `games`: avg opponent rating + dp(score%).

    Returns {"perf", "n", "score", "avg_opp", "wdl"} over the rated games in
    the slice, or None when there are fewer than MIN_RATED of them.
    """
    rated_games = rated(games)
    if len(rated_games) < MIN_RATED:
        return None
    pts = sum(SCORE[g.outcome] for g in rated_games)
    p = pts / len(rated_games)
    avg_opp = sum(g.opp_elo for g in rated_games) / len(rated_games)
    wdl = {o: sum(1 for g in rated_games if g.outcome == o)
           for o in ("win", "draw", "loss")}
    return {"perf": round(avg_opp + dp(p)), "n": len(rated_games),
            "score": round(p, 3), "avg_opp": round(avg_opp), "wdl": wdl}


def rolling(games, window: int) -> list[dict]:
    """Rolling performance series: one point per game once a full window of
    rated games is available (plotted at the window's end).

    Each point carries the window's index range into `rated(games)` — "i0"
    (inclusive) to "i1" (exclusive) — so a UI can map a clicked point back to
    the exact games behind it.
    """
    rated_games = rated(games)
    pts = []
    for i in range(window, len(rated_games) + 1):
        perf = performance(rated_games[i - window:i])
        if perf:
            pts.append({"x": rated_games[i - 1].date, "y": perf["perf"],
                        "i0": i - window, "i1": i})
    return pts


def peaks(games, window: int, k: int = 3) -> list[dict]:
    """The k best non-overlapping `window`-game stretches, best first.

    Greedy: take the highest-performance window, exclude anything overlapping
    it, repeat. Each entry carries perf/score/date range for display.
    """
    return _extreme_windows(games, window, k, best=True)


def slump(games, window: int) -> dict | None:
    """The single worst `window`-game stretch (the mirror of peaks)."""
    worst = _extreme_windows(games, window, 1, best=False)
    return worst[0] if worst else None


def _extreme_windows(games, window, k, best):
    rated_games = rated(games)
    if len(rated_games) < window:
        return []
    wins = []
    for i in range(window, len(rated_games) + 1):
        perf = performance(rated_games[i - window:i])
        if perf:
            perf["start"] = rated_games[i - window].date
            perf["end"] = rated_games[i - 1].date
            wins.append((i - window, i, perf))
    wins.sort(key=lambda w: w[2]["perf"], reverse=best)
    picked, taken = [], []
    for lo, hi, perf in wins:
        if any(lo < t_hi and hi > t_lo for t_lo, t_hi in taken):
            continue
        picked.append(perf)
        taken.append((lo, hi))
        if len(picked) == k:
            break
    return picked


def streak(games) -> dict | None:
    """The trailing run of identical outcomes, e.g. {"outcome": "win", "n": 3}."""
    run = 0
    outcome = None
    for g in reversed(games):
        if g.outcome not in SCORE:
            continue
        if outcome is None:
            outcome = g.outcome
        if g.outcome != outcome:
            break
        run += 1
    return {"outcome": outcome, "n": run} if run else None
