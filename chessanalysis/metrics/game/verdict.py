"""The game's verdict (scope="game"): a plain-language reason for the result.

Shown first, above the board — one heuristic sentence on *why* the game was won
or lost (a blunder, a drift, time pressure, an opponent's gift…), with any
secondary contributing factors noted. The reason flag can be corrected by hand
(a dropdown that persists via overrides); the correction also feeds the
aggregate "why you win & lose" view. Needs ctx.analysis (engine output).
"""
from ... import config
from ... import diagnosis as dx
from ... import fairplay
from ... import overrides
from ... import widgets as W
from ...registry import metric

_REASON_TABLES = {"win": dx.WIN_REASONS, "loss": dx.LOSS_REASONS,
                  "draw": dx.DRAW_REASONS}


@metric("game", title="Verdict", order=4, needs=("engine",))
def verdict(ctx):
    cp = int(config.get("DECISIVE_CP", "200"))
    dg = dx.diagnose(ctx.game, ctx.analysis, cp)
    if dg is None:
        return None
    verb = {"win": "won", "loss": "lost", "draw": "drew"}[dg.outcome]
    gid = getattr(ctx.game, "game_id", "")

    primary, headline, detail, manual = dg.primary, dg.headline, dg.detail, False
    ov = overrides.get(gid)
    if ov and ov.get("primary") in _REASON_TABLES[dg.outcome]:
        primary = ov["primary"]
        headline = dx.reason_label(dg.outcome, primary)
        detail = (f"Reason set manually. The automatic read was "
                  f"“{dg.headline}”: {dg.detail}")
        manual = True

    sub = None
    if dg.factors and not manual:
        sub = "also a factor: " + ", ".join(dx.factor_label(f) for f in dg.factors)

    options = [{"key": k, "label": v}
               for k, v in _REASON_TABLES[dg.outcome].items()]
    opp = getattr(ctx.game, "opponent", "")
    cheated = (f"{opp} has since been closed by Chess.com for fair-play "
               f"violations") if opp and fairplay.is_banned(opp) else None
    return W.verdict(gid, f"Why you {verb}", headline, sub, detail,
                     dg.outcome, primary, options, manual,
                     anomalous=overrides.get_flag(gid) is not None,
                     cheated=cheated)
