"""Per-file tests for domains.basketball_wnba.ingame_live_cdn_poller.

Covers gameId <-> ESPN event id mapping (both id spaces confirmed different
this wave) and the bounded poll_once entrypoint with fully injected getters
(no network).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_live_cdn_poller.py -q
"""
from __future__ import annotations

import json

from domains.basketball_wnba.ingame_live_cdn_poller import (
    fetch_scoreboardv3, gameid_map_hint, poll_once,
)


def _espn_event(event_id, home_abbr, away_abbr):
    return {"id": event_id, "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": home_abbr}},
        {"homeAway": "away", "team": {"abbreviation": away_abbr}},
    ]}]}


# ---------------------------------------------------------------------------
# id mapping (real confirmed pair: gameId 1022600149 CHI@LV <-> espn 401857038)
# ---------------------------------------------------------------------------

def test_gameid_map_hint_real_confirmed_pair():
    sb_games = [{"gameId": "1022600149", "gameCode": "20260703/CHILVA"}]
    espn_events = [_espn_event("401857038", "LV", "CHI")]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert mapping == {"1022600149": "401857038"}


def test_gameid_map_hint_ambiguous_pair_is_absent():
    sb_games = [{"gameId": "1022600149", "gameCode": "20260703/CHILVA"}]
    espn_events = [
        _espn_event("401857038", "LV", "CHI"),
        _espn_event("401857099", "LVA", "CHI2"),  # spurious second LV-ish match
    ]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert "1022600149" not in mapping


def test_gameid_map_hint_malformed_gamecode_skipped():
    sb_games = [{"gameId": "1022600149", "gameCode": ""}]
    espn_events = [_espn_event("401857038", "LV", "CHI")]
    assert gameid_map_hint(sb_games, espn_events) == {}


# ---------------------------------------------------------------------------
# non-3-letter tricode hardening (this wave -- the flagged untested case)
# ---------------------------------------------------------------------------

def test_gameid_map_hint_2plus4_split_resolved():
    # away tricode "GS" (2 chars) + home "PORT" (4 chars, hypothetical alt code).
    sb_games = [{"gameId": "9990000001", "gameCode": "20260703/GSPORT"}]
    espn_events = [_espn_event("500000001", "PORT", "GS")]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert mapping == {"9990000001": "500000001"}


def test_gameid_map_hint_4plus2_split_resolved():
    # away tricode "CONN" (4 chars) + home "NY" (2 chars, hypothetical alt code).
    sb_games = [{"gameId": "9990000002", "gameCode": "20260703/CONNNY"}]
    espn_events = [_espn_event("500000002", "NY", "CONN")]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert mapping == {"9990000002": "500000002"}


def test_gameid_map_hint_non_3_letter_ambiguous_across_splits_is_absent():
    # A blob that plausibly matches under more than one split candidate must
    # never guess -- absent beats wrong.
    sb_games = [{"gameId": "9990000003", "gameCode": "20260703/ATLATL"}]
    espn_events = [
        _espn_event("500000003", "ATL", "ATL"),  # 3+3 split matches
        _espn_event("500000004", "ATLA", "TL"),  # 4+2 split also matches (contrived)
    ]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert "9990000003" not in mapping


def test_gameid_map_hint_still_resolves_standard_3plus3_after_hardening():
    # Regression guard: the original confirmed-real pair must still resolve
    # after widening the split search.
    sb_games = [{"gameId": "1022600149", "gameCode": "20260703/CHILVA"}]
    espn_events = [_espn_event("401857038", "LV", "CHI")]
    mapping = gameid_map_hint(sb_games, espn_events)
    assert mapping == {"1022600149": "401857038"}


# ---------------------------------------------------------------------------
# fetch_scoreboardv3 (WAF/timeout degrade to [])
# ---------------------------------------------------------------------------

def test_fetch_scoreboardv3_happy_path():
    payload = json.dumps({"scoreboard": {"games": [
        {"gameId": "1022600149", "gameStatus": 2},
    ]}}).encode("utf-8")
    games = fetch_scoreboardv3("2026-07-03", http_get=lambda url: payload)
    assert len(games) == 1
    assert games[0]["gameId"] == "1022600149"


def test_fetch_scoreboardv3_waf_page_returns_empty():
    html = b"<!DOCTYPE html>We are unable to process your request"
    assert fetch_scoreboardv3("2026-07-03", http_get=lambda url: html) == []


def test_fetch_scoreboardv3_network_failure_returns_empty():
    assert fetch_scoreboardv3("2026-07-03", http_get=lambda url: None) == []


# ---------------------------------------------------------------------------
# poll_once -- bounded, injected getters, explicit game_ids bypasses discovery
# ---------------------------------------------------------------------------

def _box_payload(gid="g1"):
    team = {"inBonus": 0, "timeoutsRemaining": 4, "score": 10,
            "players": [{"personId": f"p{i}", "oncourt": "1" if i < 5 else "0",
                         "statistics": {"foulsPersonal": 0}} for i in range(6)]}
    return json.dumps({"game": {"gameId": gid, "period": 1, "gameClock": "PT10M00.00S",
                                 "homeTeam": team, "awayTeam": team}}).encode("utf-8")


def test_poll_once_explicit_game_ids_bypasses_discovery(tmp_path, monkeypatch):
    import domains.basketball_wnba.ingame_live_cdn as cdn_mod
    monkeypatch.setattr(cdn_mod, "SIDECAR_DIR", tmp_path)

    summary = poll_once(
        game_ids=["g1"], sleep_s=0.0,
        box_getter=lambda url: _box_payload("g1"),
        pbp_getter=lambda url: json.dumps({"game": {"actions": []}}).encode("utf-8"),
    )
    assert summary["n_games"] == 1
    assert summary["n_live"] == 1
    assert summary["n_snapshots"] == 1
    assert (tmp_path / "g1.jsonl").exists()


def test_poll_once_box_fetch_failure_no_snapshot(tmp_path, monkeypatch):
    import domains.basketball_wnba.ingame_live_cdn as cdn_mod
    monkeypatch.setattr(cdn_mod, "SIDECAR_DIR", tmp_path)

    summary = poll_once(game_ids=["g1"], sleep_s=0.0, box_getter=lambda url: None)
    assert summary["n_snapshots"] == 0
    assert not (tmp_path / "g1.jsonl").exists()


def test_poll_once_discovery_filters_live_only(tmp_path, monkeypatch):
    import domains.basketball_wnba.ingame_live_cdn as cdn_mod
    monkeypatch.setattr(cdn_mod, "SIDECAR_DIR", tmp_path)

    sb_payload = json.dumps({"scoreboard": {"games": [
        {"gameId": "final1", "gameStatus": 3},
        {"gameId": "live1", "gameStatus": 2},
        {"gameId": "pre1", "gameStatus": 1},
    ]}}).encode("utf-8")
    summary = poll_once(
        date_str="2026-07-03", sleep_s=0.0,
        sb_getter=lambda url: sb_payload,
        box_getter=lambda url: _box_payload("live1"),
        pbp_getter=lambda url: json.dumps({"game": {"actions": []}}).encode("utf-8"),
    )
    assert summary["n_games"] == 3
    assert summary["n_live"] == 1
    assert summary["n_snapshots"] == 1
