"""The rating-bracket corpus: other players' games, sampled and analysed.

Two views are built on it — Peers (you against players at your rating) and
Brackets (the ladder, band by band). Both are aggregates over `store.samples`,
so neither ever loads the corpus into memory: a bracket statistic is a SQL sum
over indexed integers.

One engine pass over a game yields **two** samples, one per side, because both
players' accuracy is measured in the same positions. That halves the cost and
is why a 1900-vs-2000 game populates two bands at once.
"""
from __future__ import annotations

from .. import store

DEPTH = 10          # see the depth study: unbiased vs d15, ~17x faster
MULTIPV = 1
TIME_CONTROL = "600"
BAND_SIZE = 100

# Phase columns, in the order they are shown.
PHASES = (("op", "Opening"), ("mg", "Middlegame"), ("eg", "Endgame"))

# Every comparison must run at ONE depth. Reading a deeper review-quality
# analysis for your games while the cohort sits at DEPTH would tilt the result
# by about half an accuracy point — the size of the effect being measured.
_AGG = """
  COUNT(*)                            AS n,
  AVG(s.acc)                          AS acc,
  AVG(s.acpl)                         AS acpl,
  AVG(s.plies)                        AS plies,
  AVG(s.op_acc) AS op_acc, AVG(s.mg_acc) AS mg_acc, AVG(s.eg_acc) AS eg_acc,
  100.0*SUM(s.op_bl)/NULLIF(SUM(s.op_n),0) AS op_bl,
  100.0*SUM(s.mg_bl)/NULLIF(SUM(s.mg_n),0) AS mg_bl,
  100.0*SUM(s.eg_bl)/NULLIF(SUM(s.eg_n),0) AS eg_bl,
  100.0*SUM(s.op_mi)/NULLIF(SUM(s.op_n),0) AS op_mi,
  100.0*SUM(s.mg_mi)/NULLIF(SUM(s.mg_n),0) AS mg_mi,
  100.0*SUM(s.eg_mi)/NULLIF(SUM(s.eg_n),0) AS eg_mi,
  100.0*SUM(s.outcome='win')/COUNT(*)  AS winpct,
  100.0*SUM(s.outcome='draw')/COUNT(*) AS drawpct,
  100.0*SUM(s.dec_ply IS NOT NULL)/COUNT(*) AS decisive,
  100.0*SUM(s.dec_held=1)/NULLIF(SUM(s.dec_ply IS NOT NULL),0) AS held
"""


def _one(sql, args):
    row = store.connect().execute(sql, args).fetchone()
    return dict(row) if row and row["n"] else None


def cohort(lo: int, hi: int, depth: int = DEPTH) -> dict | None:
    """Aggregate for every corpus sample whose player was rated in [lo, hi]."""
    return _one(f"SELECT {_AGG} FROM samples s JOIN games g ON g.gid=s.gid "
                "WHERE g.source='corpus' AND s.depth=? AND s.elo BETWEEN ? AND ?",
                (depth, lo, hi))


def mine(user: str, depth: int = DEPTH) -> dict | None:
    """The same aggregate over the games `user` actually played."""
    u = user.lower()
    return _one(f"SELECT {_AGG} FROM samples s JOIN games g ON g.gid=s.gid "
                "WHERE s.depth=? AND ((s.color='white' AND g.white=?) "
                "                  OR (s.color='black' AND g.black=?))",
                (depth, u, u))


def ladder(depth: int = DEPTH, min_samples: int = 30) -> list[dict]:
    """One aggregate row per rating band, weakest first."""
    rows = store.connect().execute(
        f"SELECT s.band AS band, {_AGG} FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.band IS NOT NULL "
        "GROUP BY s.band ORDER BY s.band", (depth,)).fetchall()
    return [dict(r) for r in rows if r["n"] >= min_samples]


def accuracy_histogram(lo: int, hi: int, depth: int = DEPTH,
                       step: int = 5) -> list[tuple[int, int]]:
    """Per-game accuracy distribution for a cohort, in `step`-wide buckets."""
    rows = store.connect().execute(
        "SELECT CAST(s.acc/? AS INT)*? AS b, COUNT(*) FROM samples s "
        "JOIN games g ON g.gid=s.gid WHERE g.source='corpus' AND s.depth=? "
        "AND s.elo BETWEEN ? AND ? GROUP BY b ORDER BY b",
        (step, step, depth, lo, hi)).fetchall()
    return [(r[0], r[1]) for r in rows]


def percentile(value: float, lo: int, hi: int, depth: int = DEPTH) -> int | None:
    """Where `value` falls in the cohort's per-game accuracy distribution."""
    if value is None:
        return None
    row = store.connect().execute(
        "SELECT 100.0*SUM(s.acc < ?)/COUNT(*) FROM samples s "
        "JOIN games g ON g.gid=s.gid WHERE g.source='corpus' AND s.depth=? "
        "AND s.elo BETWEEN ? AND ?", (value, depth, lo, hi)).fetchone()
    return round(row[0]) if row and row[0] is not None else None


def coverage(depth: int = DEPTH) -> list[dict]:
    """Samples held per band — what Expand uses to decide where to spend."""
    rows = store.connect().execute(
        "SELECT s.band, COUNT(*) n FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.band IS NOT NULL "
        "GROUP BY s.band ORDER BY s.band", (depth,)).fetchall()
    return [{"band": r[0], "samples": r[1]} for r in rows]


def totals(depth: int = DEPTH) -> dict:
    c = store.connect()
    return {
        "games": store.count_games("corpus"),
        "samples": c.execute("SELECT COUNT(*) FROM samples s JOIN games g "
                             "ON g.gid=s.gid WHERE g.source='corpus' AND s.depth=?",
                             (depth,)).fetchone()[0],
        "players": c.execute("SELECT COUNT(*) FROM players WHERE taken>0").fetchone()[0],
        "frontier": c.execute("SELECT COUNT(*) FROM frontier").fetchone()[0],
        "pending": c.execute(
            "SELECT COUNT(*) FROM games g LEFT JOIN analysis a "
            "ON a.gid=g.gid AND a.depth=? WHERE a.gid IS NULL", (depth,)).fetchone()[0],
        "depth": depth,
    }
