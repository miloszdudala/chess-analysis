# TODO

Things worth doing, with enough context to pick up cold.

## Done in 2.0

- **Phases by position, in one place.** `phases.py` is Lichess's Divider and
  every statistic imports it; corpus samples record where each game's
  middlegame and endgame begin, and were re-derived without the engine
  (`ensure_samples`). The ladder held: middlegame blunders per 100 moves fall
  4.15 → 2.52 (1800 → 2200) under the move-number split and 4.38 → 2.56 under
  the Divider, so that finding is about chess, not about move 32. What moved
  was the endgame (flat before, a mild decline now) and how early games are
  decided in the opening (38% → 23% before, 31% → 13% now: the Divider's
  opening ends sooner for stronger players). The endgame threshold is Lichess's
  (six or fewer minor and major pieces) — inherited, but from a published
  definition that matches the accuracy formula's source.
- **Compare became Scout.** Engine-free, so it is instant on any account; the
  "progress UI for analysing someone's whole history" problem went away with
  the engine. Head-to-head is shown as the record it is, without inference.

## 1. Blunder anatomy, still open

Unchanged in substance — see the comment in `weaknesses.py`. The training
positions (`training.py`) now carry only labels the engine proves: forced mate,
an only move (the second-best is 15%+ worse), the phase, converting or
defending. The next step is the same as before: store the refutation's
principal variation (the corpus pass already records the first move; the review
pass keeps three candidates but no lines) and classify from the line, then
audit a sample against exchange evaluation before showing a single label.

## 2. The corpus ends at 2300

`coach.plays_like` reads your loss per move off the ladder, and the corpus has
almost nothing above 2200 (12 samples at 2300). For an account at 2094 whose
moves look like 2200 or better, the upper end of the range is "2300+" because
there is nothing to read it against. `crawl.plan` targets two bands either side
of your rating; widening it upward when `plays_like` lands near the top band
would fix this. The ladder also needs ≥3000 moves per band to be used.

## 3. Only 10-minute games have peers

The corpus is 600-second rapid. The coach states this and stays silent for
blitz or bullet, but a player who mostly plays blitz gets no peer comparison.
`crawl.py` filters on `TIME_CONTROL`; a per-format corpus means a `time_control`
column in every corpus query (most already join `games`, which has it).

## 4. Multi-move training positions

A position is one move today: find the move that keeps the win chance. Where
the engine's line is forcing (an only move, then another), the trainer could
play the opponent's reply and ask again — `livengine.analyse(..., pv_len=...)`
already returns the line, and `training.attempt` judges any move. The open
question is when a line stops being forcing enough to keep asking.

## 5. Coach: frequency is shown, not tested

Each coach bucket compares how *well* you play there (loss per move), and shows
how *often* you are there (moves per game) beside the peers' figure without an
interval. Being behind half as often as your peers is a real strength, and it
gets no verdict. It needs its own control — your "behind" is your opponent's
"ahead", so the opponent-paired control does not transfer as it is.
