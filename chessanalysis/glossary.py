"""What the numbers mean — one place, so every page says it the same way.

Every unit the app reports is defined here, and every example in the
definitions is computed from the formulas the statistics actually use
(`enrich.engine`), so the guide can never drift from the numbers it explains.

The units, in the words the pages use:

* **evaluation** — the engine's verdict in pawns, from your side;
* **win chance** — the evaluation as a percentage (Lichess's formula):
  50% is level, 100% a forced mate for you;
* **win chance lost** — what one move gave away: the drop in win chance from
  the position before it. Never "points": a point is a pawn to a chess player;
* **score** — wins plus half the draws, as a share of games;
* **expected score** — the score two ratings predict, by the Elo formula;
* **95% range** — where the true figure lies given how many games there are.
"""
from __future__ import annotations

import math

from .enrich.engine import BLUNDER, INACCURACY, MISTAKE, _move_accuracy, win_prob

_K = 0.00368208          # the slope inside `win_prob`


def pawns_for(win_chance: float) -> float:
    """The evaluation (in pawns) whose win chance is `win_chance` — the
    inverse of `win_prob`. Used to say what an average win chance looks like
    on the board."""
    w = min(99.99, max(0.01, win_chance))
    return -math.log(100 / w - 1) / _K / 100


def win_chance_edge_in_pawns(points: float) -> float:
    """A win-chance edge (in % around 50%) as an evaluation in pawns."""
    return pawns_for(50 + points)


def expected_score(rating: float, opponent: float) -> float:
    """The Elo formula: the score, 0..1, two ratings predict."""
    return 1 / (1 + 10 ** ((opponent - rating) / 400))


def time_control_label(tc: str | None) -> str:
    """'600' -> '10-minute', '600+5' -> '10+5', '180+2' -> '3+2'."""
    if not tc or "/" in tc or tc == "-":
        return "daily"
    base, _, inc = tc.partition("+")
    try:
        minutes = int(base) / 60
    except ValueError:
        return tc
    m = f"{minutes:g}"
    return f"{m}+{inc}" if inc and inc != "0" else f"{m}-minute"


def signed_pct(x: float, digits: int = 0) -> str:
    """0.37 -> '+37%' with a real minus sign."""
    s = f"{100 * x:+.{digits}f}%"
    return s.replace("-", "−")


def more_or_less(x: float, digits: int = 0, more: str = "more", less: str = "less",
                 same: str = "about the same") -> str:
    """0.37 -> '37% more', -0.14 -> '14% less', 0.002 -> 'about the same'."""
    if round(abs(100 * x), digits) == 0:
        return same
    return f"{abs(100 * x):.{digits}f}% {more if x >= 0 else less}"


# --- the guide -----------------------------------------------------------------------

EVAL_EXAMPLES = (0, 50, 100, 200, 300, 500, 1000)
LOSS_EXAMPLES = (0, 2, 5, 10, 20, 40)


def guide_sections(corpus_facts: dict | None = None, book_facts: dict | None = None) -> list:
    """[(id, title, widgets)] — the guide page, every example computed."""
    from . import widgets as W

    out = []
    out.append(("evaluation", "Evaluation", [W.text(
        "The engine's verdict on a position, in pawns, always from your side: "
        "+1.00 means you are a pawn up, or have something worth a pawn; −2.00 "
        "means you are two pawns down. A mate the engine can see is shown as M "
        "and a number of moves.")]))

    rows = [[f"{cp / 100:+.2f}".replace("+0.00", "0.00"), f"{win_prob(cp):.0f}%"]
            for cp in EVAL_EXAMPLES]
    a, b = win_prob(100) - win_prob(0), win_prob(900) - win_prob(800)
    out.append(("win-chance", "Win chance", [
        W.text("The evaluation turned into a percentage — the formula Lichess uses "
               "for its accuracy score. A level position is 50%, a forced mate for "
               "you is 100%, a forced mate against you 0%."),
        W.table(["Evaluation", "Win chance"], rows),
        W.text(f"Why not just pawns: a pawn matters a lot in a level position and "
               f"hardly at all when you are already a rook up. Going from +1.00 to "
               f"0.00 costs {a:.0f}% win chance; going from +9.00 to +8.00 costs "
               f"{b:.1f}%. Measuring moves in win chance counts the first as a real "
               f"error and the second as nearly nothing, which is what a player "
               f"would say. It is the engine's scale, not a forecast of how often "
               f"players at your rating win from there."),
    ]))

    acc_rows = [[f"{loss}%", f"{_move_accuracy(loss):.0f}"] for loss in LOSS_EXAMPLES]
    out.append(("win-chance-lost", "Win chance lost — what a move costs", [
        W.text(f"How much one move lowered your win chance, compared with the "
               f"position before it. A move as good as the engine's costs 0%. The "
               f"same thresholds are used on every page, as on Lichess: an "
               f"inaccuracy costs {INACCURACY:.0f}% or more, a mistake "
               f"{MISTAKE:.0f}% or more, a blunder {BLUNDER:.0f}% or more."),
        W.text("Averaged over moves it reads as \"win chance lost per move\". About "
               "half of a typical player's moves cost under 1%. Mistakes and "
               "blunders make up about half of the average and smaller slips the "
               "other half, so it moves with both how often you slip and how badly. "
               "It is a per-move average, not a total: a whole game adds up to far "
               "more than 100%, because both sides keep handing win chance back and "
               "forth."),
        W.text("Accuracy turns each move's cost into a score out of 100 (Lichess's "
               "formula), and a game's accuracy combines them:"),
        W.table(["Win chance lost", "Move accuracy"], acc_rows),
        W.text("Average centipawn loss (ACPL) is the older measure of the same "
               "thing, in hundredths of a pawn, with evaluations capped at ±10 "
               "pawns."),
    ]))

    from .metrics.game.control import SETTLED
    out.append(("average-win-chance", "Average win chance — who had the better of a game", [
        W.text("Shown on a game's review. The win chance of the position after every "
               "move, both sides' moves, averaged over the game. Your opponent's is "
               "100% minus yours; 50% means neither side had the better of it. A game spent a pawn down reads below 50% even if it ends in a "
               "draw, and a game you were winning for long stretches reads above 50% "
               "even if you lose it."),
        W.text(f"Counting stops once the game is settled: at the first position from "
               f"which one side's win chance stays at {SETTLED:.0f}% or more (about "
               f"{pawns_for(SETTLED):.1f} pawns up) to the end. Moves after that are "
               f"left out, so how long the winner took to finish, or when the loser "
               f"resigned, does not change the figure."),
        W.text("It is not accuracy. Accuracy grades each move against the best move in "
               "its position, so a side can keep a high accuracy while defending a "
               "worse position all game. The average win chance measures the positions "
               "themselves."),
    ]))

    out.append(("score", "Score, expected score and Elo", [
        W.text("Score is wins plus half the draws, as a share of the games: 6 wins, "
               "2 draws and 2 losses is a 70% score."),
        W.table(["Opponent rated", "Your expected score"],
                [[f"{abs(d)} {'below' if d < 0 else 'above'} you" if d else "the same as you",
                  f"{100 * expected_score(0, d):.0f}%"]
                 for d in (-200, -100, -25, 0, 25, 100, 200)]),
        W.text("Expected score is what the Elo formula predicts from the two "
               "ratings. A rating moves by a fixed amount times (score − expected "
               "score), so you gain rating only by scoring more than expected — "
               "whoever you play. Performance rating (Form) is the rating at which "
               "your score would have been the expected one."),
    ]))

    c = corpus_facts or {}
    have = (f" It holds {c['games']} games from {c['players']} players."
            if c.get("games") else "")
    out.append(("peers", "Players at your rating", [W.text(
        f"Other players' {time_control_label(c.get('time_control'))} games, "
        f"downloaded from Chess.com and analysed by the same engine at the same "
        f"depth (depth {c.get('depth', '?')}) as yours, so a comparison is on equal "
        f"terms.{have} Each of your games is compared with players at the rating "
        f"you had in that game, so a climb of a few hundred points does not judge "
        f"your early games against your current level. Expand the corpus from the "
        f"Peers page.")]))

    out.append(("range", "The 95% range, and \"unclear\"", [
        W.text("A difference measured on a few dozen games can be luck. The 95% "
               "range is where the true difference lies, given how many moves it "
               "was measured on: the games are resampled a thousand times and the "
               "middle 95% of the results kept. If the range includes zero, the "
               "data cannot yet say whether you are better or worse, whichever way "
               "the estimate points, and the page says \"unclear\"."),
        W.text("Ranges narrow with the square root of the number of moves: four "
               "times the games, half the width. That is why a row built on a "
               "handful of moves a game (time trouble, replies to the opponent's "
               "mistakes) stays unclear long after the overall figure is settled: "
               "one 20% blunder more or fewer changes the average of a 50-move row by "
               "0.4% a move."),
    ]))

    out.append(("control", "The correction for your opponents", [W.text(
        "Your opponents, in the same games, are measured the same way against "
        "players at their rating. Whatever both sides of your games share and the "
        "corpus does not — the pool you are paired in, how sharp your openings make "
        "the game, the clock habits of your time control — shows up in their figure "
        "too, and is taken out of yours. A made-up example: if you give away 20% "
        "less win chance per move than players at your rating, and your opponents "
        "in the same games 10% less than players at theirs, the corrected figure "
        "is about 11% less (0.80 ÷ 0.90). The comparison bars show the corrected "
        "figure; the numbers behind each bar show both.")]))

    bk = book_facts or {}
    out.append(("book", "Book moves", [W.text(
        f"A move is book when strong players play it in that position: at least "
        f"{bk.get('min_games', '?')} games and {bk.get('min_share', '?')} of what "
        f"was played there, in {bk.get('source', 'the elite database')}"
        + (f", {bk['games']:,} games" if bk.get("games") else "") +
        ". Leaving the book means choosing a move outside it while it still "
        "had moves to offer.")]))

    out.append(("phases", "Opening, middlegame, endgame", [W.text(
        "Phases follow the position, not the move number. The middlegame begins "
        "when ten or fewer minor and major pieces are left, when either back rank "
        "is mostly empty (development), or when the armies are interlocked "
        "(Lichess's definition). The endgame begins when each side has at most 13 "
        "points of pieces left, counting a knight or bishop as 3, a rook as 5 and "
        "a queen as 9. A move belongs to the phase of the position it was "
        "played from. The opening tables measure moves 1–12 instead, a fixed "
        "stretch, so every game is measured over the same number of moves.")]))
    return out
