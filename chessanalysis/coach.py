"""Where your win chance goes, against players at your rating, on equal terms.

**The currency.** Every move changes the engine's win chance for the side that
played it. Summed over your own moves, what you lose is what your play gave
away — the same points `opening.py` calibrates against score. It is split
three ways, each a partition of the same total:

* by **phase** — the position the move was played in (`phases`);
* by **situation** — ahead, level or behind (engine eval before the move);
* by **clock** — comfortable, low, or in time trouble.

Two further lines cut across them: replies to an opponent's mistake (where the
win chance just handed to you is easiest to hand back), and the overall total.

**The comparison.** Your games and the corpus are analysed by the same engine
at the same depth and the same time control, and each of your games is
compared with corpus players *at the rating you had in that game*: a player
who climbed 400 points would otherwise have their early games judged against
their current band. The gap is your points minus theirs, per game; its interval
is a bootstrap over your games, with the corpus's own sampling error added.

Results are never compared: inside a band everyone scores about 50%, so being
better at one thing means being worse at another. Points lost are measured
directly, so that compensation cannot hide in them.
"""
from __future__ import annotations

import json
import math
import random
from bisect import bisect_left, bisect_right

from . import store
from .clocks import parse_time_control
from .enrich.engine import win_prob

LEDGER_VERSION = 1
CLAMP = 1000              # centipawns; a mate score stops being informative here
AHEAD = 150               # eval before the move, mover's view: ahead / behind
ERROR = 10.0              # an opponent move losing this much is a "mistake" to punish
TROUBLE, LOW = 0.10, 0.25 # fractions of the starting clock

# (key, group, label, what it means)
BUCKETS = [
    ("total", "Overall", "Every move", "All the win chance your moves gave away."),
    ("op", "Phase", "Opening", "Moves played before the middlegame began."),
    ("mg", "Phase", "Middlegame", "From development to the endgame."),
    ("eg", "Phase", "Endgame", "Six or fewer pieces besides kings and pawns."),
    ("ahead", "Situation", "When ahead",
     "Moves played at +1.5 or better — converting."),
    ("level", "Situation", "When level", "Moves played within ±1.5."),
    ("behind", "Situation", "When behind",
     "Moves played at −1.5 or worse — defending."),
    ("comfortable", "Clock", "Clock comfortable", "More than a quarter of the clock left."),
    ("low", "Clock", "Clock low", "Between a tenth and a quarter of the clock left."),
    ("trouble", "Clock", "Time trouble", "Under a tenth of the clock left."),
    ("reply", "Chances", "Replies to their mistakes",
     "Your move right after the opponent dropped 10% or more — punishing it."),
]
LABELS = {k: lbl for k, _, lbl, _ in BUCKETS}

MIN_WINDOW, MAX_WINDOW, MIN_PEERS = 75, 300, 150
BOOT = 1000


# --- one side of one game ------------------------------------------------------

def side_ledger(evals, division, color, clocks=None, base=None) -> dict:
    """{bucket: [win-chance points lost, moves]} for one side of one game.

    `evals` is the white-POV array (plies + 1), `division` a `phases.Division`,
    `clocks` the seconds left after each of this side's moves (or None) and
    `base` the starting clock.
    """
    sign = 1 if color == "white" else -1
    wp = [win_prob(sign * max(-CLAMP, min(CLAMP, e))) for e in evals]
    out: dict = {}

    def add(key, loss):
        b = out.setdefault(key, [0.0, 0])
        b[0] += loss
        b[1] += 1

    first = 0 if color == "white" else 1
    prev_clock = base
    for n, i in enumerate(range(first, len(evals) - 1, 2)):
        loss = max(0.0, wp[i] - wp[i + 1])
        before = sign * evals[i]
        add("total", loss)
        add(division.key_of_ply(i + 1), loss)
        add("ahead" if before >= AHEAD else "behind" if before <= -AHEAD else "level", loss)
        if i > 0 and wp[i] - wp[i - 1] >= ERROR:       # their move just handed it over
            add("reply", loss)
        if clocks and base and n < len(clocks):
            frac = (prev_clock if prev_clock is not None else base) / base
            add("trouble" if frac < TROUBLE else "low" if frac < LOW else "comfortable", loss)
            prev_clock = clocks[n]
    return {k: [round(v[0], 3), v[1]] for k, v in out.items()}


def _clocks(game, color):
    tc = parse_time_control(game.time_control)
    if not tc:
        return None, None
    clocks = [m.clock for m in game.moves if m.color == color]
    if not clocks or any(c is None for c in clocks):
        return None, None
    return clocks, tc[0]


def _compute(gid, depth, pgn_text, raw=None):
    """Both sides' ledgers for one stored game, or None if it can't be read."""
    from . import phases
    from .corpus import _rehydrate
    from .model import parse_pgn_text

    raw = raw or store.load_analysis(gid, depth)
    if not raw or not raw.get("evals"):
        return None
    parsed = parse_pgn_text(pgn_text)
    if not parsed or len(raw["evals"]) != len(parsed[0].moves) + 1:
        return None
    raw = _rehydrate(raw, pgn_text)
    if raw is None:
        return None
    game = parsed[0]
    division = phases.divide_fens(raw["fens"])
    out = {}
    for color in ("white", "black"):
        clocks, base = _clocks(game, color)
        out[color] = side_ledger(raw["evals"], division, color, clocks, base)
    return out


def ledgers(gids: list[str], depth: int) -> dict:
    """{(gid, color): ledger} for every game in `gids` analysed at `depth`,
    computing and storing whatever is missing or stale."""
    conn = store.connect()
    have = {}
    for i in range(0, len(gids), 500):
        chunk = gids[i:i + 500]
        for r in conn.execute(
                f"SELECT gid, color, data FROM ledgers WHERE depth=? AND version=? "
                f"AND gid IN ({','.join('?' * len(chunk))})",
                (depth, LEDGER_VERSION, *chunk)):
            have[(r["gid"], r["color"])] = json.loads(r["data"])
    missing = [g for g in gids if (g, "white") not in have]
    if missing:
        for i in range(0, len(missing), 500):
            chunk = missing[i:i + 500]
            rows = conn.execute(
                f"SELECT gid, pgn, welo, belo FROM games WHERE gid IN "
                f"({','.join('?' * len(chunk))})", chunk).fetchall()
            batch = []
            for r in rows:
                both = _compute(r["gid"], depth, store.unpack_pgn(r["pgn"]))
                if not both:
                    continue
                for color, led in both.items():
                    have[(r["gid"], color)] = led
                    batch.append((r["gid"], color, depth, LEDGER_VERSION,
                                  r["welo"] if color == "white" else r["belo"],
                                  json.dumps(led, separators=(",", ":"))))
            conn.executemany("INSERT OR REPLACE INTO ledgers VALUES(?,?,?,?,?,?)", batch)
            conn.commit()
    return have


# --- the comparison ------------------------------------------------------------

def _corpus(depth: int, time_control: str):
    """[(elo, ledger)] for every corpus side analysed at `depth`, by rating."""
    rows = store.connect().execute(
        "SELECT g.gid, g.welo, g.belo FROM games g JOIN analysis a "
        "ON a.gid=g.gid AND a.depth=? WHERE g.source='corpus' AND g.time_control=? "
        "AND g.welo IS NOT NULL AND g.belo IS NOT NULL", (depth, time_control)).fetchall()
    led = ledgers([r["gid"] for r in rows], depth)
    out = []
    for r in rows:
        for color, elo in (("white", r["welo"]), ("black", r["belo"])):
            if (r["gid"], color) in led:
                out.append((elo, led[(r["gid"], color)]))
    out.sort(key=lambda t: t[0])
    return out


def _value(ledger, key):
    return ledger.get(key, [0.0, 0])[0]


def _moves(ledger, key):
    return ledger.get(key, [0.0, 0])[1]


class _Rates:
    """A bucket's per-move loss among corpus players near a rating.

    Ratio of sums over every side within the window — points lost over moves
    played — read off prefix sums, and widened until it holds `MIN_PEERS`
    sides. Also how many moves per game those players spend in the bucket.
    """

    def __init__(self, corpus, key):
        self.elos = [e for e, _ in corpus]
        self.p, self.m = [0.0], [0]
        for _, led in corpus:
            self.p.append(self.p[-1] + _value(led, key))
            self.m.append(self.m[-1] + _moves(led, key))
        self._memo: dict = {}

    def at(self, elo):
        """(loss per move, moves per game) of the peers around `elo`."""
        if elo in self._memo:
            return self._memo[elo]
        w = MIN_WINDOW
        while True:
            lo = bisect_left(self.elos, elo - w)
            hi = bisect_right(self.elos, elo + w)
            if hi - lo >= MIN_PEERS or w >= MAX_WINDOW:
                break
            w += 25
        moves = self.m[hi] - self.m[lo]
        out = None
        if hi > lo and moves:
            out = ((self.p[hi] - self.p[lo]) / moves, moves / (hi - lo))
        self._memo[elo] = out
        return out


def _paired(user, depth, time_control, last=None):
    """Your games with both sides' ledgers: [(game, mine, theirs)]."""
    from .model import load_games

    games = [g for g in load_games(user)
             if g.time_control == time_control and g.user_elo and g.opp_elo
             and store.has_analysis(g.game_id, depth)]
    if last:
        games = games[-last:]
    led = ledgers([str(g.game_id) for g in games], depth)
    other = {"white": "black", "black": "white"}
    return [(g, led[(str(g.game_id), g.color)], led[(str(g.game_id), other[g.color])])
            for g in games if (str(g.game_id), g.color) in led]


def _ratio(num, den):
    return num / den if den else None


def compare(user: str, depth: int | None = None, time_control: str | None = None,
            last: int | None = None, seed: int = 0) -> dict | None:
    """Every bucket: your loss per move against players at your rating.

    For each bucket and each of your games, the peers' rate is read at the
    rating you had in that game and weighted by the moves you played in the
    bucket, so the comparison is of the same positions-per-bucket mix.

    `gap` is your rate over the peers' minus one. `control` is the same figure
    for your opponents in the same games, against players at *their* rating:
    whatever both sides of your games share and the corpus does not — the
    pool, the length, the kind of position — moves it, and it should sit near
    zero. `net` is your gap with the control taken out (a ratio of the two),
    and the verdict is drawn on it. Intervals are a paired bootstrap over
    your games; the corpus side averages thousands of moves and is taken as
    exact.
    """
    from . import corpus as C

    depth = depth or C.DEPTH
    time_control = time_control or C.TIME_CONTROL
    cohort = _corpus(depth, time_control)
    pairs = _paired(user, depth, time_control, last)
    if len(cohort) < MIN_PEERS or len(pairs) < 5:
        return None
    rng = random.Random(seed)
    idx = [[rng.randrange(len(pairs)) for _ in pairs] for _ in range(BOOT)]
    rows = []
    for key, group, label, help_ in BUCKETS:
        rates = _Rates(cohort, key)
        aligned = []      # per game (a, m, e, b, n, f, peer moves/game), or None
        for g, mine, theirs in pairs:
            ra, rb = rates.at(g.user_elo), rates.at(g.opp_elo)
            if ra is None or rb is None:
                aligned.append(None)
                continue
            m, n = _moves(mine, key), _moves(theirs, key)
            aligned.append((_value(mine, key), m, ra[0] * m,
                            _value(theirs, key), n, rb[0] * n, ra[1]))
        per = [t for t in aligned if t]
        if len(per) < 5 or sum(t[1] for t in per) < 20:
            continue

        def stats(sample):
            a, m, e, b, n, f = (sum(t[i] for t in sample) for i in range(6))
            gap = _ratio(a, e)
            ctrl = _ratio(b, f)
            net = gap / ctrl if gap is not None and ctrl else None
            return gap, ctrl, net, a, m, e

        gap, ctrl, net, a, m, e = stats(per)
        if gap is None or net is None:
            continue
        boots = [stats([aligned[i] for i in ix if aligned[i]]) for ix in idx]
        nets = sorted(b[2] for b in boots if b[2] is not None)
        gaps = sorted(b[0] for b in boots if b[0] is not None)
        q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
        lo, hi = q(nets, 0.025) - 1, q(nets, 0.975) - 1
        rows.append({
            "key": key, "group": group, "label": label, "help": help_,
            "you": round(a / m, 3), "peers": round(e / m, 3),
            "gap": round(gap - 1, 3), "gap_lo": round(q(gaps, 0.025) - 1, 3),
            "gap_hi": round(q(gaps, 0.975) - 1, 3),
            "control": round(ctrl - 1, 3), "net": round(net - 1, 3),
            "lo": round(lo, 3), "hi": round(hi, 3),
            "verdict": "leak" if lo > 0 else "strength" if hi < 0 else "level",
            "freq_you": round(m / len(per), 2),
            "freq_peers": round(sum(t[6] for t in per) / len(per), 2),
            "per_game_you": round(a / len(per), 1),
            "per_game_peers": round(e / len(per), 1),
        })
    elos = [g.user_elo for g, _, _ in pairs]
    out = {"games": len(pairs), "peers": len(cohort), "depth": depth,
           "time_control": time_control, "rows": rows, "last": last,
           "elo_range": [min(elos), max(elos)], "elo_now": elos[-1]}
    out["plays_like"] = plays_like(out, cohort, pairs, idx)
    return out


def _band_rates(cohort, min_moves=3000):
    """[(band centre, loss per move)] for every band with enough moves."""
    from . import corpus as C

    agg: dict = {}
    for elo, led in cohort:
        b = agg.setdefault(elo // C.BAND_SIZE * C.BAND_SIZE, [0.0, 0])
        b[0] += _value(led, "total")
        b[1] += _moves(led, "total")
    return [(band + C.BAND_SIZE // 2, p / m) for band, (p, m) in sorted(agg.items())
            if m >= min_moves]


def _rating_for(rate, ladder):
    """The rating whose band loses `rate` per move, by linear interpolation
    along the ladder; None outside the ladder's reach."""
    for (e0, r0), (e1, r1) in zip(ladder, ladder[1:]):
        if min(r0, r1) <= rate <= max(r0, r1) and r0 != r1:
            return e0 + (e1 - e0) * (r0 - rate) / (r0 - r1)
    return None


def plays_like(result, cohort, pairs, idx) -> dict | None:
    """The rating whose players lose what you lose per move, once the control
    has taken out what your games themselves contribute.

    Read straight off the corpus ladder, so it can only answer inside the
    bands the corpus covers; beyond them it says so instead of extrapolating.
    """
    ladder = _band_rates(cohort)
    row = next((r for r in result["rows"] if r["key"] == "total"), None)
    if len(ladder) < 3 or row is None:
        return None

    def adjusted(sample):
        a = sum(_value(mine, "total") for _, mine, _ in sample)
        m = sum(_moves(mine, "total") for _, mine, _ in sample)
        return (a / m) / (1 + row["control"]) if m else None

    point = adjusted(pairs)
    boots = sorted(x for x in (adjusted([pairs[i] for i in ix]) for ix in idx) if x)
    lo_rate, hi_rate = boots[int(0.975 * len(boots)) - 1], boots[int(0.025 * len(boots))]
    best, worst = ladder[-1][1], ladder[0][1]

    def place(rate):
        if rate < min(best, worst):
            return {"above": ladder[-1][0] + 50}
        if rate > max(best, worst):
            return {"below": ladder[0][0] - 50}
        r = _rating_for(rate, ladder)
        return {"elo": round(r / 10) * 10} if r else None

    return {"rate": round(point, 3), "point": place(point),
            "low": place(lo_rate), "high": place(hi_rate),
            "ladder": [{"elo": e, "rate": round(r, 3)} for e, r in ladder]}


def focus(result: dict, k: int = 3) -> dict:
    """The biggest leaks and strengths, ignoring the overall line."""
    rows = [r for r in result["rows"] if r["key"] != "total"]
    leaks = sorted((r for r in rows if r["verdict"] == "leak"), key=lambda r: -r["net"])
    strengths = sorted((r for r in rows if r["verdict"] == "strength"),
                       key=lambda r: r["net"])
    # nothing clears the noise: say which way the largest gaps lean instead
    leaning = sorted((r for r in rows if r["verdict"] == "level" and r["net"] > 0),
                     key=lambda r: -r["net"])
    return {"leaks": leaks[:k], "strengths": strengths[:k], "leaning": leaning[:k]}


def ladder(depth: int | None = None, time_control: str | None = None) -> list[dict]:
    """Mean points lost per game, by band — the validation that the measure
    tracks strength at all."""
    from . import corpus as C

    cohort = _corpus(depth or C.DEPTH, time_control or C.TIME_CONTROL)
    bands: dict = {}
    for elo, led in cohort:
        b = bands.setdefault(elo // C.BAND_SIZE * C.BAND_SIZE, {"n": 0})
        b["n"] += 1
        for key, *_ in BUCKETS:
            b[key] = b.get(key, 0.0) + _value(led, key)
    return [{"band": band, "n": b["n"],
             **{k: round(b.get(k, 0.0) / b["n"], 2) for k, *_ in BUCKETS}}
            for band, b in sorted(bands.items())]
