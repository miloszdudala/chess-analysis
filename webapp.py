#!/usr/bin/env python3
"""Web app: pick a mode in the browser and get the report.

    .venv/bin/python webapp.py        # then open http://127.0.0.1:5050

Thin layer over the same modes/Documents the CLI uses. Each /api/<mode>
endpoint builds a Document and returns its rendered section HTML + metadata.
"""
from __future__ import annotations

import os
import threading
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


@app.post("/api/scrape")
@api
def api_scrape():
    import scraper
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    if not user:
        return jsonify({"error": "No username. Set CHESS_USERNAME in .env."}), 400
    res = scraper.scrape(user, GAMES_DIR)   # hits the Chess.com API (user-triggered)
    res["user"] = user
    return jsonify(res)


@app.get("/api/games")
@api
def api_games():
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    games = load_games(GAMES_DIR, user)
    return jsonify([{
        "id": g.game_id, "white": g.h("White"), "black": g.h("Black"),
        "result": g.result, "date": g.date, "opponent": g.opponent,
        "color": g.color, "outcome": g.outcome, "time_class": g.time_class,
    } for g in reversed(games)])


@app.get("/api/player")
@api
def api_player():
    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    if not user:
        return jsonify({"error": "No username. Set CHESS_USERNAME in .env."}), 400
    doc = modes.get("player")(user, games_dir=GAMES_DIR, time_class=fmt)
    return jsonify(doc.to_dict())   # JSON widgets -> rendered client-side


@app.get("/api/recent")
@api
def api_recent():
    import chess.engine
    from chessanalysis.enrich import engine as eng

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    n = request.args.get("n", default=10, type=int)
    cp = int(config.get("DECISIVE_CP", "200"))
    depth = int(config.get("RECENT_DEPTH", "12"))

    games = load_games(GAMES_DIR, user)
    if fmt:
        games = [g for g in games if g.time_class == fmt]
    games = list(reversed(games))            # most recent first
    if n and n > 0:
        games = games[:n]

    proc, rows = None, []
    try:
        for g in games:
            if proc is None:                  # open one engine for the whole batch
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            a = eng.analyse_game(g, depth=depth, engine=proc)
            d = a.decisive(cp)
            rows.append({
                "id": g.game_id, "date": g.date, "color": g.color,
                "opponent": g.opponent, "opp_elo": g.opp_elo,
                "result": g.result, "outcome": g.outcome,
                "accuracy": a.accuracy.get(g.color),
                "blunders": len(a.blunders(g.color)),
                "decisive": (None if not d["reached"] else
                             {"move": d["move_no"], "held": d["held"], "side": d["side"]}),
            })
    finally:
        if proc:
            proc.quit()
    return jsonify({"threshold": cp, "games": rows})


@app.get("/api/conversion")
@api
def api_conversion():
    import chess.engine
    from chessanalysis import cache, insights
    from chessanalysis.enrich import engine as eng

    user = request.args.get("user") or config.get("CHESS_USERNAME")
    fmt = request.args.get("format") or None
    n = request.args.get("n", default=0, type=int)
    cp = int(config.get("DECISIVE_CP", "200"))
    depth = int(config.get("RECENT_DEPTH", "12"))

    games = load_games(GAMES_DIR, user)        # chronological (oldest -> newest)
    if fmt:
        games = [g for g in games if g.time_class == fmt]
    if n and n > 0:
        games = games[-n:]                     # last X games

    proc, pairs = None, []
    try:
        for g in games:
            if cache.load("engine", f"{g.game_id}_d{depth}") is None and proc is None:
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            pairs.append((g, eng.analyse_game(g, depth=depth, engine=proc)))
    finally:
        if proc:
            proc.quit()
    sections = (insights.outcome_reasons(pairs, cp)
                + insights.accuracy_trend(pairs)
                + insights.eval_curve(pairs)
                + insights.conversion_report(pairs, cp)
                + insights.advanced_report(pairs))
    return jsonify({"sections": sections})


@app.get("/api/game")
@api
def api_game():
    user = config.get("CHESS_USERNAME")
    selector = request.args.get("selector", "last")
    depth = request.args.get("depth", type=int)
    doc = modes.get("game")(user, games_dir=GAMES_DIR, selector=selector, depth=depth)
    return jsonify(doc.to_dict())


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
