"""An opening explorer over three sources at once.

For any position, what was played from it:

* **you** — your own games in one colour and format, with your score after
  each move, the engine's average verdict on the position it led to, and —
  for your own moves — the win chance it cost on average;
* **players at your rating** — corpus players within `BAND` of it, so a move
  you make can be set beside what people at your level make;
* **masters** — the elite book (2500+ against 2300+, `book.py`), as the share
  of strong games that chose each move.

Positions are keyed by their EPD (pieces, side to move, castling, a capturable
en-passant square), so transpositions meet: a position reached by two move
orders is one node, as in any opening explorer.

The same machinery serves any account — the Scout page explores an opponent's
repertoire with it.
"""
from __future__ import annotations

import threading
from collections import defaultdict

import chess
import chess.polyglot

from . import book, store
from .enrich.engine import win_prob

MAX_PLY = 30          # fifteen moves each: the opening and its first fork
BAND = 100            # "players at your rating": corpus players within this of it

_LOCK = threading.Lock()
_INDEX: dict = {}


class Index:
    """Position -> move -> tallies, for one set of games seen from one side."""

    def __init__(self):
        self.pos: dict = defaultdict(lambda: {"n": 0, "games": [], "moves": {}})

    def add(self, key, uci, san, score, eval_after=None, loss=None, ref=None):
        node = self.pos[key]
        node["n"] += 1
        if ref is not None and len(node["games"]) < 400:
            node["games"].append(ref)
        mv = node["moves"].get(uci)
        if mv is None:
            mv = node["moves"][uci] = {"uci": uci, "san": san, "n": 0, "w": 0, "d": 0,
                                       "l": 0, "ev": 0.0, "ev_n": 0, "loss": 0.0,
                                       "loss_n": 0}
        mv["n"] += 1
        mv["w" if score == 1 else "d" if score == 0.5 else "l"] += 1
        if eval_after is not None:
            mv["ev"] += max(-1000, min(1000, eval_after))
            mv["ev_n"] += 1
        if loss is not None:
            mv["loss"] += loss
            mv["loss_n"] += 1


def _walk(pgn_moves, limit=MAX_PLY):
    """Yield (ply index, EPD before the move, move, SAN) along a game."""
    board = chess.Board()
    for i, m in enumerate(pgn_moves[:limit]):
        try:
            mv = board.parse_san(m.san)
        except ValueError:
            return
        yield i, board.epd(), mv, m.san
        board.push(mv)


def _player_index(user: str, color: str, time_class: str | None) -> Index:
    """Index of one account's games in one colour, from their point of view."""
    from .enrich import engine as eng
    from .model import load_games

    idx = Index()
    for g in load_games(user):
        if g.color != color or (time_class and g.time_class != time_class):
            continue
        score = {"win": 1, "draw": 0.5, "loss": 0}[g.outcome]
        evals = None
        depth = eng.deepest_cached(g, 1)
        raw = store.load_analysis(g.game_id, depth) if depth > 1 else None
        if raw and raw.get("evals") and len(raw["evals"]) == len(g.moves) + 1:
            evals = raw["evals"]
        for i, key, mv, san in _walk(g.moves):
            ev = evals[i + 1] if evals else None
            loss = None
            if evals and ((i % 2 == 0) == (color == "white")):
                s = 1 if color == "white" else -1
                loss = max(0.0, win_prob(s * evals[i]) - win_prob(s * evals[i + 1]))
            idx.add(key, mv.uci(), san, score, ev, loss,
                    ref={"id": g.game_id, "ply": i, "date": g.date,
                         "opponent": g.opponent, "opp_elo": g.opp_elo,
                         "outcome": g.outcome})
    return idx


def _band_index(lo: int, hi: int, time_class: str | None) -> Index:
    """Index of corpus games where the side to move was rated in [lo, hi].

    Each move is credited to the player who made it, so both sides of a game
    count, each in the positions where it was their move. Score is from the
    mover's point of view.
    """
    from .model import parse_pgn_text

    idx = Index()
    q = ("SELECT pgn, welo, belo, result FROM games WHERE source='corpus' "
         "AND (welo BETWEEN ? AND ? OR belo BETWEEN ? AND ?)")
    args = [lo, hi, lo, hi]
    if time_class:
        q += " AND time_class=?"
        args.append(time_class)
    for r in store.connect().execute(q, args):
        parsed = parse_pgn_text(store.unpack_pgn(r["pgn"]))
        if not parsed:
            continue
        res = {"1-0": 1.0, "0-1": 0.0}.get(r["result"], 0.5)
        w_in = r["welo"] is not None and lo <= r["welo"] <= hi
        b_in = r["belo"] is not None and lo <= r["belo"] <= hi
        for i, key, mv, san in _walk(parsed[0].moves):
            white = i % 2 == 0
            if (white and not w_in) or (not white and not b_in):
                continue
            idx.add(key, mv.uci(), san, res if white else 1 - res)
    return idx


def _cached(key, build, stamp):
    with _LOCK:
        hit = _INDEX.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    idx = build()
    with _LOCK:
        _INDEX[key] = (stamp, idx)
    return idx


def _stamp_player(user):
    return store.connect().execute(
        "SELECT COUNT(*), (SELECT COUNT(*) FROM analysis) FROM games "
        "WHERE white=? OR black=?", (user.lower(), user.lower())).fetchone()[:]


def _stamp_corpus():
    return store.connect().execute(
        "SELECT COUNT(*) FROM games WHERE source='corpus'").fetchone()[0]


def player(user, color, time_class=None) -> Index:
    return _cached(("player", user.lower(), color, time_class),
                   lambda: _player_index(user, color, time_class),
                   (_stamp_player(user), _overrides_stamp()))


def band_range(elo) -> tuple[int, int]:
    """The ratings "players at your rating" covers: ±BAND, snapped to 50s so
    the index is shared by nearby ratings."""
    return (elo - BAND) // 50 * 50, (elo + BAND) // 50 * 50


def band(elo, time_class=None) -> Index:
    lo, hi = band_range(elo)
    return _cached(("band", lo, hi, time_class),
                   lambda: _band_index(lo, hi, time_class), _stamp_corpus())


def _overrides_stamp():
    return store.connect().execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(gid)),0) FROM overrides").fetchone()[:]


# --- one position -------------------------------------------------------------------

def _board_after(moves: list[str]):
    board = chess.Board()
    sans = []
    for u in moves:
        try:
            mv = chess.Move.from_uci(u)
        except ValueError:
            break
        if mv not in board.legal_moves:
            break
        sans.append(board.san(mv))
        board.push(mv)
    return board, sans


def _name(moves: list[str]):
    """The deepest catalogue name along the line, and its ECO code."""
    named = book._names()
    board = chess.Board()
    found = ("", "")
    for u in moves:
        try:
            board.push_uci(u)
        except ValueError:
            break
        hit = named.get(board.epd())
        if hit:
            found = hit
    return {"eco": found[0], "name": found[1]}


def _rows(index: Index | None, key: str, pov_flip: bool = False):
    if index is None or key not in index.pos:
        return {"games": 0, "moves": []}
    node = index.pos[key]
    out = []
    for m in sorted(node["moves"].values(), key=lambda m: -m["n"]):
        n = m["n"]
        out.append({
            "uci": m["uci"], "san": m["san"], "n": n, "w": m["w"], "d": m["d"],
            "l": m["l"], "score": round((m["w"] + 0.5 * m["d"]) / n, 3),
            "eval": round(m["ev"] / m["ev_n"]) if m["ev_n"] else None,
            "loss": round(m["loss"] / m["loss_n"], 1) if m["loss_n"] else None,
        })
    return {"games": node["n"], "moves": out}


def position(moves: list[str], user: str | None = None, color: str = "white",
             time_class: str | None = None, elo: int | None = None,
             db: str = "me") -> dict:
    """Everything the explorer shows for the position after `moves` (UCI).

    `db` names whose games the first column holds: "me" (the user's) or
    another account's (the Scout page).
    """
    board, sans = _board_after(moves)
    key = board.epd()
    mine = player(user, color, time_class) if user else None
    out = {"fen": board.fen(), "sans": sans, "moves": moves[:len(sans)],
           "turn": "white" if board.turn else "black", "color": color,
           "your_move": (board.turn == chess.WHITE) == (color == "white"),
           "opening": _name(moves[:len(sans)]), "me": _rows(mine, key)}
    if mine is not None and key in mine.pos:
        refs = mine.pos[key]["games"]
        out["games"] = sorted(refs, key=lambda r: r["date"], reverse=True)[:12]
    if elo:
        out["band"] = _rows(band(elo, time_class), key)
        out["band"]["range"] = list(band_range(elo))
    theory = book._book().get(chess.polyglot.zobrist_hash(board), {})
    total = sum(theory.values())
    masters = []
    for uci, n in sorted(theory.items(), key=lambda kv: -kv[1]):
        try:
            san = board.san(chess.Move.from_uci(uci))
        except (ValueError, AssertionError):
            continue
        masters.append({"uci": uci, "san": san, "n": n, "share": round(n / total, 3)})
    out["masters"] = {"games": total, "moves": masters}
    return out


def repertoire(user: str, color: str, time_class: str | None = None,
               min_games: int = 3) -> list[dict]:
    """Your openings by name in one colour: games, score, and where in each
    you left the book — a summary under the explorer."""
    from .model import load_games

    fams: dict = {}
    for g in load_games(user):
        if g.color != color or (time_class and g.time_class != time_class):
            continue
        w = book.walk(g)
        f = fams.setdefault(w.family, {"name": w.family, "n": 0, "pts": 0.0,
                                       "book": 0, "left": 0, "lines": defaultdict(int)})
        f["n"] += 1
        f["pts"] += {"win": 1, "draw": 0.5, "loss": 0}[g.outcome]
        f["book"] += w.book_moves(g.color)
        f["left"] += w.left_by == g.color
        if w.name:
            f["lines"][w.name] += 1
    out = []
    for f in sorted(fams.values(), key=lambda f: -f["n"]):
        if f["n"] < min_games:
            continue
        top = max(f["lines"].items(), key=lambda kv: kv[1])[0] if f["lines"] else ""
        out.append({"name": f["name"], "games": f["n"],
                    "score": round(f["pts"] / f["n"], 3),
                    "book": round(f["book"] / f["n"], 1),
                    "left_first": round(f["left"] / f["n"], 2), "line": top})
    return out
