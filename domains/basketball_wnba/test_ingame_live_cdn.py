"""Per-file tests for domains.basketball_wnba.ingame_live_cdn.

Fixtures are shaped exactly like the REAL live payload confirmed this wave
(gameId 1022600149, CHI@LV, 2026-07-03 2nd quarter -- see scratch
wnba_cdn_box.txt): homeTeam/awayTeam.{inBonus,timeoutsRemaining,players[]},
player.{personId,oncourt,statistics.foulsPersonal}. No network -- http_get
is always injected.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_live_cdn.py -q
"""
from __future__ import annotations

import json

from domains.basketball_wnba.ingame_live_cdn import (
    clock_to_sec, extract_state, fetch_boxscore, fetch_playbyplay,
    append_snapshot, sidecar_path, FOUL_TROUBLE_THRESHOLD,
)


def _player(person_id, oncourt, fouls=0):
    return {"personId": person_id, "oncourt": oncourt,
            "statistics": {"foulsPersonal": fouls}}


def _team(oncourt_ids, bench_ids=(), in_bonus=0, timeouts=4, score=50, fouls=None):
    fouls = fouls or {}
    players = [_player(pid, "1", fouls.get(pid, 0)) for pid in oncourt_ids]
    players += [_player(pid, "0", fouls.get(pid, 0)) for pid in bench_ids]
    return {"inBonus": in_bonus, "timeoutsRemaining": timeouts,
            "score": score, "players": players}


def _box_game(period=2, clock="PT08M01.00S", home=None, away=None):
    return {
        "gameId": "1022600149", "period": period, "gameClock": clock,
        "homeTeam": home or _team(["h1", "h2", "h3", "h4", "h5"], score=24),
        "awayTeam": away or _team(["a1", "a2", "a3", "a4", "a5"], score=24),
    }


# ---------------------------------------------------------------------------
# clock parsing
# ---------------------------------------------------------------------------

def test_clock_to_sec_iso8601():
    assert clock_to_sec("PT08M01.00S") == 481.0
    assert clock_to_sec("PT00M00.00S") == 0.0
    assert clock_to_sec("") == 0.0
    assert clock_to_sec(None) == 0.0


# ---------------------------------------------------------------------------
# fetch wrappers (injected http_get, WAF/error page must degrade to None)
# ---------------------------------------------------------------------------

def test_fetch_boxscore_happy_path():
    payload = json.dumps({"game": _box_game()}).encode("utf-8")
    got = fetch_boxscore("1022600149", http_get=lambda url: payload)
    assert got is not None
    assert got["gameId"] == "1022600149"


def test_fetch_boxscore_waf_html_page_returns_none():
    html = b"<!DOCTYPE html><html>We are unable to process your request</html>"
    assert fetch_boxscore("1022600149", http_get=lambda url: html) is None


def test_fetch_boxscore_network_failure_returns_none():
    assert fetch_boxscore("1022600149", http_get=lambda url: None) is None


def test_fetch_playbyplay_happy_path():
    payload = json.dumps({"game": {"actions": [
        {"actionType": "2pt", "clock": "PT10M00.00S", "period": 1,
         "scoreHome": 2, "scoreAway": 0},
    ]}}).encode("utf-8")
    got = fetch_playbyplay("1022600149", http_get=lambda url: payload)
    assert got is not None
    assert len(got["actions"]) == 1


# ---------------------------------------------------------------------------
# extract_state -- oncourt-exactly-5 guard
# ---------------------------------------------------------------------------

def test_oncourt_exactly_five_reported():
    state = extract_state("g1", _box_game())
    assert state["oncourt_home"] == ["h1", "h2", "h3", "h4", "h5"]
    assert state["oncourt_away"] == ["a1", "a2", "a3", "a4", "a5"]


def test_oncourt_not_five_is_honest_none():
    bad_home = _team(["h1", "h2", "h3", "h4"], score=24)  # only 4 oncourt
    state = extract_state("g1", _box_game(home=bad_home))
    assert state["oncourt_home"] is None
    assert state["oncourt_away"] is not None  # away side unaffected


def test_oncourt_six_oncourt_is_also_honest_none():
    # malformed feed reporting 6 oncourt (e.g. stale sub) -- never silently truncate
    weird_home = _team(["h1", "h2", "h3", "h4", "h5", "h6"], score=24)
    state = extract_state("g1", _box_game(home=weird_home))
    assert state["oncourt_home"] is None


# ---------------------------------------------------------------------------
# bonus / timeout parse
# ---------------------------------------------------------------------------

def test_bonus_and_timeouts_parsed():
    home = _team(["h1", "h2", "h3", "h4", "h5"], in_bonus=1, timeouts=2, score=30)
    state = extract_state("g1", _box_game(home=home))
    assert state["in_bonus_home"] is True
    assert state["in_bonus_away"] is False
    assert state["timeouts_home"] == 2
    assert state["timeouts_away"] == 4


def test_score_extracted():
    state = extract_state("g1", _box_game())
    assert state["score_home"] == 24
    assert state["score_away"] == 24


# ---------------------------------------------------------------------------
# foul trouble flags
# ---------------------------------------------------------------------------

def test_foul_trouble_flag_at_threshold():
    home = _team(["h1", "h2", "h3", "h4", "h5"], score=24,
                  fouls={"h2": FOUL_TROUBLE_THRESHOLD})
    state = extract_state("g1", _box_game(home=home))
    flags = state["foul_trouble_flags"]
    assert any(f["person_id"] == "h2" and f["side"] == "home" for f in flags)


def test_no_foul_trouble_below_threshold():
    home = _team(["h1", "h2", "h3", "h4", "h5"], score=24,
                  fouls={"h2": FOUL_TROUBLE_THRESHOLD - 1})
    state = extract_state("g1", _box_game(home=home))
    assert state["foul_trouble_flags"] == []


def test_bench_player_fouls_never_flagged():
    home = _team(["h1", "h2", "h3", "h4", "h5"], bench_ids=["h6"], score=24,
                  fouls={"h6": 5})
    state = extract_state("g1", _box_game(home=home))
    assert all(f["person_id"] != "h6" for f in state["foul_trouble_flags"])


# ---------------------------------------------------------------------------
# run_last_3min computation on fixture actions
# ---------------------------------------------------------------------------

def _mk_action(period, clock, score_home, score_away, atype="2pt"):
    return {"actionType": atype, "clock": clock, "period": period,
            "scoreHome": score_home, "scoreAway": score_away}


def test_run_last_3min_home_run():
    # period 2, current clock 7:00 remaining (elapsed = 600 + 180 = 780s).
    # Window = [780-180, 780] = [600, 780]. Two scoring actions inside window:
    # elapsed=600 (10:00 rem in Q2) score 10-10, elapsed=780 (7:00 rem) score 18-10.
    actions = [
        _mk_action(2, "PT10M00.00S", 10, 10),
        _mk_action(2, "PT07M00.00S", 18, 10),
    ]
    pbp = {"actions": actions}
    state = extract_state("g1", _box_game(period=2, clock="PT07M00.00S"), pbp)
    assert state["run_last_3min"] == 8.0  # home +8, away +0 => net +8


def test_run_last_3min_none_when_no_actions():
    state = extract_state("g1", _box_game(), pbp_game=None)
    assert state["run_last_3min"] is None


def test_run_last_3min_none_with_single_action_in_window():
    actions = [_mk_action(2, "PT08M01.00S", 24, 24)]
    state = extract_state("g1", _box_game(period=2, clock="PT08M01.00S"),
                           {"actions": actions})
    assert state["run_last_3min"] is None


def test_run_last_3min_away_run_is_negative():
    actions = [
        _mk_action(1, "PT10M00.00S", 0, 0),
        _mk_action(1, "PT07M00.00S", 0, 9),
    ]
    state = extract_state("g1", _box_game(period=1, clock="PT07M00.00S"),
                           {"actions": actions})
    assert state["run_last_3min"] == -9.0


# ---------------------------------------------------------------------------
# sidecar append (best-effort, tmp path)
# ---------------------------------------------------------------------------

def test_append_snapshot_and_sidecar_path(tmp_path, monkeypatch):
    import domains.basketball_wnba.ingame_live_cdn as mod
    monkeypatch.setattr(mod, "SIDECAR_DIR", tmp_path)
    append_snapshot("g1", {"a": 1})
    p = sidecar_path("g1")
    assert p.parent == tmp_path
    assert p.exists()
    line = p.read_text(encoding="utf-8").strip()
    assert json.loads(line)["a"] == 1
