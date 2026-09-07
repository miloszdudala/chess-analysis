#!/usr/bin/env python3
"""Web app: pick a mode in the browser and get the report.

    .venv/bin/python webapp.py        # then open http://127.0.0.1:5050

Thin layer over the same modes/Documents the CLI uses. Each /api/<mode>
endpoint builds a Document and returns its rendered section HTML + metadata.
"""
from __future__ import annotations

import os
import threading
import time
from functools import wraps

from flask import Flask, Response, jsonify, request, send_from_directory

from chessanalysis import config, modes, render_html
from chessanalysis.model import load_games

app = Flask(__name__, static_folder=None)
FRONTEND = os.path.join(os.path.dirname(__file__), "frontend")
GAMES_DIR = config.get("GAMES_DIR", "games")

# One long-lived engine for interactive variation analysis (/api/analyse).
# A lock serialises access since the dev server may handle requests in threads.
_ANALYSE_LOCK = threading.Lock()
_ANALYSE_ENGINE = None


def _analyse_engine():
    global _ANALYSE_ENGINE
    if _ANALYSE_ENGINE is None:
        import chess.engine
        from chessanalysis.enrich import engine as eng
        _ANALYSE_ENGINE = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
    return _ANALYSE_ENGINE


# --- background pre-analysis (pre-warm the review cache at review depth) ------
# Analysing every game at ENGINE_DEPTH ahead of time makes Game Review open
# instantly (it reads the same disk cache). A single worker thread runs it in
# the background; progress + a live ETA are polled from /api/prewarm.
_PREWARM_LOCK = threading.Lock()
_PREWARM_THREAD = None
_PREWARM = {"running": False, "finished": False, "error": None, "depth": 0,
            "total": 0, "already": 0, "to_compute": 0, "done": 0,
            "computed": 0, "compute_time": 0.0, "eta": None, "start": 0.0}
# rough per-game time for a depth-15 full-game pass on this machine; only used
# for the very first estimate, then replaced by the measured average.
EST_SECONDS_PER_GAME = 33


def _prewarm_key(game, depth):
    return f"{game.game_id}_d{depth}"


def _prewarm_snapshot():
    s = {k: _PREWARM[k] for k in _PREWARM if k != "start"}
    s["elapsed"] = round(time.time() - _PREWARM["start"]) if _PREWARM["start"] else 0
    return s


def _prewarm_worker(user, depth):
    import chess.engine
    from chessanalysis import cache
    from chessanalysis.enrich import engine as eng

    try:
        # flagged games included: they leave the stats but stay reviewable, and
        # Game Review should open them just as fast
        games = load_games(GAMES_DIR, user, include_flagged=True)
        todo, already = [], 0
        for g in games:
            c = cache.load("engine", _prewarm_key(g, depth))
            if c and c.get("evals") and c.get("top_moves"):
                already += 1
            else:
                todo.append(g)
        with _PREWARM_LOCK:
            _PREWARM.update(total=len(games), already=already, done=already,
                            to_compute=len(todo),
                            eta=round(len(todo) * EST_SECONDS_PER_GAME))

        proc = None
        try:
            for g in todo:
                if proc is None:
                    proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
                t = time.time()
                eng.analyse_game(g, depth=depth, engine=proc)
                dt = time.time() - t
                with _PREWARM_LOCK:
                    _PREWARM["done"] += 1
                    _PREWARM["computed"] += 1
                    _PREWARM["compute_time"] += dt
                    per = _PREWARM["compute_time"] / _PREWARM["computed"]
                    left = _PREWARM["to_compute"] - _PREWARM["computed"]
                    _PREWARM["eta"] = round(per * left)
        finally:
            if proc:
                proc.quit()
    except Exception as e:                       # noqa: BLE001
        with _PREWARM_LOCK:
            _PREWARM["error"] = f"{type(e).__name__}: {e}"
    finally:
        with _PREWARM_LOCK:
            _PREWARM["running"] = False
            _PREWARM["finished"] = True
            _PREWARM["eta"] = 0


def api(fn):
    """Wrap a route so any failure returns a clean JSON error."""
    @wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except SystemExit as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:                       # noqa: BLE001
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return wrapper


# --- static frontend --------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/app.js")
def appjs():
    return send_from_directory(FRONTEND, "app.js")


@app.get("/style.css")
def style():
    return Response(render_html.css(), mimetype="text/css")


# --- api --------------------------------------------------------------------

@app.get("/api/config")
@api
def api_config():
    return jsonify({
        "user": config.get("CHESS_USERNAME"),
        "modes": modes.names(),
        "depth": int(config.get("ENGINE_DEPTH", "15")),
    })


# Every report and review syncs first, so the same user can be re-synced several
# times a minute by ordinary clicking. Chess.com is fine with that volume, but
# there is nothing to gain from it either: a sync inside this window is skipped.
SYNC_MIN_INTERVAL = 60
_LAST_SYNC: dict[str, float] = {}


def _sync(user, force=False):
    """Download new games, then re-check opponents for fair-play bans."""
    import scraper
    from chessanalysis import fairplay

    age = time.time() - _LAST_SYNC.get(user.lower(), 0)
    if not force and age < SYNC_MIN_INTERVAL:
        return {"user": user, "new": 0, "skipped": 0, "requests": 0,
                "fresh": True, "banned": []}
    res = scraper.scrape(user, GAMES_DIR)   # hits the Chess.com API
    games = load_games(GAMES_DIR, user, include_flagged=True)
    res["banned"] = fairplay.refresh([g.opponent for g in games])["banned"]
    _LAST_SYNC[user.lower()] = time.time()
    res["user"] = user
    res["fresh"] = False
    return res


@app.post("/api/scrape")
@api
def api_scrape():
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    if not user:
        return jsonify({"error": "No username given."}), 400
    force = request.args.get("force") in ("1", "true", "yes")
    return jsonify(_sync(user, force))


@app.get("/api/prewarm")
@api
def api_prewarm_status():
    """Progress of the background review-cache warm-up. When idle, reports how
    many games still need analysis and a rough time estimate to do them."""
    from chessanalysis import cache

    with _PREWARM_LOCK:
        if _PREWARM["running"] or _PREWARM["finished"]:
            return jsonify(_prewarm_snapshot())

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    depth = int(config.get("ENGINE_DEPTH", "15"))
    games = load_games(GAMES_DIR, user, include_flagged=True)   # all reviewable
    already = sum(1 for g in games if cache.exists("engine", _prewarm_key(g, depth)))
    todo = len(games) - already
    return jsonify({
        "running": False, "finished": False, "error": None, "depth": depth,
        "total": len(games), "already": already, "to_compute": todo,
        "done": already, "computed": 0, "compute_time": 0.0, "elapsed": 0,
        "eta": round(todo * EST_SECONDS_PER_GAME),
    })


@app.post("/api/prewarm")
@api
def api_prewarm_start():
    """Kick off (or report) the background analysis of every game at review
    depth, so Game Review opens instantly afterwards."""
    global _PREWARM_THREAD
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    depth = int(config.get("ENGINE_DEPTH", "15"))
    with _PREWARM_LOCK:
        if _PREWARM["running"]:
            return jsonify(_prewarm_snapshot())
        _PREWARM.update(running=True, finished=False, error=None, depth=depth,
                        total=0, already=0, to_compute=0, done=0, computed=0,
                        compute_time=0.0, eta=None, start=time.time())
    _PREWARM_THREAD = threading.Thread(
        target=_prewarm_worker, args=(user, depth), daemon=True)
    _PREWARM_THREAD.start()
    with _PREWARM_LOCK:
        return jsonify(_prewarm_snapshot())


@app.get("/api/games")
@api
def api_games():
    """The full history — flagged games included, marked as such, so the record
    stays visible even though the statistics no longer count it."""
    from chessanalysis import fairplay, overrides

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    games = load_games(GAMES_DIR, user, include_flagged=True)
    flags = {**overrides.flags(), **fairplay.flags(games)}
    return jsonify([{
        "id": g.game_id, "white": g.h("White"), "black": g.h("Black"),
        "result": g.result, "date": g.date, "opponent": g.opponent,
        "color": g.color, "outcome": g.outcome, "time_class": g.time_class,
        **(flags.get(str(g.game_id)) or {}),
    } for g in reversed(games)])


@app.get("/api/player")
@api
def api_player():
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    if not user:
        return jsonify({"error": "No username given."}), 400
    doc = modes.get("player")(user, games_dir=GAMES_DIR, time_class=fmt)
    return jsonify(doc.to_dict())   # JSON widgets -> rendered client-side


@app.get("/api/recent")
@api
def api_recent():
    """The recent-games table. `flagged=1` also lists anomalous games (marked,
    so they read as excluded) — the only way back to one from the report."""
    import chess.engine
    from chessanalysis import fairplay, overrides
    from chessanalysis.enrich import engine as eng

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    n = request.args.get("n", default=10, type=int)
    cp = int(config.get("DECISIVE_CP", "200"))
    depth = int(config.get("RECENT_DEPTH", "12"))
    show_flagged = request.args.get("flagged") in ("1", "true", "yes")

    games = load_games(GAMES_DIR, user, include_flagged=True)
    flags = {**overrides.flags(), **fairplay.flags(games)}
    if fmt:
        games = [g for g in games if g.time_class == fmt]
    # count only this player's flagged games: overrides are keyed by game id and
    # outlive a change of account, so a global count would advertise excluded
    # games that aren't even in this player's history.
    flagged_here = sum(1 for g in games if str(g.game_id) in flags)
    if not show_flagged:
        games = [g for g in games if str(g.game_id) not in flags]
    games = list(reversed(games))            # most recent first
    if n and n > 0:
        games = games[:n]

    proc, rows = None, []
    try:
        for g in games:
            if proc is None:                  # open one engine for the whole batch
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            a = eng.analyse_game(g, depth=eng.deepest_cached(g, depth), engine=proc)
            d = a.decisive(cp)
            rows.append({
                "id": g.game_id, "date": g.date, "color": g.color,
                "opponent": g.opponent, "opp_elo": g.opp_elo,
                "result": g.result, "outcome": g.outcome,
                "depth": a.depth,
                "accuracy": a.accuracy.get(g.color),
                "blunders": len(a.blunders(g.color)),
                "decisive": (None if not d["reached"] else
                             {"move": d["move_no"], "held": d["held"], "side": d["side"]}),
                **(flags.get(str(g.game_id)) or {}),
            })
    finally:
        if proc:
            proc.quit()
    return jsonify({"threshold": cp, "games": rows, "flagged": flagged_here})


def _analysed_pairs(user, fmt, n, depth):
    """(Game, GameAnalysis) for the chosen format — cached engine analyses;
    an engine is opened only if some game isn't in the cache yet.

    `depth` is a floor, not a target: a game already analysed deeper (by Game
    Review or the pre-warm) is read back at that depth rather than analysed
    again. Depth can therefore vary game to game within one batch."""
    import chess.engine
    from chessanalysis import cache
    from chessanalysis.enrich import engine as eng

    games = load_games(GAMES_DIR, user)        # chronological (oldest -> newest)
    if fmt:
        games = [g for g in games if g.time_class == fmt]
    if n and n > 0:
        games = games[-n:]                     # last X games

    proc, pairs = None, []
    try:
        for g in games:
            d = eng.deepest_cached(g, depth)
            if cache.load("engine", f"{g.game_id}_d{d}") is None and proc is None:
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            pairs.append((g, eng.analyse_game(g, depth=d, engine=proc)))
    finally:
        if proc:
            proc.quit()
    return pairs


@app.get("/api/conversion")
@api
def api_conversion():
    from chessanalysis import insights, weaknesses

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    n = request.args.get("n", default=0, type=int)
    cp = int(config.get("DECISIVE_CP", "200"))
    depth = int(config.get("RECENT_DEPTH", "12"))

    pairs = _analysed_pairs(user, fmt, n, depth)
    sections = (insights.outcome_reasons(pairs, cp)
                + insights.progress_report(pairs, cp)
                + insights.accuracy_trend(pairs)
                + insights.eval_curve(pairs)
                + insights.conversion_report(pairs, cp)
                + weaknesses.report(pairs)
                + insights.advanced_report(pairs))
    return jsonify({"sections": sections})


@app.get("/api/game")
@api
def api_game():
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    selector = request.args.get("selector", "last")
    depth = request.args.get("depth", type=int)
    doc = modes.get("game")(user, games_dir=GAMES_DIR, selector=selector, depth=depth)
    return jsonify(doc.to_dict())


@app.post("/api/verdict")
@api
def api_set_verdict():
    """Manually set (or clear) the win/loss reason flag for one game."""
    from chessanalysis import diagnosis as dx, overrides

    gid = request.args.get("game")
    reason = request.args.get("reason") or None
    if not gid:
        return jsonify({"error": "game id required"}), 400
    allowed = set(dx.WIN_REASONS) | set(dx.LOSS_REASONS) | set(dx.DRAW_REASONS)
    if reason is not None and reason not in allowed:
        return jsonify({"error": f"unknown reason '{reason}'"}), 400
    overrides.set_reason(gid, reason)
    return jsonify({"ok": True, "game": gid, "reason": reason})


@app.post("/api/flag")
@api
def api_set_flag():
    """Flag (or unflag) a game as not representative — a disconnect, a thrown
    game. Flagged games leave every statistic but stay in the history."""
    from chessanalysis import overrides

    gid = request.args.get("game")
    flag = request.args.get("flag") or None
    note = request.args.get("note") or None
    if not gid:
        return jsonify({"error": "game id required"}), 400
    if flag is not None and flag not in overrides.FLAGS:
        return jsonify({"error": f"unknown flag '{flag}'"}), 400
    overrides.set_flag(gid, flag, note)
    return jsonify({"ok": True, "game": gid, "flag": flag, "note": note})


@app.get("/api/analyse")
@api
def api_analyse():
    """Live engine analysis of an arbitrary position, for variation exploration.

    Optionally applies one move first (uci; auto-queens a bare promotion), then
    returns the resulting FEN, eval (white-POV cp), and the top moves for arrows.
    """
    import chess
    import chess.engine
    from chessanalysis.enrich.engine import MATE_CP

    fen = request.args.get("fen")
    move = request.args.get("move")
    depth = request.args.get("depth", default=12, type=int)
    if not fen:
        return jsonify({"error": "fen required"}), 400
    try:
        board = chess.Board(fen)
    except ValueError:
        return jsonify({"error": "invalid fen"}), 400

    move_san = None
    if move:
        try:
            mv = chess.Move.from_uci(move)
        except ValueError:
            mv = None
        if mv not in board.legal_moves and move and len(move) == 4:
            mv = chess.Move.from_uci(move + "q")   # bare pawn-to-last-rank → queen
        if mv not in board.legal_moves:
            return jsonify({"fen": board.fen(), "legal": False})
        move_san = board.san(mv)
        board.push(mv)

    out = {"fen": board.fen(), "legal": True, "move_san": move_san,
           "turn": "w" if board.turn else "b", "game_over": board.is_game_over()}
    if board.is_game_over():
        if board.is_checkmate():
            out["cp"] = -MATE_CP if board.turn == chess.WHITE else MATE_CP
        else:
            out["cp"] = 0
        out["best"] = []
        return jsonify(out)

    with _ANALYSE_LOCK:
        infos = _analyse_engine().analyse(
            board, chess.engine.Limit(depth=depth), multipv=3)
    if isinstance(infos, dict):
        infos = [infos]
    best = []
    for it in infos:
        pv = it.get("pv")
        if not pv:
            continue
        best.append({"uci": pv[0].uci(), "san": board.san(pv[0]),
                     "cp": it["score"].white().score(mate_score=MATE_CP)})
    out["cp"] = best[0]["cp"] if best else 0
    out["best"] = best
    return jsonify(out)


@app.get("/api/compare")
@api
def api_compare():
    a, b = request.args.get("a"), request.args.get("b")
    if not a or not b:
        return jsonify({"error": "compare needs two players (a and b)."}), 400
    return jsonify(modes.get("compare")(a, b, games_dir=GAMES_DIR).to_dict())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    print(f"\n  chess-analyzer →  http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
