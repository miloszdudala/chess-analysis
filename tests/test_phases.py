"""The one phase split (Lichess's Divider) and the samples derived with it."""
import chess

from chessanalysis import phases
from tests.conftest import build_raw

START = chess.Board()
# White developed: three back-rank pieces left (Ra1, Rf1, Kg1)
DEVELOPED = chess.Board("r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P1b1/2NP1N2/PPPQ1PPP/R4RK1 b - - 1 8")
# rook + bishop against rook + knight: four minor/major pieces left
ENDING = chess.Board("3r2k1/5ppp/2n5/8/8/2B5/5PPP/3R2K1 w - - 0 30")


def test_the_starting_position_is_the_opening():
    assert not phases.is_middlegame(START)
    assert not phases.is_endgame(START)
    assert phases._mixedness(START) == 0        # the armies have not met


def test_development_starts_the_middlegame():
    assert phases.is_middlegame(DEVELOPED)
    assert not phases.is_endgame(DEVELOPED)


def test_few_pieces_is_an_endgame():
    assert phases.is_endgame(ENDING)


def test_division_and_the_phase_of_a_move():
    d = phases.divide_boards([START, START, DEVELOPED, DEVELOPED, ENDING, ENDING])
    assert (d.mid, d.end, d.plies) == (2, 4, 5)
    # a move takes the phase of the position it was played from
    assert [d.of_ply(p) for p in range(1, 6)] == [
        "Opening", "Opening", "Middlegame", "Middlegame", "Endgame"]
    assert d.key_of_ply(5) == "eg"


def test_a_game_that_never_develops_has_no_endgame_either():
    d = phases.divide_boards([START] * 5)
    assert (d.mid, d.end) == (None, None)
    assert {d.of_ply(p) for p in range(1, 5)} == {"Opening"}


def test_a_middlegame_no_earlier_than_the_endgame_is_dropped():
    # a position that is already an ending also passes the middlegame test;
    # Lichess keeps the endgame and drops the middlegame
    d = phases.divide_boards([START, ENDING, ENDING])
    assert d.mid is None and d.end == 1
    assert d.of_ply(1) == "Opening" and d.of_ply(2) == "Endgame"


def test_fens_and_a_replayed_game_divide_the_same(sample_raw):
    from tests.conftest import parsed_game

    game = parsed_game("1. e4 e5 2. Nf3 Nc6")
    assert phases.divide_fens(sample_raw["fens"]) == phases.divide_game(game)


def test_samples_record_where_the_phases_begin():
    from chessanalysis.corpus import analyse

    moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
    raw = build_raw(moves, [20] * 7)
    rows = analyse.sample_rows("g1", raw, 1900, 1950, "1-0")
    cols = analyse.SAMPLE_COLS.split(",")
    assert len(rows) == 2 and all(len(r) == len(cols) for r in rows)
    white = dict(zip(cols, rows[0]))
    assert white["mg_ply"] is None and white["eg_ply"] is None
    assert white["op_n"] == 3 and white["mg_n"] == 0
