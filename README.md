# Chess Analysis

This is a personal chess analysis webpage, giving insights to explore much beyond what is shown for free accounts. 
All code is AI-written while almost all ideas are mine and I explain methods to derive the more complicated statistics.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # python-chess, flask
brew install stockfish                            # the engine

cp .env.example .env                              # optional: a default username
```

`.env` (gitignored) holds `CHESS_USERNAME`, `CHESS_DB`, `STOCKFISH_PATH`,
`ENGINE_DEPTH`, `BULLET_DEPTH`, `RECENT_DEPTH`, `CORPUS_WORKERS`, `DECISIVE_CP`.

## Run it

Launch **Chess Analysis** from the Dock, Launchpad or Spotlight, or
double-click `Chess Analysis.command` in this folder. Either restarts the server
and opens the browser, so code changes are always picked up.

```bash
bin/chess-analysis            # start (restarting any old server) and open the browser
bin/chess-analysis --stop     # stop it
PORT=8080 bin/chess-analysis  # another port
.venv/bin/python webapp.py    # the long way: http://127.0.0.1:5050
```

Type a Chess.com account in the top-right box and every page reports on it; the
format selector beside it (rapid by default) chooses which games. Opening the
app syncs the account from Chess.com, then a background job analyses any game
not yet analysed — first quickly, for the peer comparison, then at review depth.
A thin bar under the header shows its progress.

> **First launch of the Dock app** asks for access to the Documents folder —
> click **Allow**. If you miss it: `tccutil reset SystemPolicyDocumentsFolder
> local.chessanalysis.launcher` and launch again. The app bundle is a launcher
> only; rebuild it with `bin/make-app`.

## The pages

Every page has an address (`#/train?kind=missed`, `#/game/<id>?ply=24`), so the
back button works and any report can link straight to a view. Light and dark
themes follow the system; ◐ switches by hand.

**Overview** — where you stand. Rating, form (FIDE performance over your last 20
games), what your moves play like, today's training, and the coach: you against
players at your rating, phase by phase, situation by situation, clock by clock.
How that comparison is made is the next section.

**Games** — your whole history, newest first, filterable by result, colour,
opening and the one-line reason the game was won or lost. Each row opens its
review.

**Game review** — why you won or lost (a correctable verdict), the board with
the engine's candidate moves drawn as arrows, clocks as they stood, and the
evaluation graph with the middlegame and endgame marked. Play any move on the
board to explore it with the live engine. Then the game in numbers — accuracy,
accuracy per phase, where you left book — and its key moments, each a jump to
that move. ← → step through the game; F flips the board.

**Openings** — an explorer over three sources at once: your games (your score
after each move, the engine's verdict, and the win chance your own move gives
away on average), other players rated near you (how often they play each move,
and their score with it), and strong players (the Lichess Elite Database).
Positions are keyed so transpositions meet. Play on the board or click a move;
moves you keep making that cost an inaccuracy's worth of win chance or more are
highlighted.

**Train** — positions from your own games, until they stick. Three kinds: your
mistakes (a move that cost 12% or more of your win chance), missed chances (your
opponent handed you 15% and your reply gave it back) and opening fixes (a costly
move you made in the same opening position more than once). Any move within 5%
of the engine's best solves it — not only the one the engine listed first — and
moves the stored analysis never considered are judged by the live engine. Solved
first time, a position returns after a day, then three, then at a growing
interval; missed, it returns within the session. The labels on a position are
only what the engine proves: a forced mate, a single good move, the phase,
whether you were converting or defending.

**Stats** — the descriptive record: results by colour and opponent strength,
form over time, the clock, why your games end the way they do, your progress
against your own baseline, and the opponent-paired phase comparison.

**Peers** — the rating corpus, at two scopes. *At my rating* sets you against
the players rated close to you; *every rating* shows what changes as rating
rises: accuracy and blunders by phase, how early games are decided, what the
opening costs. The opening section measures openings in win chance rather than
results, and *does knowing more theory pay?* compares each player with
themselves. **⊕ Expand the corpus** downloads and analyses more games, filling
the thinnest rating range first.

**Guide** — what every number means: evaluation, win chance, what a move costs,
accuracy, score and expected score, the 95% range, the correction for your
opponents. Every example in it is computed from the formulas the statistics
use, and the pages link to the definition they rely on.

**Scout** — name an opponent: their recent games are downloaded and read for
preparation, without the engine, so it takes seconds. What they open with as
White and answer as Black — each line beside your own record in it — their
openings by name, how their games end, how they use the clock against players
at their rating, and your games against them. Their repertoire opens in the
explorer.

**Extras** — lighter stats. A world map of the countries your opponents play for
(from their Chess.com profiles, looked up during a sync), shaded by how many
games, with your record against each when you point at it, and the same as a
table. Rebuild the map shapes with `bin/make-worldmap` (instructions inside).

## The units

One vocabulary on every page (`chessanalysis/glossary.py`, shown on the Guide):

- **Evaluation** — the engine's verdict in pawns, from your side.
- **Win chance** — the evaluation as a percentage, by Lichess's formula: 0.00 is
  50%, +1.00 about 59%, a forced mate 100%.
- **Win chance lost** — what one move gave away: how far it lowered your win
  chance. Inaccuracy, mistake and blunder are 5%, 10% and 20% or more, as on
  Lichess. Never called "points": to a chess player a point is a pawn.
- **Score** — wins plus half the draws; **expected score** — what the Elo formula
  predicts from two ratings.
- **95% range** — where the true figure lies given how many moves it rests on.
  A comparison whose range includes zero is reported as *unclear*, whichever
  way it leans.

## How the comparison is made

The coach measures one thing: the win chance each of your moves gives away,
per move — the quantity Lichess accuracy is built from. It is split three ways
(phase, situation, clock), plus your replies to an opponent's mistake. Every
row shows how many of your moves it rests on.

- **Same terms.** Your games and the corpus are analysed by the same engine at
  the same depth, in the same time control (10-minute: `corpus.TIME_CONTROL`).
- **Rating-matched.** Each of your games is set against corpus players at the
  rating you had *in that game*: a player who climbed 400 points would
  otherwise have their early games judged against their current level.
- **A control.** Your opponents in the same games are measured the same way,
  against players at their rating. Anything both sides of your games share and
  the corpus does not — the pool you play in, game length, the kind of position —
  moves the control, and the verdict is drawn on your gap with the control taken
  out. Without it, a "time trouble weakness" can appear that your opponents, in
  the same games, show just as much.
- **Intervals.** A paired bootstrap over your games. A row is a weakness or a
  strength only when its 95% range clears zero; otherwise it is *unclear*, and
  the page shows the range so you can see how far it could go either way.
- **Results are not compared.** Against players at your own rating everyone
  scores about 50%, so being better at one thing means being worse at another;
  win chance lost is measured directly, where that compensation cannot hide.

*Rating your moves play like* reads your control-adjusted loss per move off the
corpus's rating ladder (loss per move at each rating) and says so when you are
beyond the ratings the corpus covers, rather than extrapolating.

## Phases

Opening, middlegame and endgame follow the position
(`chessanalysis/phases.py`), not the move number. As in Lichess's Divider, the
middlegame starts with development, a thinned back rank or interlocked armies.
The endgame starts when each side has at most 13 points of pieces left (knight
or bishop 3, rook 5, queen 9), so queen, rook and minor piece each is still a
middlegame. A move belongs to the phase of the
position it was played from. Every statistic uses this one definition, except
the opening tables, which measure a fixed stretch (moves 1–12) so every game is
measured over the same number of moves.

## Where the data lives

Everything is one SQLite file, `data/chess.db`: every game's PGN (yours, the
corpus's, scouted opponents'), every engine analysis keyed by game and depth,
the corpus samples, your training schedule, your corrections and flags, and
small state such as fair-play statuses. Upgrading from 1.x imports the old
`data/cache/` and `data/overrides.json` once, on first start.

### Games that don't count

Two kinds of game leave every statistic while staying in the history, marked ⚑:
**anomalous** ones you flag in the review (a disconnect, a thrown game), and
games against an opponent **Chess.com has since banned for fair play** —
detected automatically on sync, with recent opponents re-checked twice a day.
Chess.com refunds the rating such a game cost, days later; `ratings.py` adds
the points back over exactly that stretch so the curve stays continuous.

## The command line

```bash
.venv/bin/python analyze.py                  # the coach, in the terminal
.venv/bin/python analyze.py coach --last 30  # ...over your latest 30 games
.venv/bin/python analyze.py train            # refresh training positions, show the queue
.venv/bin/python analyze.py player           # the full report  -> out/player-<user>.json
.venv/bin/python analyze.py game last        # one game's review -> out/game-<id>.json
.venv/bin/python analyze.py scout <account>  # an opponent       -> out/scout-<account>.json
.venv/bin/python scraper.py <account>        # download games without the app
.venv/bin/python -m chessanalysis.corpus.analyse rebuild   # re-derive corpus samples
```

## Architecture

```
webapp.py                  Flask: thin JSON endpoints over chessanalysis
analyze.py                 the CLI
scraper.py                 Chess.com downloader (own / scouted accounts)
frontend/
├── index.html, style.css  the shell and one stylesheet (light + dark)
└── js/                    ES modules, no build step: router, board, charts,
                           widget renderers, one module per page
chessanalysis/
├── store.py               data/chess.db — the one place anything is kept
├── model.py               PGN -> perspective-bound Game objects
├── phases.py              opening / middlegame / endgame, by position
├── enrich/engine.py       Stockfish per-move evals, Lichess accuracy
├── livengine.py           one long-lived engine for interactive questions
├── jobs.py                background jobs with pollable progress
├── glossary.py            the units, in words, and the Guide built from them
├── coach.py               win chance lost, against rating-matched peers
├── training.py            positions to solve, judging, spaced repetition
├── explorer.py            the opening explorer's position indexes
├── gamelist.py            the history, with what is known about each game
├── book.py, opening.py    opening theory and the opening research
├── corpus/                the rating corpus: crawler, engine pass, SQL aggregates
├── diagnosis.py, insights.py, weaknesses.py, form.py, clocks.py
├── fairplay.py, ratings.py, overrides.py
├── registry.py, contexts.py, document.py, widgets.py
├── metrics/               compute-only units, by scope (auto-discovered)
│   └── overview/  player/  game/  brackets/  scout/
└── modes/                 overview, player, game, brackets, scout
```

### Extending — each is one file

**A stat** — a file in `metrics/<scope>/` with an `@metric` function returning
widgets from `widgets.py`. **A mode** — a `modes/` file with `@mode("name")`
and a context; it runs every metric of its scope. **A chart** — a builder in
`widgets.py` and a renderer in `frontend/js/widgets.js`.

The discipline that keeps it easy: **metrics compute, modes shape data,
renderers render.**

## Credits

Pieces: the *cburnett* set by Colin M.L. Burnett (GPLv2+ / BSD / CC BY-SA 3.0),
as served by Lichess. The phase split and the accuracy formula follow Lichess
(scalachess `Divider`, lichess.org/page/accuracy). Opening names: the Lichess
openings catalogue (CC0). The theory book is cut from the Lichess Elite Database
(database.nikonoel.fr, CC0).
