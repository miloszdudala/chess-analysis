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

cp .env.example .env                              # then set CHESS_USERNAME
```

`.env` (gitignored) holds `CHESS_USERNAME`, `GAMES_DIR`, `REPORT_FILE`,
`STOCKFISH_PATH`, `ENGINE_DEPTH`.

## Run the web app

```bash
# 1. Download your games (public Chess.com API, no key needed)
python3 scraper.py

# 2. Start the app, then open http://127.0.0.1:5050
.venv/bin/python webapp.py

# Stop the app: press Ctrl+C in its terminal, or from another terminal:
pkill -f webapp.py
```

Run it on a different port with `PORT=8080 .venv/bin/python webapp.py`.

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
- **Compare** — two players side by side.

The Chess.com API is only ever called by `scraper.py`. Past months are recorded
in a manifest and skipped on later runs — only the current month is re-checked —
so games are effectively downloaded once.

## CLI (static HTML + JSON)

The same reports can be generated as static files without the server:

```bash
.venv/bin/python analyze.py                       # player report (all formats)
.venv/bin/python analyze.py game last             # engine review, most recent game
.venv/bin/python analyze.py game mainc4tur        # last game vs an opponent
.venv/bin/python analyze.py compare me rival      # two players side by side
```

Each run writes both `<name>.html` and `<name>.json` (the same Document the web
app consumes). Engine analysis is cached to `data/cache/`, so re-runs are instant.

## Architecture

```
scraper.py                 Chess.com scraper (username only)
analyze.py                 CLI: pick a mode → build a Document → write HTML + JSON
webapp.py                  Flask app: serves the same Documents over /api/<mode>
frontend/                  index.html + app.js: mode picker, JS widget renderer,
                           interactive rating chart
chessanalysis/
├── model.py               PGN → perspective-bound Game objects (+ parsed moves, clocks)
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
