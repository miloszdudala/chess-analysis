#!/usr/bin/env python3
"""Chess Analyzer from the terminal.

    python3 analyze.py                         # the coach: you against players at your rating
    python3 analyze.py coach [user] [--last 30]
    python3 analyze.py train [user]            # refresh training positions, show the queue
    python3 analyze.py player [user]           # the full report, as JSON
    python3 analyze.py game [selector]         # one game's review, as JSON
    python3 analyze.py scout <opponent>        # an opponent's report, as JSON

JSON reports are the same Documents the web app renders (out/<name>.json).
The account defaults to CHESS_USERNAME from .env.
"""
from __future__ import annotations

import argparse
import os
import sys

from chessanalysis import config


def _write(doc, name):
    os.makedirs("out", exist_ok=True)
    path = os.path.join("out", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc.to_json())
    print(f"Wrote {path}")


def coach(user, last=None):
    from chessanalysis import coach as C

    res = C.compare(user, last=last)
    if not res:
        sys.exit("Not enough analysed games yet — open the web app once to analyse them, "
                 "or grow the corpus from its Peers tab.")
    pl = res["plays_like"] or {}
    lo, hi = res["elo_range"]

    def place(p):
        if not p:
            return "?"
        return str(p.get("elo") or (f"{p['above']}+" if "above" in p else f"<{p['below']}"))

    print(f"\n  {user} — {res['games']} games ({lo}–{hi}) against corpus players at the "
          f"rating you had in each\n  {res['peers']} game sides · depth {res['depth']} · "
          f"{res['time_control']}s games\n")
    if pl:
        print(f"  Your moves play like ≈{place(pl['point'])} "
              f"(95%: {place(pl['low'])}–{place(pl['high'])})\n")
    print(f"  {'':28}{'you':>7}{'peers':>8}{'gap':>7}{'control':>9}{'net':>7}   interval")
    group = None
    for r in res["rows"]:
        if r["group"] != group:
            group = r["group"]
            print(f"  {group.upper()}")
        mark = {"leak": "▲ leak", "strength": "▼ strength"}.get(r["verdict"], "")
        print(f"    {r['label']:26}{r['you']:7.2f}{r['peers']:8.2f}{100 * r['gap']:+6.0f}%"
              f"{100 * r['control']:+8.0f}%{100 * r['net']:+6.0f}%   "
              f"[{100 * r['lo']:+.0f}%, {100 * r['hi']:+.0f}%]  {mark}")
    print("\n  Win-chance points lost per move; net = your gap with your opponents' "
          "(the control) taken out.\n")


def train(user):
    from chessanalysis import training

    s = training.sync(user)
    print(f"\n  {s['total']} positions from your games ({s['added']} new this time)")
    for k, v in s["by_kind"].items():
        print(f"    {s['kinds'][k]:18} {v['total']:4}   due {v['due']:3}   unseen {v['new']:3}"
              f"   learned {v['learned']:3}")
    print(f"\n  Today: {s['due']} due + {min(s['new'], s['new_left_today'])} new. "
          f"Train them in the web app's Train tab.\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="coach",
                    choices=["coach", "train", "player", "game", "scout"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--format", default="rapid", help="time class (player/scout)")
    ap.add_argument("--last", type=int, help="coach: only your most recent N games")
    ap.add_argument("--depth", type=int, help="game: engine depth")
    a = ap.parse_args()

    from chessanalysis import modes

    me = config.get("CHESS_USERNAME")
    if a.command in ("coach", "train", "player"):
        user = a.args[0] if a.args else me
        if not user:
            sys.exit("No username. Pass one or set CHESS_USERNAME in .env.")
        if a.command == "coach":
            coach(user, a.last)
        elif a.command == "train":
            train(user)
        else:
            _write(modes.get("player")(user, time_class=a.format), f"player-{user}")
    elif a.command == "game":
        if not me:
            sys.exit("Set CHESS_USERNAME in .env.")
        doc = modes.get("game")(me, selector=a.args[0] if a.args else "last", depth=a.depth)
        _write(doc, f"game-{doc.meta['game_id']}")
    else:
        if not a.args:
            sys.exit("scout needs an opponent: analyze.py scout <account>")
        import scraper
        scraper.scrape(a.args[0], source="scout", months=6, log=lambda *_: None)
        _write(modes.get("scout")(a.args[0], me=me or "", time_class=a.format),
               f"scout-{a.args[0]}")


if __name__ == "__main__":
    main()
