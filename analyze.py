#!/usr/bin/env python3
"""Generate chess analysis reports.

Modes:
    player  [username]            full game-history report (default)
    game    [selector]           deep engine review of one game
                                   selector: game id, opponent name, index,
                                   or "last" (default: last game)
    compare <player_a> <player_b> two players side by side

Examples:
    python3 analyze.py                      # player report from CHESS_USERNAME
    python3 analyze.py game last            # review your most recent game
    python3 analyze.py game mainc4tur       # review last game vs that opponent
    python3 analyze.py compare me rival

Each run writes <name>.html and <name>.json (the same Document — JSON is the
contract a future JS frontend would consume).
"""
import argparse
import os

from chessanalysis import config, modes
from chessanalysis.render_html import render_document


def _write(doc, html_path):
    json_path = os.path.splitext(html_path)[0] + ".json"
    os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_document(doc))
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(doc.to_json())
    return json_path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="player",
                    choices=modes.names(), help="report mode (default: player)")
    ap.add_argument("args", nargs="*", help="mode arguments (see examples)")
    ap.add_argument("--games", default=config.get("GAMES_DIR", "games"))
    ap.add_argument("--out", help="output HTML path (default depends on mode)")
    ap.add_argument("--depth", type=int, help="engine depth (game mode)")
    args = ap.parse_args()

    user = config.get("CHESS_USERNAME")
    fn = modes.get(args.mode)

    if args.mode == "player":
        username = args.args[0] if args.args else user
        if not username:
            raise SystemExit("No username. Pass one or set CHESS_USERNAME in .env.")
        doc = fn(username, games_dir=args.games)
        out = args.out or config.get("REPORT_FILE", "report.html")

    elif args.mode == "game":
        username = user
        selector = args.args[0] if args.args else "last"
        if not username:
            raise SystemExit("No username. Set CHESS_USERNAME in .env.")
        doc = fn(username, games_dir=args.games, selector=selector, depth=args.depth)
        gid = doc.meta.get("game_id", "game")
        out = args.out or os.path.join("out", f"game-{gid}.html")

    elif args.mode == "compare":
        if len(args.args) < 2:
            raise SystemExit("compare needs two players: analyze.py compare A B")
        doc = fn(args.args[0], args.args[1], games_dir=args.games)
        out = args.out or os.path.join("out", f"compare-{args.args[0]}-{args.args[1]}.html")

    json_path = _write(doc, out)
    print(f"Wrote {out}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
