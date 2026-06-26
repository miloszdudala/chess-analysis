# chess-analyzer

Scrape your Chess.com games and generate analysis reports — a full
game-history overview, a deep **engine review** of a single game (Stockfish),
and player **comparison**. Built around a pluggable architecture: new stats,
new modes, and new charts each drop in as a single file.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # python-chess
brew install stockfish                            # engine for game review

cp .env.example .env                              # then set CHESS_USERNAME
```

`.env` (gitignored) holds `CHESS_USERNAME`, `GAMES_DIR`, `REPORT_FILE`,
`STOCKFISH_PATH`, `ENGINE_DEPTH`.

## Usage

```bash
# Download your games (public Chess.com API, no key needed)
python3 scraper.py

# Reports (run under the venv so python-chess/Stockfish are available)
.venv/bin/python analyze.py                       # player report (default)
.venv/bin/python analyze.py game last             # engine review, most recent game
.venv/bin/python analyze.py game mainc4tur        # last game vs an opponent
.venv/bin/python analyze.py game 170739219564     # by Chess.com game id
.venv/bin/python analyze.py compare me rival      # two players side by side
```

Each run writes both `<name>.html` and `<name>.json`. The JSON is the same
Document — it's the contract a future JS frontend would consume for richer
plots. Engine analysis is cached to `data/cache/`, so re-runs are instant.

## Architecture

```
scraper.py                 Chess.com scraper (username only)
analyze.py                 CLI: pick a mode → build a Document → write HTML + JSON
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
