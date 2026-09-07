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


# --- game flags: excluded from stats, still in the history --------------------

def test_flag_set_get_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    assert overrides.get_flag("g1") is None
    overrides.set_flag("g1", "anomaly", "opponent disconnected")
    assert overrides.get_flag("g1") == {"flag": "anomaly",
                                        "note": "opponent disconnected"}
    assert overrides.flagged_ids() == {"g1"}
    overrides.set_flag("g1", None)
    assert overrides.get_flag("g1") is None and overrides.flagged_ids() == set()


def test_flag_and_reason_coexist(tmp_path, monkeypatch):
    """Both live in one entry — setting either must not wipe the other."""
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    overrides.set_reason("g2", "drift")
    overrides.set_flag("g2", "anomaly")
    assert overrides.get("g2")["primary"] == "drift"
    assert overrides.get_flag("g2")["flag"] == "anomaly"
    overrides.set_reason("g2", None)                  # clear just the reason
    assert overrides.get_flag("g2")["flag"] == "anomaly"
    overrides.set_flag("g2", None)                    # last field -> entry gone
    assert overrides.get("g2") is None


def test_flags_annotates_a_whole_list_in_one_read(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    overrides.set_flag("a", "anomaly", "disconnect")
    overrides.set_flag("b", "anomaly")
    overrides.set_reason("c", "drift")             # a reason is not a flag
    assert overrides.flags() == {"a": {"flag": "anomaly", "note": "disconnect"},
                                 "b": {"flag": "anomaly", "note": None}}
    assert overrides.flagged_ids() == {"a", "b"}


def test_unknown_flag_is_not_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    overrides.set_flag("g3", "nonsense")
    assert overrides.get_flag("g3") is None            # not in FLAGS -> ignored
    assert overrides.flagged_ids() == set()


PGN = """[Event "Live Chess"]
[Site "Chess.com"]
[White "{white}"]
[Black "{black}"]
[Result "{result}"]
[UTCDate "2026.01.0{n}"]
[UTCTime "12:00:00"]
[WhiteElo "1500"]
[BlackElo "1500"]
[TimeControl "600"]
[Link "https://www.chess.com/game/live/{gid}"]

1. e4 e5 2. Nf3 Nc6 {result}
"""


def _library(tmp_path):
    for n, (gid, result) in enumerate([("111", "1-0"), ("222", "0-1")], start=1):
        (tmp_path / f"g{gid}.pgn").write_text(
            PGN.format(white="me", black="opp", result=result, n=n, gid=gid))
    return str(tmp_path)


def test_load_games_drops_flagged_but_can_include_them(tmp_path, monkeypatch):
    from chessanalysis.model import load_games

    monkeypatch.setattr(overrides, "_PATH", str(tmp_path / "ov.json"))
    folder = _library(tmp_path)
    assert {g.game_id for g in load_games(folder, "me")} == {"111", "222"}

    overrides.set_flag("111", "anomaly", "server died")
    # statistics see only the honest game...
    assert [g.game_id for g in load_games(folder, "me")] == ["222"]
    # ...while the history still lists both
    assert {g.game_id for g in load_games(folder, "me", include_flagged=True)} \
        == {"111", "222"}


def _loss_groups(sections):
    reasons = [w for w in sections[0]["widgets"] if w["type"] == "reasons"]
    return {w["label"]: w for w in reasons}["Why you lose"]["groups"]
