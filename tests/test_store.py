"""The store: small keyed state, and the one-time import of the 1.x files."""
import json

from chessanalysis import fairplay, overrides, store


def test_kv_round_trip():
    store.kv_set("ns", "k", {"a": 1})
    assert store.kv_get("ns", "k") == {"a": 1}
    assert store.kv_get("ns", "missing", "dflt") == "dflt"
    assert store.kv_all("ns") == {"k": {"a": 1}}


def test_legacy_files_beside_the_database_are_imported_once(tmp_path, monkeypatch):
    (tmp_path / "cache" / "fairplay").mkdir(parents=True)
    (tmp_path / "cache" / "fairplay" / "cheater.json").write_text(
        json.dumps({"status": fairplay.BANNED, "checked": 1}))
    (tmp_path / "overrides.json").write_text(
        json.dumps({"g1": {"flag": "anomaly", "note": "disconnect", "primary": "time"}}))
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "chess.db"))
    store.reset()
    assert fairplay.is_banned("cheater")
    assert overrides.get_flag("g1") == {"flag": "anomaly", "note": "disconnect"}
    assert overrides.get("g1")["primary"] == "time"
    # changed after the import: the files are not read again
    overrides.set_flag("g1", None)
    store.reset()
    assert overrides.get_flag("g1") is None


def test_a_store_elsewhere_never_reads_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "cache" / "fairplay").mkdir(parents=True)
    (tmp_path / "data" / "cache" / "fairplay" / "x.json").write_text(
        json.dumps({"status": fairplay.BANNED}))
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "elsewhere" / "chess.db"))
    store.reset()
    assert not fairplay.is_banned("x")
