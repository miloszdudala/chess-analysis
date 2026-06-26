"""Engine math, MoveEval derivation, and the top_moves cache guard."""
from __future__ import annotations

import pytest

from chessanalysis import cache
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


# --- analyse_game cache guard (no real engine needed) -----------------------

def test_cache_used_when_top_moves_present(isolated_cache, monkeypatch):
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    g = FakeGame(game_id="g1")
    cache.save("engine", f"{g.game_id}_d12", raw)
    # if the cache is honoured, the engine is never opened
    monkeypatch.setattr(eng, "find_engine",
                        lambda: pytest.fail("should not open engine"))
    a = eng.analyse_game(g, depth=12)
    assert a.evals == [10, 8, 12]
    assert len(a.top_moves) == 3


def test_stale_cache_without_top_moves_recomputes(isolated_cache, monkeypatch):
    raw = build_raw(["e2e4", "e7e5"], [10, 8, 12])
    del raw["top_moves"]                       # simulate a pre-multipv cache
    g = FakeGame(game_id="g2")
    cache.save("engine", f"{g.game_id}_d12", raw)

    class Sentinel(RuntimeError):
        pass

    def boom():
        raise Sentinel("recomputing")
    monkeypatch.setattr(eng, "find_engine", boom)
    # stale cache must be bypassed -> it tries to open the engine -> our sentinel
    with pytest.raises(Sentinel):
        eng.analyse_game(g, depth=12)
