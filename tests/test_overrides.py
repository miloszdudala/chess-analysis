"""Manual reason overrides: persistence + effect on the aggregate distribution."""
from __future__ import annotations

import chessanalysis.overrides as overrides
from chessanalysis import diagnosis as dx
from chessanalysis import insights
from tests.test_diagnosis import DGame, analysis, mev


def test_set_get_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    assert overrides.get("g1") is None
    overrides.set_reason("g1", "threw_away")
    assert overrides.get("g1") == {"primary": "threw_away"}
    overrides.set_reason("g1", None)           # clearing removes it
    assert overrides.get("g1") is None


def test_override_moves_a_game_to_another_bucket(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    # a loss the heuristic reads as one blunder
    blunder = analysis([mev(1, "white", "blunder", wp=40.0, cpl=420)], [20, -400])
    g = DGame("loss")
    g.game_id = "gid-1"
    pairs = [(g, blunder)]

    base = insights.outcome_reasons(pairs)
    loss_groups = _loss_groups(base)
    assert loss_groups[0]["label"] == dx.LOSS_REASONS["blunder"]

    # the player insists it was really a slow drift
    overrides.set_reason("gid-1", "drift")
    after = insights.outcome_reasons(pairs)
    groups = _loss_groups(after)
    assert groups[0]["label"] == dx.LOSS_REASONS["drift"]
    assert groups[0]["games"][0]["detail"].startswith("Reason set manually.")


def test_override_ignored_if_reason_not_in_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    blunder = analysis([mev(1, "white", "blunder", wp=40.0, cpl=420)], [20, -400])
    g = DGame("loss")
    g.game_id = "gid-2"
    overrides.set_reason("gid-2", "comeback")   # a win-only key, invalid for a loss
    groups = _loss_groups(insights.outcome_reasons([(g, blunder)]))
    assert groups[0]["label"] == dx.LOSS_REASONS["blunder"]   # falls back to auto


def _loss_groups(sections):
    reasons = [w for w in sections[0]["widgets"] if w["type"] == "reasons"]
    return {w["label"]: w for w in reasons}["Why you lose"]["groups"]
