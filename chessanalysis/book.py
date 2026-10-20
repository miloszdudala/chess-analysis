"""Opening theory: how far a game follows known lines, and who left them.

**The book** is what strong players actually play. It is built from the Lichess
Elite Database (database.nikonoel.fr, CC0 like the Lichess database it is cut
from): every game between a 2500+ and a 2300+ player in one month, blitz and
up (`facts()` counts them). A move counts as *book* in a position when at least
`MIN_GAMES` of those games played it there and it is at least `MIN_SHARE` of
what was played. Positions are compared by Zobrist key, not by move order, so
transpositions count. The finished book is small enough to ship with the code
(`data/elite_book.tsv.gz`); `python -m chessanalysis.book build <pgn>...`
rebuilds it.

**The names** come from a different list, the Lichess openings catalogue
(`data/lichess_openings.tsv`, CC0, github.com/lichess-org/chess-openings). It
was tried as the book first and is useless for that: it lists *named* lines,
so 1.e4 c5 2.Nc3 Nc6 3.Nf3, an entirely normal move, falls off it at move 3.
It is kept for what it is good at, saying which opening a game is.

This module is only the reference — what theory is and where a game left it.
What is measured with it, and how it is compared, is in `opening.py`.

Two ways out of the book are kept apart, because only one of them says anything
about the player:

- **left** — strong players had moves here and the player chose something else.
  They were out of theory first.
- **exhausted** — too few strong games reached the position to say what theory
  is. Nobody deviated.
"""
from __future__ import annotations

import csv
import gzip
import io
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

import chess
import chess.pgn
import chess.polyglot

_DIR = os.path.join(os.path.dirname(__file__), "data")
_TSV = os.path.join(_DIR, "lichess_openings.tsv")
_BOOK = os.path.join(_DIR, "elite_book.tsv.gz")

MIN_GAMES = 5         # strong games that played a move before it is theory
MIN_SHARE = 0.01      # ...and its share of what was played in that position
BUILD_PLIES = 40      # how deep the book is built
NAME_PLIES = 30       # how deep a game is followed for its opening's name

STRUCTURE_PLY = 20    # the pawn structure is read after move 10


@dataclass(frozen=True)
class Walk:
    plies: int            # plies played inside the book, from move 1
    left_by: str | None   # colour that left the book while it still went on
    eco: str              # deepest named position reached ("" if none)
    name: str
    pawns: frozenset | None = None   # (colour, square) of every pawn after move 10

    @property
    def family(self) -> str:
        """'Sicilian Defense: Closed, Traditional' -> 'Sicilian Defense'."""
        return self.name.split(":")[0] if self.name else "Unnamed"

    def book_moves(self, color: str) -> int:
        """How many of `color`'s own moves were book moves."""
        return (self.plies + 1) // 2 if color == "white" else self.plies // 2


@lru_cache(maxsize=1)
def _names() -> dict:
    """Position where a named catalogue line ends -> (eco, name)."""
    named: dict = {}
    with open(_TSV, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            game = chess.pgn.read_game(io.StringIO(row["pgn"]))
            board = game.board()
            for mv in game.mainline_moves():
                board.push(mv)
            named[board.epd()] = (row["eco"], row["name"])
    return named


@lru_cache(maxsize=1)
def _book() -> dict:
    """Zobrist key -> {uci: games} for every book move."""
    book: dict = defaultdict(dict)
    with gzip.open(_BOOK, "rt", encoding="ascii") as f:
        next(f)                                   # header
        for line in f:
            key, uci, n = line.split("\t")
            book[int(key, 16)][uci] = int(n)
    return book


SOURCE = "the Lichess Elite Database of games between 2500+ and 2300+ players"


@lru_cache(maxsize=1)
def facts() -> dict:
    """What the book is, read off the book itself: every game has a first
    move, so the moves counted at the starting position are its games (those
    whose first move made the cut, which is all but a handful)."""
    root = _book().get(chess.polyglot.zobrist_hash(chess.Board()), {})
    return {"games": sum(root.values()), "source": SOURCE,
            "min_games": MIN_GAMES, "min_share": f"{100 * MIN_SHARE:g}%"}


def is_book(board: chess.Board, uci: str) -> bool:
    """Whether strong players play `uci` in this position (see the module)."""
    return uci in _book().get(chess.polyglot.zobrist_hash(board), {})


_WALKS: dict = {}


def walk(game) -> Walk:
    """Follow `game` through the book. Cached by game id: the answer never
    changes, and the corpus asks for every game on each page load."""
    gid = str(game.game_id)
    if gid in _WALKS:
        return _WALKS[gid]
    theory, named = _book(), _names()
    board = chess.Board()
    plies, left_by, eco, name, pawns = 0, None, "", "", None
    in_book = True
    for i, m in enumerate(game.moves[:NAME_PLIES]):
        try:
            mv = board.parse_san(m.san)
        except ValueError:
            break
        if in_book:
            known = theory.get(chess.polyglot.zobrist_hash(board))
            if known and mv.uci() in known:
                plies = i + 1
            else:
                if known:
                    left_by = "white" if i % 2 == 0 else "black"
                in_book = False
        board.push(mv)
        hit = named.get(board.epd())
        if hit:
            eco, name = hit
        if i + 1 == STRUCTURE_PLY:
            pawns = frozenset((p.color, sq) for sq, p in board.piece_map().items()
                              if p.piece_type == chess.PAWN)
    _WALKS[gid] = w = Walk(plies, left_by, eco, name, pawns)
    return w


def build(pgn_paths: list[str], out: str = _BOOK, scratch: str | None = None) -> int:
    """Count every (position, move) in the first BUILD_PLIES of each game and
    write the ones that qualify as theory. Returns the rows written.

    Counting is exact and happens in a scratch SQLite file, flushed every
    chunk: the raw (position, move) pairs run to millions, nearly all seen
    once, and holding them in a dict would cost gigabytes for rows that are
    thrown away at the end.
    """
    import sqlite3

    from .model import _TOKEN_RE

    scratch = scratch or out + ".scratch.db"
    if os.path.exists(scratch):
        os.remove(scratch)
    db = sqlite3.connect(scratch)
    db.execute("CREATE TABLE pm (key INTEGER, uci TEXT, n INTEGER, "
               "PRIMARY KEY (key, uci)) WITHOUT ROWID")

    def flush(counts):
        db.executemany("INSERT INTO pm VALUES (?,?,?) ON CONFLICT(key, uci) "
                       "DO UPDATE SET n = n + excluded.n",
                       ((k - (1 << 63), u, n) for (k, u), n in counts.items()))
        db.commit()
        counts.clear()

    def movetexts(path):
        text: list[str] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("["):
                    if text:
                        yield " ".join(text)
                        text = []
                elif line.strip():
                    text.append(line.strip())
        if text:
            yield " ".join(text)

    counts: Counter = Counter()
    games = 0
    for path in pgn_paths:
        for mt in movetexts(path):
            board = chess.Board()
            ply = 0
            for tok in _TOKEN_RE.findall(mt):
                if tok[0] in "{$" or tok[0].isdigit() or tok == "*":
                    continue                     # comment, NAG, move no., result
                try:
                    mv = board.parse_san(tok)
                except ValueError:
                    break
                counts[(chess.polyglot.zobrist_hash(board), mv.uci())] += 1
                board.push(mv)
                ply += 1
                if ply >= BUILD_PLIES:
                    break
            games += 1
            if games % 20000 == 0:
                flush(counts)
                print(f"{games} games", file=sys.stderr)
    flush(counts)

    rows = db.execute(
        "SELECT pm.key, pm.uci, pm.n FROM pm JOIN (SELECT key, SUM(n) t FROM pm "
        "GROUP BY key) tot ON tot.key = pm.key WHERE pm.n >= ? AND pm.n >= ? * tot.t "
        "ORDER BY pm.key, pm.n DESC", (MIN_GAMES, MIN_SHARE)).fetchall()
    db.close()
    os.remove(scratch)
    with gzip.open(out, "wt", encoding="ascii") as f:
        f.write("key\tuci\tgames\n")
        for k, u, n in rows:
            f.write(f"{k + (1 << 63):016x}\t{u}\t{n}\n")
    print(f"{games} games -> {len(rows)} book moves", file=sys.stderr)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "build":
        build(sys.argv[2:])
    else:
        sys.exit("usage: python -m chessanalysis.book build <elite.pgn>...")
