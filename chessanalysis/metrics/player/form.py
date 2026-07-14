"""Form: how strongly you're playing right now vs your best/worst stretches.

Built on FIDE performance ratings (form.performance) over sliding windows of
rated games — independent of the Elo the rating system shows, and comparable
across time. Engine-free.
"""
from ...registry import metric
from ... import form as F
from ... import widgets as W

WINDOW = 20                 # the headline window for cards & peak list
CHART_WINDOWS = (10, 20, 30)  # switchable in the chart ("dynamic windows")


def _range(p):
    return f"{p['start']} – {p['end']}"


def _score_sub(p):
    w = p["wdl"]
    return f"{w['win']}-{w['draw']}-{w['loss']} · avg opp {p['avg_opp']}"


@metric("player", title="Form", order=19, category="Results & form")
def form(ctx):
    games = F.rated(ctx.games)                      # rated, chronological
    if len(games) < F.MIN_RATED:
        return None

    cur = F.performance(games[-WINDOW:])
    short = F.performance(games[-10:])
    best = F.peaks(games, WINDOW, k=1)     # the peak-form card only
    worst = F.slump(games, WINDOW)
    run = F.streak(games)

    cards = [W.card(cur["perf"] if cur else "—", f"Current form (last {WINDOW})",
                    sub=_score_sub(cur) if cur else "not enough rated games")]
    if short:
        cards.append(W.card(short["perf"], "Last 10 games",
                            sub=_score_sub(short)))
    if best:
        cards.append(W.card(best[0]["perf"], "Peak form",
                            sub=_range(best[0])))
    if worst and (not best or worst["perf"] < best[0]["perf"]):
        cards.append(W.card(worst["perf"], "Deepest slump",
                            sub=_range(worst)))
    if run:
        letter = {"win": "W", "draw": "D", "loss": "L"}[run["outcome"]]
        cards.append(W.card(f"{letter}{run['n']}", "Current streak"))
    widgets = [
        W.text("Form = FIDE performance rating: the average rating of your "
               "opposition plus the FIDE conversion of your score against "
               "them — how strongly you actually played in a stretch, "
               "regardless of what your Elo was doing."),
        W.cards(cards),
    ]

    # rolling performance chart with switchable window sizes; each point maps
    # (via i0/i1) into this roster so a click can list the window's games
    variants = []
    for wnd in CHART_WINDOWS:
        pts = F.rolling(games, wnd)
        if len(pts) >= 2:
            variants.append({"label": f"{wnd} games", "points": pts,
                             "default": wnd == WINDOW})
    if variants:
        if not any(v.get("default") for v in variants):
            variants[-1]["default"] = True
        line = W.line([{"name": "Performance",
                        "points": variants[0]["points"]}], y_label="Performance")
        line["variants"] = variants
        line["games"] = [{
            "id": getattr(g, "game_id", ""), "date": g.date,
            "opponent": g.opponent, "opp_elo": g.opp_elo, "outcome": g.outcome,
        } for g in games]
        widgets.append(line)

    recent = ctx.games[-60:]
    widgets.append(W.timeline(
        [{"outcome": g.outcome,
          "label": f"{g.date} vs {g.opponent} · {g.outcome}"} for g in recent],
        title=f"Recent form — last {len(recent)} games (oldest → newest)"))
    return widgets
