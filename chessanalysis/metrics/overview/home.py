"""The home page: where you stand, how you compare, what to work on."""
import time

from ... import coach as C
from ... import form as F
from ... import glossary as G
from ... import widgets as W
from ...enrich.engine import win_prob
from ...registry import metric

# where each coach bucket sends you to work on it
ROUTES = {
    "op": ("Explore your openings", "#/openings"),
    "mg": ("Train middlegame positions", "#/train?phase=Middlegame"),
    "eg": ("Train endgame positions", "#/train?phase=Endgame"),
    "ahead": ("Train converting positions", "#/train?theme=Converting"),
    "behind": ("Train defending positions", "#/train?theme=Defending"),
    "level": ("Train your mistakes", "#/train?kind=mistake"),
    "reply": ("Train missed chances", "#/train?kind=missed"),
    "trouble": ("See your clock habits", "#/stats?cat=Time%20management"),
    "low": ("See your clock habits", "#/stats?cat=Time%20management"),
    "comfortable": ("Train your mistakes", "#/train?kind=mistake"),
    "total": ("Train your mistakes", "#/train"),
}


def _place(p):
    if not p:
        return "—"
    if "elo" in p:
        return f"{p['elo']}"
    if "above" in p:
        return f"{p['above']}+"
    return f"<{p['below']}"


def _days_ago(games, days):
    cutoff = time.strftime("%Y.%m.%d", time.gmtime(time.time() - days * 86400))
    before = [g for g in games if g.sort_key < cutoff and g.user_elo_raw]
    return before[-1].user_elo_raw if before else None


@metric("overview", title=None, order=10)
def glance(ctx):
    games = ctx.games
    # the Rating card is Chess.com's number, as the site shows it: every game,
    # flagged ones too, and no cheat-refund correction
    record = ctx.record or games
    elos = [g.user_elo_raw for g in record if g.user_elo_raw]
    cards = []
    if elos:
        then = _days_ago(record, 30)
        sub = (f"{elos[-1] - then:+d} in 30 days" if then else
               f"from {elos[0]} · peak {max(elos)}")
        cards.append(W.card(elos[-1], "Rating", sub=sub))
    cur = F.performance(F.rated(games)[-20:])
    if cur:
        w = cur["wdl"]
        cards.append(W.card(cur["perf"], "Form · last 20",
                            sub=f"{w['win']}-{w['draw']}-{w['loss']} · avg opp {cur['avg_opp']}"))
    pl = (ctx.coach or {}).get("plays_like")
    if pl:
        rec = (ctx.recent or {}).get("plays_like")
        sub = f"95% range {_place(pl['low'])}–{_place(pl['high'])}"
        if rec:
            sub += f" · last {ctx.recent['games']} games ≈{_place(rec['point'])}"
        cards.append(W.card(f"≈{_place(pl['point'])}", "Rating your moves play like",
                            sub=sub))
    t = ctx.training or {}
    if t.get("total"):
        today = t["due"] + min(t["new"], t["new_left_today"])
        cards.append(W.card(today, "To train today",
                            sub=f"{t['due']} due · {t['new']} unseen · {t['learned']} learned"))
    run = F.streak(games)
    if run:
        letter = {"win": "W", "draw": "D", "loss": "L"}[run["outcome"]]
        cards.append(W.card(f"{letter}{run['n']}", "Current streak"))
    return W.cards(cards)


def _range(lo, hi):
    """The 95% range of a relative gap, in words: 'from 48% less to 197% more'."""
    return f"from {G.more_or_less(lo)} to {G.more_or_less(hi)}"


def _detail(r):
    return (f"Your moves here give away {r['you']:.1f}% win chance on average; players "
            f"at your rating {r['peers']:.1f}% — yours is {G.more_or_less(r['gap'])} than "
            f"theirs. Your opponents, in the same games, against players at their rating: "
            f"{G.more_or_less(r['control'])}. So the part put down to you is "
            f"{G.more_or_less(r['net'])}. Measured on {r['moves']} of your moves "
            f"({r['freq_you']:.1f} a game; players at your rating {r['freq_peers']:.1f}). "
            f"95% range: {_range(r['lo'], r['hi'])}.")


def _rows(result):
    return [{"key": r["key"], "label": r["label"], "group": r["group"], "help": r["help"],
             "gap": r["net"], "lo": r["lo"], "hi": r["hi"], "verdict": r["verdict"],
             "moves": r["moves"], "detail": _detail(r), "raw": r["gap"],
             "control": r["control"]}
            for r in result["rows"]]


@metric("overview", title="Win chance lost vs players at your rating", order=20)
def comparison(ctx):
    from ... import corpus

    res = ctx.coach
    tc = G.time_control_label(corpus.TIME_CONTROL)
    if not res:
        msg = ("The comparison needs your games analysed at the depth the other "
               f"players' games were ({ctx.pending} still to go — they are being "
               f"analysed in the background) and enough of their games (Peers → "
               f"Expand the corpus).")
        if ctx.time_class and ctx.time_class != "rapid":
            msg = (f"The other players' games are {tc} games, so this comparison "
                   f"covers rapid only.")
        return W.text(msg)
    lo, hi = res["elo_range"]
    variants = [{"label": f"All {res['games']} games", "rows": _rows(res)}]
    if ctx.recent:
        variants.append({"label": f"Last {ctx.recent['games']}", "rows": _rows(ctx.recent)})
    chart = W.gapchart(variants[0]["rows"], note=(
        "Each bar: how much more (right — worse) or less (left — better) win chance "
        "your moves give away than players at your rating, after the correction for "
        "your opponents. The thin line is the 95% range: a row is called a strength "
        "or a weakness only when the whole range sits on one side of the centre. "
        "\"Unclear\" means the moves measured so far cannot tell which side it is "
        "on, however large the bar; \"too few moves\" means the range spans more "
        "than 100% (say, from 40% less to 70% more)."))
    chart["variants"] = variants
    intro = (f"How much win chance your moves give away, against other players' {tc} "
             f"games. Each of your {res['games']} games (rated {lo}–{hi}) is compared "
             f"with players at the rating you had in that game: {res['peers']} game "
             f"sides, analysed by the same engine at the same depth. Win chance is the "
             f"evaluation as a percentage (0.00 is 50%, +1.00 about "
             f"{win_prob(100):.0f}%); a move's cost is how far it lowers yours.")
    pl = res.get("plays_like")
    if pl and pl.get("point"):
        intro += (f" \"Rating your moves play like\" (≈{_place(pl['point'])}) is the "
                  f"rating at which players give away as much win chance per move as "
                  f"you do, after the same correction.")
    if ctx.pending:
        intro += f" {ctx.pending} recent games are still being analysed."
    return [W.text(intro, guide="win-chance-lost", label="What win chance means"),
            chart]


@metric("overview", title="Strengths and weaknesses", order=25)
def focus(ctx):
    items = []
    res = ctx.coach
    if res:
        f = C.focus(res)
        # every item states the same measured facts; the tone is the only
        # judgement, and it is the 95% range's: wholly above, below, or across 0
        for tone, rows in (("leak", f["leaks"]), ("strength", f["strengths"]),
                           ("lean", [] if f["leaks"] else f["leaning"])):
            side = {"leak": "lies wholly above", "strength": "lies wholly below",
                    "lean": "includes"}[tone]
            for r in rows:
                label, route = ROUTES.get(r["key"], ROUTES["total"])
                items.append({
                    "tone": tone,
                    "title": f"{r['label']}: {G.more_or_less(r['net'])} win chance lost",
                    "body": f"{r['help']} Measured on {r['moves']} of your moves "
                            f"against players at your rating. The 95% range, "
                            f"{_range(r['lo'], r['hi'])}, {side} their figure.",
                    "action": None if tone == "strength" else {"label": label, "route": route}})
    t = ctx.training or {}
    if t.get("total"):
        kinds = t["by_kind"]
        body = ", ".join(f"{v['total']} {t['kinds'][k].lower()}" for k, v in kinds.items()
                         if v["total"])
        items.append({"tone": "info", "title": f"{t['total']} positions from your own games",
                      "body": f"{body}. {t['due']} due now, {t['new']} not yet seen.",
                      "action": {"label": "Start training", "route": "#/train"}})
    return W.focus(items) if items else None


@metric("overview", title="Recent games", order=30)
def recent(ctx):
    games = ctx.games[-40:]
    if not games:
        return None
    return W.timeline([{"outcome": g.outcome, "id": g.game_id,
                        "label": f"{g.date} · {g.color} vs {g.opponent} "
                                 f"({g.opp_elo or '?'}) · {g.outcome}"} for g in games],
                      title=f"Last {len(games)} games, oldest to newest — click one to review")


@metric("overview", title="Rating", order=35)
def rating(ctx):
    pts = [{"x": g.date, "y": g.user_elo} for g in ctx.games if g.user_elo]
    if len(pts) < 2:
        return None
    line = W.line([{"name": ctx.player, "points": pts}], y_label="Elo")
    line["ma"] = True
    return line
