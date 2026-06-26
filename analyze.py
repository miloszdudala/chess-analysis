#!/usr/bin/env python3
"""Generate an HTML chess stats report from PGNs.

Usage:
    python analyze.py <username> [--games games] [--out report.html]

The report is assembled from every stat registered in chessanalysis/stats/.
To add a stat, drop a new file there — no changes needed here.
"""
import argparse

from chessanalysis import config
from chessanalysis import stats as _stats  # noqa: F401  (triggers auto-discovery)
from chessanalysis.model import load_games
from chessanalysis.registry import all_stats
from chessanalysis.render import page


def build_report(games, user):
    sections = []
    for stat in all_stats():
        body = stat.fn(games)
        if not body:
            continue
        if stat.title:
            sections.append(f"<h2>{stat.title}</h2>\n{body}")
        else:
            sections.append(body)
    return page(user, len(games), "\n".join(sections))


def main():
    ap = argparse.ArgumentParser(description="Generate HTML chess stats from PGNs.")
    ap.add_argument("username", nargs="?", default=config.get("CHESS_USERNAME"),
                    help="Your account name (defaults to CHESS_USERNAME in .env)")
    ap.add_argument("--games", default=config.get("GAMES_DIR", "games"),
                    help="Folder of PGN files")
    ap.add_argument("--out", default=config.get("REPORT_FILE", "report.html"),
                    help="Output HTML file")
    args = ap.parse_args()

    if not args.username:
        raise SystemExit("No username given. Pass one, or set CHESS_USERNAME in .env.")

    games = load_games(args.games, args.username)
    if not games:
        raise SystemExit(
            f"No games for '{args.username}' found in '{args.games}/'. "
            f"Run scraper.py first, and check the name matches the PGN tags."
        )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_report(games, args.username))
    print(f"Wrote {args.out} ({len(games)} games, {len(all_stats())} stat blocks).")


if __name__ == "__main__":
    main()
