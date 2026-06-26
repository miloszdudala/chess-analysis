"""PGN parsing into rich, perspective-bound Game objects.

A Game is bound to one user: fields like `color`, `outcome`, `user_elo` are
always from that user's point of view, so stats never re-derive perspective.
Moves are parsed too (SAN, clock, annotation NAG) so move-level stats —
time management, blunder counts — have data without re-parsing.
"""
from __future__ import annotations

import glob
import os
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

    # --- perspective (filled by bind()) ---
    user: str = ""
    color: str = ""          # "white" | "black"
    outcome: str = ""        # "win" | "loss" | "draw"
    user_elo: int | None = None
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


def parse_pgn_file(path: str) -> list[Game]:
    """Parse every game in a (possibly multi-game) PGN file. No perspective yet."""
    games: list[Game] = []
    headers: dict = {}
    movetext: list[str] = []
    in_moves = False

    def flush():
        if headers:
            games.append(Game(headers=dict(headers), moves=_parse_moves(" ".join(movetext))))

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            tag = _TAG_RE.match(line)
            if tag:
                if in_moves:        # a new game's headers begin
                    flush()
                    headers, movetext, in_moves = {}, [], False
                headers[tag.group(1)] = tag.group(2)
            elif line.strip() == "":
                if headers and not in_moves:
                    in_moves = True
            else:
                in_moves = True
                movetext.append(line.strip())
    flush()
    return games


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
    game.opp_elo = int(game.h(opp_elo_tag)) if game.h(opp_elo_tag).isdigit() else None
    game.opponent = black if game.color == "white" else white
    return game


def load_games(folder: str, user: str) -> list[Game]:
    """Load all PGNs in `folder`, bound to `user`, sorted chronologically."""
    games: list[Game] = []
    for path in glob.glob(os.path.join(folder, "*.pgn")):
        for g in parse_pgn_file(path):
            bound = bind(g, user)
            if bound:
                games.append(bound)
    games.sort(key=lambda g: g.sort_key)
    return games
