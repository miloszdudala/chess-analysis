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
  SUM(s.op_n + s.mg_n + s.eg_n)       AS moves,
  SUM(s.blun)                         AS blunders,
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
  SUM(s.outcome='win') AS wins, SUM(s.outcome='draw') AS draws,
  SUM(s.outcome='loss') AS losses,
  100.0*SUM(s.outcome='win')/COUNT(*)  AS winpct,
  100.0*SUM(s.dec_held=1)/NULLIF(SUM(s.dec_ply IS NOT NULL),0) AS held,
  -- how the game ended, relative to who first got a winning position.
  -- `dec_side` is the side the eval first crossed +/-2.00 for; comparing it to
  -- this sample's own colour separates converting from throwing away.
  SUM(s.outcome='win'  AND s.dec_side=s.color)  AS converted,
  SUM(s.outcome='loss' AND s.dec_side=s.color)  AS threw,
  SUM(s.outcome='win'  AND s.dec_side IS NOT NULL AND s.dec_side<>s.color) AS comeback,
  SUM(s.outcome='loss' AND s.dec_side IS NOT NULL AND s.dec_side<>s.color) AS outplayed,
  -- when it happened: the phase of the position where the eval first crossed,
  -- on the same per-game boundaries (phases.py) the accuracy split uses
  AVG(CASE WHEN s.dec_ply IS NOT NULL THEN (s.dec_ply+1)/2 END) AS dec_move,
  SUM(s.dec_ply < COALESCE(s.mg_ply, s.eg_ply, 100000)) AS dec_op,
  SUM(s.dec_ply >= s.mg_ply AND (s.eg_ply IS NULL OR s.dec_ply < s.eg_ply)) AS dec_mg,
  SUM(s.dec_ply >= s.eg_ply) AS dec_eg
"""


def excluded_ids(user: str) -> list[str]:
    """Your games that every other statistic drops: flagged, or against an
    account Chess.com has since closed for cheating.

    `load_games` applies this for anything that goes through it. The aggregates
    here read `samples` directly for speed, so they have to apply it too — or
    the Peers tab counts games the Player report does not.
    """
    from .. import fairplay, overrides
    from ..model import load_games

    games = load_games(user, include_flagged=True)
    return sorted(overrides.flagged_ids() | fairplay.cheated_ids(games))


def _skip_clause(user: str, alias: str = "s"):
    """(sql fragment, params) excluding those games. Usually a handful."""
    bad = excluded_ids(user)
    if not bad:
        return "", []
    return f" AND {alias}.gid NOT IN ({','.join('?' * len(bad))})", bad


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
    skip, args = _skip_clause(user)
    return _one(f"SELECT {_AGG} FROM samples s JOIN games g ON g.gid=s.gid "
                "WHERE s.depth=? AND ((s.color='white' AND g.white=?) "
                "                  OR (s.color='black' AND g.black=?))" + skip,
                (depth, u, u, *args))


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


def accuracy_values(lo: int, hi: int, depth: int = DEPTH) -> list[float]:
    """Every cohort game's own accuracy — the distribution, not its average."""
    return [r[0] for r in store.connect().execute(
        "SELECT s.acc FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.elo BETWEEN ? AND ? "
        "AND s.acc IS NOT NULL", (depth, lo, hi))]


def my_accuracy_values(user: str, depth: int = DEPTH) -> list[float]:
    u = user.lower()
    skip, args = _skip_clause(user)
    return [r[0] for r in store.connect().execute(
        "SELECT s.acc FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE s.depth=? AND s.acc IS NOT NULL "
        "AND ((s.color='white' AND g.white=?) OR (s.color='black' AND g.black=?))"
        + skip, (depth, u, u, *args))]


def quantiles(values: list[float], qs=(10, 25, 50, 75, 90)) -> dict:
    """Percentile points of a sample, by nearest rank."""
    if not values:
        return {}
    xs = sorted(values)
    return {q: xs[min(len(xs) - 1, max(0, round(q / 100 * len(xs)) - 1))] for q in qs}


def percentile(value: float, lo: int, hi: int, depth: int = DEPTH) -> int | None:
    """Where `value` falls in the cohort's per-game accuracy distribution."""
    if value is None:
        return None
    row = store.connect().execute(
        "SELECT 100.0*SUM(s.acc < ?)/COUNT(*) FROM samples s "
        "JOIN games g ON g.gid=s.gid WHERE g.source='corpus' AND s.depth=? "
        "AND s.elo BETWEEN ? AND ?", (value, depth, lo, hi)).fetchone()
    return round(row[0]) if row and row[0] is not None else None


def player_percentile(value: float, lo: int, hi: int, depth: int = DEPTH,
                      min_games: int = 5) -> tuple[int, int] | None:
    """Where an average sits among the cohort's *player* averages.

    Comparing your average against the spread of individual games is not a
    like-for-like question: a single game swings far more than an average of
    many, so any average lands mid-range whatever it is. Averaging each player
    first puts both sides on the same footing.
    """
    if value is None:
        return None
    rows = store.connect().execute(
        "SELECT AVG(s.acc) a FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.elo BETWEEN ? AND ? "
        "GROUP BY CASE WHEN s.color='white' THEN g.white ELSE g.black END "
        "HAVING COUNT(*) >= ?", (depth, lo, hi, min_games)).fetchall()
    avgs = [r[0] for r in rows if r[0] is not None]
    if len(avgs) < 20:
        return None
    return round(100 * sum(a < value for a in avgs) / len(avgs)), len(avgs)


def pending_own(user: str, depth: int = DEPTH) -> list:
    """Your games with no analysis at the corpus depth.

    New games are analysed at *review* depth by the pre-warm, which the Peers
    tab cannot use — mixing depths would bias every comparison on it. Until
    they are analysed here too they are simply absent from these statistics,
    which is worse than slow, so the tab tops them up itself.
    """
    from ..model import load_games

    return [g for g in load_games(user)
            if not store.has_analysis(g.game_id, depth)]


def my_pairs(user: str, depth: int = DEPTH):
    """(Game, GameAnalysis) for your own games, at the corpus depth.

    Same engine and depth as the cohort — a review-depth analysis would tilt
    every comparison here by about half an accuracy point.
    """
    from ..enrich import engine as eng
    from ..model import load_games

    out = []
    for g in load_games(user):
        raw = store.load_analysis(g.game_id, depth)
        if not raw or not raw.get("evals"):
            continue
        raw = _rehydrate(raw, g.pgn)
        if raw:
            out.append((g, eng._derive(raw, depth, "corpus")))
    return out


def coverage(depth: int = DEPTH) -> list[dict]:
    """Samples held per band — what Expand uses to decide where to spend."""
    rows = store.connect().execute(
        "SELECT s.band, COUNT(*) n FROM samples s JOIN games g ON g.gid=s.gid "
        "WHERE g.source='corpus' AND s.depth=? AND s.band IS NOT NULL "
        "GROUP BY s.band ORDER BY s.band", (depth,)).fetchall()
    return [{"band": r[0], "samples": r[1]} for r in rows]


def colour_split(depth: int = DEPTH) -> list[dict]:
    """White / draw / black, per band and overall — counted once per GAME.

    Everything else here counts samples (both sides), which would make this
    particular question meaningless: every white win is also a black loss.
    """
    rows = store.connect().execute(
        "SELECT band, SUM(result='1-0'), SUM(result='1/2-1/2'), SUM(result='0-1'), "
        "COUNT(*) FROM games WHERE source='corpus' AND band IS NOT NULL "
        "GROUP BY band ORDER BY band").fetchall()
    return [{"band": r[0], "white": r[1], "draw": r[2], "black": r[3], "games": r[4]}
            for r in rows]


def _rehydrate(raw: dict, pgn_text: str) -> dict | None:
    """Fill in whatever a stored analysis is missing, from the PGN alone.

    Analyses banked by the earliest corpus pass hold only the eval array. SAN,
    UCI and FENs are all recoverable by replaying the moves — no engine — which
    is the point of keeping the PGN beside the evals. Only `best_uci` is truly
    engine-only, so `best_san` comes back empty and the move-by-move commentary
    loses its "better was ..." clause; every number is unaffected.
    """
    import io

    import chess
    import chess.pgn

    if raw.get("moves_san") and raw.get("fens"):
        return raw
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None
    board = game.board()
    san, uci, fens = [], [], []
    for mv in game.mainline_moves():
        fens.append(board.fen())
        san.append(board.san(mv))
        uci.append(mv.uci())
        board.push(mv)
    fens.append(board.fen())
    if len(raw["evals"]) != len(san) + 1:
        return None                       # evals and moves disagree — skip it
    return {**raw, "moves_san": san, "moves_uci": uci, "fens": fens,
            "best_uci": raw.get("best_uci") or [""] * len(san),
            "top_moves": raw.get("top_moves") or []}


def pairs(lo: int, hi: int, depth: int = DEPTH, limit: int = 400):
    """(Game, GameAnalysis) for corpus games, bound to the in-range player.

    This is what lets the player-report machinery — `diagnosis.diagnose`,
    `insights`, `weaknesses` — run over the corpus unchanged: they take exactly
    this shape. Nothing is recomputed, because the corpus pass stored the full
    raw engine output, so a GameAnalysis is rebuilt by `_derive` off the disk.
    Sampled at random and capped, since these are per-move analyses and holding
    every one of them at once is the only part of this that costs real memory.
    """
    from ..enrich import engine as eng
    from ..model import bind, parse_pgn_text

    rows = store.connect().execute(
        "SELECT g.gid, g.pgn, g.white, g.black, g.welo, g.belo FROM games g "
        "JOIN analysis a ON a.gid=g.gid AND a.depth=? WHERE g.source='corpus' "
        "AND (g.welo BETWEEN ? AND ? OR g.belo BETWEEN ? AND ?) "
        "ORDER BY RANDOM() LIMIT ?", (depth, lo, hi, lo, hi, limit)).fetchall()
    out = []
    for r in rows:
        raw = store.load_analysis(r["gid"], depth)
        if not raw or not raw.get("evals"):
            continue
        pgn_text = store.unpack_pgn(r["pgn"])
        raw = _rehydrate(raw, pgn_text)
        if raw is None:
            continue
        parsed = parse_pgn_text(pgn_text)
        if not parsed:
            continue
        who = r["white"] if (r["welo"] is not None and lo <= r["welo"] <= hi) else r["black"]
        g = bind(parsed[0], who)
        if g is None:
            continue
        out.append((g, eng._derive(raw, depth, "corpus")))
    return out


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
            "ON a.gid=g.gid AND a.depth=? WHERE a.gid IS NULL AND g.source='corpus'",
            (depth,)).fetchone()[0],
        "depth": depth,
    }
