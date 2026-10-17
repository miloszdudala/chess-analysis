"""The home page: where you stand, how you compare, what to work on."""
import time

from ... import coach as C
from ... import form as F
from ... import widgets as W
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
    before = [g for g in games if g.sort_key < cutoff and g.user_elo]
    return before[-1].user_elo if before else None


@metric("overview", title=None, order=10)
def glance(ctx):
    games = ctx.games
    elos = [g.user_elo for g in games if g.user_elo]
    cards = []
    if elos:
        then = _days_ago(games, 30)
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
        sub = f"range {_place(pl['low'])}–{_place(pl['high'])}"
        if rec:
            sub = f"last {ctx.recent['games']}: ≈{_place(rec['point'])} · " + sub
        cards.append(W.card(f"≈{_place(pl['point'])}", "Your moves play like", sub=sub))
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


def _detail(r):
    return (f"You lose {r['you']:.2f} win-chance points a move here; players at your "
            f"rating {r['peers']:.2f} ({100 * r['gap']:+.0f}%). Your opponents, in "
            f"the same games, against players at their rating: "
            f"{100 * r['control']:+.0f}%. Moves a game here: you {r['freq_you']:.1f}, "
            f"peers {r['freq_peers']:.1f}.")


def _rows(result):
    return [{"key": r["key"], "label": r["label"], "group": r["group"], "help": r["help"],
             "gap": r["net"], "lo": r["lo"], "hi": r["hi"], "verdict": r["verdict"],
             "detail": _detail(r), "raw": r["gap"], "control": r["control"]}
            for r in result["rows"]]


@metric("overview", title="You against players at your rating", order=20)
def comparison(ctx):
    res = ctx.coach
    if not res:
        msg = ("The peer comparison needs your games analysed at the corpus depth "
               f"({ctx.pending} still to go — they are being analysed in the "
               f"background) and a filled corpus (Peers → Expand database).")
        if ctx.time_class and ctx.time_class != "rapid":
            msg = ("The rating corpus holds 10-minute games, so the peer comparison "
                   "covers rapid only.")
        return W.text(msg)
    lo, hi = res["elo_range"]
    variants = [{"label": f"All {res['games']} games", "rows": _rows(res)}]
    if ctx.recent:
        variants.append({"label": f"Last {ctx.recent['games']}", "rows": _rows(ctx.recent)})
    chart = W.gapchart(variants[0]["rows"], note=(
        "Bars: how much more (right) or less (left) win chance you lose per move "
        "than players at your rating, with your opponents' same figure taken out "
        "as a control. Whiskers: 95% interval."))
    chart["variants"] = variants
    intro = (f"Every one of your {res['games']} games ({lo}–{hi}) is set against "
             f"corpus players at the rating you had in that game — {res['peers']} "
             f"game sides, same engine, depth {res['depth']}, same 10-minute "
             f"control. The measure is the win chance each move gives away. Results "
             f"are not compared: inside a band everyone scores about 50%.")
    if ctx.pending:
        intro += f" {ctx.pending} recent games are still being analysed."
    return [W.text(intro), chart]


@metric("overview", title="What to work on", order=25)
def focus(ctx):
    items = []
    res = ctx.coach
    if res:
        f = C.focus(res)
        for r in f["leaks"]:
            label, route = ROUTES.get(r["key"], ROUTES["total"])
            items.append({"tone": "leak", "title": f"{r['label']}: {100 * r['net']:+.0f}%",
                          "body": f"{r['help']} You lose more here than players at your "
                                  f"rating, beyond what noise explains "
                                  f"({100 * r['lo']:+.0f}% to {100 * r['hi']:+.0f}%).",
                          "action": {"label": label, "route": route}})
        for r in f["strengths"]:
            items.append({"tone": "strength", "title": f"{r['label']}: {100 * r['net']:+.0f}%",
                          "body": f"{r['help']} A clear strength against players at your "
                                  f"rating ({100 * r['lo']:+.0f}% to {100 * r['hi']:+.0f}%).",
                          "action": None})
        if not f["leaks"]:
            lean = ", ".join(f"{r['label'].lower()} ({100 * r['net']:+.0f}%)"
                             for r in f["leaning"]) or "nothing in particular"
            items.append({"tone": "lean", "title": "No leak clears the noise",
                          "body": f"With {res['games']} games no area is clearly worse than "
                                  f"your peers'. Leaning that way: {lean}. More games "
                                  f"narrow the intervals.", "action": None})
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
