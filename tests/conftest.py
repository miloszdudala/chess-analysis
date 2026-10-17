"""Shared fixtures and helpers for the test suite.

Most tests avoid invoking a real engine: they feed `engine._derive` a
cache-shaped `raw` dict built from a real move sequence (so FENs/SAN are valid)
with synthetic evals and top-3 moves. Stockfish-backed tests live in
test_integration_stockfish.py and skip themselves when no engine is installed.
"""
from __future__ import annotations

import chess
import pytest

from chessanalysis import store
from chessanalysis.enrich import engine as eng


# --- a fake Game good enough for the engine + game-review code paths --------

class FakeGame:
    def __init__(self, game_id="testgame", color="white",
                 white="Alice", black="Bob", pgn=""):
        self._id = game_id
        self.color = color
        self.pgn = pgn
        self._h = {"White": white, "Black": black}

    @property
    def game_id(self):
        return self._id

    def h(self, key, default=""):
        return self._h.get(key, default)


# --- build a cache-shaped raw dict from a UCI move list ---------------------

def build_raw(uci_moves, evals, engine_name="TestFish"):
    """Construct what `engine._raw_evals` would cache for a move sequence.

    `evals` is the white-POV centipawn list (len == len(uci_moves) + 1).
    FENs and SAN are derived from a real board so they're always valid; the
    per-position top-3 moves are the first 3 legal moves with synthetic evals.
    """
    assert len(evals) == len(uci_moves) + 1, "evals must be plies + 1"
    board = chess.Board()
    fens, moves_san, moves_uci, best_uci, top_moves = [], [], [], [], []
    for u in uci_moves:
        mv = chess.Move.from_uci(u)
        fens.append(board.fen())
        moves_san.append(board.san(mv))
        moves_uci.append(u)
        legal = list(board.legal_moves)[:3]
        top = [{"uci": m.uci(), "cp": 30 - 10 * i} for i, m in enumerate(legal)]
        top_moves.append(top)
        best_uci.append(top[0]["uci"] if top else "")
        board.push(mv)
    fens.append(board.fen())                        # final position
    legal = list(board.legal_moves)[:3]
    top_moves.append([{"uci": m.uci(), "cp": 0} for m in legal])
    return {
        "evals": list(evals), "best_uci": best_uci, "moves_san": moves_san,
        "moves_uci": moves_uci, "fens": fens, "top_moves": top_moves,
        "engine_name": engine_name,
    }


# 1.e4 e5 2.Nf3 Nc6 — white drifts then blunders on move 2 (black's reply great)
SAMPLE_UCI = ["e2e4", "e7e5", "g1f3", "b8c6"]
SAMPLE_EVALS = [20, 18, 35, 30, 600]   # last jump => white's 2nd move is a blunder


@pytest.fixture
def sample_raw():
    return build_raw(SAMPLE_UCI, SAMPLE_EVALS)


@pytest.fixture
def sample_analysis(sample_raw):
    return eng._derive(sample_raw, depth=12, engine_name="TestFish")


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Every test gets its own empty store.

    Autouse on purpose: the store holds real games and real engine analyses,
    and a test that wrote into it would corrupt them silently.
    """
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test-chess.db"))
    store.reset()
    yield store
    store.reset()


# --- the opening book, built small ----------------------------------------------

_game_ids = iter(range(10 ** 9))


def parsed_game(moves: str, result: str = "1-0", headers: str = ""):
    """A parsed game with a unique id — book walks are cached by game id."""
    from chessanalysis.model import parse_pgn_text

    n = next(_game_ids)
    pgn = (f'[White "w{n}"]\n[Black "b{n}"]\n[Date "2026.01.01"]\n'
           f'[UTCTime "{n}"]\n[Result "{result}"]\n{headers}\n{moves} {result}\n')
    return parse_pgn_text(pgn)[0]


TINY_BOOK_GAMES = (["1. e4 c5 2. Nc3 Nc6 3. Nf3 *"] * 3
                   + ["1. e4 e5 2. Nf3 Nc6 3. Bb5 *"] * 3
                   + ["1. Nf3 Nc6 2. e4 e5 *"] * 3
                   + ["1. e4 e5 2. Nf3 Qh4 *"])        # once: too rare for the book


@pytest.fixture
def tiny_book(tmp_path, monkeypatch):
    """A book built by `book.build` itself from a handful of games."""
    from chessanalysis import book

    pgn = tmp_path / "strong.pgn"
    pgn.write_text("".join(f'[Event "x"]\n\n{m}\n\n' for m in TINY_BOOK_GAMES))
    out = tmp_path / "book.tsv.gz"
    monkeypatch.setattr(book, "MIN_GAMES", 2)
    book.build([str(pgn)], str(out))
    monkeypatch.setattr(book, "_BOOK", str(out))
    loaded = book._book.__wrapped__()
    monkeypatch.setattr(book, "_book", lambda: loaded)
    return loaded


# --- whole games in the store ---------------------------------------------------

_store_ids = iter(range(10 ** 9))


def store_game(white, black, welo, belo, sans, result="1-0", source="corpus",
               evals=None, depth=10, top=False, date="2026.10.01", tc="600"):
    """Put one game — PGN with clocks — and optionally its analysis in the store.

    `sans` is the move list; `evals` the white-POV array (len(sans) + 1).
    With `top`, every position also gets three candidate moves (the first
    three legal ones), the first scored as the eval — enough for training.
    Returns the game id.
    """
    from chessanalysis import model, store

    n = next(_store_ids)
    gid = str(900000 + n)
    clock, parts = 600.0, []
    for i, san in enumerate(sans):
        if i % 2 == 0:
            parts.append(f"{i // 2 + 1}.")
            clock -= 7
        parts.append(f"{san} {{[%clk 0:{int(clock) // 60:02d}:{int(clock) % 60:02d}]}}")
    pgn = (f'[Event "Live Chess"]\n[Site "Chess.com"]\n[Date "{date}"]\n'
           f'[White "{white}"]\n[Black "{black}"]\n[Result "{result}"]\n'
           f'[WhiteElo "{welo}"]\n[BlackElo "{belo}"]\n[TimeControl "{tc}"]\n'
           f'[UTCDate "{date}"]\n[UTCTime "10:{n % 60:02d}:00"]\n'
           f'[Termination "{white} won by resignation"]\n'
           f'[Link "https://www.chess.com/game/live/{gid}"]\n\n'
           f'{" ".join(parts)} {result}\n')
    game = model.parse_pgn_text(pgn)[0]
    store.save_games([model.game_row(game, source=source)])
    if evals is not None:
        board = chess.Board()
        fens, uci, tops = [], [], []
        for san in sans:
            fens.append(board.fen())
            mv = board.parse_san(san)
            uci.append(mv.uci())
            board.push(mv)
        fens.append(board.fen())
        if top:
            b = chess.Board()
            for i, fen in enumerate(fens):
                b = chess.Board(fen)
                legal = [m.uci() for m in b.legal_moves][:3]
                tops.append([{"uci": u, "cp": evals[i] - 40 * j} for j, u in enumerate(legal)])
        raw = {"evals": list(evals), "moves_san": list(sans), "moves_uci": uci,
               "fens": fens, "best_uci": [t[0]["uci"] if t else "" for t in tops] or [""] * len(sans),
               "top_moves": tops}
        store.save_analysis(gid, depth, raw, multipv=3 if top else 1, engine="test")
    return gid


# a short, legal game: 20 plies of normal development
GAME_SANS = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d3", "d6",
             "O-O", "O-O", "Re1", "a6", "Bb3", "Ba7", "h3", "h6", "Nbd2", "Re8"]
