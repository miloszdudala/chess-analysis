#!/usr/bin/env python3
"""Download all of a Chess.com account's games as PGN files.

Usage:
    python scraper.py <username> [--out games] [--year 2026] [--month 6]

Uses the Chess.com public API (no key required):
    https://www.chess.com/news/view/published-data-api
"""
import argparse
import calendar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from chessanalysis import cache, config

API = "https://api.chess.com/pub"
# Chess.com blocks requests without a real-looking User-Agent.
HEADERS = {"User-Agent": "Personal storage"}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def split_pgns(text):
    """Split a monthly PGN feed into one PGN string per game."""
    return [g.strip() for g in re.split(r'(?m)^(?=\[Event ")', text) if g.strip()]


def tag(pgn, name, default=""):
    """Value of a PGN header tag, or `default` if it is missing."""
    m = re.search(r'\[%s "([^"]*)"\]' % name, pgn)
    return m.group(1) if m else default


def end_time(pgn):
    """Unix timestamp from the UTC EndDate/EndTime tags (0 if unparseable)."""
    stamp = f"{tag(pgn, 'EndDate')} {tag(pgn, 'EndTime')}"
    try:
        return calendar.timegm(time.strptime(stamp, "%Y.%m.%d %H:%M:%S"))
    except ValueError:
        return 0


def list_archives(username):
    """Return list of monthly archive URLs, oldest first."""
    data = get_json(f"{API}/player/{username}/games/archives")
    return data.get("archives", [])


def download_month(archive_url, out_dir, username):
    """Download one month's games, one PGN file per game. Returns count saved.

    Reads the archive's `/pgn` feed rather than its JSON twin. The JSON one is
    served from a cache that routinely lags an hour behind (its `Age` runs far
    past the `max-age=5` it advertises), so today's games are simply absent
    from it; the PGN feed is rebuilt on request. Both carry the same games, and
    filenames and file contents here are unchanged, so games fetched by earlier
    versions are still recognised and never re-downloaded.
    """
    text = get_text(archive_url.rstrip("/") + "/pgn")
    # archive_url ends with /YYYY/MM
    year, month = archive_url.rstrip("/").split("/")[-2:]
    saved = 0
    for pgn in split_pgns(text):
        white = tag(pgn, "White", "white")
        black = tag(pgn, "Black", "black")
        name = f"{year}.{month}_{white}_vs_{black}_{end_time(pgn)}.pgn"
        # sanitize
        name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(pgn + "\n")
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
