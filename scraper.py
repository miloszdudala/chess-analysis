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

from chessanalysis import cache, config

API = "https://api.chess.com/pub"
# Chess.com blocks requests without a real-looking User-Agent.
HEADERS = {"User-Agent": "personal game storage"}


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


def scrape(username, out_dir="games", year=None, month=None, log=print):
    """Download games for `username` into `out_dir`. Returns a summary dict.

    Reusable by both the CLI and the web app's Sync button. Past months are
    recorded in a manifest and skipped on later runs (no API call); only the
    current month is re-checked. A date filter bypasses the manifest.
    """
    username = username.lower()
    os.makedirs(out_dir, exist_ok=True)

    try:
        archives = list_archives(username)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"No such Chess.com account: '{username}'")
        raise
    if not archives:
        return {"new": 0, "skipped": 0, "requests": 1}

    filtered = bool(year)
    if year:
        archives = [a for a in archives if f"/{year:04d}/" in a]
        if month:
            sel = f"/{year:04d}/{month:02d}"
            archives = [a for a in archives if a.rstrip("/").endswith(sel)]

    manifest = cache.load("scrape", username) or {"completed": []}
    completed = set(manifest.get("completed", []))
    latest = archives[-1] if archives else None

    total = skipped = requests = 0
    requests += 1  # the archives list
    for url in archives:
        if not filtered and url != latest and url in completed:
            skipped += 1
            continue
        try:
            n = download_month(url, out_dir, username)
            requests += 1
            total += n
            label = "/".join(url.rstrip("/").split("/")[-2:])
            log(f"  {label}: +{n} new games")
            if not filtered and url != latest:
                completed.add(url)        # past month: fetched once, never again
        except urllib.error.HTTPError as e:
            log(f"  {url}: error {e.code}")
        time.sleep(0.3)  # be polite to the API

    if not filtered:
        cache.save("scrape", username, {"completed": sorted(completed)})

    return {"new": total, "skipped": skipped, "requests": requests}


def main():
    ap = argparse.ArgumentParser(description="Scrape Chess.com games to PGN.")
    ap.add_argument("username", nargs="?", default=config.get("CHESS_USERNAME"),
                    help="Chess.com account name (defaults to CHESS_USERNAME in .env)")
    ap.add_argument("--out", default=config.get("GAMES_DIR", "games"),
                    help="Output folder (default: games)")
    ap.add_argument("--year", type=int, help="Only this year")
    ap.add_argument("--month", type=int, help="Only this month (needs --year)")
    args = ap.parse_args()

    if not args.username:
        sys.exit("No username given. Pass one, or set CHESS_USERNAME in .env.")
    try:
        res = scrape(args.username, args.out, args.year, args.month)
    except ValueError as e:
        sys.exit(str(e))

    extra = f" ({res['skipped']} months already complete, skipped)" if res["skipped"] else ""
    print(f"\nDone. {res['new']} new games saved to '{args.out}/'{extra}.")


if __name__ == "__main__":
    main()
