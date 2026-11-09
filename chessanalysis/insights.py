"""Aggregate conversion / stage analysis over many analysed games.

Answers "where do I perform well or poorly?" along several axes:
  * outcome-level conversion and save rates
  * where games are decided — the phase at the point of no return, for wins vs losses
  * accuracy by game phase (opening / middlegame / endgame)
  * accuracy by position state when it's my move (winning / equal / losing)
"""
from __future__ import annotations

from collections import Counter

from . import diagnosis as dx
from . import overrides
from . import widgets as W
from .enrich.engine import MISTAKE
from .phases import ORDER as PHASE_ORDER


def _table_for(outcome):
    return (dx.WIN_REASONS if outcome == "win"
            else dx.LOSS_REASONS if outcome == "loss" else dx.DRAW_REASONS)

# (label, predicate on user-perspective centipawns before the move)
STATES = [
    ("Winning (≥ +2)", lambda c: c >= 200),
    ("Better (+0.8…+2)", lambda c: 80 <= c < 200),
    ("Equal (±0.8)", lambda c: -80 < c < 80),
    ("Worse (−2…−0.8)", lambda c: -200 < c <= -80),
    ("Losing (≤ −2)", lambda c: c <= -200),
]


def _blank():
    return {"n": 0, "acc": 0.0, "bl": 0, "mi": 0, "t3": 0}


def conversion_report(pairs, cp: int = 200) -> list[dict]:
    """pairs: list of (Game, GameAnalysis). Returns a list of {title, widgets}."""
    phase_agg = {p: _blank() for p in PHASE_ORDER}
    state_agg = {s[0]: _blank() for s in STATES}
    reached_win = won = reached_loss = saved = decisive = 0
    won_phase, lost_phase = Counter(), Counter()
    won_moves, lost_moves = [], []

    for g, a in pairs:
        evals = a.evals
        if not evals:
            continue
        user_evals = [e if g.color == "white" else -e for e in evals]
        if max(user_evals) >= cp:
            reached_win += 1
            won += (g.outcome == "win")
        if min(user_evals) <= -cp:
            reached_loss += 1
            saved += (g.outcome in ("win", "draw"))
        if max(abs(e) for e in evals) >= cp:
            decisive += 1

        # Point of no return: the move after which you hold a real lead (win) or
        # stay behind (loss) for the rest of the game — where it was really decided.
        # "Lead" = at least half the decisive threshold (e.g. +/-1 pawn).
        lead = cp // 2
        # The deciding move is ply idx+1; its phase is the one it was played in.
        if g.outcome == "win":
            idx = max((i for i, v in enumerate(user_evals) if v < lead), default=-1)
            mv = max(1, (idx + 2) // 2)
            won_phase[a.phase_of(max(1, idx + 1))] += 1
            won_moves.append(mv)
        elif g.outcome == "loss":
            idx = max((i for i, v in enumerate(user_evals) if v > -lead), default=-1)
            mv = max(1, (idx + 2) // 2)
            lost_phase[a.phase_of(max(1, idx + 1))] += 1
            lost_moves.append(mv)

        for m in a.moves:
            if m.color != g.color:
                continue
            cp_white = evals[m.ply - 1] if 0 <= m.ply - 1 < len(evals) else 0
            cp_user = cp_white if g.color == "white" else -cp_white
            state = next(s[0] for s in STATES if s[1](cp_user))
            for bucket in (phase_agg[a.phase_of(m.ply)], state_agg[state]):
                bucket["n"] += 1
                bucket["acc"] += m.accuracy
                bucket["bl"] += (m.label == "blunder")
                bucket["mi"] += (m.label == "mistake")
                bucket["t3"] += int(m.top3)

    def table(agg, order, label_col):
        rows = []
        for key in order:
            b = agg[key]
            if not b["n"]:
                continue
            rows.append([
                key, b["n"], f"{b['acc'] / b['n']:.1f}%",
                f"{round(100 * b['t3'] / b['n'])}%",
                round(100 * b["mi"] / b["n"], 1), round(100 * b["bl"] / b["n"], 1),
            ])
        return W.table([label_col, "Moves", "Accuracy", "Engine's top 3",
                        "Mistakes per 100", "Blunders per 100"], rows)

    thr = f"{cp / 100:.2f}"
    moves_n = sum(b["n"] for b in phase_agg.values())
    moves_t3 = sum(b["t3"] for b in phase_agg.values())
    # headline accuracy = mean of the per-game (Lichess-style) accuracies, not a
    # naive average over every move.
    game_accs = [a.accuracy.get(g.color) for g, a in pairs
                 if a.accuracy.get(g.color) is not None]
    cards = W.cards([
        W.card(f"{sum(game_accs) / len(game_accs):.1f}%" if game_accs else "—",
               "Your accuracy", sub="average per game, Lichess's method"),
        W.card(f"{round(100 * moves_t3 / moves_n)}%" if moves_n else "—",
               "Moves in the engine's top 3", sub=f"of {moves_n} moves"),
        W.card(f"{round(100 * won / reached_win)}%" if reached_win else "—",
               "Winning positions won", sub=f"{won} of {reached_win} games you reached +{thr}"),
        W.card(f"{round(100 * saved / reached_loss)}%" if reached_loss else "—",
               "Losing positions saved",
               sub=f"{saved} of {reached_loss} games you reached −{thr} (won or drawn)"),
        W.card(f"{round(100 * decisive / len(pairs))}%" if pairs else "—",
               "Games where someone got winning", sub=f"the evaluation reached ±{thr}"),
    ])

    def top_phase(counter):
        total = sum(counter.values())
        if not total:
            return "—", ""
        ph, c = counter.most_common(1)[0]
        return ph, f"{round(100 * c / total)}% of {total}"

    won_top, lost_top = top_phase(won_phase), top_phase(lost_phase)
    decided_cards = W.cards([
        W.card(won_top[0], "Wins decided in", sub=won_top[1]),
        W.card(lost_top[0], "Losses decided in", sub=lost_top[1]),
        W.card(f"move {round(sum(won_moves) / len(won_moves))}" if won_moves else "—",
               "Wins decided, on average"),
        W.card(f"move {round(sum(lost_moves) / len(lost_moves))}" if lost_moves else "—",
               "Losses decided, on average"),
    ])
    decided_note = W.text(
        f"Where a game was decided: the move after which the winner stayed at least "
        f"{lead / 100:.2f} ahead for the rest of the game.")
    decided_table = W.table(
        ["Phase", "Wins decided here", "Losses decided here"],
        [[ph, won_phase.get(ph, 0), lost_phase.get(ph, 0)] for ph in PHASE_ORDER],
    )

    # (no raw "accuracy by phase" table here: phase accuracy is confounded by
    # phase difficulty — weaknesses.phase_parity shows the fair, opponent-paired
    # version instead. phase_agg still feeds the Top-3 headline card above.)
    return [
        {"title": "Outcomes", "widgets": [cards]},
        {"title": "Phase where games are decided", "widgets": [decided_note, decided_cards,
                                                          decided_table]},
        {"title": "Accuracy by the position you moved in",
         "widgets": [W.text("Your moves grouped by the evaluation before them. Blunders "
                            "are rare in losing positions for an arithmetic reason: "
                            "with little win chance left, there is little left to lose."),
                     table(state_agg, [s[0] for s in STATES], "Position")]},
    ]


# colours for the eval-curve series
_C_ALL = "#1d6f6a"
_C_WHITE, _C_BLACK = "#1d6f6a", "#b06a2c"
_C_WIN, _C_DRAW, _C_LOSS = W.WDL_PALETTE["win"], "#b9b09c", W.WDL_PALETTE["loss"]


def _avg_eval_series(pairs, label_of, order, max_moves: int = 60) -> list[dict]:
    """Average evaluation (your POV) per move number, grouped by `label_of(game)`.

    order: [(label, color)] fixing series order/colour. A move number is plotted
    for a group only while ≥20% of that group's games are still going, so the
    long tail doesn't wander on a handful of games. Evals are clamped to ±10
    pawns so one mate score can't dominate the mean.

    The floor is two samples — one game, which contributes both its plies at
    every move number it reaches. It must not be higher: a hard floor of four
    silently erased any group holding a single game, so a lone loss with White
    simply had no line and nothing said why. Each series carries its `games`
    count instead, which the legend shows, so a thin line is visibly thin
    rather than absent.
    """
    sums, cnts, gcount = {}, {}, {}
    for g, a in pairs:
        if not a.evals:
            continue
        lab = label_of(g)
        if lab is None:
            continue
        gcount[lab] = gcount.get(lab, 0) + 1
        s, c = sums.setdefault(lab, {}), cnts.setdefault(lab, {})
        sgn = 1 if g.color == "white" else -1
        for ply in range(1, len(a.evals)):          # skip the start position
            mv = (ply + 1) // 2
            if mv > max_moves:
                break
            e = max(-1000, min(1000, sgn * a.evals[ply]))
            s[mv] = s.get(mv, 0.0) + e
            c[mv] = c.get(mv, 0) + 1
    series = []
    for lab, color, *rest in order:
        if lab not in sums:
            continue
        dash = bool(rest[0]) if rest else False
        floor = max(2, 0.4 * gcount[lab])            # ~20% of games (2 plies each)
        pts = [{"x": mv, "y": round(sums[lab][mv] / cnts[lab][mv] / 100, 2)}
               for mv in sorted(sums[lab]) if cnts[lab][mv] >= floor]
        if len(pts) >= 2:
            series.append({"name": lab, "color": color, "dash": dash,
                           "games": gcount[lab], "points": pts})
    return series


def eval_curve(pairs) -> list[dict]:
    """Average evaluation (your POV) at each move number, with switchable splits.

    One chart, three groupings: the overall average, split by colour played, and
    split by result (won / drawn / lost) — so you can see, e.g., that your losses
    drift negative from the opening while your wins build up from the middlegame.
    """
    res_label = {"win": "Won", "draw": "Drawn", "loss": "Lost"}
    overall = _avg_eval_series(pairs, lambda g: "All games", [("All games", _C_ALL)])
    by_color = _avg_eval_series(
        pairs, lambda g: "As White" if g.color == "white" else "As Black",
        [("As White", _C_WHITE), ("As Black", _C_BLACK)])
    by_result = _avg_eval_series(
        pairs, lambda g: res_label.get(g.outcome),
        [("Won", _C_WIN), ("Drawn", _C_DRAW), ("Lost", _C_LOSS)])

    # colour × result: result sets the line colour, colour-played the style
    # (White solid, Black dashed) — up to six series.
    def colres_label(g):
        if g.outcome not in res_label:
            return None
        return f"{'White' if g.color == 'white' else 'Black'} · {res_label[g.outcome]}"
    by_both = _avg_eval_series(pairs, colres_label, [
        ("White · Won", _C_WIN, False), ("White · Drawn", _C_DRAW, False),
        ("White · Lost", _C_LOSS, False), ("Black · Won", _C_WIN, True),
        ("Black · Drawn", _C_DRAW, True), ("Black · Lost", _C_LOSS, True),
    ])

    groupings = []
    if overall:
        groupings.append({"key": "all", "label": "Average", "series": overall})
    if by_color:
        groupings.append({"key": "color", "label": "By colour", "series": by_color})
    if by_result:
        groupings.append({"key": "result", "label": "By result", "series": by_result})
    if len(by_both) > max(len(by_color), len(by_result)):
        groupings.append({"key": "colres", "label": "Colour × result",
                          "series": by_both})
    if not groupings:
        return []
    default = "color" if by_color else groupings[0]["key"]
    return [{"title": "Average evaluation by move",
             "widgets": [W.text("Your mean engine evaluation (in pawns, from your "
                                 "side's point of view) at each move number — how "
                                 "your typical game drifts for and against you. "
                                 "Switch between the overall average, by colour, by "
                                 "result, or colour × result (White solid, Black "
                                 "dashed)."),
                         W.evalcurve(groupings, default=default)]}]


def accuracy_trend(pairs) -> list[dict]:
    """Your engine accuracy per game over time (Game / Day / Month averaging).

    pairs must be chronological. One point per game; the chart's Day/Month
    buttons average accuracy within each period (agg='mean').
    """
    pts = [{"x": g.date, "y": round(a.accuracy[g.color], 1)}
           for g, a in pairs
           if a.accuracy.get(g.color) is not None and g.date]
    if len(pts) < 2:
        return []
    line = W.line([{"name": "Accuracy", "points": pts}], y_label="Accuracy")
    line["toolbar"] = True
    line["agg"] = "mean"
    line["y_max"] = 100      # accuracy is a percentage — never scale past 100
    return [{"title": "Accuracy over time", "widgets": [line]}]


# --- advanced, engine-derived diagnostics -----------------------------------
ERROR_LABELS = {"mistake", "blunder"}


def _is_error(label) -> bool:
    return label in ERROR_LABELS


def punish_chances(game, analysis):
    """[(their move, your reply)] for every opponent mistake or blunder (a move
    that cost them at least `MISTAKE` win chance) that you got to answer.

    The one definition of "a chance to punish" — the Stats page, the progress
    check and the Peers comparison all count it this way; "punished" means the
    reply was the engine's first choice.
    """
    moves = analysis.moves
    return [(m, moves[i + 1]) for i, m in enumerate(moves[:-1])
            if m.color != game.color and m.wp_loss >= MISTAKE
            and moves[i + 1].color == game.color]


def punished(reply) -> bool:
    return bool(reply.best_san) and reply.san == reply.best_san


def advanced_report(pairs) -> list[dict]:
    """Punishing mistakes, and whether one error breeds the next.

    Two engine-derived diagnostics with a clear chess meaning: do you answer
    an opponent's mistake with the engine's move, and how often does a
    mistake of yours come straight after another one?
    """
    opp_chances = opp_taken = 0
    err_followed = err_then_err = 0
    base_moves = base_err = 0

    for g, a in pairs:
        if not a.evals:
            continue
        for _, reply in punish_chances(g, a):
            opp_chances += 1
            opp_taken += punished(reply)
        mine = [m for m in a.moves if m.color == g.color]
        for j, m in enumerate(mine):
            base_moves += 1
            base_err += _is_error(m.label)
            if _is_error(m.label) and j + 1 < len(mine):
                err_followed += 1
                err_then_err += _is_error(mine[j + 1].label)

    if not base_moves:
        return []

    pct = lambda n, d: f"{round(100 * n / d)}%" if d else "—"
    cards = W.cards([
        W.card(pct(opp_taken, opp_chances), "Their mistakes you punished",
               sub=f"{opp_taken} of {opp_chances} answered with the engine's move"),
        W.card(pct(err_then_err, err_followed), "A mistake straight after a mistake",
               sub=f"{err_then_err} of {err_followed} times · on any move "
                   f"{pct(base_err, base_moves)}"),
    ])
    notes = W.text(
        f"Their mistakes you punished: when your opponent's move cost them "
        f"{MISTAKE:.0f}% win chance or more, how often your reply was the engine's "
        f"first choice. A mistake straight after a mistake: after a move of yours "
        f"that was a mistake or a blunder, how often the next one was too, beside "
        f"your rate on any move.")
    return [{"title": "Punishing mistakes, and mistakes in a row", "widgets": [cards, notes]}]


# --- progress check: recent games vs your own baseline ----------------------
# metric key -> (label, higher_is_better, "no change" epsilon, sample floor key)
_PROGRESS_METRICS = [
    ("acc", "Accuracy", True, 0.5),
    ("bl100", "Blunders per 100 moves", False, 0.3),
    ("conv", "Winning positions won", True, 3.0),
    ("punish", "Their mistakes you punished", True, 3.0),
    ("open_loss", "Opening: win chance lost per move", False, 0.3),
    ("tt", "Games reaching time trouble", False, 3.0),
]


def _progress_block(pairs, cp):
    """The tracked metrics over one block of (Game, GameAnalysis) pairs.

    Returns {key: (value, n)} with n = the metric's own sample size, so each
    row can be gated independently.
    """
    from .clocks import TIME_TROUBLE_FRAC, clock_profile

    accs, open_loss = [], []
    own = bl = reached = won = chances = taken = prof = tt = 0
    for g, a in pairs:
        if not a.evals or not a.moves:
            continue
        sgn = 1 if g.color == "white" else -1
        user_evals = [sgn * e for e in a.evals]
        v = a.accuracy.get(g.color)
        if v is not None:
            accs.append(v)
        if max(user_evals) >= cp:
            reached += 1
            won += (g.outcome == "win")
        for m in a.moves:
            if m.color == g.color:
                own += 1
                bl += (m.label == "blunder")
                if a.phase_of(m.ply) == "Opening":
                    open_loss.append(m.wp_loss)
        for _, reply in punish_chances(g, a):
            chances += 1
            taken += punished(reply)
        try:
            pp = clock_profile(g, g.color)
        except Exception:                   # noqa: BLE001 — clockless stubs/games
            pp = None
        if pp:
            prof += 1
            tt += (pp.min_frac < TIME_TROUBLE_FRAC)

    out = {}
    if accs:
        out["acc"] = (sum(accs) / len(accs), len(accs))
    if own >= 200:
        out["bl100"] = (100 * bl / own, own)
    if reached >= 5:
        out["conv"] = (100 * won / reached, reached)
    if chances >= 5:
        out["punish"] = (100 * taken / chances, chances)
    if len(open_loss) >= 100:
        out["open_loss"] = (sum(open_loss) / len(open_loss), len(open_loss))
    if prof >= 10:
        out["tt"] = (100 * tt / prof, prof)
    return out


def progress_report(pairs, cp: int = 200) -> list[dict]:
    """Are you actually improving? Recent games vs your own earlier baseline.

    Splits the analysed games chronologically (recent = last 25 once there are
    50+, else the last third) and compares the key leak metrics. The baseline is
    the player's own history — a fair comparison — and every metric is gated on
    its own sample size, so thin data drops the row rather than faking a trend.
    """
    usable = [(g, a) for g, a in pairs if a.evals and a.moves]
    if len(usable) < 20:
        return []
    cut = len(usable) - (25 if len(usable) >= 50 else len(usable) // 3)
    base = _progress_block(usable[:cut], cp)
    recent = _progress_block(usable[cut:], cp)

    unit = {"acc": "%", "conv": "%", "punish": "%", "tt": "%",
            "bl100": "", "open_loss": "%"}
    rows, better = [], 0
    tracked = 0
    for key, label, higher, eps in _PROGRESS_METRICS:
        if key not in base or key not in recent:
            continue
        (b, bn), (r, rn) = base[key], recent[key]
        delta = r - b
        u = unit[key]
        if abs(delta) < eps:
            change = "about the same"
        else:
            good = (delta > 0) == higher
            arrow = "▲" if delta > 0 else "▼"
            change = f"{arrow} {abs(delta):.1f}{u} {'better' if good else 'worse'}"
            better += good
        tracked += 1
        rows.append([label, f"{b:.1f}{u}", f"{r:.1f}{u}", change])
    if not rows:
        return []

    head = W.cards([
        W.card(f"{better}/{tracked}", "Measures that got better",
               sub=f"last {len(usable) - cut} games against the {cut} before"),
    ])
    note = W.text(
        f"Your last {len(usable) - cut} analysed games against your {cut} games "
        f"before them. No row here has a 95% range.")
    return [{"title": "Progress check — recent vs baseline", "widgets": [
        head, note,
        W.table(["Metric", "Baseline", "Recent", "Change"], rows),
    ]}]


def outcome_reasons(pairs, cp: int = 200) -> list[dict]:
    """Why your games end the way they do — the distribution of win/loss reasons.

    Runs the per-game diagnosis (diagnosis.diagnose) over every analysed game and
    tallies the dominant reason for wins and for losses separately, plus the
    cross-cutting factors (time pressure, drift) that recur across games.
    """
    # outcome -> reason key -> list of per-game entries (for the drill-down)
    buckets = {"win": {}, "loss": {}, "draw": {}}
    totals = Counter()
    n = tt_errors = 0
    for g, a in pairs:
        dg = dx.diagnose(g, a, cp)
        if dg is None:
            continue
        n += 1
        low_at, _ = dx._clock_ctx(g, g.color)
        tt_errors += any(m.color == g.color and m.wp_loss >= MISTAKE and low_at(m.ply)
                         for m in a.moves)
        # honour a manual correction of the reason flag, if the player set one
        primary, detail = dg.primary, dg.detail
        ov = overrides.get(getattr(g, "game_id", ""))
        if ov and ov.get("primary") in _table_for(dg.outcome):
            primary = ov["primary"]
            detail = "Reason set manually. " + dg.detail
        totals[dg.outcome] += 1
        buckets[dg.outcome].setdefault(primary, []).append({
            "id": getattr(g, "game_id", ""),
            "date": getattr(g, "date", ""),
            "opponent": getattr(g, "opponent", ""),
            "opp_elo": getattr(g, "opp_elo", None),
            "outcome": dg.outcome,
            "detail": detail,
            "acc": a.accuracy.get(getattr(g, "color", "")),
        })
    if not n:
        return []

    def top_card(reason_keys, reasons, label):
        items = buckets[reason_keys]
        total = sum(len(v) for v in items.values())
        if not total:
            return W.card("—", label)
        key, entries = max(items.items(), key=lambda kv: len(kv[1]))
        return W.card(reasons[key], label,
                      sub=f"{len(entries)}/{total} · {round(100 * len(entries) / total)}%")

    cards = W.cards([
        top_card("loss", dx.LOSS_REASONS, "Top reason you lose"),
        top_card("win", dx.WIN_REASONS, "Top reason you win"),
        W.card(f"{round(100 * tt_errors / n)}%" if n else "—",
               "Games with a mistake in time trouble",
               sub=f"{tt_errors} of {n}: a mistake or blunder with under "
                   f"{int(100 * dx.TIME_TROUBLE_FRAC)}% of your clock left"),
    ])

    plural = {"win": "wins", "loss": "losses", "draw": "draws"}

    def groups_for(outcome, reasons):
        total = totals[outcome] or 1
        out = []
        for key, entries in sorted(buckets[outcome].items(),
                                   key=lambda kv: -len(kv[1])):
            accs = [e["acc"] for e in entries if e["acc"] is not None]
            elos = [e["opp_elo"] for e in entries if e["opp_elo"]]
            stat = []
            if accs:
                stat.append(f"avg accuracy {sum(accs) / len(accs):.0f}%")
            if elos:
                stat.append(f"avg opponent {round(sum(elos) / len(elos))}")
            out.append({
                "label": reasons.get(key, key),
                "count": len(entries),
                "sub": f"{round(100 * len(entries) / total)}% of {plural[outcome]}",
                "stat": " · ".join(stat),
                "games": sorted(entries, key=lambda e: e["date"], reverse=True),
            })
        return out

    notes = W.text(
        "Each game is reduced to one main reason for its result — a single "
        "blunder, a slow positional drift, time pressure, an opponent's gift, a "
        "winning position let slip, or simply being outplayed. Click any reason "
        "to see the games behind it.")
    widgets = [cards, notes]
    for outcome, reasons, label in (("loss", dx.LOSS_REASONS, "Why you lose"),
                                    ("win", dx.WIN_REASONS, "Why you win"),
                                    ("draw", dx.DRAW_REASONS, "Your draws")):
        groups = groups_for(outcome, reasons)
        if groups:
            widgets.append(W.reasons(label, groups))
    return [{"title": "Why you win & lose", "widgets": widgets}]
