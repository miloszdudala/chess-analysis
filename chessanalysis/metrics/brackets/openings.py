"""The opening: how much it costs you, how varied it is, and whether theory pays.

Everything here is measured, for you and for the corpus, by `opening.py` against
the same book and the same engine depth. The units are the app's own
(`glossary`): win chance in %, score in %, evaluations in pawns. Every
conclusion in the text is drawn from the numbers beside it and their 95%
range — nothing is asserted that the data on the page does not show.
"""
from collections import Counter, defaultdict

from ... import glossary as G
from ... import opening as op
from ... import widgets as W
from ...corpus import BAND_SIZE
from ...registry import metric

MIN_FAMILY = 5       # your games in an opening before it gets its own row
MIN_PEER = 10        # peer samples in an opening before its peer column is shown
MOVES = op.CHECK // 2


def _records(ctx):
    """(yours, the whole corpus), built once per page."""
    if getattr(ctx, "_opening_cache", None) is None:
        mine = op.own_records(ctx.user, ctx.depth) if ctx.user else []
        ctx._opening_cache = (mine, op.corpus_records(ctx.depth))
    return ctx._opening_cache


def _band(corpus, lo, hi):
    return [r for r in corpus if r["elo"] is not None and lo <= r["elo"] <= hi]


def _mean(recs, key):
    return op._mean([r[key] for r in recs])


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def _wc(x, digits=1):
    """Win chance or score, already in percent: 22.2 -> '22.2%'."""
    return "—" if x is None else f"{x:.{digits}f}%"


def _num(x, digits=1):
    return "—" if x is None else f"{x:.{digits}f}"


def _signed(x, digits=1, unit="%"):
    return f"{x:+.{digits}f}{unit}".replace("-", "−")


def _clock(sec):
    return "—" if sec is None else f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def _range(v, digits=1):
    """'+1.9% (+0.5% to +3.5%)' from (estimate, low, high)."""
    e, lo, hi = v
    return f"{_signed(e, digits)} ({_signed(lo, digits)} to {_signed(hi, digits)})"


def _clear(v):
    """Whether a (estimate, low, high) range stays on one side of zero."""
    return v[1] > 0 or v[2] < 0


def _gap(mine, theirs, key):
    """(your mean - theirs, 95% half-width) for a per-game measure."""
    a = op.mean_ci([r[key] for r in mine])
    b = op.mean_ci([r[key] for r in theirs])
    if not a or not b:
        return None
    return a[0] - b[0], (a[1] ** 2 + b[1] ** 2) ** 0.5


def _who(ctx):
    return ctx.who[0].upper() + ctx.who[1:]


@metric("brackets", title=f"Your opening: moves 1–{MOVES}", order=40)
def strength(ctx):
    if ctx.scope != "peers" or not ctx.user:
        return None
    every, corpus = _records(ctx)
    band = _band(corpus, ctx.lo, ctx.hi)
    # win chance needs the engine; the book facts do not, so they use every game
    mine = [r for r in every if r["own_op"] is not None]
    peers = [r for r in band if r["own_op"] is not None]
    if len(mine) < 10 or len(peers) < 50:
        return None
    me, co = op.summary(mine), op.summary(peers)
    me_all, co_all = op.summary(every), op.summary(band)
    for r in mine + peers:
        r["net_op"] = r["opp_op"] - r["own_op"]

    def gap_row(label, key):
        g = _gap(mine, peers, key)
        if not g:
            return None
        d, ci = g
        return [label, _wc(_mean(mine, key)), _wc(_mean(peers, key)),
                f"{_signed(d)} ({_signed(d - ci)} to {_signed(d + ci)})"]

    rows = [r for r in (
        gap_row("Win chance your moves give away", "own_op"),
        gap_row("Win chance your opponents' moves give away", "opp_op"),
        gap_row("Net: your opponents' total minus yours", "net_op"),
    ) if r]
    clock = _gap([r for r in mine if r["clock12"] is not None],
                 [r for r in peers if r["clock12"] is not None], "clock12")
    if clock:
        d, ci = clock
        rows.append([f"Clock used on moves 1–{MOVES}", _clock(me["clock12"]),
                     _clock(co["clock12"]),
                     f"{_signed(d, 0, ' s')} ({_signed(d - ci, 0, ' s')} to "
                     f"{_signed(d + ci, 0, ' s')})"])

    depth_me, depth_co = op.theory_depth(every), op.theory_depth(band)
    rows += [
        ["Book moves you play (median)", _num(depth_me["median"], 0),
         _num(depth_co["median"], 0), ""],
        ["Games where you leave the book first", _pct(me_all["left"]),
         _pct(co_all["left"]), ""],
        ["What leaving the book costs (pawns, on average)",
         _num(me["cost"] and me["cost"] / 100, 2), _num(co["cost"] and co["cost"] / 100, 2), ""],
    ]

    two = G.win_chance_edge_in_pawns(2.0)
    intro = (f"Your first {MOVES} moves against {ctx.who} ({len(peers)} of their games), "
             f"same engine and depth. Every move changes the win chance — the "
             f"evaluation as a percentage, 0.00 being 50%. The first two rows add up, "
             f"per game, what your moves and your opponents' moves gave away in moves "
             f"1–{MOVES}; the third is the difference, so a positive number means you "
             f"come out of the opening better than you went in. For scale, a 2% edge "
             f"in win chance is about +{two:.2f} pawns. Book moves count only while "
             f"your opponent is still in book too, so their early departures do not "
             f"cut your count short.")

    said = []
    g = _gap(mine, peers, "own_op")
    if g and abs(g[0]) > g[1]:
        said.append(f"You give away {abs(g[0]):.1f}% {'less' if g[0] < 0 else 'more'} "
                    f"win chance in the opening than {ctx.who}, and the 95% range "
                    f"rules out chance.")
    elif g:
        said.append(f"How much win chance you give away in the opening is within chance "
                    f"of {ctx.who}.")
    n = _gap(mine, peers, "net_op")
    if n and abs(n[0]) > n[1]:
        said.append(f"Counting your opponents' moves too, you come out of the opening "
                    f"{abs(n[0]):.1f}% {'better' if n[0] > 0 else 'worse'} off than they "
                    f"do — beyond chance.")
    out = [W.text(intro, guide="win-chance", label="What win chance means"),
           W.table(["", "You", _who(ctx), "Difference (95% range)"], rows)]
    if said:
        out.append(W.text(" ".join(said)))
    return out


@metric("brackets", title="How varied your openings are", order=41)
def repertoire(ctx):
    if ctx.scope != "peers" or not ctx.user:
        return None
    mine, corpus = _records(ctx)
    if len(mine) < op.WINDOW:
        return None
    rows, said = [], {}
    for label, color in (("As White", "white"), ("As Black", "black"), ("Overall", None)):
        me = op.windowed_similarity(mine, color)
        theirs = sorted(s["moves"] for s in op.player_similarities(corpus, color))
        if not me or len(theirs) < 30:
            continue
        more_varied = sum(t < me["moves"] for t in theirs) / len(theirs)
        said[color] = (me["moves"], theirs)
        rows.append([label, _pct(me["moves"]), _pct(theirs[len(theirs) // 2]),
                     f"{_pct(theirs[len(theirs) // 4])}–{_pct(theirs[3 * len(theirs) // 4])}",
                     _pct(more_varied)])
    me = op.windowed_similarity(mine)
    pawns = sorted(s["pawns"] for s in op.player_similarities(corpus) if s["pawns"] is not None)
    if me and me["pawns"] is not None and len(pawns) >= 30:
        rows.append([f"Pawn structure after move {op.REP_MOVES}", _pct(me["pawns"]),
                     _pct(pawns[len(pawns) // 2]),
                     f"{_pct(pawns[len(pawns) // 4])}–{_pct(pawns[3 * len(pawns) // 4])}",
                     _pct(sum(t < me["pawns"] for t in pawns) / len(pawns))])
    if not rows:
        return None

    intro = (f"How much your own first {op.REP_MOVES} moves repeat between games that "
             f"began the same way (your opponent's first move was the same): which "
             f"piece goes to which square, in any order. 100% would be the identical "
             f"setup every time. It is measured over every run of {op.WINDOW} "
             f"consecutive games — as many as the corpus holds per player — so you and "
             f"the other players are measured on the same footing. The pawn-structure "
             f"row compares the pawns after move {op.REP_MOVES} the same way.")
    out = [W.text(intro),
           W.table(["How alike your games are", "You", "Typical player (median)",
                    "Middle half of players", "Players who vary more than you"], rows)]

    white = Counter(r["first"] for r in mine if r["color"] == "white" and r["first"])
    if "white" in said and white:
        mv, n = white.most_common(1)[0]
        mine_s, theirs = said["white"]
        q1, q3 = theirs[len(theirs) // 4], theirs[3 * len(theirs) // 4]
        shape = ("after the first move you vary more than three players in four"
                 if mine_s < q1 else
                 "after the first move you keep to a set system more than three players in four"
                 if mine_s > q3 else
                 "inside the middle half of players, so after the first move you vary "
                 "about as much as most")
        out.append(W.text(f"As White you opened 1.{mv} in {n} of {sum(white.values())} "
                          f"games; by move {op.REP_MOVES} your moves overlap "
                          f"{_pct(mine_s)} between games that began the same way, "
                          f"against {_pct(theirs[len(theirs) // 2])} for the typical "
                          f"player — {shape}."))
    return out + _by_opening(ctx, mine, corpus)


def _by_opening(ctx, mine, corpus):
    mine = [r for r in mine if r["own_op"] is not None]
    peers = [r for r in _band(corpus, ctx.lo, ctx.hi) if r["own_op"] is not None]
    pop = op.popularity(corpus)
    groups, peer_groups = defaultdict(list), defaultdict(list)
    for r in mine:
        groups[(r["family"], r["color"])].append(r)
    for r in peers:
        peer_groups[(r["family"], r["color"])].append(r)

    def pair(m, p, key, fmt=_wc):
        return f"{fmt(m[key])} / {fmt(p[key]) if p else '—'}"

    rows, other = [], []
    for key, recs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(recs) < MIN_FAMILY:
            other.extend(recs)
            continue
        m = op.summary(recs)
        p = op.summary(peer_groups[key]) if len(peer_groups[key]) >= MIN_PEER else None
        rows.append([key[0], key[1].title(), m["n"], op.bucket_of(pop, key[0]),
                     pair(m, p, "own_op"), pair(m, p, "opp_op"), pair(m, p, "book", _num),
                     _pct(m["score"])])
    if other:
        m = op.summary(other)
        rows.append([f"Everything else ({len({r['family'] for r in other})} openings)", "",
                     m["n"], "", f"{_wc(m['own_op'])} / —", f"{_wc(m['opp_op'])} / —",
                     f"{_num(m['book'])} / —", _pct(m["score"])])
    if not rows:
        return []
    return [W.text(f"By opening: you / {ctx.who} in the same opening with the same "
                   f"colour (— where they have fewer than {MIN_PEER} games). Win chance "
                   f"is added up over moves 1–{MOVES}, as above. How common is read off "
                   f"the other players' games: the mainstream openings together make up "
                   f"{100 * op.MAINSTREAM:.0f}% of them, a niche one under "
                   f"{100 * op.NICHE:g}% each. Your score is wins plus half the draws."),
            W.table(["Opening", "Colour", "Games", "How common",
                     "Win chance your moves give away", "Win chance their moves give away",
                     "Book moves", "Your score"], rows)]


@metric("brackets", title="Does knowing more theory pay?", order=43)
def worth(ctx):
    _, corpus = _records(ctx)
    pop = op.popularity(corpus)
    groups = [("All openings", lambda r: True),
              ("Mainstream", lambda r: op.bucket_of(pop, r["family"]) == "Mainstream"),
              ("Uncommon and niche", lambda r: op.bucket_of(pop, r["family"]) != "Mainstream")]
    found = [(label, op.theory_contrast(corpus, keep)) for label, keep in groups]
    found = [(label, c) for label, c in found if c]
    if not found:
        return None
    rows = [[label, c["players"], _range(c["op"]), _range(c["mg"]), _range(c["rest"]),
             _range(c["result"])] for label, c in found]
    allc = found[0][1]
    o, m, res = allc["op"], allc["mg"], allc["result"]
    elo = op.ELO_PER_POINT

    intro = (f"Each of the other players is compared with themselves: their games where "
             f"the opponent left the book first, against their games where they left it "
             f"first. The same player on both sides, so their strength and style are "
             f"held fixed. The numbers are expected score — the share of the points "
             f"(win 1, draw ½) a position is worth, read from the engine's evaluation "
             f"and checked against how games from such positions actually ended at "
             f"this level. The four columns add up to the difference in the final "
             f"result.")

    said = []
    if _clear(o):
        k = op.calibration(corpus)["k"][op.CHECK]
        pawns = G.win_chance_edge_in_pawns(o[0] / k) if k else None
        said.append(f"At move {MOVES} the player who stayed in book longer stands "
                    f"{'better' if o[0] > 0 else 'worse'}: {_range(o)} expected score"
                    + (f", about what a {pawns:+.2f} pawn edge is worth" if pawns else "")
                    + f" — roughly {abs(o[0]) * elo:.0f} Elo of performance in that game.")
    else:
        said.append(f"At move {MOVES} there is no measurable difference: {_range(o)}.")
    if not _clear(m):
        said.append(f"In moves {MOVES + 1}–{op.MID // 2} it neither grows nor shrinks "
                    f"measurably: {_range(m)}.")
    else:
        said.append(f"In moves {MOVES + 1}–{op.MID // 2} it "
                    f"{'grows' if m[0] > 0 else 'is given back'}: {_range(m)}.")
    if _clear(res):
        said.append(f"It shows in the final results: {_range(res)}.")
    else:
        said.append(f"The final results cannot show an effect this small: they differ "
                    f"by {_range(res)}, a range many times wider than the move-{MOVES} "
                    f"edge.")
    by = dict(found)
    if "Mainstream" in by and "Uncommon and niche" in by:
        a, b = by["Mainstream"]["op"], by["Uncommon and niche"]["op"]
        same = a[1] < b[0] < a[2] or b[1] < a[0] < b[2]
        said.append("Mainstream and less common openings do not differ measurably."
                    if same else
                    f"In less common openings the move-{MOVES} edge is "
                    f"{abs(b[0] - a[0]):.1f}% {'larger' if b[0] > a[0] else 'smaller'} "
                    f"than in mainstream ones.")

    out = [W.text(intro, guide="score", label="What expected score means"),
           W.text(" ".join(said)),
           W.table(["Openings", "Players", f"At move {MOVES}",
                    f"Moves {MOVES + 1}–{op.MID // 2}",
                    f"After move {op.MID // 2}, incl. the clock", "Final result"], rows)]

    if ctx.scope == "peers" and ctx.user and _clear(o):
        mine, _ = _records(ctx)
        left = op._mean([1.0 if r["left"] else 0.0 for r in mine])
        if left:
            gain = left * o[0]
            out.append(W.text(
                f"For you: you leave the book first in {_pct(left)} of your games. Had "
                f"your opponent left it first instead in every one of them, the move-"
                f"{MOVES} edge would be worth at most {gain:.1f}% expected score a game "
                f"— about {gain * elo:.0f} Elo — and, by the table, less by the end."))

    out.append(W.text(
        "One bias is left and its direction is known: an opponent who leaves the book "
        "first is, a little, likelier to be a weaker opening player and so, at the same "
        "rating, a stronger one afterwards. That works against the player who knew the "
        "line longer in the later columns, so an edge there is if anything understated."))
    return out


@metric("brackets", title="The opening at each rating", order=41)
def by_band(ctx):
    if ctx.scope != "ladder" or not ctx.bands:
        return None
    _, corpus = _records(ctx)
    rows, ends = [], []
    for b in ctx.bands:
        lo, hi = b["band"], b["band"] + BAND_SIZE - 1
        recs = [r for r in _band(corpus, lo, hi) if r["own_op"] is not None]
        if len(recs) < 50:
            continue
        s, depth = op.summary(recs), op.theory_depth(recs)["median"]
        ends.append((f"{lo}–{hi}", s["own_op"], depth, s["clock12"]))
        rows.append([f"{lo}–{hi}", s["n"], _num(depth, 0), _wc(s["own_op"], 0),
                     _clock(s["clock12"]), _pct(s["left"]),
                     _num(s["cost"] and s["cost"] / 100, 2)])
    if not rows:
        return None
    text = (f"Win chance is what a player's own moves 1–{MOVES} gave away, added up per "
            f"game. Book moves are a player's own moves in book, counted only while the "
            f"opponent was in book too (the median). Each game counts once for each "
            f"player.")
    if len(ends) > 1:
        (r0, err0, d0, c0), (r1, err1, d1, c1) = ends[0], ends[-1]
        text = (f"From {r0} to {r1}: the win chance given away in moves 1–{MOVES} goes "
                f"from {err0:.0f}% to {err1:.0f}% a game, the median number of book "
                f"moves from {d0} to {d1}, and the clock used on those moves from "
                f"{_clock(c0)} to {_clock(c1)}. " + text)
    return [
        W.text(text),
        W.table(["Rating", "Game sides", "Book moves (median)",
                 f"Win chance given away, moves 1–{MOVES}",
                 f"Clock used, moves 1–{MOVES}", "Leave the book first",
                 "What leaving costs (pawns)"], rows),
    ]
