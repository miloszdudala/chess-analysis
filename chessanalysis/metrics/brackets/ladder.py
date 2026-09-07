"""The ladder: what actually changes as rating goes up."""
from ... import widgets as W
from ...corpus import BAND_SIZE, PHASES
from ...registry import metric

PHASE_COLORS = {"Opening": "#8aa4b8", "Middlegame": "#c1573f", "Endgame": "#3f7d5a"}


def _label(band):
    return f"{band}–{band + BAND_SIZE - 1}"


@metric("brackets", title="Every band, side by side", order=12)
def table(ctx):
    if ctx.scope != "ladder":
        return None
    rows = []
    for b in ctx.bands:
        rows.append([
            _label(b["band"]), int(b["n"]), f"{b['acc']:.1f}", f"{b['acpl']:.0f}",
            f"{b['plies'] / 2:.0f}",
            f"{b['op_acc']:.1f}", f"{b['mg_acc']:.1f}", f"{b['eg_acc']:.1f}",
            f"{b['mg_bl']:.2f}", f"{b['dec_move']:.0f}",
            f"{100 * int(b['draws']) / int(b['n']):.0f}%",
        ])
    return [
        W.text("Every game contributes both sides, so a band's sample count is "
               "roughly twice the games behind it. Game length is shown because "
               "it confounds accuracy: shorter games are cleaner games."),
        W.table(["Band", "Samples", "Accuracy", "ACPL", "Moves",
                 "Opening", "Middle", "Endgame", "Mid blunders/100", "Decided by move",
                 "Draws"],
                rows),
    ]


@metric("brackets", title="Accuracy by phase, across the ladder", order=20)
def phase_curve(ctx):
    """The opening barely moves with rating and the endgame is flat; the
    middlegame carries the signal. Plotted together, that is the whole story."""
    if ctx.scope != "ladder":
        return None
    series = []
    for key, label in PHASES:
        pts = [{"x": b["band"], "y": round(b[key + "_acc"], 2)}
               for b in ctx.bands if b[key + "_acc"] is not None]
        if pts:
            series.append({"name": label, "color": PHASE_COLORS[label], "points": pts})
    return W.xyline(series, y_label="Accuracy", x_label="Rating band")


@metric("brackets", title="Blunders by phase, across the ladder", order=30)
def blunder_curve(ctx):
    if ctx.scope != "ladder":
        return None
    series = []
    for key, label in PHASES:
        pts = [{"x": b["band"], "y": round(b[key + "_bl"], 2)}
               for b in ctx.bands if b[key + "_bl"] is not None]
        if pts:
            series.append({"name": label, "color": PHASE_COLORS[label], "points": pts})
    return [
        W.text("Per 100 moves played in that phase. This is where rating lives: "
               "the middlegame blunder rate falls faster than any other number here."),
        W.xyline(series, y_label="Blunders / 100 moves", x_label="Rating band",
                 y_zero=True),
    ]


@metric("brackets", title="Coverage", order=90)
def coverage(ctx):
    """Which bands are thin — i.e. where the next Expand batch will be spent."""
    if ctx.scope != "ladder":
        return None
    rows = [{"label": _label(b["band"]),
             "segments": [{"name": "samples", "value": int(b["n"])}],
             "note": f"{int(b['n'])}"} for b in ctx.bands]
    t = ctx.totals
    return [
        W.barstack(rows, {"samples": "#8aa4b8"}),
        W.text(f"{t['games']} games from {t['players']} players; "
               f"{t['frontier']} more players discovered and not yet visited. "
               f"Thin bands are filled first when you expand the database."),
    ]
