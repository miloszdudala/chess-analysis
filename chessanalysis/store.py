"""The one place games and engine analyses live.

Every game — yours and the sampled games of other players — is a row in
`games`; everything the engine has ever computed is a row in `analysis`.

Why one SQLite file rather than directories of files:

  * `load_games` used to glob `games/*.pgn`, parse **every** file, then discard
    the ones that didn't involve the player. Here it is an indexed lookup, and
    only the matching games are ever parsed.
  * de-duplication is a primary key, not a `set` built after parsing everything.
  * `cache.keys()` did an `os.listdir` of the whole engine cache, and
    `deepest_cached` called it once per game — quadratic as the cache grows.
    Here it is an indexed range scan.
  * a 2 KB PGN no longer occupies a 4 KB disk block, and tens of thousands of
    games no longer mean tens of thousands of inodes.

This module knows nothing about chess: it takes and returns plain dicts.
Turning a PGN into a row, or a row back into a `Game`, is `model`'s job.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import zlib

from . import config

DB_PATH = config.get("CHESS_DB") or os.path.join("data", "chess.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  gid          TEXT PRIMARY KEY,
  white        TEXT NOT NULL,
  black        TEXT NOT NULL,
  welo         INTEGER,
  belo         INTEGER,
  time_control TEXT,
  time_class   TEXT,
  date         TEXT,
  sort_key     TEXT,
  eco          TEXT,
  result       TEXT,
  termination  TEXT,
  plies        INTEGER,
  level        INTEGER,   -- mean of the two ratings
  band         INTEGER,   -- level floored to 100: the rating bracket
  gap          INTEGER,   -- |welo - belo|
  source       TEXT,      -- 'own' (a tracked account) | 'corpus' (crawled)
  pgn          BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_games_white ON games(white);
CREATE INDEX IF NOT EXISTS ix_games_black ON games(black);
CREATE INDEX IF NOT EXISTS ix_games_band  ON games(band, source);
CREATE INDEX IF NOT EXISTS ix_games_sort  ON games(sort_key);

CREATE TABLE IF NOT EXISTS analysis (
  gid     TEXT NOT NULL,
  depth   INTEGER NOT NULL,
  multipv INTEGER,
  engine  TEXT,
  secs    REAL,
  raw     BLOB NOT NULL,     -- zlib(json): evals, best_uci, moves_san, fens, ...
  PRIMARY KEY (gid, depth)
);

-- The rating-bracket corpus. `samples` is one row per (game, side): a single
-- engine pass over a game yields two data points, in two different brackets
-- when the players are not in the same one. Phase columns are pre-aggregated
-- because bracket statistics are SQL sums over them, but nothing is lost by
-- that: the eval array in `analysis` plus the PGN re-derives any move-level
-- stat, so a new phase split never needs the engine again.
CREATE TABLE IF NOT EXISTS samples (
  gid TEXT NOT NULL, color TEXT NOT NULL, depth INTEGER NOT NULL,
  elo INTEGER, opp_elo INTEGER, band INTEGER, outcome TEXT, plies INTEGER,
  acc REAL, acpl REAL, inacc INTEGER, mist INTEGER, blun INTEGER,
  op_n INTEGER, op_acc REAL, op_cpl INTEGER, op_ia INTEGER, op_mi INTEGER, op_bl INTEGER,
  mg_n INTEGER, mg_acc REAL, mg_cpl INTEGER, mg_ia INTEGER, mg_mi INTEGER, mg_bl INTEGER,
  eg_n INTEGER, eg_acc REAL, eg_cpl INTEGER, eg_ia INTEGER, eg_mi INTEGER, eg_bl INTEGER,
  dec_ply INTEGER, dec_side TEXT, dec_held INTEGER,
  PRIMARY KEY (gid, color, depth)
);
CREATE INDEX IF NOT EXISTS ix_samples_band ON samples(band, depth);

-- Crawl bookkeeping: who we have already spent, and who we could visit next.
CREATE TABLE IF NOT EXISTS players (
  username TEXT PRIMARY KEY, rating INTEGER, status TEXT, checked REAL,
  archives TEXT, spent TEXT, taken INTEGER DEFAULT 0, tried INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS frontier (
  username TEXT PRIMARY KEY, rating INTEGER, seen REAL);

-- Small keyed state that used to be a folder of JSON files: fair-play statuses
-- (ns 'fairplay'), which archive months a sync has finished (ns 'scrape'), and
-- the store's own bookkeeping (ns 'meta').
CREATE TABLE IF NOT EXISTS kv (
  ns TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  PRIMARY KEY (ns, key));

-- What the player has said about their own games: a corrected win/loss reason,
-- and the anomaly flag that drops a game from every statistic.
CREATE TABLE IF NOT EXISTS overrides (
  gid TEXT PRIMARY KEY, reason TEXT, flag TEXT, note TEXT);

-- Training: positions from the player's own games, scheduled for spaced
-- repetition. `ply` is the move to find; `fen` the position it is found in.
CREATE TABLE IF NOT EXISTS puzzles (
  id TEXT PRIMARY KEY, user TEXT NOT NULL, gid TEXT NOT NULL, ply INTEGER NOT NULL,
  kind TEXT NOT NULL, fen TEXT NOT NULL, solution TEXT NOT NULL, data TEXT NOT NULL,
  created REAL, due REAL, interval REAL DEFAULT 0, ease REAL DEFAULT 2.5,
  reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, last REAL, grade TEXT,
  retired INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_puzzles_due ON puzzles(user, retired, due);

-- Where each side of an analysed game lost its win chance (see coach.py), kept
-- because summarising a game means replaying it; `version` says by which recipe.
CREATE TABLE IF NOT EXISTS ledgers (
  gid TEXT NOT NULL, color TEXT NOT NULL, depth INTEGER NOT NULL,
  version INTEGER NOT NULL, elo INTEGER, data TEXT NOT NULL,
  PRIMARY KEY (gid, color, depth));
"""

# Columns added after a table first shipped: CREATE TABLE IF NOT EXISTS never
# alters an existing table, so they are added here when missing.
_ADDED_COLUMNS = {
    "samples": (("mg_ply", "INTEGER"), ("eg_ply", "INTEGER")),
}

GAME_COLS = ("gid", "white", "black", "welo", "belo", "time_control", "time_class",
             "date", "sort_key", "eco", "result", "termination", "plies",
             "level", "band", "gap", "source", "pgn")

_local = threading.local()
_init_lock = threading.Lock()
_initialised: set[str] = set()


def connect() -> sqlite3.Connection:
    """A connection for this thread. Flask serves requests on several."""
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == DB_PATH:
        return conn
    if conn is not None:
        conn.close()
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # readers never block the writer
    conn.execute("PRAGMA busy_timeout=120000")   # analysis shards write in parallel
    with _init_lock:
        if DB_PATH not in _initialised:
            conn.executescript(SCHEMA)
            for table, cols in _ADDED_COLUMNS.items():
                have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, kind in cols:
                    if name not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
            conn.commit()
            _import_legacy(conn)
            _initialised.add(DB_PATH)
    _local.conn, _local.path = conn, DB_PATH
    return conn


def reset() -> None:
    """Forget the cached connection — for tests that repoint DB_PATH."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = _local.path = None
    _initialised.discard(DB_PATH)


# --- games -------------------------------------------------------------------

def save_games(rows: list[dict]) -> int:
    """Insert games, ignoring ones already stored. Returns how many were new."""
    if not rows:
        return 0
    conn = connect()
    before = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    conn.executemany(
        f"INSERT OR IGNORE INTO games({','.join(GAME_COLS)}) "
        f"VALUES({','.join('?' * len(GAME_COLS))})",
        [tuple(r.get(c) for c in GAME_COLS) for r in rows])
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] - before


def games_of(user: str) -> list[dict]:
    """Every stored game the player appears in, oldest first."""
    user = user.lower()
    rows = connect().execute(
        "SELECT * FROM games WHERE white=? OR black=? ORDER BY sort_key",
        (user, user)).fetchall()
    return [dict(r) for r in rows]


def has_game(gid: str) -> bool:
    return connect().execute("SELECT 1 FROM games WHERE gid=?",
                             (str(gid),)).fetchone() is not None


def game_ids() -> set[str]:
    return {r[0] for r in connect().execute("SELECT gid FROM games")}


def count_games(source: str | None = None) -> int:
    q, a = "SELECT COUNT(*) FROM games", ()
    if source:
        q, a = q + " WHERE source=?", (source,)
    return connect().execute(q, a).fetchone()[0]


def unpack_pgn(blob) -> str:
    return zlib.decompress(blob).decode("utf-8", "replace")


def pack_pgn(text: str):
    return zlib.compress(text.encode("utf-8"), 6)


# --- engine analysis ---------------------------------------------------------

def load_analysis(gid: str, depth: int) -> dict | None:
    row = connect().execute("SELECT raw, engine FROM analysis WHERE gid=? AND depth=?",
                            (str(gid), depth)).fetchone()
    if row is None:
        return None
    try:
        raw = json.loads(zlib.decompress(row["raw"]).decode("utf-8"))
    except (zlib.error, json.JSONDecodeError, UnicodeDecodeError):
        return None
    raw.setdefault("engine_name", row["engine"] or "cache")
    return raw


def save_analysis(gid: str, depth: int, raw: dict, multipv: int = 3,
                  engine: str = "", secs: float | None = None) -> None:
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO analysis(gid,depth,multipv,engine,secs,raw) "
        "VALUES(?,?,?,?,?,?)",
        (str(gid), depth, multipv, engine or raw.get("engine_name", ""), secs,
         zlib.compress(json.dumps(raw, separators=(",", ":")).encode(), 6)))
    conn.commit()


def has_analysis(gid: str, depth: int) -> bool:
    return connect().execute("SELECT 1 FROM analysis WHERE gid=? AND depth=?",
                             (str(gid), depth)).fetchone() is not None


def mark_own(user: str) -> None:
    """Flag every game a tracked account played as 'own'.

    A game of yours can also turn up while crawling an opponent's archive; the
    insert that got there first wins. Re-stamping keeps cohort queries — which
    read `source='corpus'` — from ever comparing you against yourself.
    """
    conn = connect()
    conn.execute("UPDATE games SET source='own' WHERE white=? OR black=?",
                 (user.lower(), user.lower()))
    conn.commit()


def analysed_depths(gid: str) -> list[int]:
    """Depths already computed for a game, deepest last."""
    return [r[0] for r in connect().execute(
        "SELECT depth FROM analysis WHERE gid=? ORDER BY depth", (str(gid),))]


# --- small keyed state ---------------------------------------------------------

def kv_get(ns: str, key: str, default=None):
    row = connect().execute("SELECT value FROM kv WHERE ns=? AND key=?",
                            (ns, str(key))).fetchone()
    return json.loads(row[0]) if row else default


def kv_set(ns: str, key: str, value) -> None:
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO kv(ns,key,value) VALUES(?,?,?)",
                 (ns, str(key), json.dumps(value, separators=(",", ":"))))
    conn.commit()


def kv_all(ns: str) -> dict:
    return {r[0]: json.loads(r[1]) for r in connect().execute(
        "SELECT key, value FROM kv WHERE ns=?", (ns,))}


def _import_legacy(conn: sqlite3.Connection) -> None:
    """Fold the pre-2.0 JSON files into the store, once.

    They lived beside the database — `cache/<ns>/<key>.json` and
    `overrides.json` — so they are looked for beside *this* database, never in
    the working directory: a test's throwaway store must not inherit a real
    player's flags.
    """
    if conn.execute("SELECT 1 FROM kv WHERE ns='meta' AND key='legacy_imported'").fetchone():
        return
    base = os.path.dirname(DB_PATH) or "."
    for ns in ("fairplay", "scrape"):
        folder = os.path.join(base, "cache", ns)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    value = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            conn.execute("INSERT OR IGNORE INTO kv(ns,key,value) VALUES(?,?,?)",
                         (ns, name[:-5], json.dumps(value)))
    try:
        with open(os.path.join(base, "overrides.json"), encoding="utf-8") as f:
            legacy = json.load(f)
    except (OSError, json.JSONDecodeError):
        legacy = {}
    for gid, e in legacy.items():
        if isinstance(e, dict):
            conn.execute("INSERT OR IGNORE INTO overrides(gid,reason,flag,note) "
                         "VALUES(?,?,?,?)", (gid, e.get("primary"), e.get("flag"),
                                             e.get("note")))
    conn.execute("INSERT OR REPLACE INTO kv(ns,key,value) VALUES('meta','legacy_imported','true')")
    conn.commit()
