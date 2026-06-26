# chess-analyzer

A small, zero-dependency toolkit to scrape your Chess.com games and generate an
HTML stats report. Built around a **plugin architecture** — adding a new stat is
just dropping one file into `chessanalysis/stats/`.

## Usage

```bash
# 1. Download your games (uses the public Chess.com API, no key needed)
python3 scraper.py <username>

# Optional: limit to a year / month
python3 scraper.py <username> --year 2026 --month 6

# 2. Build the HTML report
python3 analyze.py <username>
open report.html
```

Games are saved to `games/` and the report to `report.html` — both are
gitignored, so no personal data is committed.

## Architecture

```
scraper.py                 # Chess.com scraper (username only)
analyze.py                 # driver: load games → run all stats → write HTML
chessanalysis/
├── model.py               # PGN → perspective-bound Game objects (+ parsed moves, clocks, annotations)
├── registry.py            # @register decorator
├── util.py                # tally() + WDL aggregation helpers
├── render.py              # HTML widgets (cards, tables, bars, sparklines) + page shell
└── stats/                 # one file per stat, auto-discovered at import
```

## Adding a stat

Drop a file in `chessanalysis/stats/`. It self-registers — no wiring needed:

```python
from ..registry import register
from ..render import wdl_table
from ..util import tally

@register("By time control", order=30)
def by_time_control(games):
    return wdl_table("Format", tally(games, lambda g: g.time_class))
```

Each `Game` is bound to the analysed player, so `g.color`, `g.outcome`,
`g.user_elo`, `g.opponent`, and `g.my_moves` (with clocks and annotations) are
ready to use. `order=` controls placement in the report.
