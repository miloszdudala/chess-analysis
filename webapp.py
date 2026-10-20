#!/usr/bin/env python3
"""Chess Analyzer — the web app.

    .venv/bin/python webapp.py        # then open http://127.0.0.1:5050

A thin layer: every endpoint hands its work to a module in `chessanalysis`
and returns JSON. Reports are Documents (ordered widgets, rendered by
frontend/js/widgets.js); the interactive pages — training, the explorer —
have endpoints of their own.
"""
from __future__ import annotations

import os
import re
import time
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory

from chessanalysis import config, jobs, modes, store
from chessanalysis.model import load_games

app = Flask(__name__, static_folder=None)
FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
FORMATS = ("bullet", "blitz", "rapid", "daily")


def api(fn):
    """Wrap a route so any failure returns a clean JSON error."""
    @wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except SystemExit as e:
            return jsonify({"error": str(e)}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:                       # noqa: BLE001
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return wrapper


# Chess.com usernames: letters, digits, underscores and hyphens. Anything else
# never reaches an API path.
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def _account(name, what="username"):
    name = (name or "").strip()
    if not name:
        raise ValueError(f"No {what} given.")
    if not _NAME.match(name):
        raise ValueError(f"'{name}' is not a Chess.com {what}.")
    return name


def _user():
    return _account(request.args.get("user") or config.get("CHESS_USERNAME"))


def _format():
    fmt = request.args.get("format") or None
    if fmt and fmt not in FORMATS:
        raise ValueError(f"unknown format '{fmt}'")
    return fmt


def _review_depth():
    return int(config.get("ENGINE_DEPTH", "15"))


# --- the frontend -------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/style.css")
def style():
    return send_from_directory(FRONTEND, "style.css")


@app.get("/js/<path:name>")
def script(name):
    return send_from_directory(os.path.join(FRONTEND, "js"), name,
                               mimetype="text/javascript")


# --- account ------------------------------------------------------------------

@app.get("/api/config")
@api
def api_config():
    from chessanalysis import book, corpus, glossary
    from chessanalysis.enrich import engine as eng

    return jsonify({"user": config.get("CHESS_USERNAME"), "modes": modes.names(),
                    "depth": _review_depth(), "formats": list(FORMATS),
                    "corpus": {"time_control": corpus.TIME_CONTROL, "depth": corpus.DEPTH,
                               "label": glossary.time_control_label(corpus.TIME_CONTROL)},
                    "book": book.facts(),
                    "thresholds": {"inaccuracy": eng.INACCURACY, "mistake": eng.MISTAKE,
                                   "blunder": eng.BLUNDER}})


SYNC_MIN_INTERVAL = 60
_LAST_SYNC: dict[str, float] = {}


def _sync(user, force=False, source="own", months=None):
    """Download new games, then re-check opponents for fair-play bans."""
    import scraper
    from chessanalysis import fairplay

    key = (user.lower(), source)
    if not force and time.time() - _LAST_SYNC.get(key, 0) < SYNC_MIN_INTERVAL:
        return {"user": user, "new": 0, "requests": 0, "fresh": True, "banned": []}
    res = scraper.scrape(user, source=source, months=months, log=lambda *_: None)
    res["banned"] = []
    if source == "own":
        games = load_games(user, include_flagged=True)
        res["banned"] = fairplay.refresh(fairplay.opponents_of(games))["banned"]
    _LAST_SYNC[key] = time.time()
    return {**res, "user": user, "fresh": False}


@app.post("/api/sync")
@app.post("/api/scrape")
@api
def api_sync():
    force = request.args.get("force") in ("1", "true", "yes")
    return jsonify(_sync(_user(), force))


# --- background analysis ----------------------------------------------------------
# One job analyses your games twice over: first at the corpus depth (about a
# second a game — it feeds the peer comparison), then at review depth (about
# half a minute — Game Review and training read it). Positions to train are
# refreshed as it goes.

EST = {"corpus": 1.2, "review": 33.0}


def _analysis_todo(user):
    from chessanalysis import corpus

    depth = _review_depth()
    counted = [g for g in load_games(user)
               if g.time_control == corpus.TIME_CONTROL
               and not store.has_analysis(g.game_id, corpus.DEPTH)]
    review = []
    for g in load_games(user, include_flagged=True):
        raw = store.load_analysis(g.game_id, depth)
        if not (raw and raw.get("evals") and raw.get("top_moves")):
            review.append(g)
    return counted, list(reversed(review))           # newest reviews first


def _analysis_worker(job, user):
    import chess.engine
    from chessanalysis import corpus, training
    from chessanalysis.corpus import analyse as corpus_analyse
    from chessanalysis.enrich import engine as eng

    counted, review = _analysis_todo(user)
    total = len(counted) + len(review)
    job.update(total=total, done=0, stage="peer comparison", corpus_todo=len(counted),
               review_todo=len(review), depth=_review_depth(),
               eta=round(len(counted) * EST["corpus"] + len(review) * EST["review"]))
    spent = {"corpus": [0.0, 0], "review": [0.0, 0]}

    def eta():
        per = {k: (v[0] / v[1] if v[1] else EST[k]) for k, v in spent.items()}
        left_c = max(0, len(counted) - spent["corpus"][1])
        left_r = max(0, len(review) - spent["review"][1])
        return round(left_c * per["corpus"] + left_r * per["review"])

    def corpus_done(secs):
        spent["corpus"][0] += secs
        spent["corpus"][1] += 1
        job.step()
        job.update(eta=eta())

    if counted:
        corpus_analyse.analyse_own(user, corpus.DEPTH, limit=None,
                                   on_game=corpus_done, stop=lambda: job.stopping)
    if job.stopping:
        return
    training.sync(user)
    job.update(stage="game reviews")
    proc = None
    try:
        for i, g in enumerate(review):
            if job.stopping:
                return
            if proc is None:
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            t = time.time()
            eng.analyse_game(g, depth=_review_depth(), engine=proc)
            spent["review"][0] += time.time() - t
            spent["review"][1] += 1
            job.step()
            job.update(eta=eta())
            if (i + 1) % 10 == 0:
                training.sync(user)
    finally:
        if proc:
            proc.quit()
    training.sync(user)
    job.update(eta=0)


@app.get("/api/job/analysis")
@api
def api_analysis_status():
    user = _user()
    job = jobs.get("analysis")
    snap = job.snapshot()
    if snap["running"] or (snap["finished"] and (snap["key"] or "").lower() == user.lower()):
        return jsonify(snap)
    counted, review = _analysis_todo(user)
    return jsonify({"name": "analysis", "key": user, "running": False, "finished": False,
                    "error": None, "total": len(counted) + len(review), "done": 0,
                    "corpus_todo": len(counted), "review_todo": len(review),
                    "eta": round(len(counted) * EST["corpus"] + len(review) * EST["review"])})


@app.post("/api/job/analysis")
@api
def api_analysis_start():
    return jsonify(jobs.start("analysis", _user(), _analysis_worker, _user()))


# --- reports (Documents) ----------------------------------------------------------

@app.get("/api/overview")
@api
def api_overview():
    return jsonify(modes.get("overview")(_user(), time_class=_format()).to_dict())


@app.get("/api/guide")
@api
def api_guide():
    return jsonify(modes.get("guide")().to_dict())


@app.get("/api/player")
@api
def api_player():
    return jsonify(modes.get("player")(_user(), time_class=_format()).to_dict())


def _analysed_pairs(user, fmt, n, depth):
    """(Game, GameAnalysis) for the chosen format, at least `depth` deep.

    `depth` is a floor, not a target: a game already analysed deeper is read
    back at that depth rather than analysed again."""
    import chess.engine
    from chessanalysis.enrich import engine as eng

    games = load_games(user)
    if fmt:
        games = [g for g in games if g.time_class == fmt]
    if n and n > 0:
        games = games[-n:]
    proc, pairs = None, []
    try:
        for g in games:
            d = eng.deepest_cached(g, depth)
            if not store.has_analysis(g.game_id, d) and proc is None:
                proc = chess.engine.SimpleEngine.popen_uci(eng.find_engine())
            pairs.append((g, eng.analyse_game(g, depth=d, engine=proc)))
    finally:
        if proc:
            proc.quit()
    return pairs


@app.get("/api/insights")
@app.get("/api/conversion")
@api
def api_insights():
    from chessanalysis import insights, weaknesses

    cp = int(config.get("DECISIVE_CP", "200"))
    n = request.args.get("n", default=0, type=int)
    pairs = _analysed_pairs(_user(), _format(), n, int(config.get("RECENT_DEPTH", "12")))
    sections = (insights.outcome_reasons(pairs, cp)
                + insights.progress_report(pairs, cp)
                + insights.accuracy_trend(pairs)
                + insights.eval_curve(pairs)
                + insights.conversion_report(pairs, cp)
                + weaknesses.report(pairs)
                + insights.advanced_report(pairs))
    return jsonify({"sections": sections})


@app.get("/api/games")
@api
def api_games():
    from chessanalysis import gamelist

    return jsonify(gamelist.rows(_user(), _format()))


@app.get("/api/game")
@api
def api_game():
    doc = modes.get("game")(_user(), selector=request.args.get("selector", "last"),
                            depth=request.args.get("depth", type=int))
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
    """Flag (or unflag) a game as not representative. Flagged games leave every
    statistic but stay in the history."""
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


# --- the live engine ----------------------------------------------------------------

@app.get("/api/analyse")
@api
def api_analyse():
    """Live analysis of a position, optionally after one move (uci; a bare
    promotion becomes a queen): the resulting FEN, eval and top moves."""
    import chess
    from chessanalysis import livengine

    fen = request.args.get("fen")
    if not fen:
        return jsonify({"error": "fen required"}), 400
    try:
        board = chess.Board(fen)
    except ValueError:
        return jsonify({"error": "invalid fen"}), 400
    depth = max(6, min(22, request.args.get("depth", default=14, type=int)))
    multipv = max(1, min(5, request.args.get("multipv", default=3, type=int)))
    move_san = None
    move = request.args.get("move")
    if move:
        mv = livengine.parse_move(board, move)
        if mv is None:
            return jsonify({"fen": board.fen(), "legal": False})
        move_san = board.san(mv)
        board.push(mv)
    res = livengine.analyse(board.fen(), depth=depth, multipv=multipv,
                            pv_len=request.args.get("pv", default=0, type=int))
    return jsonify({"fen": board.fen(), "legal": True, "move_san": move_san,
                    "turn": "w" if board.turn else "b",
                    "game_over": board.is_game_over(), **res})


# --- openings -------------------------------------------------------------------------

def _elo(user, fmt):
    games = [g for g in load_games(user) if g.user_elo and (not fmt or g.time_class == fmt)]
    return games[-1].user_elo if games else None


@app.get("/api/explorer")
@api
def api_explorer():
    from chessanalysis import explorer

    user = _user()
    who = _account(request.args.get("db")) if request.args.get("db") else user
    fmt = _format()
    color = request.args.get("color", "white")
    if color not in ("white", "black"):
        raise ValueError("color must be white or black")
    moves = [m for m in (request.args.get("moves") or "").split(",") if m]
    elo = _elo(who, fmt)
    return jsonify(explorer.position(moves, who, color, fmt, elo=elo))


@app.get("/api/repertoire")
@api
def api_repertoire():
    from chessanalysis import explorer

    who = _account(request.args.get("db")) if request.args.get("db") else _user()
    color = request.args.get("color", "white")
    return jsonify(explorer.repertoire(who, color, _format()))


# --- training -------------------------------------------------------------------------

@app.post("/api/train/sync")
@api
def api_train_sync():
    from chessanalysis import training

    return jsonify(training.sync(_user()))


@app.get("/api/train/summary")
@api
def api_train_summary():
    from chessanalysis import training

    return jsonify(training.summary(_user()))


@app.get("/api/train/next")
@api
def api_train_next():
    from chessanalysis import training

    a = request.args
    p = training.next_puzzle(_user(), kind=a.get("kind") or None,
                             phase=a.get("phase") or None, theme=a.get("theme") or None,
                             game=a.get("game") or None, exclude=a.get("exclude") or None)
    return jsonify({"puzzle": p, "summary": training.summary(_user())})


@app.post("/api/train/attempt")
@api
def api_train_attempt():
    from chessanalysis import training

    return jsonify(training.attempt(_user(), request.args["id"], request.args["uci"]))


@app.get("/api/train/reveal")
@api
def api_train_reveal():
    from chessanalysis import training

    return jsonify(training.reveal(_user(), request.args["id"]))


@app.post("/api/train/grade")
@api
def api_train_grade():
    from chessanalysis import training

    return jsonify(training.grade(_user(), request.args["id"], request.args["grade"]))


# --- scouting ---------------------------------------------------------------------------

@app.get("/api/scout")
@api
def api_scout():
    opp = _account(request.args.get("opp"), "account to scout")
    months = max(1, min(24, request.args.get("months", default=6, type=int)))
    me = request.args.get("user") or config.get("CHESS_USERNAME") or ""
    note = None
    try:
        _sync(opp, source="scout", months=months)
    except ValueError:
        raise
    except Exception as e:                       # noqa: BLE001 — stored games suffice
        note = f"Could not reach Chess.com ({type(e).__name__}); showing stored games."
    doc = modes.get("scout")(opp, me=me, time_class=_format() or "rapid", months=months)
    out = doc.to_dict()
    if note:
        out["meta"]["note"] = note
    return jsonify(out)


# --- the rating corpus ------------------------------------------------------------------

CORPUS_WORKERS = int(config.get("CORPUS_WORKERS", "3"))


def _expand_worker(job, user, n):
    from chessanalysis import corpus
    from chessanalysis.corpus import analyse, crawl

    elo = _elo(user, None) or 1500
    depth = corpus.DEPTH
    job.update(note="finding games…")
    banked = crawl.expand(n, user, elo, crawl.targets(elo, depth), depth,
                          log=lambda msg: job.update(note=msg))
    job.update(banked=banked, note=f"analysing {analyse.pending(depth)} games…")
    done = analyse.run(CORPUS_WORKERS, depth)
    job.update(analysed=done, note=f"added {banked} games")


@app.get("/api/corpus")
@api
def api_corpus_status():
    from chessanalysis import corpus

    return jsonify({**corpus.totals(), "coverage": corpus.coverage(),
                    "band_size": corpus.BAND_SIZE,
                    "job": jobs.get("expand").snapshot()})


@app.post("/api/corpus/expand")
@api
def api_corpus_expand():
    user = _user()
    n = max(10, min(1000, request.args.get("n", default=100, type=int)))
    return jsonify(jobs.start("expand", "corpus", _expand_worker, user, n,
                              initial={"target": n, "banked": 0, "analysed": 0,
                                       "note": "starting…"}))


@app.get("/api/brackets")
@api
def api_brackets():
    """One tab, two scopes: `peers` (your band) or `ladder` (every band)."""
    from chessanalysis import corpus
    from chessanalysis.corpus import analyse

    analyse.ensure_samples(corpus.DEPTH)
    scope = request.args.get("scope", "ladder")
    user = request.args.get("user") or config.get("CHESS_USERNAME") or ""
    if scope == "peers" and not user:
        raise ValueError("No username given.")
    window = request.args.get("window", default=70, type=int)
    return jsonify(modes.get("brackets")(user, scope=scope, window=window).to_dict())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    print(f"\n  Chess Analyzer →  http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
