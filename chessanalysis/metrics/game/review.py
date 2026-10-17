"""Game-review metrics (scope="game"): need ctx.analysis (engine output)."""
import chess

from ... import config
from ... import widgets as W
from ...phases import ORDER as PHASES
from ...registry import metric


def _acc(v):
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
    played = getattr(g, "moves", None) or []
    clocks = [m.clock for m in played] if len(played) == len(moves) else []

    w = W.review(positions, moves, g.color, g.h("White"), g.h("Black"))
    w["division"] = a.division.to_dict()
    w["clocks"] = clocks
    return w


@metric("game", title="Evaluation", order=6, needs=("engine",))
def eval_graph(ctx):
    a = ctx.analysis
    if len(a.evals) < 2:
        return None
    plies = [{"ply": 0, "cp": a.evals[0], "label": "ok"}]
    for i, m in enumerate(a.moves):
        plies.append({"ply": i + 1, "cp": a.evals[i + 1], "label": m.label})
    w = W.evalbar(plies, [m.san for m in a.moves], me=ctx.game.color)
    w["division"] = a.division.to_dict()
    return w


def _phase_acc(a, side):
    """Mean move accuracy per phase for one side — the per-move figures the
    game's accuracy is built from, not a re-run of the game formula."""
    out = {}
    for ph in PHASES:
        accs = [m.accuracy for m in a.moves if m.color == side and a.phase_of(m.ply) == ph]
        out[ph] = (sum(accs) / len(accs), len(accs)) if accs else None
    return out


@metric("game", title="The game in numbers", order=10, needs=("engine",))
def summary(ctx):
    from ... import book

    g, a = ctx.game, ctx.analysis
    cp = int(config.get("DECISIVE_CP", "200"))
    d = a.decisive(cp)
    cards = [W.card(_acc(a.accuracy.get(s)), f"{s.title()} accuracy", sub=g.h(s.title()))
             for s in ("white", "black")]
    walk = book.walk(g) if getattr(g, "moves", None) else None
    if walk and walk.name:
        left = ("both stayed in book as far as it goes" if walk.left_by is None else
                f"{'you' if walk.left_by == g.color else 'they'} left book at move "
                f"{walk.plies // 2 + 1}")
        cards.append(W.card(walk.eco or "—", walk.name.split(":")[0], sub=left))
    if d["reached"]:
        cards.append(W.card(f"move {d['move_no']}", f"Decisive (±{cp / 100:.0f})",
                            sub=f"{d['side'].title()} · {'held' if d['held'] else 'lost it'}"))
    else:
        cards.append(W.card("—", f"Decisive (±{cp / 100:.0f})", sub="never crossed"))

    rows = []
    for side in ("white", "black"):
        c, pa = a.counts[side], _phase_acc(a, side)
        t3 = a.top3.get(side)
        rows.append([side.title(), _acc(a.accuracy.get(side)), a.acpl.get(side),
                     f"{t3:.0f}%" if t3 is not None else "—",
                     *[f"{pa[ph][0]:.0f}% ({pa[ph][1]})" if pa[ph] else "—" for ph in PHASES],
                     c["inaccuracy"], c["mistake"], c["blunder"]])
    div = a.division
    span = []
    if div.mid is not None:
        span.append(f"middlegame from move {div.mid // 2 + 1}")
    if div.end is not None:
        span.append(f"endgame from move {div.end // 2 + 1}")
    note = ("Phases follow the position, not the move number: " + ", ".join(span) + "."
            if span else "The game never left the opening by the position's measure.")
    return [W.cards(cards),
            W.table(["Side", "Accuracy", "ACPL", "Top-3", "Opening", "Middlegame",
                     "Endgame", "Inacc.", "Mistakes", "Blunders"], rows),
            W.text(note + " Phase columns are the mean accuracy of the moves played "
                   "in that phase (and how many).")]


# move-quality palette (also fixes legend order)
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


@metric("game", title="Every move, classified", order=30, needs=("engine",))
def move_quality(ctx):
    a = ctx.analysis
    rows = [{"label": side.title(),
             "segments": [{"name": k, "value": v}
                          for k, v in _quality_counts(a, side).items()]}
            for side in ("white", "black")]
    return W.barstack(rows, QUALITY_PALETTE)


def _move_label(m):
    return f"{(m.ply + 1) // 2}{'.' if m.ply % 2 else '…'} {m.san}"


@metric("game", title="Key moments", order=40, needs=("engine",))
def key_moments(ctx):
    """The costliest moves of the game, each a jump to that point on the board."""
    a = ctx.analysis
    moments = a.key_moments(8)
    if not moments:
        return None
    items = [{"ply": m.ply, "label": _move_label(m), "kind": m.label,
              "mine": m.color == ctx.game.color,
              "note": f"−{m.wp_loss:.0f}% · best {m.best_san}" if m.best_san
                      else f"−{m.wp_loss:.0f}%"}
             for m in sorted(moments, key=lambda m: m.ply)]
    out = [{"type": "moments", "items": items}]
    try:
        from ... import training
        mine = training.for_game(ctx.player, ctx.game.game_id) if ctx.player else []
    except Exception:                       # noqa: BLE001 — training is optional here
        mine = []
    if mine:
        out.append(W.actions([{
            "label": f"Train the {len(mine)} position{'s' if len(mine) != 1 else ''} "
                     f"from this game",
            "route": f"#/train?game={ctx.game.game_id}"}]))
    return out
