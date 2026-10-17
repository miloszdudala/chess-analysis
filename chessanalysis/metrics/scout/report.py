"""Scouting an opponent: what they play, how their games end, how they use
the clock — and how your own games went in the lines they choose.

Engine-free on purpose: it reads the PGN headers, moves and clocks of their
recent games, so a report on any account is ready as soon as its games are
downloaded. Clock habits are set against corpus players at their rating, so
"30% of games in time trouble" comes with what that number usually is.
"""
from collections import Counter, defaultdict

from ... import form as F
from ... import widgets as W
from ...clocks import TIME_TROUBLE_FRAC, clock_profile
from ...registry import metric
from ...util import WDL



def _wdl(games):
    r = WDL()
    for g in games:
        r.add(g.outcome)
    return r


def _score(r: WDL):
    return f"{100 * r.score:.0f}%" if r.total else "—"


def _rec(r: WDL):
    return f"{r.win}-{r.draw}-{r.loss}"


@metric("scout", title=None, order=10)
def headline(ctx):
    games = ctx.games
    if not games:
        return W.text(f"No {ctx.time_class or ''} games found for {ctx.opponent} "
                      f"in the last {ctx.months} months.")
    elos = [g.user_elo for g in games if g.user_elo]
    rec = _wdl(games)
    cur = F.performance(F.rated(games)[-20:])
    run = F.streak(games)
    cards = [
        W.card(elos[-1] if elos else "—", "Rating now",
               sub=f"peak {max(elos)}" if elos else None),
        W.card(len(games), "Games", sub=f"last {ctx.months} months"),
        W.card(_score(rec), "Score", sub=_rec(rec)),
    ]
    if cur:
        cards.append(W.card(cur["perf"], "Form (last 20)",
                            sub=f"avg opponent {cur['avg_opp']}"))
    if run:
        letter = {"win": "W", "draw": "D", "loss": "L"}[run["outcome"]]
        cards.append(W.card(f"{letter}{run['n']}", "Current streak"))
    return W.cards(cards)


@metric("scout", title="Rating", order=12)
def rating(ctx):
    pts = [{"x": g.date, "y": g.user_elo} for g in ctx.games if g.user_elo]
    if len(pts) < 2:
        return None
    line = W.line([{"name": ctx.opponent, "points": pts}], y_label="Elo")
    line["ma"] = True
    return line


def _first(g, color):
    """Their first move as White, or their reply to White's first as Black."""
    i = 0 if color == "white" else 1
    return g.moves[i].san if len(g.moves) > i else None


def _your_record(mine, opening_moves: tuple, your_color: str):
    """Your games as `your_color` that began with `opening_moves` (SAN)."""
    out = [g for g in mine if g.color == your_color and len(g.moves) >= len(opening_moves)
           and tuple(m.san for m in g.moves[:len(opening_moves)]) == opening_moves]
    return _wdl(out)


@metric("scout", title="What they play", order=20)
def repertoire(ctx):
    games = ctx.games
    if not games:
        return None
    widgets = []
    as_white = [g for g in games if g.color == "white"]
    if as_white:
        first = Counter(_first(g, "white") for g in as_white if _first(g, "white"))
        rows = []
        for mv, n in first.most_common(5):
            theirs = _wdl([g for g in as_white if _first(g, "white") == mv])
            yours = _your_record(ctx.mine, (mv,), "black")
            rows.append([f"1.{mv}", f"{n} ({100 * n / len(as_white):.0f}%)",
                         _score(theirs), {"bar": [theirs.win, theirs.draw, theirs.loss]},
                         f"{yours.total} · {_score(yours)}" if yours.total else "—"])
        widgets += [W.text(f"As White ({len(as_white)} games). The last column is your "
                           f"own record as Black after the same first move."),
                    W.table(["They open", "Games", "Their score", "",
                             "You, as Black, vs this"], rows)]
    as_black = [g for g in games if g.color == "black"]
    if as_black:
        rows = []
        by_first = defaultdict(list)
        for g in as_black:
            if g.moves:
                by_first[g.moves[0].san].append(g)
        for wm, gs in sorted(by_first.items(), key=lambda kv: -len(kv[1]))[:3]:
            replies = Counter(_first(g, "black") for g in gs if _first(g, "black"))
            for rm, n in replies.most_common(3):
                theirs = _wdl([g for g in gs if _first(g, "black") == rm])
                yours = _your_record(ctx.mine, (wm, rm), "white")
                rows.append([f"1.{wm} {rm}", f"{n} of {len(gs)}", _score(theirs),
                             {"bar": [theirs.win, theirs.draw, theirs.loss]},
                             f"{yours.total} · {_score(yours)}" if yours.total else "—"])
        widgets += [W.text(f"As Black ({len(as_black)} games): their answer to each "
                           f"first move, and your own record as White in that line."),
                    W.table(["Line", "Games", "Their score", "",
                             "You, as White, here"], rows)]
    return widgets or None


@metric("scout", title="Their openings by name", order=22)
def families(ctx):
    from ... import explorer

    rows = []
    for color in ("white", "black"):
        for f in explorer.repertoire(ctx.opponent, color, ctx.time_class, min_games=2)[:6]:
            rows.append([f["name"], color.title(), f["games"], f"{100 * f['score']:.0f}%",
                         f["line"], f"{f['book']:.1f}"])
    if not rows:
        return None
    return [W.table(["Opening", "Colour", "Games", "Their score", "Usual line",
                     "Book moves"], rows),
            W.actions([{"label": "Explore their games as White",
                        "route": f"#/scout/{ctx.opponent}/explore/white"},
                       {"label": "Explore their games as Black",
                        "route": f"#/scout/{ctx.opponent}/explore/black"}])]


def _ending(g):
    t = g.termination.lower()
    if "checkmate" in t:
        return "checkmate"
    if "resign" in t:
        return "resignation"
    if "time" in t:
        return "time"
    if "abandon" in t:
        return "abandoned"
    if "repetition" in t:
        return "repetition"
    if "agreement" in t:
        return "agreement"
    if "insufficient" in t or "stalemate" in t or "50" in t:
        return "dead position"
    return "other"


@metric("scout", title="How their games end", order=30)
def endings(ctx):
    if not ctx.games:
        return None
    pal = {"checkmate": "#3f7d5a", "resignation": "#8aa4b8", "time": "#c9a227",
           "abandoned": "#9b958a", "repetition": "#7d6b9e", "agreement": "#cbc3b2",
           "dead position": "#b9b09c", "other": "#ddd"}
    rows = []
    for outcome, label in (("win", "They won"), ("loss", "They lost"), ("draw", "Drawn")):
        gs = [g for g in ctx.games if g.outcome == outcome]
        if not gs:
            continue
        c = Counter(_ending(g) for g in gs)
        rows.append({"label": f"{label} ({len(gs)})",
                     "segments": [{"name": k, "value": c.get(k, 0)} for k in pal if c.get(k)]})
    short = [g for g in ctx.games if g.outcome == "loss" and len(g.moves) < 50]
    out = [W.barstack(rows, pal)]
    losses = sum(1 for g in ctx.games if g.outcome == "loss")
    if losses:
        out.append(W.text(f"{len(short)} of their {losses} losses were over inside 25 "
                          f"moves — a measure of how often they collapse early."))
    return out


def _clock_stats(games, color_of):
    n = tt = 0
    end = []
    for g in games:
        pp = clock_profile(g, color_of(g))
        if not pp:
            continue
        n += 1
        end.append(pp.end_frac)
        tt += pp.min_frac < TIME_TROUBLE_FRAC
    return n, tt, end


@metric("scout", title="The clock", order=35)
def clock(ctx):
    games = ctx.games
    n, tt, end = _clock_stats(games, lambda g: g.color)
    if n < 5:
        return None
    lost_time = sum(1 for g in games if g.outcome == "loss" and _ending(g) == "time")
    won_time = sum(1 for g in games if g.outcome == "win" and _ending(g) == "time")
    band = _band_clock(games)
    sub = (f"players at their rating: {100 * band[1] / band[0]:.0f}%"
           if band and band[0] else None)
    cards = [
        W.card(f"{100 * tt / n:.0f}%", "Games in time trouble",
               sub=sub or f"clock under {int(TIME_TROUBLE_FRAC * 100)}%"),
        W.card(f"{100 * sum(end) / len(end):.0f}%", "Clock left at the end",
               sub=(f"band: {100 * sum(band[2]) / len(band[2]):.0f}%"
                    if band and band[2] else None)),
        W.card(f"{won_time} / {lost_time}", "Won / lost on time"),
    ]
    return W.cards(cards)


_BAND_CLOCK: dict = {}


def _band_clock(games):
    """(sides, in time trouble, end fractions) for corpus players at their
    rating — the same clock figures, for comparison."""
    from ... import store
    from ...model import parse_pgn_text

    elos = [g.user_elo for g in games if g.user_elo]
    if not elos:
        return None
    elo = elos[-1] // 50 * 50
    if elo in _BAND_CLOCK:
        return _BAND_CLOCK[elo]
    rows = store.connect().execute(
        "SELECT pgn, welo, belo FROM games WHERE source='corpus' AND "
        "(welo BETWEEN ? AND ? OR belo BETWEEN ? AND ?) LIMIT 600",
        (elo - 100, elo + 100, elo - 100, elo + 100)).fetchall()
    sides = []
    for r in rows:
        parsed = parse_pgn_text(store.unpack_pgn(r["pgn"]))
        if not parsed:
            continue
        for color, e in (("white", r["welo"]), ("black", r["belo"])):
            if e is not None and elo - 100 <= e <= elo + 100:
                sides.append((parsed[0], color))
    if len(sides) < 50:
        _BAND_CLOCK[elo] = None
        return None
    n, tt, end = 0, 0, []
    for g, color in sides:
        pp = clock_profile(g, color)
        if not pp:
            continue
        n += 1
        tt += pp.min_frac < TIME_TROUBLE_FRAC
        end.append(pp.end_frac)
    _BAND_CLOCK[elo] = (n, tt, end)
    return _BAND_CLOCK[elo]


@metric("scout", title="Head to head", order=40)
def head_to_head(ctx):
    h2h = ctx.head_to_head
    if not ctx.me:
        return None
    if not h2h:
        return W.text(f"You have not played {ctx.opponent} yet.")
    rec = _wdl(h2h)
    rows = [{"cells": [g.date, g.color.title(), {"w": "✓", "l": "✗"}.get(g.outcome[0], "="),
                       g.opening[:40]],
             "games": [{"id": g.game_id, "ply": None, "date": g.date,
                        "opponent": ctx.opponent, "outcome": g.outcome,
                        "note": g.termination}]}
            for g in reversed(h2h)]
    return [W.cards([W.card(_rec(rec), "Your record against them",
                            sub=f"{_score(rec)} in {rec.total} games")]),
            W.drilltable(["Date", "You had", "Result", "Opening"], rows)]
