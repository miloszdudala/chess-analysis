"""Opening book: building it, and walking a game through it."""
import chess
import chess.polyglot
import pytest

from chessanalysis import book

from .conftest import parsed_game as game

pytestmark = pytest.mark.usefixtures("tiny_book")


def test_build_keeps_only_moves_strong_players_repeat():
    start = book._book()[chess.polyglot.zobrist_hash(chess.Board())]
    assert start == {"e2e4": 7, "g1f3": 3}   # the one-off 2...Qh4 game starts 1.e4 too


def test_walk_follows_the_book_and_names_the_opening():
    w = book.walk(game("1. e4 c5 2. Nc3 Nc6 3. Nf3"))
    assert w.plies == 5                      # 3.Nf3 is theory, not a deviation
    assert w.family == "Sicilian Defense"
    assert w.left_by is None
    assert (w.book_moves("white"), w.book_moves("black")) == (3, 2)


def test_leaving_the_book_blames_the_mover():
    w = book.walk(game("1. e4 e5 2. Nf3 Qh4 3. Nxh4"))
    assert w.plies == 3
    assert w.left_by == "black"


def test_a_position_without_a_book_is_nobodys_fault():
    w = book.walk(game("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"))
    assert w.plies == 5
    assert w.left_by is None


def test_transpositions_count_as_book():
    # 3.Bb5 is only in the book via 1.e4 e5 2.Nf3 Nc6; same position here
    w = book.walk(game("1. Nf3 Nc6 2. e4 e5 3. Bb5"))
    assert w.plies == 5
    assert w.left_by is None


def test_walk_reads_the_pawn_structure_after_move_ten():
    shuffle = " ".join(f"{i}. Nf3 Nf6 {i + 1}. Ng1 Ng8" for i in range(1, 11, 2))
    w = book.walk(game(shuffle))
    assert w.pawns == frozenset((p.color, sq) for sq, p in chess.Board().piece_map().items()
                                if p.piece_type == chess.PAWN)
    assert book.walk(game("1. e4 e5")).pawns is None    # never reached move 10
