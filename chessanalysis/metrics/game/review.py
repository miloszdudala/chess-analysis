"""Game-review metrics (scope="game"): need ctx.analysis (engine output)."""
import chess
import chess.svg

from ... import config
from ...registry import metric
from ... import widgets as W


def _acc(a, side):
    v = a.accuracy.get(side)
    return f"{v:.1f}%" if v is not None else "—"


@metric("game", title="Board", order=5, needs=("engine",))
def board_explorer(ctx):
    """Interactive move-by-move board: navigate, see eval + top-3 engine moves."""
    g, a = ctx.game, ctx.analysis
    if len(a.fens) < 2:
        return None

    positions = []
    for i, fen in enumerate(a.fens):
        cp = a.evals[i] if i < len(a.evals) else 0
        tops = a.top_moves[i] if i < len(a.top_moves) else []
        best = []
        try:
            b = chess.Board(fen)
            for t in tops[:3]:
                try:
                    mv = chess.Move.from_uci(t["uci"])
                    best.append({"uci": t["uci"], "san": b.san(mv), "cp": t["cp"]})
                except (ValueError, AssertionError):
                    continue
        except ValueError:
            pass
        positions.append({"fen": fen, "cp": cp, "best": best})

    moves = [{
        "san": m.san, "uci": m.move_uci, "label": m.label,
        "cp_loss": m.cp_loss, "wp_loss": round(m.wp_loss, 1), "best_san": m.best_san,
    } for m in a.moves]

    return W.review(positions, moves, g.color, g.h("White"), g.h("Black"))


def _top3(a, side):
    v = a.top3.get(side)
    return f"{v:.0f}%" if v is not None else "—"


@metric("game", title=None, order=10, needs=("engine",))
def summary(ctx):
    g, a = ctx.game, ctx.analysis
    white, black = g.h("White"), g.h("Black")
    return W.cards([
        W.card(_acc(a, "white"), "White accuracy", sub=white),
        W.card(_acc(a, "black"), "Black accuracy", sub=black),
        W.card(_top3(a, "white"), "White top-3 match", sub="moves in engine's top 3"),
        W.card(_top3(a, "black"), "Black top-3 match", sub="moves in engine's top 3"),
        W.card(a.acpl.get("white"), "White ACPL"),
        W.card(a.acpl.get("black"), "Black ACPL"),
        W.card(len(a.blunders()), "Blunders (both)"),
    ])


@metric("game", title="Conversion", order=15, needs=("engine",))
def conversion(ctx):
    cp = int(config.get("DECISIVE_CP", "200"))
    d = ctx.analysis.decisive(cp)
    thr = f"{cp / 100:.1f}"
    if not d["reached"]:
        return W.cards([W.card("—", f"Decisive (±{thr})",
                               sub=f"stayed within ±{thr}")])
    ticker = "held ✓" if d["held"] else "lost ✗"
    return W.cards([W.card(
        f"move {d['move_no']}", f"Decisive (±{thr})",
        sub=f"{d['side'].title()} · {ticker}")])


@metric("game", title="Evaluation", order=20, needs=("engine",))
def eval_graph(ctx):
    a = ctx.analysis
    if len(a.evals) < 2:
        return None
    plies = [{"ply": 0, "cp": a.evals[0], "label": "ok"}]
    for i, m in enumerate(a.moves):
        plies.append({"ply": i + 1, "cp": a.evals[i + 1], "label": m.label})
    return W.evalbar(plies, [m.san for m in a.moves])


# move-quality palette (also fixes legend order), shared with the chart below
QUALITY_PALETTE = {
    "best": "#3f9d5a", "good": "#9bbf6a", "inaccuracy": "#c69a16",
    "mistake": "#e08a2b", "blunder": "#d0493b",
}


def _quality_counts(analysis, side):
    """Per-side move counts split into best / good / inaccuracy / mistake / blunder.

    "best" = the move matched the engine's top choice; the rest of the clean
    moves are "good"; the three error tiers come straight from the labels.
    """
    counts = {k: 0 for k in QUALITY_PALETTE}
    for m in analysis.moves:
        if m.color != side:
            continue
        if m.label in ("inaccuracy", "mistake", "blunder"):
            counts[m.label] += 1
        elif m.best_san and m.san == m.best_san:
            counts["best"] += 1
        else:
            counts["good"] += 1
    return counts


@metric("game", title="Move quality", order=30, needs=("engine",))
def move_quality(ctx):
    a = ctx.analysis
    # 1) visual breakdown of every move by quality, per side
    rows = [{"label": side.title(),
             "segments": [{"name": k, "value": v}
                          for k, v in _quality_counts(a, side).items()]}
            for side in ("white", "black")]
    chart = W.barstack(rows, QUALITY_PALETTE, title="Every move, classified")
    # 2) the accuracy / top-3 / ACPL / error-count table
    cols = ["Side", "Accuracy", "Top-3 match", "ACPL",
            "Inaccuracies", "Mistakes", "Blunders"]
    table_rows = []
    for side in ("white", "black"):
        c = a.counts[side]
        t3 = a.top3.get(side)
        table_rows.append([
            side.title(), _acc(a, side), f"{t3:.0f}%" if t3 is not None else "—",
            a.acpl.get(side), c["inaccuracy"], c["mistake"], c["blunder"],
        ])
    return [chart, W.table(cols, table_rows)]


# --- tactical misses vs. positional drift -----------------------------------
# A tactical miss is one move that drops a lot at once (a missed forced line);
# positional drift is a run of consecutive small losses — slow strategic decline.
TACTICAL_CP = 150               # single-move centipawn loss = a tactical miss
DRIFT_LO, DRIFT_HI = 15, 90     # per-move loss band that counts as "small"
DRIFT_MIN = 4                   # this many small losses in a row = a drift episode


def _drift_runs(side_moves):
    """Maximal runs of consecutive small-loss moves (>= DRIFT_MIN long)."""
    runs, cur = [], []
    for m in side_moves:
        if DRIFT_LO <= m.cp_loss <= DRIFT_HI:
            cur.append(m)
        else:
            if len(cur) >= DRIFT_MIN:
                runs.append(cur)
            cur = []
    if len(cur) >= DRIFT_MIN:
        runs.append(cur)
    return runs


def _move_label(m):
    return f"{(m.ply + 1) // 2}{'.' if m.ply % 2 else '…'}"


@metric("game", title="Tactical vs positional", order=35, needs=("engine",))
def error_profile(ctx):
    a = ctx.analysis
    if not a.moves:
        return None

    rows = []
    for side in ("white", "black"):
        sm = [m for m in a.moves if m.color == side]
        tactical = [m for m in sm if m.cp_loss >= TACTICAL_CP]
        runs = _drift_runs(sm)
        longest = max((len(r) for r in runs), default=0)
        rows.append([side.title(), len(tactical), len(runs), longest or "—"])
    table = W.table(
        ["Side", "Tactical misses", "Drift episodes", "Longest drift"], rows)

    explain = W.text(
        f"Tactical misses are single moves that lose ≥{TACTICAL_CP / 100:.1f} "
        f"pawns at once (a missed forced sequence). Positional drift is "
        f"{DRIFT_MIN}+ moves in a row each bleeding {DRIFT_LO}–{DRIFT_HI}cp — "
        f"slow strategic decline rather than a single blunder.")

    # narrative for the analysed player's own side
    me = ctx.game.color
    runs = _drift_runs([m for m in a.moves if m.color == me])
    if runs:
        spans = "; ".join(
            f"{_move_label(r[0])}–{_move_label(r[-1])} "
            f"(−{sum(m.cp_loss for m in r)}cp over {len(r)} moves)" for r in runs)
        note = W.text(f"Your positional drift: {spans}.")
    else:
        note = W.text("No positional drift on your side — your inaccuracies were "
                      "isolated rather than sustained.")
    return [explain, table, note]


@metric("game", title="Depth-dependent errors", order=37, needs=("engine",))
def depth_delta(ctx):
    """Moves a shallow search is happy with that a deeper search refutes.

    Re-analyses the game at a shallower depth and compares move-by-move: a move
    classified 'ok' shallow but a mistake/blunder at the review depth was chosen
    on superficial calculation — refuted only by a deeper, non-obvious line.
    """
    from ...enrich import engine as eng
    a_hi = ctx.analysis
    low = max(6, a_hi.depth - 6)
    if not a_hi.moves or a_hi.depth - low < 4:
        return None

    a_lo = eng.analyse_game(ctx.game, depth=low)
    lo_label = {m.ply: m.label for m in a_lo.moves}
    flips = {"white": [], "black": []}
    for m in a_hi.moves:
        if lo_label.get(m.ply) == "ok" and m.label in ("mistake", "blunder"):
            flips[m.color].append(m)

    explain = W.text(
        f"A shallow search (depth {low}) is compared against the review depth "
        f"({a_hi.depth}). Moves the shallow engine likes but the deeper one flags "
        f"reveal combinations refuted only by deeper, non-obvious continuations.")
    table = W.table(
        ["Side", f"Fine at d{low}, error at d{a_hi.depth}"],
        [[s.title(), len(flips[s])] for s in ("white", "black")])

    me = ctx.game.color
    if flips[me]:
        spans = "; ".join(f"{_move_label(m)} {m.san} ({m.label})" for m in flips[me])
        note = W.text(f"Your depth-dependent errors: {spans}.")
    else:
        note = W.text(f"None of your moves flipped from fine at depth {low} to an "
                      f"error at depth {a_hi.depth} — your calculation held up.")
    return [explain, table, note]


@metric("game", title="Key moments", order=40, needs=("engine",))
def key_moments(ctx):
    a = ctx.analysis
    moments = a.key_moments(6)
    if not moments:
        return None
    boards = []
    for m in moments:
        try:
            board = chess.Board(m.fen_before)
            lastmove = chess.Move.from_uci(m.move_uci) if m.move_uci else None
        except (ValueError, IndexError):
            continue
        svg = chess.svg.board(
            board, lastmove=lastmove, size=240,
            orientation=chess.WHITE if m.color == "white" else chess.BLACK,
        )
        move_no = (m.ply + 1) // 2
        dots = "…" if m.color == "black" else "."
        best = f" · best {m.best_san}" if m.best_san else ""
        caption = (f"{move_no}{dots} {m.san} — {m.label}, "
                   f"−{m.wp_loss:.0f}% win{best}")
        boards.append(W.board(m.fen_before, caption=caption,
                              lastmove=m.move_uci, svg=svg))
    return W.group("", boards, layout="grid")
