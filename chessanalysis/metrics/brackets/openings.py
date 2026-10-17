"""The opening: how strong yours is, how wide, and what it is worth.

Everything here is measured, for you and for the corpus, by `opening.py` against
the same book and the same engine depth. See its docstring for why results are
not compared directly inside a band, and what is measured instead.
"""
from collections import Counter, defaultdict

from ... import opening as op
from ... import widgets as W
from ...corpus import BAND_SIZE
from ...registry import metric

MIN_FAMILY = 5       # your games in an opening before it gets its own row
MIN_PEER = 10        # peer samples in an opening before its peer column is shown


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


def _num(x, digits=1):
    return "—" if x is None else f"{x:.{digits}f}"


def _clock(sec):
    return "—" if sec is None else f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def _range(v, digits=1):
    """'+1.9 (+0.5 to +3.5)' from (estimate, low, high)."""
    e, lo, hi = v
    return f"{e:+.{digits}f} ({lo:+.{digits}f} to {hi:+.{digits}f})"


def _gap(mine, theirs, key):
    """(your mean - theirs, 95% half-width) for a per-game measure."""
    a = op.mean_ci([r[key] for r in mine])
    b = op.mean_ci([r[key] for r in theirs])
    if not a or not b:
        return None
    return a[0] - b[0], (a[1] ** 2 + b[1] ** 2) ** 0.5


def _elo(points, cal):
    """Win-chance points at move 12 -> Elo, through what they are worth here."""
    return points * cal["k"][op.CHECK] * op.ELO_PER_POINT


@metric("brackets", title="Your opening, measured", order=40)
def strength(ctx):
    if ctx.scope != "peers" or not ctx.user:
        return None
    every, corpus = _records(ctx)
    band = _band(corpus, ctx.lo, ctx.hi)
    # points need the engine; the book facts do not, so they use every game
    mine = [r for r in every if r["own_op"] is not None]
    peers = [r for r in band if r["own_op"] is not None]
    if len(mine) < 10 or len(peers) < 50:
        return None
    cal, sp = op.calibration(corpus), op.spreads(corpus)
    me, co = op.summary(mine), op.summary(peers)
    me_all, co_all = op.summary(every), op.summary(band)
    for r in mine + peers:
        r["net_op"] = r["opp_op"] - r["own_op"]

    def spread(key, elo=True):
        if key not in sp:
            return "—"
        sd = sp[key][0]
        return f"{sd:.1f} (≈ {_elo(sd, cal):.0f} Elo)" if elo else _clock(sd)

    def gap_row(label, key, better_low, spread_key):
        g = _gap(mine, peers, key)
        if not g:
            return None
        d, ci = g
        elo = _elo(-d if better_low else d, cal)
        return [label, _num(_mean(mine, key)), _num(_mean(peers, key)),
                f"{d:+.1f} ± {ci:.1f}", f"{elo:+.0f} ± {_elo(ci, cal):.0f}",
                spread(spread_key)]

    rows = [r for r in (
        gap_row("Points you give away, moves 1–12", "own_op", True, "own_op"),
        gap_row("Points your opponents give away", "opp_op", False, "opp_op"),
        gap_row("Net: what the opening hands you", "net_op", False, "net"),
    ) if r]
    clock = _gap([r for r in mine if r["clock12"] is not None],
                 [r for r in peers if r["clock12"] is not None], "clock12")
    if clock:
        rows.append(["Clock for moves 1–12", _clock(me["clock12"]), _clock(co["clock12"]),
                     f"{clock[0]:+.0f} s ± {clock[1]:.0f}", "", spread("clock12", elo=False)])

    depth_me, depth_co = op.theory_depth(every), op.theory_depth(band)
    rows += [
        ["Theory depth (median own book moves)", _num(depth_me["median"], 0),
         _num(depth_co["median"], 0), "", "", ""],
        ["You leave the book first", _pct(me_all["left"]), _pct(co_all["left"]),
         "", "", ""],
        ["What leaving costs (pawns)", _num(me["cost"] and me["cost"] / 100, 2),
         _num(co["cost"] and co["cost"] / 100, 2), "", "", ""],
        ["After move 12: points you lose per move", _num(me["rest_per_move"], 2),
         _num(co["rest_per_move"], 2), "", "", ""],
    ]

    intro = (f"What the opening hands you, measured in the engine's win chance "
             f"(points out of 100) summed over moves 1–12 — not in results, because "
             f"inside a band everyone scores about 50% and better openings have to "
             f"be paid for somewhere else. Players at your rating means "
             f"{ctx.lo}–{ctx.hi}, {len(peers)} games, same engine and depth. Elo is "
             f"what the points are worth at this level, everything else equal. "
             f"The last column is how much players at the same rating really "
             f"differ (one standard deviation, game-to-game luck taken out). Theory "
             f"depth counts your book moves only while your opponent is still in "
             f"book too, so their early departures do not cap it.")

    said = []
    g = _gap(mine, peers, "own_op")
    if g and abs(g[0]) > g[1]:
        said.append(f"You make {'fewer' if g[0] < 0 else 'more'} opening errors than "
                    f"players at your rating: {abs(g[0]):.1f} points a game, worth "
                    f"about {abs(_elo(g[0], cal)):.0f} Elo.")
    elif g:
        said.append("Your opening errors are within noise of your band's.")
    if "own_opp_corr" in sp and "net" in sp:
        corr = min(sp["own_opp_corr"][0], 1.0)
        said.append(f"Players who err more in their openings also get more errors "
                    f"out of their opponents (a correlation of {corr:.2f} between "
                    f"players): sharp openings cut both ways. That is why what the "
                    f"opening nets varies so little between players at the same "
                    f"rating — about {_elo(sp['net'][0], cal):.0f} Elo — against "
                    f"{_elo(sp['own_op'][0], cal):.0f} for the errors alone.")
    if me["rest_per_move"] and co["rest_per_move"]:
        rel = me["rest_per_move"] / co["rest_per_move"] - 1
        said.append(f"After move 12 you lose {me['rest_per_move']:.2f} points a move "
                    f"against {co['rest_per_move']:.2f} for your band "
                    f"({100 * rel:+.0f}%).")
    out = [W.text(intro),
           W.table(["Measure", "You", "Players at your rating", "Gap (95%)",
                    "Gap in Elo", "Real spread at one rating"], rows)]
    if said:
        out.append(W.text(" ".join(said)))
    return out


@metric("brackets", title="Your repertoire to move 10", order=41)
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
        said[color] = (me["moves"], theirs[len(theirs) // 2])
        rows.append([label, _pct(me["moves"]), _pct(theirs[len(theirs) // 2]),
                     f"{_pct(theirs[len(theirs) // 4])}–{_pct(theirs[3 * len(theirs) // 4])}",
                     _pct(more_varied)])
    me = op.windowed_similarity(mine)
    pawns = sorted(s["pawns"] for s in op.player_similarities(corpus) if s["pawns"] is not None)
    if me and me["pawns"] is not None and len(pawns) >= 30:
        rows.append(["Pawn structure after move 10", _pct(me["pawns"]),
                     _pct(pawns[len(pawns) // 2]),
                     f"{_pct(pawns[len(pawns) // 4])}–{_pct(pawns[3 * len(pawns) // 4])}",
                     _pct(sum(t < me["pawns"] for t in pawns) / len(pawns))])
    if not rows:
        return None

    intro = ("At this level exact positions stop repeating by move 7 — your "
             "opponents see to that — so a repertoire to move 10 cannot be read "
             "off positions. This reads what you control: your own first ten moves "
             "(which piece to which square, in any order), compared between your "
             "games where the opponent made the same first move, over every stretch "
             f"of {op.WINDOW} games — the same footing as the corpus players' "
             f"{op.WINDOW} games. A London or a fixed Closed Sicilian setup scores "
             "around 80%; fixing only the first move or two, around 35%. The pawn "
             "structure row is the other side of it: how alike the positions you "
             "end up in are.")
    out = [W.text(intro),
           W.table(["How alike your games are", "You", "Players (median)",
                    "Middle half", "Players more varied than you"], rows)]

    white = Counter(r["first"] for r in mine if r["color"] == "white" and r["first"])
    if "white" in said and white:
        mv, n = white.most_common(1)[0]
        mine_s, theirs_s = said["white"]
        shape = ("you fix the first move and improvise after it" if mine_s < theirs_s
                 else "you keep to a set system well past the first move")
        out.append(W.text(f"As White you opened 1.{mv} in {n} of {sum(white.values())} "
                          f"games, yet by move 10 your moves overlap {_pct(mine_s)} "
                          f"between games that started alike, against "
                          f"{_pct(theirs_s)} for the typical player: {shape}."))
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

    def pair(m, p, key):
        return f"{_num(m[key])} / {_num(p[key]) if p else '—'}"

    rows, other = [], []
    for key, recs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(recs) < MIN_FAMILY:
            other.extend(recs)
            continue
        m = op.summary(recs)
        p = op.summary(peer_groups[key]) if len(peer_groups[key]) >= MIN_PEER else None
        rows.append([key[0], key[1].title(), m["n"], op.bucket_of(pop, key[0]),
                     pair(m, p, "own_op"), pair(m, p, "opp_op"), pair(m, p, "book"),
                     _pct(m["score"])])
    if other:
        m = op.summary(other)
        rows.append([f"Everything else ({len({r['family'] for r in other})} openings)", "",
                     m["n"], "", f"{_num(m['own_op'])} / —", f"{_num(m['opp_op'])} / —",
                     f"{_num(m['book'])} / —", _pct(m["score"])])
    if not rows:
        return []
    return [W.text("By opening, you / players at your rating in the same opening "
                   "with the same colour. Points are summed over moves 1–12; book "
                   "moves are your own."),
            W.table(["Opening", "Colour", "Games", "How common",
                     "Points you give away", "Points they give away", "Book moves",
                     "Your score"], rows)]


@metric("brackets", title="What the opening is worth", order=43)
def worth(ctx):
    _, corpus = _records(ctx)
    cal = op.calibration(corpus)
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
    k, kw = cal["k"][op.CHECK], cal["k_within"]

    first = (f"A point of win chance at move 12 is worth {k:.2f} of a point of score "
             f"at this level — there is a whole game left to play — and {kw:.2f} "
             f"inside the same player's games, so it is not the band effect (better "
             f"openings, worse afterwards) that flattens it. Near 50% a point of "
             f"score is about {op.ELO_PER_POINT:.0f} Elo.")

    o, m, res = allc["op"], allc["mg"], allc["result"]
    verdict = (f"Knowing the line longer than your opponent is worth {o[0]:+.1f} points "
               f"at move 12 (about {o[0] * op.ELO_PER_POINT:.0f} Elo in that game). ")
    if m[1] < 0 < m[2]:
        verdict += (f"It does not carry into the middlegame: moves 13–32 come out at "
                    f"{m[0]:+.1f} ({m[1]:+.1f} to {m[2]:+.1f}), which rules out a "
                    f"better-plan effect bigger than {m[2]:.0f} points. ")
    elif m[1] > 0:
        verdict += f"And it carries on: moves 13–32 add {m[0]:+.1f}. "
    verdict += (f"The result alone could never have settled this — its interval is "
                f"{(res[2] - res[1]) / 2:.0f} points either way, several times the "
                f"effect.")
    by = dict(found)
    if "Mainstream" in by and "Uncommon and niche" in by:
        a, b = by["Mainstream"]["op"], by["Uncommon and niche"]["op"]
        same = a[1] < b[0] < a[2] or b[1] < a[0] < b[2]
        verdict += (" In uncommon openings it is the same as in mainstream ones."
                    if same else
                    f" In uncommon openings it is {abs(b[0] - a[0]):.1f} points "
                    f"{'more' if b[0] > a[0] else 'less'} than in mainstream ones.")

    out = [W.text(first), W.text(verdict),
           W.table(["Openings", "Players", "At move 12", "Moves 13–32",
                    "After move 32 and clock", "Result"], rows)]

    if ctx.scope == "peers" and ctx.user:
        mine, _ = _records(ctx)
        left = op._mean([1.0 if r["left"] else 0.0 for r in mine])
        if left:
            gain = left * o[0]
            out.append(W.text(
                f"What perfect theory would be worth to you: you leave the book first "
                f"in {_pct(left)} of your games. Turning every one of those into a "
                f"game where your opponent leaves first instead is worth at most "
                f"{gain:.1f} points a game — about {gain * op.ELO_PER_POINT:.0f} Elo."))

    note = ("How this is measured: each corpus player is compared with themselves — "
            "the games where the opponent left the book first against the games "
            "where they did — so their own strengths and weaknesses are held fixed. "
            "Points are score points against the colour's average. One bias is left "
            "and its direction is known: an opponent who leaves the book first is, a "
            "little, likelier to be a weaker opening player and so, at the same "
            "rating, a stronger one afterwards — which makes the later columns "
            "understate any edge, not overstate it.")
    rel = op.reliability(corpus)
    if rel and rel["games_for_06"]:
        note += (f" The other design — players alike in the rest of the game but "
                 f"different in the opening, compared by rating — needs the rest of "
                 f"the game measured reliably, and {op.WINDOW} games do not: the two "
                 f"halves of a player's games agree at r = {rel['split']:.2f}. "
                 f"Matching on a measure that is mostly noise leaves the rest of the "
                 f"game uncontrolled and credits the opening with it. It would take "
                 f"about {rel['games_for_06']:.0f} games per player.")
    out.append(W.text(note))
    return out


@metric("brackets", title="The opening, band by band", order=41)
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
        ends.append((lo, s["own_op"], depth, s["clock12"]))
        rows.append([f"{lo}–{hi}", s["n"], _num(depth, 0),
                     _num(s["own_op"]), _clock(s["clock12"]), _pct(s["left"]),
                     _num(s["cost"] and s["cost"] / 100, 2)])
    if not rows:
        return None
    (lo0, err0, d0, c0), (lo1, err1, d1, c1) = ends[0], ends[-1]
    trend = (f"From {lo0} to {lo1}, the points given away in the opening fall from "
             f"{err0:.0f} to {err1:.0f} a game and theory depth goes from {d0} to {d1} "
             f"moves, while the clock spent on it stays at about {_clock(c0)}–"
             f"{_clock(c1)}: stronger players know more and err less in the opening, "
             f"without taking longer over it. ")
    return [
        W.text(trend + "Theory depth is the median number of your own book moves, "
               "counted only while the opponent is still in book too. Points are the "
               "engine's win chance given away on your own moves 1–12."),
        W.table(["Band", "Samples", "Theory depth", "Points given away, moves 1–12",
                 "Clock for moves 1–12", "Leave the book first",
                 "What leaving costs (pawns)"], rows),
    ]
