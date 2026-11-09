"""PGN parsing into rich, perspective-bound Game objects.

A Game is bound to one user: fields like `color`, `outcome`, `user_elo` are
always from that user's point of view, so stats never re-derive perspective.
Moves are parsed too (SAN, clock, annotation NAG) so move-level stats —
time management, blunder counts — have data without re-parsing.

PGN text itself lives in `store` (one SQLite file), not in a folder of files,
so loading a player's games is an indexed lookup rather than a parse of every
game on disk. This module is the translation layer between the two: rows in,
`Game` objects out, and `game_row` back the other way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]\s*$')
_CLK_RE = re.compile(r"%clk\s+([0-9:.]+)")
# Token stream of the movetext: comment | NAG | move-number | result | SAN
_TOKEN_RE = re.compile(r"\{[^}]*\}|\$\d+|\d+\.(?:\.\.)?|1-0|0-1|1/2-1/2|\*|[^\s]+")

# Chess.com / standard NAG meanings worth surfacing.
NAG_NAMES = {
    "$1": "good", "$2": "mistake", "$3": "brilliant", "$4": "blunder",
    "$5": "interesting", "$6": "dubious",
}

TIME_CLASSES = ("bullet", "blitz", "rapid", "classical", "daily")


@dataclass
class Move:
    ply: int                 # 1-based half-move number
    color: str               # "white" | "black"
    san: str                 # e.g. "Nf3", "O-O", "exd5"
    clock: float | None = None   # seconds left on mover's clock after the move
    nag: str | None = None       # raw NAG token, e.g. "$4"

    @property
    def annotation(self) -> str | None:
        return NAG_NAMES.get(self.nag) if self.nag else None


@dataclass
class Game:
    headers: dict
    moves: list[Move] = field(default_factory=list)
    pgn: str = ""            # raw PGN text (for engine replay via python-chess)

    # --- perspective (filled by bind()) ---
    user: str = ""
    color: str = ""          # "white" | "black"
    outcome: str = ""        # "win" | "loss" | "draw"
    user_elo: int | None = None      # rebased: see ratings.apply
    user_elo_raw: int | None = None  # exactly as Chess.com recorded it
    opp_elo: int | None = None
    opponent: str = ""

    # convenience header access -------------------------------------------------
    def h(self, key: str, default: str = "") -> str:
        return self.headers.get(key, default)

    @property
    def result(self) -> str:
        return self.h("Result", "*")

    @property
    def eco(self) -> str:
        return self.h("ECO", "?")

    @property
    def opening(self) -> str:
        """Human-readable opening name, derived from ECOUrl when present."""
        url = self.h("ECOUrl")
        if url:
            return url.rstrip("/").split("/")[-1].replace("-", " ")
        return self.eco

    @property
    def time_control(self) -> str:
        return self.h("TimeControl")

    @property
    def time_class(self) -> str:
        """bullet / blitz / rapid / classical / daily, from TimeControl."""
        tc = self.time_control
        if "/" in tc:
            return "daily"
        base = tc.split("+")[0]
        try:
            base = int(base)
        except ValueError:
            return "other"
        if base < 180:
            return "bullet"
        if base < 600:
            return "blitz"
        if base < 1800:
            return "rapid"
        return "classical"

    @property
    def termination(self) -> str:
        return self.h("Termination", "?")

    @property
    def date(self) -> str:
        return self.h("UTCDate") or self.h("Date", "")

    @property
    def game_id(self) -> str:
        """Stable identity for de-duplication across files.

        Chess.com Link/URL tags embed a numeric game id; the same game can
        appear under different Link formats (e.g. .../analysis), so we pull the
        id out. Falls back to players + start time for non-Chess.com PGNs.
        """
        for tag in ("Link", "ECOUrl"):
            url = self.h(tag)
            m = re.search(r"/(?:live|daily)/(\d+)", url)
            if m:
                return m.group(1)
        return "|".join((
            self.h("White"), self.h("Black"),
            self.h("UTCDate") or self.h("Date"),
            self.h("UTCTime") or self.h("StartTime"),
        ))

    @property
    def sort_key(self) -> str:
        """Chronological, lexicographically sortable."""
        d = self.h("EndDate") or self.h("UTCDate") or self.h("Date", "")
        t = self.h("EndTime") or self.h("UTCTime") or self.h("StartTime", "")
        return f"{d} {t}"

    @property
    def my_moves(self) -> list[Move]:
        """Only the moves the user actually played."""
        return [m for m in self.moves if m.color == self.color]


def _clock_seconds(s: str) -> float | None:
    """'0:09:58.5' -> 598.5 seconds."""
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _parse_moves(movetext: str) -> list[Move]:
    moves: list[Move] = []
    ply = 0
    for tok in _TOKEN_RE.findall(movetext):
        if tok.startswith("{"):                       # comment -> attach clock
            if moves:
                m = _CLK_RE.search(tok)
                if m:
                    moves[-1].clock = _clock_seconds(m.group(1))
        elif tok.startswith("$"):                      # NAG -> attach annotation
            if moves:
                moves[-1].nag = tok
        elif re.fullmatch(r"\d+\.(?:\.\.)?", tok):     # move number -> ignore
            continue
        elif tok in ("1-0", "0-1", "1/2-1/2", "*"):    # result -> ignore
            continue
        else:                                          # SAN
            ply += 1
            moves.append(Move(ply=ply, color="white" if ply % 2 else "black", san=tok))
    return moves


def parse_pgn_text(text: str) -> list[Game]:
    """Parse every game in a (possibly multi-game) PGN string. No perspective yet."""
    games: list[Game] = []
    headers: dict = {}
    movetext: list[str] = []
    raw: list[str] = []
    in_moves = False

    def flush():
        if headers:
            games.append(Game(
                headers=dict(headers),
                moves=_parse_moves(" ".join(movetext)),
                pgn="\n".join(raw),
            ))

    for line in text.splitlines():
        tag = _TAG_RE.match(line)
        if tag:
            if in_moves:            # a new game's headers begin
                flush()
                headers, movetext, raw, in_moves = {}, [], [], False
            headers[tag.group(1)] = tag.group(2)
        elif line.strip() == "":
            if headers and not in_moves:
                in_moves = True
        else:
            in_moves = True
            movetext.append(line.strip())
        raw.append(line)
    flush()
    return games


def parse_pgn_file(path: str) -> list[Game]:
    """Parse a PGN file from disk — used when importing games into the store."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_pgn_text(f.read())


def _int(value: str):
    return int(value) if value.isdigit() else None


def game_row(game: Game, source: str = "own") -> dict:
    """A parsed Game as a `store.games` row.

    The rating columns (`level`, `band`, `gap`) are denormalised so bracket
    statistics are a SQL aggregate over indexed integers and never have to
    touch, let alone parse, the PGN text.
    """
    from . import store

    welo, belo = _int(game.h("WhiteElo")), _int(game.h("BlackElo"))
    level = band = gap = None
    if welo is not None and belo is not None:
        level = (welo + belo) // 2
        band = level // 100 * 100
        gap = abs(welo - belo)
    return {
        "gid": str(game.game_id),
        "white": game.h("White").lower(), "black": game.h("Black").lower(),
        "welo": welo, "belo": belo,
        "time_control": game.time_control, "time_class": game.time_class,
        "date": game.date, "sort_key": game.sort_key,
        "eco": game.eco, "result": game.result,
        "termination": game.termination[:80], "plies": len(game.moves),
        "level": level, "band": band, "gap": gap,
        "source": source, "pgn": store.pack_pgn(game.pgn),
    }


def bind(game: Game, user: str) -> Game | None:
    """Fill perspective fields. Returns None if the user isn't in this game."""
    user = user.lower()
    white = game.h("White").lower()
    black = game.h("Black").lower()
    if user not in (white, black):
        return None

    game.user = user
    game.color = "white" if user == white else "black"

    res = game.result
    if res == "1/2-1/2":
        game.outcome = "draw"
    elif (res == "1-0") == (game.color == "white"):
        game.outcome = "win"
    else:
        game.outcome = "loss"

    elo_tag = "WhiteElo" if game.color == "white" else "BlackElo"
    opp_elo_tag = "BlackElo" if game.color == "white" else "WhiteElo"
    game.user_elo = int(game.h(elo_tag)) if game.h(elo_tag).isdigit() else None
    game.user_elo_raw = game.user_elo
    game.opp_elo = int(game.h(opp_elo_tag)) if game.h(opp_elo_tag).isdigit() else None
    game.opponent = black if game.color == "white" else white
    return game


def load_games(user: str, include_flagged: bool = False) -> list[Game]:
    """Every stored game `user` played, bound to them, sorted chronologically.

    Two kinds of game are left out unless `include_flagged`: those the player
    flagged as unrepresentative (see `overrides`), and those played against an
    account Chess.com has since closed for cheating (see `fairplay`). Every
    statistic goes through here, so excluding a game drops it from all of them
    at once. Views that show the record rather than measure it (the history
    list, a game's own review) pass True.

    Ratings are rebased first, over the *whole* history — a cheated game's
    refund is only readable with every sample present, and the correction has
    to be in place before anything downstream reads `user_elo`.
    """
    from . import fairplay, overrides, ratings, store

    games: list[Game] = []
    seen: set[str] = set()
    for row in store.games_of(user):
        for g in parse_pgn_text(store.unpack_pgn(row["pgn"])):
            bound = bind(g, user)
            if not bound:
                continue
            if bound.game_id in seen:   # the same game reached us twice
                continue
            seen.add(bound.game_id)
            games.append(bound)
    games.sort(key=lambda g: g.sort_key)

    cheated = fairplay.cheated_ids(games)
    ratings.apply(games, cheated, fairplay.banned_since(games))
    if include_flagged:
        return games
    skip = overrides.flagged_ids() | cheated
    return [g for g in games if str(g.game_id) not in skip]
