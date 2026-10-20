"""Opponent-strength stats (aggregate, within the chosen format).

Chess.com PGN headers carry POST-game ratings, so both the per-game rating
change and the strength gap are reconstructed from the chronological
(single-format) game list: your pre-game rating for game i is your post-game
rating from game i-1 (Δ = elo_i − elo_{i-1}), and the opponent's pre-game
rating is your exchange handed back (opp_post + Δ). Chess.com's rapid exchange
is mirrored: checked on games between two downloaded accounts, that estimate
was within 2 points of the opponent's true pre-game rating 99% of the time.

Classifying by the post-game gap instead would invert the answer: a win lowers
the opponent's rating by what you gained, so every win would look like a game
against a weaker player and every loss like one against a stronger player.
"""
from ...registry import metric
from ... import glossary as G
from ... import widgets as W
from ...util import WDL

MAX_CHANGE = 40       # a bigger jump is an adjustment (a fair-play refund), not a game

# (label, low, high) on the pre-game gap = opponent − you, strongest first.
# ±25 matches the steps Chess.com's rating-range setting moves in.
BUCKETS = [
    ("Much stronger (100+ above)", 100, 10 ** 6),
    ("Stronger (25–100 above)", 25, 100),
    ("Level (within ±25)", -25, 25),
    ("Weaker (25–100 below)", -100, -25),
    ("Much weaker (100+ below)", -10 ** 6, -100),
]


def _pct(n, t):
    return f"{round(100 * n / t)}%" if t else "—"


@metric("player", title="By opponent strength", order=30, category="Opponents")
def by_opponent_strength(ctx):
    agg = {label: {"wdl": WDL(), "dsum": 0, "dn": 0, "exp": 0.0, "en": 0}
           for label, _, _ in BUCKETS}
    prev = None
    for g in ctx.games:
        delta = (g.user_elo - prev) if (g.user_elo is not None and prev is not None) else None
        user_pre = prev
        if g.user_elo is not None:
            prev = g.user_elo
        if not (g.user_elo and g.opp_elo):
            continue
        if delta is not None and abs(delta) <= MAX_CHANGE:
            opp_pre = g.opp_elo + delta          # see the module docstring
            gap = opp_pre - user_pre
        elif delta is None:
            opp_pre, gap = None, g.opp_elo - g.user_elo   # first game: post-only fallback
        else:
            continue                                      # an adjustment landed here
        bucket = next(agg[label] for label, lo, hi in BUCKETS if lo <= gap < hi)
        bucket["wdl"].add(g.outcome)
        if opp_pre is not None:
            bucket["dsum"] += delta
            bucket["dn"] += 1
            bucket["exp"] += G.expected_score(user_pre, opp_pre)
            bucket["en"] += 1

    rows = []
    for label, _, _ in BUCKETS:
        b = agg[label]
        w = b["wdl"]
        if not w.total:
            continue
        avg_d = f"{b['dsum'] / b['dn']:+.1f}".replace("-", "−") if b["dn"] else "—"
        exp = f"{100 * b['exp'] / b['en']:.0f}%" if b["en"] else "—"
        rows.append([label, w.total, _pct(w.total, sum(a["wdl"].total for a in agg.values())),
                     w.win, w.draw, w.loss, f"{100 * w.score:.0f}%", exp, avg_d,
                     {"bar": [w.win, w.draw, w.loss]}])
    if not rows:
        return None
    return [W.text("Opponents grouped by their rating against yours before the game. "
                   "Score is wins plus half the draws; expected score is what the two "
                   "ratings predicted. A rating rises only when the score beats the "
                   "expected score, so the last column follows the gap between the two, "
                   "not how strong the opponents were.",
                   guide="score", label="What expected score means"),
            W.table(["Opponent", "Games", "Share", "W", "D", "L", "Score", "Expected score",
                     "Rating change per game", ""], rows)]
