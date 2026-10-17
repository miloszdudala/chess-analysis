"""Engine math, MoveEval derivation, and the top_moves cache guard."""
from __future__ import annotations

import pytest

from chessanalysis import store
from chessanalysis.enrich import engine as eng
from chessanalysis.enrich.engine import GameAnalysis

from .conftest import FakeGame, build_raw


# --- pure scoring functions -------------------------------------------------

def test_win_prob_centered_and_symmetric():
    assert eng.win_prob(0) == pytest.approx(50.0)
    assert eng.win_prob(300) > 50 > eng.win_prob(-300)
    # win% for both sides of a position sums to 100
    assert eng.win_prob(250) + eng.win_prob(-250) == pytest.approx(100.0)


def test_classify_thresholds():
    assert eng._classify(0) == "ok"
    assert eng._classify(eng.INACCURACY) == "inaccuracy"
    assert eng._classify(eng.MISTAKE) == "mistake"
    assert eng._classify(eng.BLUNDER) == "blunder"
    assert eng._classify(eng.BLUNDER + 50) == "blunder"


def test_move_accuracy_bounds():
    assert eng._move_accuracy(0) == pytest.approx(100.0, abs=0.5)
    assert eng._move_accuracy(1000) == 0.0          # clamped, never negative
    assert 0.0 <= eng._move_accuracy(12) <= 100.0


# --- _derive: raw cache dict -> GameAnalysis --------------------------------

def test_derive_basic_shape(sample_analysis):
    a = sample_analysis
    assert a.depth == 12 and a.engine_name == "TestFish"
    assert len(a.moves) == 4
    assert len(a.evals) == 5
    # fens and top_moves are passed through, one per position
    assert len(a.fens) == 5
    assert len(a.top_moves) == 5


def test_derive_move_fields(sample_analysis):
    m0 = sample_analysis.moves[0]
    assert m0.ply == 1 and m0.color == "white" and m0.san == "e4"
    assert m0.best_san            # best_uci was a legal move -> SAN resolved
    # white's move 2 (Nf3, ply 3) hands black a winning reply -> black blunder flagged
    labels = [m.label for m in sample_analysis.moves]
    assert "blunder" in labels


def test_derive_cploss_perspective(sample_analysis):
    # eval jumps +570 for white after black's last move => black lost ground
    black_moves = [m for m in sample_analysis.moves if m.color == "black"]
    assert black_moves[-1].cp_loss > 0
    assert black_moves[-1].wp_loss > 0


def test_derive_accuracy_and_counts(sample_analysis):
    a = sample_analysis
    assert a.accuracy["white"] is not None and a.accuracy["black"] is not None
    assert set(a.counts["white"]) == {"inaccuracy", "mistake", "blunder"}
    assert a.acpl["white"] is not None


def test_top3_match_flag_and_aggregate():
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    raw["top_moves"][0] = [{"uci": "e2e4", "cp": 10}]    # white played the #1
    raw["top_moves"][1] = [{"uci": "g8f6", "cp": 8}]     # black did NOT (played e5)
    a = eng._derive(raw, depth=10, engine_name="x")
    assert a.moves[0].top3 is True and a.moves[1].top3 is False
    assert a.top3["white"] == 100.0 and a.top3["black"] == 0.0


def test_game_accuracy_penalises_a_blunder():
    clean = eng._derive(build_raw(["e2e4", "e7e5", "g1f3"], [10, 10, 10, 10]),
                        depth=10, engine_name="x")
    assert clean.accuracy["white"] > 95          # flat eval -> near-perfect
    # same but white throws away the game on move 2
    blund = eng._derive(build_raw(["e2e4", "e7e5", "f1c4"], [10, 10, 10, -900]),
                        depth=10, engine_name="x")
    assert blund.accuracy["white"] < clean.accuracy["white"]


def test_game_accuracy_follows_lichess_blend():
    """Lichess method: a clean game scores high, while one blunder in a sharp
    spot is felt through both the harmonic mean and the volatility weighting."""
    import types
    evals = [20, 40, 10, 60, 30, 50, 20]                     # a real back-and-forth
    strong = [types.SimpleNamespace(ply=p, color="white", accuracy=96.0)
              for p in (1, 3, 5)]
    clean = eng._game_accuracy(evals, strong)["white"]
    assert clean > 90                                        # all strong -> high

    with_blunder = [types.SimpleNamespace(ply=1, color="white", accuracy=96.0),
                    types.SimpleNamespace(ply=3, color="white", accuracy=15.0),
                    types.SimpleNamespace(ply=5, color="white", accuracy=96.0)]
    dented = eng._game_accuracy(evals, with_blunder)["white"]
    assert dented < 60 and dented < clean - 20               # the blunder counts


def test_derive_handles_missing_top_moves():
    """Old caches predate top_moves; _derive must still work (empty list)."""
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    del raw["top_moves"]
    a = eng._derive(raw, depth=10, engine_name="x")
    assert a.top_moves == []
    assert len(a.moves) == 2


# --- GameAnalysis methods ---------------------------------------------------

def test_decisive_white_holds():
    a = GameAnalysis(depth=8, engine_name="x", evals=[0, 50, 250, 300, 280])
    d = a.decisive(200)
    assert d["reached"] and d["side"] == "white" and d["held"] is True
    assert d["ply"] == 2


def test_decisive_not_reached():
    a = GameAnalysis(depth=8, engine_name="x", evals=[0, 50, -30, 10])
    assert a.decisive(200)["reached"] is False


def test_decisive_advantage_lost():
    # white reaches +250 then it collapses below threshold -> not held
    a = GameAnalysis(depth=8, engine_name="x", evals=[0, 250, 100, 50])
    d = a.decisive(200)
    assert d["reached"] and d["held"] is False


def test_blunders_and_key_moments(sample_analysis):
    assert all(m.label == "blunder" for m in sample_analysis.blunders())
    km = sample_analysis.key_moments(6)
    assert km and km[0].wp_loss >= km[-1].wp_loss      # sorted worst-first


# --- analyse_game store guard (no real engine needed) -----------------------

def test_stored_analysis_used_when_top_moves_present(monkeypatch):
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    g = FakeGame(game_id="g1")
    store.save_analysis(g.game_id, 12, raw)
    # if the stored analysis is honoured, the engine is never opened
    monkeypatch.setattr(eng, "find_engine",
                        lambda: pytest.fail("should not open engine"))
    a = eng.analyse_game(g, depth=12)
    assert a.evals == [10, 8, 12]
    assert len(a.top_moves) == 3


def test_analysis_without_top_moves_recomputes(monkeypatch):
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    del raw["top_moves"]                       # a multipv-1 / pre-multipv pass
    g = FakeGame(game_id="g2")
    store.save_analysis(g.game_id, 12, raw)

    class Sentinel(RuntimeError):
        pass

    def boom():
        raise Sentinel("recomputing")
    monkeypatch.setattr(eng, "find_engine", boom)
    # it must be bypassed -> tries to open the engine -> our sentinel
    with pytest.raises(Sentinel):
        eng.analyse_game(g, depth=12)


def test_centipawn_loss_caps_mate_scores():
    """A forced mate traded for a won position is not 9000cp of 'loss' (the
    Lichess cap); win%, and so accuracy, is unaffected."""
    from .conftest import build_raw

    raw = build_raw(["e2e4", "e7e5", "g1f3"], [eng.MATE_CP - 3, 0, 500, 0])
    a = eng._derive(raw, depth=12, engine_name="t")
    assert a.moves[0].cp_loss == eng.CP_CAP          # 1000 -> 0, not 9997 -> 0
    assert a.moves[0].label == "blunder"
