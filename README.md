# chess-analyzer

Scrape your Chess.com games and generate analysis reports — a full
game-history overview, a deep **engine review** of a single game (Stockfish),
and player **comparison**. Built around a pluggable architecture: new stats,
new modes, and new charts each drop in as a single file.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # python-chess, flask
brew install stockfish                            # engine for game review

cp .env.example .env                              # optional: a default username
```

`.env` (gitignored) holds `CHESS_USERNAME`, `CHESS_DB`, `REPORT_FILE`,
`STOCKFISH_PATH`, `ENGINE_DEPTH`. `CHESS_USERNAME` only pre-fills the web app's
username box — type any account there to analyse it.

## Run the web app

**One click — no terminal.** Launch **Chess Analyzer** from the Dock,
Launchpad or Spotlight (the app lives in `~/Applications`; drag it to the Dock
once to keep it there). It restarts the server and opens the browser for you,
so code edits are always picked up. `Chess Analyzer.command` in this folder
does the same thing from Finder.

Both are thin wrappers around one script:

```bash
bin/chess-analyzer            # start (restarting any old server) and open the browser
bin/chess-analyzer --stop     # stop the server
PORT=8080 bin/chess-analyzer  # a different port
```

Server output goes to `data/webapp.log`. Or run it the long way:

```bash
.venv/bin/python webapp.py         # then open http://127.0.0.1:5050
pkill -f webapp.py                 # stop it
```

Type a Chess.com account in the **Username** box in the header and every tab
reports on it — there is no separate download step, since showing stats or
opening a review syncs that account's games first. `python3 scraper.py` still
downloads games from the terminal if you want it.

> **First launch of the Dock app** shows *"Chess Analyzer would like to access
> files in your Documents folder"* — click **Allow**. macOS blocks apps from
> reading `~/Documents` until you do, and this project lives there. If you miss
> the prompt, macOS won't ask twice: reset it with
> `tccutil reset SystemPolicyDocumentsFolder local.chessanalyzer.launcher` and
> launch again, or tick **Chess Analyzer** under System Settings → Privacy &
> Security → Files and Folders. The `.command` file needs no permission — it
> runs through Terminal, which already has access.
>
> The app bundle is a launcher only; rebuild it with `bin/make-app`.

In the browser, pick a tab:

- **Player report** — choose a format (bullet / blitz / rapid) first, then pick
  which stats to show. Includes a zoomable rating chart (drag/scroll to zoom,
  double-click to reset, hover for date / rating / change; Game / Day / Month
  grouping), opening **move trees** per color, opponent-strength aggregates, and
  a **Recent games** list (5 / 10 / 20 / All) — each engine-analysed with
  accuracy, blunders, and the conversion stat; click a row to open its review.
- **Game review** — pick a game and depth; Stockfish reports accuracy, an eval
  graph, annotated key moments, and the **conversion** stat (when the eval first
  crossed ±X and whether it held).
- **Brackets** — the rating corpus, at two scopes. *My band* puts you against
  the players actually at your rating, measured in the same currency (their
  games run through the same engine at the same depth as yours); *Every band*
  is the ladder. Both lead with the opening / middlegame / endgame split, which
  is where the diagnosis lives — across 1800–2200 the opening barely moves and
  the endgame is flat, while middlegame blunders per 100 moves halve. Games
  also get decided later as rating rises: average move 16 at 1800, 19 at 2100,
  with the share settled in the opening falling from 38% to 23%.
  **⊕ Expand database** fetches more games and analyses them in the
  background, filling the thinnest band first.
- **Compare** — two players side by side.

### Where the data lives

Everything is one SQLite file, `data/chess.db`: the PGN of every game (yours
and, for the rating-bracket work, other players'), and every engine analysis
ever computed, keyed by game and depth. Loading a player's games is an indexed
lookup rather than a parse of every game on disk, de-duplication is a primary
key, and tens of thousands of games cost neither tens of thousands of inodes
nor an `os.listdir` per lookup.

### Syncing, and games that don't count

Reports sync before they run, so the games on screen are always current. That
stays cheap: past months are recorded in a manifest and never re-fetched, only
the current month is re-read, and a repeat sync of the same account inside a
minute is skipped. Games are read from the archive's `/pgn` feed rather than its
JSON twin — the JSON one is served from a cache that lags an hour behind, so
games played today are missing from it.

Two kinds of game are left out of every statistic while staying visible in the
history, marked ⚑:

- **Anomalous** — a disconnect, a game thrown on purpose. You tick this yourself
  in the game's review.
- **Opponent banned for fair play** — detected automatically. Chess.com
  publishes an account's standing, so opponents are checked on sync and games
  against a closed account are dropped. Chess.com refunds the rating such a game
  cost you, but days later, which leaves a dip and then a jump in the rating
  curve; `ratings.py` adds the points back over exactly that stretch so the
  curve is continuous. A win or draw against someone later banned keeps its
  gain, so it gets no correction.

## CLI (static HTML + JSON)

The same reports can be generated as static files without the server:

```bash
.venv/bin/python analyze.py                       # player report (all formats)
.venv/bin/python analyze.py game last             # engine review, most recent game
.venv/bin/python analyze.py game mainc4tur        # last game vs an opponent
.venv/bin/python analyze.py compare me rival      # two players side by side
```

Each run writes both `<name>.html` and `<name>.json` (the same Document the web
app consumes). Engine analysis is kept in the store, so re-runs are instant.

## Architecture

```
scraper.py                 Chess.com scraper (username only)
analyze.py                 CLI: pick a mode → build a Document → write HTML + JSON
webapp.py                  Flask app: serves the same Documents over /api/<mode>
frontend/                  index.html + app.js: mode picker, JS widget renderer,
                           interactive rating chart
chessanalysis/
├── store.py               data/chess.db — every game and every engine analysis
├── corpus/                rating-bracket corpus: SQL aggregates, crawler,
│                          sharded depth-10 engine pass (2 samples per game)
├── model.py               PGN → perspective-bound Game objects (+ parsed moves, clocks)
├── fairplay.py            opponents Chess.com closed for cheating (cached lookups)
├── ratings.py             rebases the rating curve around a refunded cheated game
├── contexts.py            per-mode input shapes (Player / Game / Compare)
├── enrich/engine.py       Stockfish per-move evals, accuracy, blunder detection (cached)
├── registry.py            @metric decorator; metrics tagged by scope
├── metrics/               compute-only units → widget data (auto-discovered)
│   ├── player/  game/  compare/
├── widgets.py             widget vocabulary = backend↔frontend data contract
├── document.py            a mode's output: ordered widgets + metadata → JSON
├── modes/                 build context → run scope's metrics → assemble Document
└── render_html.py         default renderer: Document → static HTML (incl. SVG)
```

## Three ways to extend — each is one file

**A new stat** — drop a file in `metrics/<scope>/`:

```python
from ...registry import metric
from ... import widgets as W
from ...util import tally, wdl_rows

@metric("player", title="By time control", order=30)
def by_time_control(ctx):
    return W.wdl_table("Format", wdl_rows(tally(ctx.games, lambda g: g.time_class)))
```

**A new mode** — add a `modes/` file with `@mode("name")` and a context type;
it reuses every metric of that scope.

**A new chart** — add a builder to `widgets.py` and a handler in
`render_html.py` (and, later, a frontend component).

The discipline that keeps it easy: **metrics compute, modes shape data,
renderers render** — never the other way around.
