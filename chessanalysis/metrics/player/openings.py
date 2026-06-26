"""Opening explorer: a move tree per color.

At each depth the tree holds every move actually played from that position —
yours on your move, the opponent's on theirs — with how often it occurred and
the W/D/L from your perspective. Drill in to find where a line underperforms.
"""
from ...registry import metric
from ... import widgets as W

MAX_PLY = 16   # ~8 moves each side — the opening/early middlegame


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


@metric("player", title="Openings as White", order=50)
def openings_white(ctx):
    children = _build_tree(ctx.games, "white")
    return W.movetree(children) if children else None


@metric("player", title="Openings as Black", order=51)
def openings_black(ctx):
    children = _build_tree(ctx.games, "black")
    return W.movetree(children) if children else None
