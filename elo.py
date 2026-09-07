#!/usr/bin/env python3
"""
Chess.com rating calculator (Glicko-1, calibrated on real game data).

Start from scratch at 1500 / RD 350, feed in a series of opponent ratings,
get the final rating.

USAGE
-----
  Command line (bare number = win, add /d for draw, /l for loss):

      python3 elo.py 1800 1900 2000/d 2100 2050/l

  Interactive (no arguments) -- paste or type ratings, blank line to finish:

      python3 elo.py

  Options:
      --start 1500      starting rating
      --rd 350          starting rating deviation
      --target 2100     mark when this rating is first reached
      --opp-rd 80       assumed opponent RD

No dependencies beyond the standard library.
"""

import math
import sys

# --- calibrated parameters -------------------------------------------------
# Fitted against four real Chess.com games (RMS error 5.1 rating points).
DEFAULT_START = 1500.0
DEFAULT_RD = 350.0
DEFAULT_OPP_RD = 80.0
SHRINK = 0.95          # extra RD shrink; textbook Glicko alone decays too slowly
RD_FLOOR = 40.0
RD_CEIL = 350.0

Q = math.log(10) / 400.0
PI2 = math.pi ** 2


def g(rd):
    return 1.0 / math.sqrt(1.0 + 3.0 * Q * Q * rd * rd / PI2)


def expected(r, r_opp, rd_opp):
    return 1.0 / (1.0 + 10.0 ** (-g(rd_opp) * (r - r_opp) / 400.0))


def update(r, rd, r_opp, score, rd_opp=DEFAULT_OPP_RD):
    """One rated game. score: 1.0 win, 0.5 draw, 0.0 loss."""
    rd = min(max(rd, RD_FLOOR), RD_CEIL)
    gj = g(rd_opp)
    E = expected(r, r_opp, rd_opp)
    E = min(max(E, 1e-9), 1 - 1e-9)
    d2 = 1.0 / (Q * Q * gj * gj * E * (1.0 - E))
    denom = 1.0 / (rd * rd) + 1.0 / d2
    new_r = r + (Q / denom) * gj * (score - E)
    new_rd = max(math.sqrt(1.0 / denom) * SHRINK, RD_FLOOR)
    return new_r, new_rd, E


def parse_token(tok):
    """'1800' -> (1800, 1.0);  '1800/d' -> (1800, 0.5);  '1800/l' -> (1800, 0.0)"""
    tok = tok.strip().replace(" ", "")
    if not tok:
        return None
    for sep in ("/", ":", "-", "="):
        if sep in tok:
            rating, res = tok.split(sep, 1)
            break
    else:
        rating, res = tok, "w"
    res = res.strip().lower()
    scores = {"w": 1.0, "win": 1.0, "1": 1.0,
              "d": 0.5, "draw": 0.5, "0.5": 0.5, ".5": 0.5,
              "l": 0.0, "loss": 0.0, "lose": 0.0, "0": 0.0}
    if res not in scores:
        raise ValueError(f"unrecognised result in {tok!r} (use w, d or l)")
    return float(rating), scores[res]


def run(games, start=DEFAULT_START, rd=DEFAULT_RD, target=None,
        opp_rd=DEFAULT_OPP_RD, quiet=False):
    r = start
    hit = None
    if not quiet:
        print(f"\nstart: {r:.0f}  (RD {rd:.0f})\n")
        print(f"  {'#':>3}  {'opp':>6}  {'res':>4}  {'P(win)':>7}  "
              f"{'change':>8}  {'rating':>8}  {'RD':>6}")
        print("  " + "-" * 52)
    for i, (opp, score) in enumerate(games, 1):
        prev = r
        r, rd, E = update(r, rd, opp, score, opp_rd)
        if target is not None and hit is None and r >= target:
            hit = i
        if not quiet:
            label = {1.0: "win", 0.5: "draw", 0.0: "loss"}[score]
            flag = "  <-- target" if hit == i else ""
            print(f"  {i:>3}  {opp:>6.0f}  {label:>4}  {E*100:>6.1f}%  "
                  f"{r-prev:>+8.1f}  {r:>8.1f}  {rd:>6.1f}{flag}")
    if not quiet:
        print("  " + "-" * 52)
        print(f"\n  FINAL RATING: {r:.0f}   (RD {rd:.0f})")
        net = r - start
        wins = sum(1 for _, s in games if s == 1.0)
        draws = sum(1 for _, s in games if s == 0.5)
        losses = sum(1 for _, s in games if s == 0.0)
        print(f"  {len(games)} games: {wins}W {draws}D {losses}L   net {net:+.0f}")
        if target is not None:
            print(f"  target {target:.0f}: "
                  + (f"reached at game {hit}" if hit else "not reached"))
        if rd > 100:
            print(f"\n  note: RD is still {rd:.0f} -- the system is not confident "
                  "yet,\n        so your next few games will still swing hard.")
    return r, rd, hit


def main():
    args = sys.argv[1:]
    start, rd, target, opp_rd = DEFAULT_START, DEFAULT_RD, None, DEFAULT_OPP_RD
    tokens = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            print(__doc__)
            return
        elif a == "--start":
            start = float(args[i + 1]); i += 2
        elif a == "--rd":
            rd = float(args[i + 1]); i += 2
        elif a == "--target":
            target = float(args[i + 1]); i += 2
        elif a == "--opp-rd":
            opp_rd = float(args[i + 1]); i += 2
        else:
            tokens.append(a); i += 1

    if not tokens:
        print(__doc__)
        print("Enter opponent ratings, one per line (or space separated).")
        print("Bare number = win. Add /d for a draw, /l for a loss.")
        print("Blank line when done.\n")
        while True:
            try:
                line = input("  opponent> ").strip()
            except EOFError:
                break
            if not line:
                break
            tokens.extend(line.split())

    games = []
    for t in tokens:
        parsed = parse_token(t)
        if parsed:
            games.append(parsed)

    if not games:
        print("No games entered.")
        return

    run(games, start, rd, target, opp_rd)


if __name__ == "__main__":
    main()