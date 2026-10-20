"""The ladder: what actually changes as rating goes up."""
from ... import widgets as W
from ...corpus import BAND_SIZE, PHASES
from ...registry import metric

PHASE_COLORS = {"Opening": "#8aa4b8", "Middlegame": "#c1573f", "Endgame": "#3f7d5a"}


def _label(band):
    return f"{band}–{band + BAND_SIZE - 1}"


@metric("brackets", title="Every rating range, side by side", order=12)
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
        W.text("Each game counts once for each player, in the range of that player's "
               "rating, so a range's game sides are about twice its games. Accuracy is "
               "shown overall and by phase; game length is shown because it affects "
               "accuracy (short games tend to be cleaner). \"Decided by move\" is the "
               "average move at which the evaluation first reached ±2.00.",
               guide="win-chance-lost", label="What accuracy and ACPL are"),
        W.table(["Rating", "Game sides", "Accuracy", "ACPL", "Moves",
                 "Opening accuracy", "Middlegame accuracy", "Endgame accuracy",
                 "Middlegame blunders per 100 moves", "Decided by move", "Draws"],
                rows),
    ]


@metric("brackets", title="Accuracy by phase, at each rating", order=20)
def phase_curve(ctx):
    """Accuracy in each phase, against rating."""
    if ctx.scope != "ladder":
        return None
    series = []
    for key, label in PHASES:
        pts = [{"x": b["band"], "y": round(b[key + "_acc"], 2)}
               for b in ctx.bands if b[key + "_acc"] is not None]
        if pts:
            series.append({"name": label, "color": PHASE_COLORS[label], "points": pts})
    return W.xyline(series, y_label="Accuracy", x_label="Rating (start of range)")


@metric("brackets", title="Blunders by phase, at each rating", order=30)
def blunder_curve(ctx):
    if ctx.scope != "ladder":
        return None
    series = []
    for key, label in PHASES:
        pts = [{"x": b["band"], "y": round(b[key + "_bl"], 2)}
               for b in ctx.bands if b[key + "_bl"] is not None]
        if pts:
            series.append({"name": label, "color": PHASE_COLORS[label], "points": pts})
    text = "Blunders per 100 moves played in that phase."
    ends = []
    for key, label in PHASES:
        pts = [b[key + "_bl"] for b in ctx.bands if b[key + "_bl"] is not None]
        if len(pts) > 1 and pts[0]:
            ends.append((label.lower(), pts[0], pts[-1]))
    if ends:
        lo, hi = ctx.bands[0]["band"], ctx.bands[-1]["band"]
        most = min(ends, key=lambda e: e[2] - e[1])           # the largest drop
        rel = min(ends, key=lambda e: e[2] / e[1])            # the largest share of it
        text += (f" From {_label(lo)} to {_label(hi)} the {most[0]} rate falls the most, "
                 f"{most[1]:.1f} to {most[2]:.1f}")
        text += (f"; the {rel[0]} rate falls the most in proportion, {rel[1]:.1f} to "
                 f"{rel[2]:.1f}." if rel is not most else " — also the most in proportion.")
    return [
        W.text(text),
        W.xyline(series, y_label="Blunders per 100 moves", x_label="Rating (start of range)",
                 y_zero=True),
    ]


@metric("brackets", title="Coverage", order=90)
def coverage(ctx):
    """Which rating ranges are thin — where the next Expand batch goes."""
    if ctx.scope != "ladder":
        return None
    rows = [{"label": _label(b["band"]),
             "segments": [{"name": "samples", "value": int(b["n"])}],
             "note": f"{int(b['n'])}"} for b in ctx.bands]
    t = ctx.totals
    return [
        W.barstack(rows, {"samples": "#8aa4b8"}),
        W.text(f"Game sides in each rating range: {t['games']} games from "
               f"{t['players']} players; {t['frontier']} more players found and not yet "
               f"visited. Expanding the corpus fills the thinnest ranges first."),
    ]
