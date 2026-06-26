"""Game-review metrics (scope="game"): need ctx.analysis (engine output)."""
import chess
import chess.svg

from ...registry import metric
from ... import widgets as W


def _acc(a, side):
    v = a.accuracy.get(side)
    return f"{v:.1f}%" if v is not None else "—"


@metric("game", title=None, order=10, needs=("engine",))
def summary(ctx):
    g, a = ctx.game, ctx.analysis
    white, black = g.h("White"), g.h("Black")
    return W.cards([
        W.card(_acc(a, "white"), "White accuracy", sub=white),
        W.card(_acc(a, "black"), "Black accuracy", sub=black),
        W.card(a.acpl.get("white"), "White ACPL"),
        W.card(a.acpl.get("black"), "Black ACPL"),
        W.card(len(a.blunders()), "Blunders (both)"),
    ])


@metric("game", title="Evaluation", order=20, needs=("engine",))
def eval_graph(ctx):
    a = ctx.analysis
    if len(a.evals) < 2:
        return None
    plies = [{"ply": 0, "cp": a.evals[0], "label": "ok"}]
    for i, m in enumerate(a.moves):
        plies.append({"ply": i + 1, "cp": a.evals[i + 1], "label": m.label})
    return W.evalbar(plies, [m.san for m in a.moves])


@metric("game", title="Move quality", order=30, needs=("engine",))
def move_quality(ctx):
    a = ctx.analysis
    cols = ["Side", "Accuracy", "ACPL", "Inaccuracies", "Mistakes", "Blunders"]
    rows = []
    for side in ("white", "black"):
        c = a.counts[side]
        rows.append([
            side.title(), _acc(a, side), a.acpl.get(side),
            c["inaccuracy"], c["mistake"], c["blunder"],
        ])
    return W.table(cols, rows)


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
