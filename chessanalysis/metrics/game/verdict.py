"""The game's verdict (scope="game"): a plain-language reason for the result.

Shown first, above the board — one heuristic sentence on *why* the game was won
or lost (a blunder, a drift, time pressure, an opponent's gift…), with any
secondary contributing factors noted. Needs ctx.analysis (engine output).
"""
from ... import config
from ... import diagnosis as dx
from ... import widgets as W
from ...registry import metric


@metric("game", title="Verdict", order=4, needs=("engine",))
def verdict(ctx):
    cp = int(config.get("DECISIVE_CP", "200"))
    dg = dx.diagnose(ctx.game, ctx.analysis, cp)
    if dg is None:
        return None
    verb = {"win": "won", "loss": "lost", "draw": "drew"}[dg.outcome]
    sub = None
    if dg.factors:
        sub = "also a factor: " + ", ".join(dx.factor_label(f) for f in dg.factors)
    return [
        W.cards([W.card(dg.headline, f"Why you {verb}", sub=sub)]),
        W.text(dg.detail),
    ]
