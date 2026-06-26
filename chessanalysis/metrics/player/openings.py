"""Opening explorer: a move tree per color.

At each depth the tree holds every move actually played from that position —
yours on your move, the opponent's on theirs — with how often it occurred and
the W/D/L from your perspective. Drill in to find where a line underperforms.
"""
from collections import Counter

from ...registry import metric
from ... import widgets as W
from ...util import WDL

MAX_PLY = 16   # ~8 moves each side — the opening/early middlegame
REPERTOIRE_MIN = 6   # an opening needs at least this many games to be worth judging


def _build_tree(games, color):
    roots: dict = {}
    for g in games:
        if g.color != color:
            continue
        level = roots
        for ply, mv in enumerate(g.moves[:MAX_PLY], start=1):
            node = level.get(mv.san)
            if node is None:
                mine = (ply % 2 == 1) if color == "white" else (ply % 2 == 0)
                node = {"move": mv.san, "count": 0, "w": 0, "d": 0, "l": 0,
                        "mine": mine, "_kids": {}}
                level[mv.san] = node
            node["count"] += 1
            node["w" if g.outcome == "win" else
                 "d" if g.outcome == "draw" else "l"] += 1
            level = node["_kids"]

    def finalize(d):
        out = []
        for node in sorted(d.values(), key=lambda x: -x["count"]):
            node["children"] = finalize(node.pop("_kids"))
            out.append(node)
        return out

    return finalize(roots)


@metric("player", title="Openings as White", order=40, category="Openings")
def openings_white(ctx):
    children = _build_tree(ctx.games, "white")
    return W.movetree(children) if children else None


@metric("player", title="Openings as Black", order=41, category="Openings")
def openings_black(ctx):
    children = _build_tree(ctx.games, "black")
    return W.movetree(children) if children else None


def _opening_family(name: str) -> str:
    """Reduce a Chess.com opening name to its root family (first two words).

    'Giuoco Piano Game Giuoco Pianissimo 4.d3' -> 'Giuoco Piano'. Move notation
    is dropped and only the root is kept so individual sub-lines aggregate into
    a recognisable, usefully-sized family (e.g. 'Ruy Lopez', 'Sicilian Defense').
    """
    out = []
    for tok in name.split(" "):
        if tok[:1].isdigit():        # stop at the first move-number token
            break
        out.append(tok)
        if len(out) == 2:
            break
    return " ".join(out) or name


@metric("player", title="Opening repertoire", order=45, category="Openings")
def opening_repertoire(ctx):
    """Your most-played openings, scored against your overall baseline.

    Grouped by opening family (so individual sub-lines aggregate into a usable
    sample) and gated at REPERTOIRE_MIN games, so single noisy games can't pose
    as a 'weakness'. The 'vs avg' column shows over/under-performance honestly:
    a line is only a real problem if it lags your own baseline by a clear margin.
    """
    overall = WDL()
    for g in ctx.games:
        overall.add(g.outcome)
    if not overall.total:
        return None
    base = overall.score

    fam: dict = {}    # family name -> {wdl, color Counter}
    for g in ctx.games:
        name = _opening_family(g.opening)
        if not name or name == "?":
            continue
        f = fam.setdefault(name, {"wdl": WDL(), "color": Counter()})
        f["wdl"].add(g.outcome)
        f["color"][g.color] += 1

    rows = []
    for name, d in fam.items():
        w = d["wdl"]
        if w.total < REPERTOIRE_MIN:
            continue
        color = d["color"].most_common(1)[0][0].title()
        rows.append([name[:42], color, w.total, f"{w.win}-{w.draw}-{w.loss}",
                     f"{100 * w.score:.0f}%", f"{100 * (w.score - base):+.0f}%",
                     {"bar": [w.win, w.draw, w.loss]}])
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: -r[2])       # most-played first
    return [
        W.text(f"Your repertoire vs your overall score ({100 * base:.0f}%). "
               "“vs avg” is what matters: a negative figure across enough games "
               "is a line genuinely costing you points."),
        W.table(["Opening", "Color", "Games", "W-D-L", "Score", "vs avg", ""], rows),
    ]
