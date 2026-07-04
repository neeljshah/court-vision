"""Per-file tests for domains.basketball_wnba.cdn_backfill.

No network -- get_json is always injected. tmp_path monkeypatches BACKFILL_DIR
so nothing touches the real data/domains/wnba/cdn_backfill tree.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_cdn_backfill.py -q
"""
from __future__ import annotations

import json

import domains.basketball_wnba.cdn_backfill as mod
from domains.basketball_wnba.cdn_backfill import (
    backfill_one_game, fetch_completed_game_ids, game_dir, run_backfill,
)


def _schedule_payload(games):
    return {"leagueSchedule": {"gameDates": [{"gameDate": "x", "games": games}]}}


def _box_payload(gid):
    return {"game": {"gameId": gid, "period": 4, "homeTeam": {}, "awayTeam": {}}}


def _pbp_payload(gid):
    return {"game": {"gameId": gid, "actions": [{"actionType": "period"}]}}


# ---------------------------------------------------------------------------
# fetch_completed_game_ids -- filters to FINAL status, degrades on bad payload
# ---------------------------------------------------------------------------

def test_fetch_completed_game_ids_filters_final_only():
    payload = _schedule_payload([
        {"gameId": "g1", "gameStatus": 3, "gameCode": "20260101/AAABBB", "gameDateEst": "2026-01-01T00:00:00Z"},
        {"gameId": "g2", "gameStatus": 1, "gameCode": "20260102/CCCDDD", "gameDateEst": "2026-01-02T00:00:00Z"},
        {"gameId": "g3", "gameStatus": 2, "gameCode": "20260103/EEEFFF", "gameDateEst": "2026-01-03T00:00:00Z"},
    ])
    games = fetch_completed_game_ids(get_json=lambda url: payload)
    assert [g["game_id"] for g in games] == ["g1"]
    assert games[0]["date"] == "2026-01-01"


def test_fetch_completed_game_ids_bad_payload_returns_empty():
    assert fetch_completed_game_ids(get_json=lambda url: None) == []
    assert fetch_completed_game_ids(get_json=lambda url: {"unexpected": 1}) == []


def test_fetch_completed_game_ids_missing_gameid_skipped():
    payload = _schedule_payload([{"gameStatus": 3, "gameCode": "x"}])
    assert fetch_completed_game_ids(get_json=lambda url: payload) == []


# ---------------------------------------------------------------------------
# backfill_one_game -- resumability + partial/failed classification
# ---------------------------------------------------------------------------

def test_backfill_one_game_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)

    def getter(url):
        if "boxscore" in url:
            return _box_payload("g1")
        return _pbp_payload("g1")

    result = backfill_one_game("g1", get_json=getter)
    assert result == {"game_id": "g1", "status": "fetched"}
    assert (game_dir("g1") / "boxscore.json").exists()
    assert (game_dir("g1") / "playbyplay.json").exists()
    data = json.loads((game_dir("g1") / "boxscore.json").read_text(encoding="utf-8"))
    assert data["game"]["gameId"] == "g1"


def test_backfill_one_game_resumable_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    calls = []

    def getter(url):
        calls.append(url)
        return _box_payload("g1") if "boxscore" in url else _pbp_payload("g1")

    backfill_one_game("g1", get_json=getter)
    n_calls_first = len(calls)
    result2 = backfill_one_game("g1", get_json=getter)
    assert result2 == {"game_id": "g1", "status": "skipped_exists"}
    assert len(calls) == n_calls_first  # no additional network calls on skip


def test_backfill_one_game_force_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    getter = lambda url: _box_payload("g1") if "boxscore" in url else _pbp_payload("g1")
    backfill_one_game("g1", get_json=getter)
    result = backfill_one_game("g1", get_json=getter, force=True)
    assert result["status"] == "fetched"


def test_backfill_one_game_partial_when_only_box_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    getter = lambda url: _box_payload("g1") if "boxscore" in url else None
    result = backfill_one_game("g1", get_json=getter)
    assert result["status"] == "partial"
    assert (game_dir("g1") / "boxscore.json").exists()
    assert not (game_dir("g1") / "playbyplay.json").exists()


def test_backfill_one_game_failed_when_both_none(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    result = backfill_one_game("g1", get_json=lambda url: None)
    assert result["status"] == "failed"


def test_backfill_one_game_waf_html_shaped_none_degrades_to_failed(tmp_path, monkeypatch):
    # A non-dict / missing "game" key payload (e.g. a WAF page that HAPPENED to
    # parse as some other JSON shape) must never be written as if it were real.
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    result = backfill_one_game("g1", get_json=lambda url: {"unexpected": True})
    assert result["status"] == "failed"
    assert not (game_dir("g1") / "boxscore.json").exists()


# ---------------------------------------------------------------------------
# run_backfill -- bounded, resumable, explicit game_ids bypasses discovery
# ---------------------------------------------------------------------------

def test_run_backfill_explicit_game_ids_bypasses_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    getter = lambda url: _box_payload("g1") if "boxscore" in url else _pbp_payload("g1")
    summary = run_backfill(game_ids=["g1", "g2"], sleep_s=0.0, get_json=getter)
    assert summary["n_targeted"] == 2
    assert summary["fetched"] == 2


def test_run_backfill_respects_max_games_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    getter = lambda url: _box_payload("g1") if "boxscore" in url else _pbp_payload("g1")
    summary = run_backfill(game_ids=["g1", "g2", "g3"], max_games=2, sleep_s=0.0, get_json=getter)
    assert summary["n_targeted"] == 2


def test_run_backfill_second_pass_all_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "BACKFILL_DIR", tmp_path)
    getter = lambda url: _box_payload("g1") if "boxscore" in url else _pbp_payload("g1")
    run_backfill(game_ids=["g1"], sleep_s=0.0, get_json=getter)
    summary2 = run_backfill(game_ids=["g1"], sleep_s=0.0, get_json=getter)
    assert summary2["skipped_exists"] == 1
    assert summary2["fetched"] == 0
