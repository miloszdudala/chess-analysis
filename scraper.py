#!/usr/bin/env python3
"""Download all of a Chess.com account's games as PGN files.

Usage:
    python scraper.py <username> [--out games] [--year 2026] [--month 6]

Uses the Chess.com public API (no key required):
    https://www.chess.com/news/view/published-data-api
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.chess.com/pub"
# Chess.com blocks requests without a real-looking User-Agent.
HEADERS = {"User-Agent": "chess-analyzer (personal game-analysis tool)"}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_archives(username):
    """Return list of monthly archive URLs, oldest first."""
    data = get_json(f"{API}/player/{username}/games/archives")
    return data.get("archives", [])


def download_month(archive_url, out_dir, username):
    """Download one month's games, one PGN file per game. Returns count saved."""
    data = get_json(archive_url)
    games = data.get("games", [])
    saved = 0
    for g in games:
        pgn = g.get("pgn")
        if not pgn:
            continue
        # archive_url ends with /YYYY/MM
        year, month = archive_url.rstrip("/").split("/")[-2:]
        white = g.get("white", {}).get("username", "white")
        black = g.get("black", {}).get("username", "black")
        end = g.get("end_time", 0)
        name = f"{year}.{month}_{white}_vs_{black}_{end}.pgn"
        # sanitize
        name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(pgn)
        saved += 1
    return saved


def main():
    ap = argparse.ArgumentParser(description="Scrape Chess.com games to PGN.")
    ap.add_argument("username", help="Chess.com account name")
    ap.add_argument("--out", default="games", help="Output folder (default: games)")
    ap.add_argument("--year", type=int, help="Only this year")
    ap.add_argument("--month", type=int, help="Only this month (needs --year)")
    args = ap.parse_args()

    username = args.username.lower()
    os.makedirs(args.out, exist_ok=True)

    try:
        archives = list_archives(username)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"No such Chess.com account: '{username}'")
        raise

    if not archives:
        sys.exit(f"No games found for '{username}'.")

    if args.year:
        sel = f"/{args.year:04d}/"
        archives = [a for a in archives if sel in a]
        if args.month:
            sel = f"/{args.year:04d}/{args.month:02d}"
            archives = [a for a in archives if a.rstrip("/").endswith(sel)]

    total = 0
    for url in archives:
        try:
            n = download_month(url, args.out, username)
            total += n
            label = "/".join(url.rstrip("/").split("/")[-2:])
            print(f"  {label}: +{n} new games")
        except urllib.error.HTTPError as e:
            print(f"  {url}: error {e.code}", file=sys.stderr)
        time.sleep(0.3)  # be polite to the API

    print(f"\nDone. {total} new games saved to '{args.out}/'.")


if __name__ == "__main__":
    main()
