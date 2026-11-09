"""Opening / middlegame / endgame: the one definition every statistic uses.

The split follows the position rather than a move number. The middlegame and
the overall structure come from Lichess's `Divider` (scalachess,
`chess/Divider.scala`) — the same source the accuracy formula in `enrich.engine`
is ported from. The endgame test does not:

* the **middlegame** begins at the first position where the minor and major
  pieces left on the board number 10 or fewer, or either side's back rank holds
  fewer than four of its own pieces (development), or the two armies are
  "mixed" — interlocked across 2x2 regions of the board — past a score of 150;
* the **endgame** begins at the first position where each side has at most 13
  points of pieces (knight or bishop 3, rook 5, queen 9; Speelman's definition);
* a game that never satisfies the middlegame test has no endgame either, and a
  middlegame that would begin no earlier than the endgame is dropped.

Lichess's endgame test counts pieces, six or fewer: queen, rook and minor piece
each passes it, and that is still a middlegame. Counting material leaves that
position in the middlegame while keeping rook-and-minor-piece endings.

A move belongs to the phase of the position it was played *from*: the move that
makes the trade completing the endgame is a middlegame move, and the reply to
it is the first endgame move.

Why not "moves 1–12 / 13–32 / 33+": many games never reach an endgame, yet every
move past 32 of every one of those games was counted as endgame play, and the
games that do reach one start it far from any fixed move. Positions, not move
counts, are what make a phase.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess

OPENING, MIDDLEGAME, ENDGAME = "Opening", "Middlegame", "Endgame"
ORDER = (OPENING, MIDDLEGAME, ENDGAME)
KEYS = {OPENING: "op", MIDDLEGAME: "mg", ENDGAME: "eg"}

_REGIONS = [0x0303 << (x + 8 * y) for y in range(7) for x in range(7)]
_RANK1 = chess.BB_RANK_1
_RANK8 = chess.BB_RANK_8
ENDGAME_MATERIAL = 13     # pieces each side may keep, in points, in an endgame
_PIECE_POINTS = ((chess.KNIGHT, 3), (chess.BISHOP, 3), (chess.ROOK, 5), (chess.QUEEN, 9))


def _count(bb: int) -> int:
    return bin(bb).count("1")


def _score(y: int, white: int, black: int) -> int:
    """Lichess's mixedness score for one 2x2 region on row `y` (1–7)."""
    if white == 0:
        if black == 1:
            return 1 + y
        if black == 2:
            return 2 + (6 - y) if y < 6 else 0
        if black in (3, 4):
            return 3 + (7 - y) if y < 7 else 0
        return 0
    if white == 1:
        if black == 0:
            return 1 + (8 - y)
        if black == 1:
            return 5 + abs(4 - y)
        if black == 2:
            return 4 + (7 - y)
        if black == 3:
            return 5 + (7 - y)
        return 0
    if white == 2:
        if black == 0:
            return 2 + (y - 2) if y > 2 else 0
        if black == 1:
            return 4 + (y - 1)
        if black == 2:
            return 7
        return 0
    if white in (3, 4):
        if black == 0:
            return 3 + (y - 1) if y > 1 else 0
        if black == 1 and white == 3:
            return 5 + (y - 1)
        return 0
    return 0


def _majors_and_minors(board: chess.Board) -> int:
    return _count(board.occupied & ~(board.kings | board.pawns))


def _backrank_sparse(board: chess.Board) -> bool:
    white = board.occupied_co[chess.WHITE]
    black = board.occupied_co[chess.BLACK]
    return _count(_RANK1 & white) < 4 or _count(_RANK8 & black) < 4


def _mixedness(board: chess.Board) -> int:
    white = board.occupied_co[chess.WHITE]
    black = board.occupied_co[chess.BLACK]
    acc = 0
    for i, region in enumerate(_REGIONS):
        acc += _score(i // 7 + 1, _count(white & region), _count(black & region))
    return acc


def is_middlegame(board: chess.Board) -> bool:
    return (_majors_and_minors(board) <= 10 or _backrank_sparse(board)
            or _mixedness(board) > 150)


def _piece_points(board: chess.Board, color: chess.Color) -> int:
    return sum(points * _count(board.pieces_mask(piece, color))
               for piece, points in _PIECE_POINTS)


def is_endgame(board: chess.Board) -> bool:
    return (_piece_points(board, chess.WHITE) <= ENDGAME_MATERIAL
            and _piece_points(board, chess.BLACK) <= ENDGAME_MATERIAL)


@dataclass(frozen=True)
class Division:
    """Where a game's phases begin, as position indices: position k is the one
    after k plies, so `mid == 14` means the position after move 7 is the first
    middlegame position. None = that phase was never reached."""
    mid: int | None
    end: int | None
    plies: int

    def of_ply(self, ply: int) -> str:
        """The phase of the move with this 1-based ply number — the phase of
        the position it was played from (position ply - 1)."""
        pos = ply - 1
        if self.end is not None and pos >= self.end:
            return ENDGAME
        if self.mid is not None and pos >= self.mid:
            return MIDDLEGAME
        return OPENING

    def of_position(self, pos: int) -> str:
        return self.of_ply(pos + 1)

    def key_of_ply(self, ply: int) -> str:
        return KEYS[self.of_ply(ply)]

    def to_dict(self) -> dict:
        return {"mid": self.mid, "end": self.end, "plies": self.plies}


def divide_boards(boards) -> Division:
    """Divide a game given every position in order, starting position first."""
    boards = list(boards)
    mid = next((i for i, b in enumerate(boards) if i and is_middlegame(b)), None)
    end = None
    if mid is not None:
        end = next((i for i, b in enumerate(boards) if i and is_endgame(b)), None)
    if mid is not None and end is not None and mid >= end:
        mid = None
    return Division(mid, end, max(0, len(boards) - 1))


def divide_fens(fens) -> Division:
    """Divide from a stored analysis's FEN list (len = plies + 1)."""
    return divide_boards(chess.Board(f) for f in fens)


def divide_game(game) -> Division:
    """Divide a parsed `model.Game` by replaying its moves."""
    board = chess.Board()
    boards = [board.copy(stack=False)]
    for m in game.moves:
        try:
            board.push_san(m.san)
        except ValueError:
            break
        boards.append(board.copy(stack=False))
    return divide_boards(boards)


def by_move_number(ply: int) -> str:
    """The split this app used before 2.0 — kept only so the change can be
    measured against it (see `corpus.phase_check`)."""
    move_no = (ply + 1) // 2
    if move_no <= 12:
        return OPENING
    return MIDDLEGAME if move_no <= 32 else ENDGAME
