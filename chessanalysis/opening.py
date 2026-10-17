"""Opening strength and repertoire, measured so that they can be compared.

**Why results are not compared.** Inside a rating band everyone scores about
50% — that is what a rating is. A player there with better openings has to be
worse somewhere else, so "do the players who know more theory win more?"
answers itself, and a table of results by opening knowledge measures nothing.
Three things can be measured instead.

**What the opening hands you, in points.** Every move changes the engine's win
chance. Summed over moves 1–12, what you lose on your own moves are your
opening errors, what your opponents lose is what your openings get out of
them, and the difference is the opening's net contribution. The win chance is
the engine's, so it is checked against what actually happened: at this level a
point of win chance at move 12 is worth about 0.8 of a point of score, because
a whole game is still to be played. The same holds inside one player's games,
so it is not the band effect in disguise. Near 50%, one point of score is about
7 Elo.

**How much players really differ.** Ten games are few, and most of what
separates two players' ten-game averages is luck. Each player's games are split
into two halves and only what the halves agree on — their covariance — counts
as a real difference; with the rating trend taken out, that is the spread
between players *at the same rating*.

**What theory is worth.** Comparing one player with another brings the band
problem back. Comparing a player with themselves — the games where the opponent
left the book first against the games where they did — holds their whole skill
profile fixed.

**Repertoire** is read from the moves only you choose. At this level exact
positions stop repeating by move 7 — the opponents see to that — so a
repertoire "to move 10" cannot be read off positions. What you control can be:
your own first ten moves, compared between games where the opponent made the
same first move. System players (a London, a fixed Closed Sicilian setup) score
around 80% on it; players who fix only their first moves score around 35%.
"""
from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from itertools import combinations

from . import book

CHECK = 24            # plies: the opening ends after move 12, as everywhere else
MID = 64              # ...and the middlegame after move 32
CLAMP = 1000          # centipawns; keeps a mate score from swamping an average
WINDOW = 10           # games per repertoire window — all a corpus player holds
REP_MOVES = 10        # own moves compared for the repertoire
MIN_GAMES = 8         # corpus games before a player counts as a player
MAINSTREAM = 0.50     # the commonest families covering this share of games
NICHE = 0.005         # families under this share of games
BOOT = 400            # bootstrap resamples behind every interval
ELO_PER_POINT = 400 / (math.log(10) * 0.25) / 100   # ≈ 6.95, near 50%

_SQ = re.compile(r"[a-h][1-8]")


def _norm(san: str) -> str:
    """'Nbxd2+' -> 'Nd2', 'exd5' -> 'Pd5'. A move as a choice: which piece goes
    where. Captures and checks are the position's doing, not the repertoire's."""
    if san.startswith("O-O"):
        return san.rstrip("+#")
    squares = _SQ.findall(san)
    piece = san[0] if san[0] in "NBRQK" else "P"
    return piece + squares[-1] if squares else san


def _clock_used(game, own_moves, n: int = 12):
    """Seconds spent on your first `n` moves, or None (no clocks, daily, short)."""
    tc = game.time_control
    if "/" in tc or len(own_moves) < n or own_moves[n - 1].clock is None:
        return None
    base, _, inc = tc.partition("+")
    try:
        base, inc = int(base), int(inc or 0)
    except ValueError:
        return None
    return base + inc * n - own_moves[n - 1].clock


def record(game, color: str, evals: list[int] | None, player: str = "",
           elo: int | None = None) -> dict:
    """One side of one game: everything the opening statistics need.

    `evals` is the white-POV engine array (plies + 1 long) or None; without it
    the record keeps the book, clock and repertoire facts but no points.
    """
    from .enrich.engine import win_prob

    w = book.walk(game)
    n = len(game.moves)
    sign = 1 if color == "white" else -1
    res = {"1-0": 1.0, "0-1": 0.0}.get(game.h("Result"), 0.5)
    own_moves = [m for m in game.moves if m.color == color]
    rec = {
        "gid": str(game.game_id), "color": color, "player": player, "elo": elo,
        "sort_key": game.sort_key, "family": w.family, "name": w.name,
        "result": res if color == "white" else 1 - res, "plies": n,
        "book": w.book_moves(color), "left": w.left_by == color,
        "opp_left": w.left_by is not None and w.left_by != color,
        "first": own_moves[0].san if own_moves else None,
        "moves": frozenset(_norm(m.san) for m in own_moves[:REP_MOVES]),
        "opp_first": (game.moves[1].san if color == "white" else game.moves[0].san)
                     if n > 1 else None,
        "pawns": w.pawns, "clock12": _clock_used(game, own_moves),
        "cost": None, "wp24": None, "wp64": None,
        "own_op": None, "opp_op": None, "own_rest": None, "rest_moves": 0,
    }
    if not evals or len(evals) != n + 1:
        return rec
    cp = [max(-CLAMP, min(CLAMP, e)) for e in evals]
    wp = [win_prob(sign * e) for e in cp]
    mine = [(i % 2 == 0) == (color == "white") for i in range(n)]
    rec["own_op"] = sum(wp[i] - wp[i + 1] for i in range(min(CHECK, n)) if mine[i])
    rec["opp_op"] = sum(wp[i + 1] - wp[i] for i in range(min(CHECK, n)) if not mine[i])
    rest = [wp[i] - wp[i + 1] for i in range(CHECK, n) if mine[i]]
    rec["own_rest"], rec["rest_moves"] = sum(rest), len(rest)
    rec["wp24"], rec["wp64"] = wp[min(CHECK, n)], wp[min(MID, n)]
    if rec["left"]:
        i = w.plies                       # the deviating move's index
        rec["cost"] = sign * (cp[i] - cp[i + 1])
    return rec


_CORPUS: dict = {}


def corpus_records(depth: int) -> list[dict]:
    """Both sides of every analysed corpus game. Cached per depth until the
    corpus grows, since rebuilding means reading every stored analysis."""
    from . import store
    from .model import parse_pgn_text

    c = store.connect()
    n = c.execute("SELECT COUNT(*) FROM analysis a JOIN games g ON g.gid=a.gid "
                  "WHERE g.source='corpus' AND a.depth=?", (depth,)).fetchone()[0]
    hit = _CORPUS.get(depth)
    if hit and hit[0] == n:
        return hit[1]
    out = []
    rows = c.execute("SELECT g.gid, g.pgn, g.white, g.black, g.welo, g.belo "
                     "FROM games g JOIN analysis a ON a.gid=g.gid AND a.depth=? "
                     "WHERE g.source='corpus'", (depth,)).fetchall()
    for r in rows:
        parsed = parse_pgn_text(store.unpack_pgn(r["pgn"]))
        if not parsed:
            continue
        evals = (store.load_analysis(r["gid"], depth) or {}).get("evals")
        out.append(record(parsed[0], "white", evals, r["white"], r["welo"]))
        out.append(record(parsed[0], "black", evals, r["black"], r["belo"]))
    _CORPUS[depth] = (n, out)
    _MEMO.clear()
    return out


def own_records(user: str, depth: int) -> list[dict]:
    """Your side of every game that counts (flagged and cheated ones dropped),
    with evals from the same depth as the corpus."""
    from . import store
    from .model import load_games

    out = []
    for g in load_games(user):
        evals = (store.load_analysis(g.game_id, depth) or {}).get("evals")
        out.append(record(g, g.color, evals, g.user, g.user_elo))
    return out


_MEMO: dict = {}


def _memo(name, corpus, fn):
    """Corpus-wide statistics are the same for every page until the corpus
    grows; the bootstraps behind them are not free, so keep them."""
    key = (name, id(corpus), len(corpus))
    hit = _MEMO.get(key)
    if hit is None or hit[0] is not corpus:     # held, so the id cannot be reused
        _MEMO[key] = hit = (corpus, fn())
    return hit[1]


# --- small statistics ------------------------------------------------------------

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _cov(u, v):
    n = len(u)
    mu, mv = sum(u) / n, sum(v) / n
    return sum((a - mu) * (b - mv) for a, b in zip(u, v)) / (n - 1)


def _slope(pairs):
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    return sum((x - mx) * (y - my) for x, y in pairs) / sxx if sxx else None


def mean_ci(xs) -> tuple[float, float] | None:
    """Mean and the half-width of its 95% interval."""
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    return m, 1.96 * sd / math.sqrt(len(xs))


def _interval(values) -> tuple[float, float]:
    xs = sorted(values)
    return xs[int(0.025 * len(xs))], xs[min(len(xs) - 1, int(0.975 * len(xs)))]


def players(corpus: list[dict]) -> list[list[dict]]:
    """Each corpus player with enough games, their games in order."""
    by = defaultdict(list)
    for r in corpus:
        by[r["player"]].append(r)
    return [sorted(v, key=lambda r: r["sort_key"]) for v in by.values()
            if len(v) >= MIN_GAMES]


def popularity(corpus: list[dict]) -> dict:
    """Family -> "Mainstream" | "Uncommon" | "Niche", by share of corpus games.

    Mainstream is the handful of families that between them make up half of
    all games; niche is anything under half a percent; the rest is uncommon.
    """
    games = Counter(r["family"] for r in corpus if r["color"] == "white")
    total = sum(games.values()) or 1
    out, cum = {}, 0
    for fam, n in games.most_common():
        out[fam] = ("Mainstream" if cum < MAINSTREAM * total else
                    "Niche" if n / total < NICHE else "Uncommon")
        cum += n
    return out


def bucket_of(pop: dict, family: str) -> str:
    return pop.get(family, "Niche")


# --- points: calibration and the opening's share of the result -------------------

def calibration(corpus: list[dict]) -> dict:
    """How engine win chance turns into score at this level.

    For moves 12 and 32: the slope of the actual score on the engine's win
    chance, among games still being played, colour-centred — pooled, and
    within the same player's games (so that the band effect, better openings
    meaning a worse rest of the game, cannot be what flattens it). Plus the
    colour averages the opening's share of the result is measured against.
    """
    def build():
        cal = {"k": {}, "mw": {}, "mr": {}}
        scored = [r for r in corpus if r["wp24"] is not None]
        for t, key in ((CHECK, "wp24"), (MID, "wp64")):
            run = [r for r in scored if r["plies"] > t]
            mw = {c: _mean([r[key] for r in run if r["color"] == c]) for c in ("white", "black")}
            mr = {c: _mean([100 * r["result"] for r in run if r["color"] == c])
                  for c in ("white", "black")}
            cal["k"][t] = _slope([(r[key] - mw[r["color"]], 100 * r["result"] - mr[r["color"]])
                                  for r in run])
            cal["mw"][t], cal["mr"][t] = mw, mr
        within = []
        for recs in players(scored):
            run = [r for r in recs if r["plies"] > CHECK]
            if len(run) < 3:
                continue
            xs = [r["wp24"] - cal["mw"][CHECK][r["color"]] for r in run]
            ys = [100 * r["result"] - cal["mr"][CHECK][r["color"]] for r in run]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            within += [(x - mx, y - my) for x, y in zip(xs, ys)]
        cal["k_within"] = _slope(within) if within else None
        raw = [(_ledger_raw(r, cal), r["color"]) for r in scored]
        cal["base"] = {k: {c: _mean([v[k] for v, col in raw if col == c])
                           for c in ("white", "black")}
                       for k in ("op", "mg", "rest", "result")}
        return cal
    return _memo("calibration", corpus, build)


def _checkpoint(rec, t, cal):
    """Expected score (points) at ply t, or the result if the game was over."""
    if rec["plies"] <= t:
        return 100 * rec["result"]
    wp = rec["wp24"] if t == CHECK else rec["wp64"]
    c = rec["color"]
    return cal["mr"][t][c] + cal["k"][t] * (wp - cal["mw"][t][c])


def _ledger_raw(rec, cal):
    x24, x64 = _checkpoint(rec, CHECK, cal), _checkpoint(rec, MID, cal)
    return {"op": x24, "mg": x64 - x24, "rest": 100 * rec["result"] - x64,
            "result": 100 * rec["result"]}


def ledger(rec, cal) -> dict | None:
    """Score points this game gained or lost against its colour's average, by
    stretch: the opening (to move 12), moves 13–32, and everything after
    including the clock. The three add up to the result's own excess."""
    if rec["wp24"] is None:
        return None
    raw = _ledger_raw(rec, cal)
    return {k: v - cal["base"][k][rec["color"]] for k, v in raw.items()}


# --- how much players at the same rating really differ ----------------------------

def _resid(ys, xs):
    vx = _cov(xs, xs)
    b = _cov(xs, ys) / vx if vx else 0.0       # no rating spread: just centre
    my, mx = sum(ys) / len(ys), sum(xs) / len(xs)
    return [y - my - b * (x - mx) for y, x in zip(ys, xs)]


SPREAD_MEASURES = {
    "own_op": lambda gs: _mean([g["own_op"] for g in gs]),
    "opp_op": lambda gs: _mean([g["opp_op"] for g in gs]),
    "clock12": lambda gs: _mean([g["clock12"] for g in gs]),
}


def _true_cov(groups, f, g):
    """Between-player covariance of measures f and g at fixed rating: the
    halves' cross-covariance after the rating trend is taken out of each."""
    rows = []
    for recs in groups:
        a, b = recs[0::2], recs[1::2]
        vals = (f(a), f(b), g(a), g(b))
        if None not in vals:
            rows.append((*vals, _mean([r["elo"] for r in recs])))
    if len(rows) < 30:
        return None
    elo = [r[4] for r in rows]
    fa, fb, ga, gb = (_resid([r[i] for r in rows], elo) for i in range(4))
    return (_cov(fa, gb) + _cov(ga, fb)) / 2


def spreads(corpus: list[dict]) -> dict:
    """Measure -> (sd, low, high): the real between-player spread at fixed
    rating, with a bootstrap interval. Also the correlation between your
    opening errors and your opponents' ('own_opp_corr') and the net edge's
    spread ('net')."""
    def build():
        groups = players([r for r in corpus if r["wp24"] is not None])
        own, opp = SPREAD_MEASURES["own_op"], SPREAD_MEASURES["opp_op"]

        def stats(gs):
            out = {k: _true_cov(gs, f, f) for k, f in SPREAD_MEASURES.items()}
            c = _true_cov(gs, own, opp)
            if None not in (out["own_op"], out["opp_op"], c):
                out["net"] = out["own_op"] + out["opp_op"] - 2 * c
                out["own_opp_corr"] = (c / math.sqrt(out["own_op"] * out["opp_op"])
                                       if out["own_op"] > 0 and out["opp_op"] > 0 else None)
            return out

        est = stats(groups)
        rng = random.Random(0)
        boots = [stats([rng.choice(groups) for _ in groups]) for _ in range(BOOT)]
        res = {}
        for k, v in est.items():
            if v is None:
                continue
            bs = [b[k] for b in boots if b.get(k) is not None]
            if k == "own_opp_corr":
                res[k] = (v, *_interval(bs))
            else:
                res[k] = (math.sqrt(max(v, 0)),
                          *(math.sqrt(max(x, 0)) for x in _interval(bs)))
        return res
    return _memo("spreads", corpus, build)


# --- what theory is worth, within a player -----------------------------------------

def theory_contrast(corpus: list[dict], keep=lambda r: True) -> dict | None:
    """Same player, two kinds of game: the opponent left the book first, or
    they did. Score points by stretch, the first kind minus the second,
    averaged over players (weighted by how many of each they have), with a
    bootstrap over players for the interval.

    One bias is left and its direction is known: an opponent who left the book
    first is, a little, likelier to be a weaker opening player and so — at the
    same rating — a stronger one afterwards. It shrinks the later columns, so
    an edge that shows up here is if anything understated.
    """
    cal = calibration(corpus)
    per = []
    for recs in players([r for r in corpus if r["wp24"] is not None]):
        plus = [ledger(r, cal) for r in recs if r["opp_left"] and keep(r)]
        minus = [ledger(r, cal) for r in recs if r["left"] and keep(r)]
        if plus and minus:
            w = len(plus) * len(minus) / (len(plus) + len(minus))
            per.append((w, {k: _mean([x[k] for x in plus]) - _mean([x[k] for x in minus])
                            for k in plus[0]}))
    if len(per) < 30:
        return None

    def est(sample):
        total = sum(w for w, _ in sample)
        return {k: sum(w * d[k] for w, d in sample) / total for k in sample[0][1]}

    rng = random.Random(0)
    boots = [est([rng.choice(per) for _ in per]) for _ in range(BOOT)]
    point = est(per)
    return {"players": len(per),
            **{k: (v, *_interval([b[k] for b in boots])) for k, v in point.items()}}


# --- theory depth ------------------------------------------------------------------

def theory_depth(recs: list[dict], upto: int = 20) -> dict:
    """How long you stay in theory, counted fairly.

    A plain average of book moves is capped by the opponent: when they leave
    the book first you never get to show how far you knew it. So this is a
    survival curve (Kaplan–Meier): a game where the opponent left first, or the
    book ran out, stops counting at that point instead of counting as you
    leaving. `survival[m-1]` is the chance you are still in book after your
    m-th move; the median is the move at which that falls to a half.
    """
    alive, curve, median = 1.0, [], None
    for m in range(1, upto + 1):
        at_risk = sum(1 for r in recs
                      if (r["left"] and r["book"] + 1 >= m) or (not r["left"] and r["book"] >= m))
        events = sum(1 for r in recs if r["left"] and r["book"] + 1 == m)
        if at_risk:
            alive *= 1 - events / at_risk
        curve.append(alive)
        if median is None and alive <= 0.5:
            median = m
    return {"median": median, "survival": curve, "n": len(recs)}


# --- repertoire ----------------------------------------------------------------------

def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def similarity(recs: list[dict], color: str | None = None) -> dict | None:
    """How alike your opening choices are between games that started alike.

    Pairs of your games with the same colour where the opponent made the same
    first move: `moves` is the overlap of your first ten moves (which piece to
    which square, in any order), `pawns` the overlap of the pawn structure
    after move 10. 100% would be the same setup every time.
    """
    mv, pw = [], []
    for a, b in combinations([r for r in recs if color in (None, r["color"])], 2):
        if a["color"] != b["color"] or a["opp_first"] is None or a["opp_first"] != b["opp_first"]:
            continue
        mv.append(_jaccard(a["moves"], b["moves"]))
        if a["pawns"] is not None and b["pawns"] is not None:
            pw.append(_jaccard(a["pawns"], b["pawns"]))
    if not mv:
        return None
    return {"moves": _mean(mv), "pawns": _mean(pw), "pairs": len(mv)}


def windowed_similarity(recs: list[dict], color: str | None = None,
                        k: int = WINDOW) -> dict | None:
    """`similarity` over every stretch of `k` consecutive games, averaged — the
    same footing a corpus player's ten games are measured on. Over a whole
    history the same habits look different: there are simply more pairs."""
    recs = sorted(recs, key=lambda r: r["sort_key"])
    wins = [similarity(recs[i:i + k], color) for i in range(max(0, len(recs) - k + 1))]
    wins = [w for w in wins if w]
    if not wins:
        return None
    return {"moves": _mean([w["moves"] for w in wins]),
            "pawns": _mean([w["pawns"] for w in wins]), "windows": len(wins)}


def player_similarities(corpus: list[dict], color: str | None = None) -> list[dict]:
    """`similarity` for every corpus player, over their latest `WINDOW` games."""
    def build():
        out = []
        for recs in players(corpus):
            s = similarity(recs[-WINDOW:], color)
            if s:
                out.append({**s, "elo": _mean([r["elo"] for r in recs])})
        return out
    return _memo(("similarity", color), corpus, build)


def summary(recs: list[dict]) -> dict:
    """Headline opening numbers over a set of records."""
    rest_moves = sum(r["rest_moves"] for r in recs if r["own_rest"] is not None)
    return {
        "n": len(recs),
        "own_op": _mean([r["own_op"] for r in recs]),
        "opp_op": _mean([r["opp_op"] for r in recs]),
        "rest_per_move": (sum(r["own_rest"] for r in recs if r["own_rest"] is not None)
                          / rest_moves if rest_moves else None),
        "clock12": _mean([r["clock12"] for r in recs]),
        "book": _mean([r["book"] for r in recs]),
        "left": _mean([1.0 if r["left"] else 0.0 for r in recs]),
        "opp_left": _mean([1.0 if r["opp_left"] else 0.0 for r in recs]),
        "cost": _mean([r["cost"] for r in recs if r["left"]]),
        "score": _mean([r["result"] for r in recs]),
    }


def rest_per_move(recs: list[dict]) -> float | None:
    """Win-chance points you lose per move after move 12."""
    moves = sum(r["rest_moves"] for r in recs if r["own_rest"] is not None)
    return sum(r["own_rest"] for r in recs if r["own_rest"] is not None) / moves if moves else None


def reliability(corpus: list[dict], f=rest_per_move) -> dict | None:
    """How far ten games pin a player's measure down: the correlation between
    the two halves of each player's games, the reliability of all ten that it
    implies (Spearman–Brown), and the games per player a reliability of 0.6
    would take.

    It is the reason the obvious design — players alike in the rest of the
    game but different in the opening, compared by rating — is not run here.
    Matching on a measure that is mostly noise leaves the rest of the game
    uncontrolled, and the opening, measured more reliably, takes its credit.
    """
    rows = [(f(g[0::2]), f(g[1::2])) for g in players([r for r in corpus
                                                       if r["wp24"] is not None])]
    rows = [r for r in rows if None not in r]
    if len(rows) < 30:
        return None
    a, b = [r[0] for r in rows], [r[1] for r in rows]
    r = _cov(a, b) / math.sqrt(_cov(a, a) * _cov(b, b))
    if r <= 0:
        return {"split": r, "full": 0.0, "games_for_06": None}
    full = 2 * r / (1 + r)
    need = WINDOW * 0.6 * (1 - full) / (full * (1 - 0.6))
    return {"split": r, "full": full, "games_for_06": need}
