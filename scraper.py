#!/usr/bin/env python3
"""Download all of a Chess.com account's games into the store.

Usage:
    python scraper.py <username> [--year 2026] [--month 6]

Uses the Chess.com public API (no key required):
    https://www.chess.com/news/view/published-data-api
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from chessanalysis import config, model, store

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


def list_archives(username):
    """Return list of monthly archive URLs, oldest first."""
    data = get_json(f"{API}/player/{username}/games/archives")
    return data.get("archives", [])


def download_month(archive_url, source="own"):
    """Download one month's games into the store. Returns how many were new.

    Reads the archive's `/pgn` feed rather than its JSON twin. The JSON one is
    served from a cache that routinely lags an hour behind (its `Age` runs far
    past the `max-age=5` it advertises), so today's games are simply absent
    from it; the PGN feed is rebuilt on request.

    Re-downloading a month costs nothing: the game id is the store's primary
    key, so games already held are ignored rather than duplicated.
    """
    text = get_text(archive_url.rstrip("/") + "/pgn")
    return store.save_games([model.game_row(g, source=source)
                             for g in model.parse_pgn_text(text)])


def scrape(username, year=None, month=None, log=print, source="own",
           months=None):
    """Download games for `username` into the store. Returns a summary dict.

    Reusable by both the CLI and the web app's Sync button. Past months are
    recorded in a manifest and skipped on later runs (no API call); only the
    current month is re-checked. A date filter bypasses the manifest.

    `source` says whose games these are. "own" — an account being tracked —
    re-stamps every stored game of theirs as own, so the corpus never compares
    you against yourself. "scout" — an opponent being prepared for — leaves
    any of their games already in the corpus where they are. `months` keeps
    only the most recent archive months: scouting wants current form, not a
    five-year career.
    """
    username = username.lower()

    try:
        archives = list_archives(username)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"No such Chess.com account: '{username}'")
        raise
    if not archives:
        return {"new": 0, "skipped": 0, "requests": 1}

    filtered = bool(year)
    if months:
        archives = archives[-months:]
    if year:
        archives = [a for a in archives if f"/{year:04d}/" in a]
        if month:
            sel = f"/{year:04d}/{month:02d}"
            archives = [a for a in archives if a.rstrip("/").endswith(sel)]

    manifest = store.kv_get("scrape", username) or {"completed": []}
    completed = set(manifest.get("completed", []))
    latest = archives[-1] if archives else None

    total = skipped = requests = 0
    requests += 1  # the archives list
    for url in archives:
        if not filtered and url != latest and url in completed:
            skipped += 1
            continue
        try:
            n = download_month(url, source)
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
        store.kv_set("scrape", username, {"completed": sorted(completed)})

    if source == "own":
        store.mark_own(username)
    return {"new": total, "skipped": skipped, "requests": requests}


def main():
    ap = argparse.ArgumentParser(description="Download Chess.com games into the store.")
    ap.add_argument("username", nargs="?", default=config.get("CHESS_USERNAME"),
                    help="Chess.com account name (defaults to CHESS_USERNAME in .env)")
    ap.add_argument("--year", type=int, help="Only this year")
    ap.add_argument("--month", type=int, help="Only this month (needs --year)")
    args = ap.parse_args()

    if not args.username:
        sys.exit("No username given. Pass one, or set CHESS_USERNAME in .env.")
    try:
        res = scrape(args.username, args.year, args.month)
    except ValueError as e:
        sys.exit(str(e))

    extra = f" ({res['skipped']} months already complete, skipped)" if res["skipped"] else ""
    print(f"\nDone. {res['new']} new games stored in {store.DB_PATH}{extra}.")


if __name__ == "__main__":
    main()
