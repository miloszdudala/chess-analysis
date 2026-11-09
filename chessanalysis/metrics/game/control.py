"""Who had the better of the game: the average win chance.

Accuracy grades each move against the engine's best move in that position; it
says nothing about how good the positions themselves were. A side can play
accurately for forty moves a pawn down, or blunder once and still have been
better for most of the game. This measures the positions instead: the win
chance after every move, by both sides, averaged over the game — the share of
it each side had, as possession and chances are in football. Shown as one card
in "Summary" (`review.summary`).

Counting stops once the game is settled for good: at the first position from
which one side's win chance stays at `SETTLED` or more to the end. Without that
a long mop-up would pull the figure toward 100%, and the same game would read
differently depending on when the loser resigned.
"""
from ...enrich.engine import win_prob

SETTLED = 90.0         # win chance one side keeps from here on: the game is over


def control(evals, color):
    """The win chance after each move, from `color`'s side, averaged up to where
    the game was settled: {"avg", "counted", "total"}. None for a game with no
    moves."""
    sign = 1 if color == "white" else -1
    wc = [win_prob(sign * cp) for cp in evals[1:]]
    if not wc:
        return None
    end, lo, hi = len(wc), wc[-1], wc[-1]
    for p in range(len(wc) - 1, -1, -1):     # the longest settled tail
        lo, hi = min(lo, wc[p]), max(hi, wc[p])
        if lo < SETTLED and hi > 100 - SETTLED:
            break
        end = p + 1
    return {"avg": sum(wc[:end]) / end, "counted": end, "total": len(wc)}
