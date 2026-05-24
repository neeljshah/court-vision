"""Tests for scripts/live_game_poll.py — cycle 88a (loop 5).

All tests run offline — nba_api / cdn.nba.com are NEVER hit. We inject
fake fetch_fn / sleep_fn callables so behavior is deterministic and CI-
safe.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.live_game_poll as lgp  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _player(name, *, pid=1001, team="LAL", min_="14:30", pts=12, reb=4,
            ast=3, fg3m=2, stl=1, blk=0, tov=1, pf=2, starter=True):
    """Mimic a single cdn.nba.com `game.<side>Team.players[i]` entry."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,
        "statistics": {
            "minutes":               f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":                pts,
            "reboundsTotal":         reb,
            "assists":               ast,
            "threePointersMade":     fg3m,
            "steals":                stl,
            "blocks":                blk,
            "turnovers":             tov,
            "foulsPersonal":         pf,
        },
    }


def _fixture_payload(*, game_id="0022400123", status=2, period=2,
                      clock="PT05M42.00S", home_score=56, away_score=48):
    """Build a fake cdn.nba.com boxscore payload."""
    return {
        "game": {
            "gameId":     game_id,
            "gameStatus": status,
            "period":     period,
            "gameClock":  clock,
            "homeTeam": {
                "teamTricode": "LAL",
                "score":       home_score,
                "players": [
                    _player("LeBron James",  pid=2544, team="LAL",
                            pts=22, reb=8, ast=9),
                    _player("Anthony Davis", pid=203076, team="LAL",
                            pts=18, reb=10, ast=2, starter=True),
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    _player("Nikola Jokic", pid=203999, team="DEN",
                            pts=20, reb=11, ast=8, starter=True),
                    _player("Reggie Jackson", pid=202704, team="DEN",
                            min_="6:15", pts=4, reb=1, ast=2, starter=False),
                ],
            },
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Parsing tests
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_boxscore_payload_canonical_schema():
    """Parsed snapshot has all required top-level keys + correct status mapping."""
    payload = _fixture_payload(status=2, period=2, clock="PT05M42.00S",
                                 home_score=56, away_score=48)
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-05-24T19:42:18+00:00")

    # Top-level keys present
    expected_keys = {"game_id", "captured_at", "game_status", "period", "clock",
                     "home_team", "away_team", "home_score", "away_score", "players"}
    assert expected_keys.issubset(snap.keys())

    # Status code 2 → LIVE
    assert snap["game_status"] == "LIVE"
    assert snap["period"] == 2
    assert snap["clock"] == "5:42"
    assert snap["home_team"] == "LAL"
    assert snap["away_team"] == "DEN"
    assert snap["home_score"] == 56
    assert snap["away_score"] == 48
    assert snap["captured_at"] == "2026-05-24T19:42:18+00:00"

    # 4 players total (2 per team)
    assert len(snap["players"]) == 4
    by_name = {p["name"]: p for p in snap["players"]}
    jokic = by_name["Nikola Jokic"]
    assert jokic["player_id"] == 203999
    assert jokic["team"] == "DEN"
    assert jokic["pts"] == 20
    assert jokic["reb"] == 11
    assert jokic["ast"] == 8
    assert jokic["is_starter"] is True
    assert jokic["min"] == pytest.approx(14.5)  # 14:30 → 14.5

    reggie = by_name["Reggie Jackson"]
    assert reggie["is_starter"] is False
    assert reggie["min"] == pytest.approx(6.25)


def test_parse_status_codes_map_to_canonical_strings():
    """Status codes 1/2/3 must map to PRE_GAME/LIVE/FINAL."""
    for status_int, expected in [(1, "PRE_GAME"), (2, "LIVE"), (3, "FINAL")]:
        snap = lgp.parse_boxscore_payload(_fixture_payload(status=status_int))
        assert snap["game_status"] == expected, f"status {status_int}"


def test_parse_handles_empty_payload():
    """Malformed / empty payload doesn't crash, returns empty defaults."""
    snap = lgp.parse_boxscore_payload({})
    assert snap["players"] == []
    assert snap["game_id"] == ""
    assert snap["game_status"] == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot path / persistence tests
# ─────────────────────────────────────────────────────────────────────────────

def test_snapshot_path_includes_timestamp(tmp_path):
    """Two snapshots for the same game_id at different times → distinct paths."""
    gid = "0022400123"
    p1 = lgp.snapshot_path(gid, captured_at="2026-05-24T19:42:18+00:00",
                            live_dir=str(tmp_path))
    p2 = lgp.snapshot_path(gid, captured_at="2026-05-24T19:42:48+00:00",
                            live_dir=str(tmp_path))
    assert p1 != p2
    assert gid in os.path.basename(p1)
    assert gid in os.path.basename(p2)
    assert p1.endswith(".json") and p2.endswith(".json")


def test_write_snapshot_round_trip(tmp_path):
    """Snapshot written to disk reads back identically."""
    snap = lgp.parse_boxscore_payload(
        _fixture_payload(), captured_at="2026-05-24T19:42:18+00:00")
    path = lgp.write_snapshot(snap, live_dir=str(tmp_path))
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded == snap


# ─────────────────────────────────────────────────────────────────────────────
# Polling logic tests
# ─────────────────────────────────────────────────────────────────────────────

def test_poll_once_writes_one_snapshot_per_game(tmp_path):
    """--once: each game id gets exactly one snapshot file."""
    fetch_fn = MagicMock(side_effect=[
        _fixture_payload(game_id="0022400123"),
        _fixture_payload(game_id="0022400124", home_score=99, away_score=101),
    ])
    sleep_fn = MagicMock()
    results = lgp.poll_once(
        ["0022400123", "0022400124"],
        fetch_fn=fetch_fn, sleep_fn=sleep_fn,
        api_sleep=0.6, live_dir=str(tmp_path),
    )
    assert set(results.keys()) == {"0022400123", "0022400124"}
    files = sorted(os.listdir(tmp_path))
    assert len(files) == 2
    # Both filenames begin with their respective game_ids
    assert any(f.startswith("0022400123_") for f in files)
    assert any(f.startswith("0022400124_") for f in files)


def test_poll_once_rate_limit_sleep_between_calls(tmp_path):
    """Politeness: sleep is invoked between game fetches with _API_SLEEP arg."""
    fetch_fn = MagicMock(side_effect=[
        _fixture_payload(game_id="g1"),
        _fixture_payload(game_id="g2"),
        _fixture_payload(game_id="g3"),
    ])
    sleep_fn = MagicMock()
    lgp.poll_once(["g1", "g2", "g3"],
                   fetch_fn=fetch_fn, sleep_fn=sleep_fn,
                   api_sleep=0.6, live_dir=str(tmp_path))
    # 3 games → sleep called twice (between game 1→2 and 2→3, not before #1).
    assert sleep_fn.call_count == 2
    for call in sleep_fn.call_args_list:
        assert call.args == (0.6,)


def test_poll_daemon_drops_final_games_on_next_tick(tmp_path):
    """A FINAL game should not be polled again on the subsequent tick."""
    # Tick 1: both games LIVE
    # Tick 2: game1 still LIVE, game2 FINAL
    # Tick 3: game1 FINAL (then loop exits)
    payloads = {
        "g1": [
            _fixture_payload(game_id="g1", status=2),
            _fixture_payload(game_id="g1", status=2),
            _fixture_payload(game_id="g1", status=3),
        ],
        "g2": [
            _fixture_payload(game_id="g2", status=2),
            _fixture_payload(game_id="g2", status=3),
            # No 3rd payload — if poller calls again, side_effect raises.
        ],
    }
    call_counts = {"g1": 0, "g2": 0}

    def fake_fetch(gid):
        idx = call_counts[gid]
        call_counts[gid] += 1
        return payloads[gid][idx]

    ticks = lgp.poll_daemon(
        ["g1", "g2"], interval=0.0,
        fetch_fn=fake_fetch, sleep_fn=lambda _s: None,
        api_sleep=0.0, live_dir=str(tmp_path),
        max_ticks=10,
    )
    # g2 should be polled only 2 times (LIVE then FINAL), not 3.
    assert call_counts["g2"] == 2
    # g1 polled 3 times (LIVE, LIVE, FINAL).
    assert call_counts["g1"] == 3
    # Total of 3 ticks: both finished by then.
    assert ticks == 3


def test_poll_once_skips_games_with_no_payload(tmp_path):
    """If a CDN call returns {} (game not yet posted), skip writing."""
    fetch_fn = MagicMock(side_effect=[
        _fixture_payload(game_id="g1"),
        {},  # game not yet live
    ])
    results = lgp.poll_once(
        ["g1", "g2"], fetch_fn=fetch_fn,
        sleep_fn=lambda _s: None, api_sleep=0.0, live_dir=str(tmp_path),
    )
    assert "g1" in results
    assert "g2" not in results
    files = os.listdir(tmp_path)
    assert len(files) == 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI / main tests
# ─────────────────────────────────────────────────────────────────────────────

def test_main_once_exits_after_single_pass(monkeypatch, tmp_path):
    """`--once` exits with 0 after one pass and writes one file."""
    monkeypatch.setattr(lgp, "_LIVE_DIR", str(tmp_path))
    monkeypatch.setattr(lgp, "discover_games_for_today",
                        lambda date=None: ["0022400123"])
    monkeypatch.setattr(lgp, "fetch_live_boxscore",
                        lambda gid, **kw: _fixture_payload(game_id=gid))
    monkeypatch.setattr(sys, "argv",
                        ["live_game_poll.py", "--once"])
    rc = lgp.main()
    assert rc == 0
    files = os.listdir(tmp_path)
    assert len(files) == 1
    assert files[0].startswith("0022400123_")


def test_main_no_games_returns_zero(monkeypatch):
    """Empty slate is a clean exit, not an error."""
    monkeypatch.setattr(lgp, "discover_games_for_today",
                        lambda date=None: [])
    monkeypatch.setattr(sys, "argv", ["live_game_poll.py", "--once"])
    assert lgp.main() == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
