"""The opening explorer, scouting, and the background-job runner."""
import time

import pytest

from chessanalysis import explorer, jobs, modes, store

from .conftest import store_game


@pytest.fixture(autouse=True)
def fresh_indexes():
    explorer._INDEX.clear()
    yield
    explorer._INDEX.clear()


ITALIAN = ["e4", "e5", "Nf3", "Nc6", "Bc4"]
SPANISH_BY_TRANSPOSITION = ["Nf3", "Nc6", "e4", "e5", "Bb5"]
AFTER = ["e2e4", "e7e5", "g1f3", "b8c6"]


def test_transpositions_meet_in_one_position():
    store_game("me", "a", 2000, 2000, ITALIAN, result="1-0", source="own")
    store_game("me", "b", 2000, 2000, SPANISH_BY_TRANSPOSITION, result="0-1", source="own")
    p = explorer.position(AFTER, "me", "white")
    assert p["me"]["games"] == 2 and p["your_move"]
    by = {m["san"]: m for m in p["me"]["moves"]}
    assert by["Bc4"]["score"] == 1.0 and by["Bb5"]["score"] == 0.0
    assert p["opening"]["name"].startswith("King's Knight Opening") or p["opening"]["name"]
    assert len(p["games"]) == 2 and {g["ply"] for g in p["games"]} == {4}


def test_the_band_credits_each_move_to_its_player():
    store_game("x", "y", 2000, 1400, ITALIAN, result="1-0")      # only White is in range
    p = explorer.position([], "me", "white", elo=2000)
    assert p["band"]["games"] == 1 and p["band"]["moves"][0]["san"] == "e4"
    after_e4 = explorer.position(["e2e4"], "me", "white", elo=2000)
    assert after_e4["band"]["games"] == 0                          # Black was 1400


def test_the_book_column(tiny_book):
    p = explorer.position([], None, "white")
    assert {m["san"] for m in p["masters"]["moves"]} == {"e4", "Nf3"}
    assert abs(sum(m["share"] for m in p["masters"]["moves"]) - 1) < 0.01


def test_illegal_moves_stop_the_line():
    p = explorer.position(["e2e4", "e2e4"], None, "white")
    assert p["moves"] == ["e2e4"]


def test_scouting_reads_their_games_and_your_lines():
    today = time.strftime("%Y.%m.%d")
    for k in range(6):
        store_game("rival", f"o{k}", 2050, 2000, ITALIAN, result="1-0", source="scout", date=today)
    store_game("x", "rival", 2000, 2050, ["e4", "c5"], result="0-1", source="scout", date=today)
    store_game("me", "y", 2000, 2000, ITALIAN, result="1-0", source="own", date=today)
    store_game("rival", "me", 2050, 2000, ITALIAN, result="0-1", source="scout", date=today)
    doc = modes.get("scout")("rival", me="me", time_class="rapid", months=3)
    titles = [s.title for s in doc.sections]
    assert "What they play" in titles and "How their games end" in titles
    assert "Head to head" in titles
    assert doc.meta["opponent"] == "rival"


def test_scouting_never_restamps_games_as_your_own(monkeypatch):
    import scraper

    gid = store_game("rival", "other", 2000, 2000, ITALIAN)       # already in the corpus
    pgn = store.unpack_pgn(store.connect().execute(
        "SELECT pgn FROM games WHERE gid=?", (gid,)).fetchone()[0])
    monkeypatch.setattr(scraper, "list_archives", lambda u: ["https://x/2026/10"])
    monkeypatch.setattr(scraper, "get_text", lambda url: pgn)
    monkeypatch.setattr(scraper.time, "sleep", lambda s: None)
    scraper.scrape("rival", source="scout", months=3, log=lambda *a: None)
    assert store.count_games("corpus") == 1 and store.count_games("own") == 0


def test_a_job_runs_once_per_key_and_stops_for_another():
    seen = []

    def work(job, tag):
        seen.append(tag)
        while not job.stopping:
            time.sleep(0.01)
        job.update(stopped_for=job.want)

    jobs.start("t", "alice", work, "a")
    snap = jobs.start("t", "alice", work, "again")     # same key: just reports
    assert snap["running"] and snap["key"] == "alice"
    jobs.start("t", "bob", work, "b")                  # another key: asked to stop
    done = jobs.wait("t", timeout=5)
    assert seen == ["a"] and done["finished"] and done["stopped_for"] == "bob"
