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


# ─────────────────────────────────────────────────────────────────────────────
# CV_SNAP_FF — W-001 four-factor capture tests
# ─────────────────────────────────────────────────────────────────────────────

def _player_with_ff(name, *, pid=1001, team="LAL", min_="14:30", pts=12, reb=4,
                    ast=3, fg3m=2, stl=1, blk=0, tov=1, pf=2, starter=True,
                    fga=10, fgm=5, fg3a=4, fta=3, ftm=2):
    """Player fixture that includes four-factor CDN fields."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,
        "statistics": {
            "minutes":                  f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":                   pts,
            "reboundsTotal":            reb,
            "assists":                  ast,
            "threePointersMade":        fg3m,
            "steals":                   stl,
            "blocks":                   blk,
            "turnovers":                tov,
            "foulsPersonal":            pf,
            # four-factor CDN fields
            "fieldGoalsAttempted":      fga,
            "fieldGoalsMade":           fgm,
            "threePointersAttempted":   fg3a,
            "freeThrowsAttempted":      fta,
            "freeThrowsMade":           ftm,
        },
    }


def _fixture_payload_ff(*, game_id="0022400123", status=2, period=2,
                         clock="PT05M42.00S", home_score=56, away_score=48):
    """Build a fake CDN boxscore payload that includes four-factor CDN fields."""
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
                    _player_with_ff("LeBron James",  pid=2544,   team="LAL",
                                    pts=22, reb=8, ast=9,
                                    fga=16, fgm=9, fg3a=4, fta=5, ftm=4),
                    _player_with_ff("Anthony Davis", pid=203076, team="LAL",
                                    pts=18, reb=10, ast=2,
                                    fga=12, fgm=7, fg3a=0, fta=6, ftm=4),
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    _player_with_ff("Nikola Jokic",    pid=203999, team="DEN",
                                    pts=20, reb=11, ast=8,
                                    fga=14, fgm=8, fg3a=2, fta=7, ftm=6),
                    _player_with_ff("Reggie Jackson",  pid=202704, team="DEN",
                                    min_="6:15", pts=4, reb=1, ast=2,
                                    starter=False,
                                    fga=5, fgm=2, fg3a=3, fta=1, ftm=1),
                ],
            },
        }
    }


def test_snap_ff_flag_off_byte_identical(monkeypatch):
    """CV_SNAP_FF=OFF: snapshot keys and values MUST be byte-identical to baseline.

    'Byte-identical' means the player dicts have exactly the same keys as
    before — no fga/fgm/fg3a/fta/ftm, no schema_version.
    """
    monkeypatch.setattr(lgp, "_SNAP_FF", False)
    payload = _fixture_payload_ff()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    # Top-level schema: no schema_version
    assert "schema_version" not in snap

    # Baseline player keys (must be exactly these — no extras)
    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        assert set(p.keys()) == _BASELINE_PLAYER_KEYS, (
            f"Player {p['name']!r} has unexpected keys: "
            f"{set(p.keys()) - _BASELINE_PLAYER_KEYS}"
        )


def test_snap_ff_flag_on_new_fields_present_and_non_null(monkeypatch):
    """CV_SNAP_FF=ON: fga/fgm/fg3a/fta/ftm present and non-null on every player row."""
    monkeypatch.setattr(lgp, "_SNAP_FF", True)
    payload = _fixture_payload_ff()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    assert snap.get("schema_version") == "live-snapshot-2"

    _FF_KEYS = ("fga", "fgm", "fg3a", "fta", "ftm")
    for p in snap["players"]:
        for k in _FF_KEYS:
            assert k in p, f"Player {p['name']!r} missing key {k!r}"
            assert p[k] is not None, f"Player {p['name']!r} key {k!r} is None"
            assert isinstance(p[k], int), (
                f"Player {p['name']!r} key {k!r} should be int, got {type(p[k])}"
            )


def test_snap_ff_fga_ge_fgm_sanity(monkeypatch):
    """CV_SNAP_FF=ON: fga >= fgm for every player (attempted >= made)."""
    monkeypatch.setattr(lgp, "_SNAP_FF", True)
    payload = _fixture_payload_ff()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")
    for p in snap["players"]:
        assert p["fga"] >= p["fgm"], (
            f"Player {p['name']!r}: fga={p['fga']} < fgm={p['fgm']} (impossible)"
        )


def test_snap_ff_team_sum_sanity(monkeypatch):
    """CV_SNAP_FF=ON: team-summed fga/fgm for home/away match the fixture values."""
    monkeypatch.setattr(lgp, "_SNAP_FF", True)
    payload = _fixture_payload_ff()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    home_players = [p for p in snap["players"] if p["team"] == "LAL"]
    away_players = [p for p in snap["players"] if p["team"] == "DEN"]

    # Home: LeBron fga=16 + AD fga=12 = 28; fgm=9+7=16
    assert sum(p["fga"] for p in home_players) == 28
    assert sum(p["fgm"] for p in home_players) == 16

    # Away: Jokic fga=14 + Jackson fga=5 = 19; fgm=8+2=10
    assert sum(p["fga"] for p in away_players) == 19
    assert sum(p["fgm"] for p in away_players) == 10

    # All away players: fga >= fgm (team-level sanity)
    for p in snap["players"]:
        assert p["fga"] >= p["fgm"]


def test_snap_ff_flag_on_baseline_keys_still_present(monkeypatch):
    """CV_SNAP_FF=ON: existing baseline keys (pts, reb, ast, …) are unaffected."""
    monkeypatch.setattr(lgp, "_SNAP_FF", True)
    payload = _fixture_payload_ff()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        missing = _BASELINE_PLAYER_KEYS - set(p.keys())
        assert not missing, (
            f"Player {p['name']!r} missing baseline keys: {missing}"
        )


def test_snap_ff_missing_cdn_fields_default_to_zero(monkeypatch):
    """CV_SNAP_FF=ON: if CDN omits four-factor fields, they default to 0 (not crash)."""
    monkeypatch.setattr(lgp, "_SNAP_FF", True)
    # Use the baseline fixture (no fieldGoalsAttempted etc in statistics)
    payload = _fixture_payload()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")
    for p in snap["players"]:
        for k in ("fga", "fgm", "fg3a", "fta", "ftm"):
            assert p[k] == 0, (
                f"Expected 0 for missing CDN field {k!r} on {p['name']!r}, "
                f"got {p[k]}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# CV_SNAP_ONCOURT — W-002 on-court 5-man lineup capture tests
# ─────────────────────────────────────────────────────────────────────────────

def _player_with_oncourt(name, *, pid=1001, team="LAL", min_="14:30", pts=12,
                         reb=4, ast=3, fg3m=2, stl=1, blk=0, tov=1, pf=2,
                         starter=True, oncourt=False):
    """Player fixture that includes the CDN `oncourt` field."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,
        "oncourt":   oncourt,
        "statistics": {
            "minutes":           f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":            pts,
            "reboundsTotal":     reb,
            "assists":           ast,
            "threePointersMade": fg3m,
            "steals":            stl,
            "blocks":            blk,
            "turnovers":         tov,
            "foulsPersonal":     pf,
        },
    }


def _fixture_payload_oncourt(*, game_id="0022400123", status=2, period=2,
                              clock="PT05M42.00S", home_score=56, away_score=48):
    """CDN payload that includes `oncourt` on 5 home + 5 away players.

    A realistic mid-game snapshot: 5 starters per side oncourt=True, benched
    players oncourt=False.  Total oncourt_true = 10 across 12 players.
    """
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
                    _player_with_oncourt("LeBron James",    pid=2544,   team="LAL",
                                         pts=22, reb=8,  ast=9,  oncourt=True),
                    _player_with_oncourt("Anthony Davis",   pid=203076, team="LAL",
                                         pts=18, reb=10, ast=2,  oncourt=True),
                    _player_with_oncourt("D'Angelo Russell", pid=1626156, team="LAL",
                                         pts=10, reb=2,  ast=5,  oncourt=True),
                    _player_with_oncourt("Austin Reaves",   pid=1629750, team="LAL",
                                         pts=8,  reb=2,  ast=3,  oncourt=True),
                    _player_with_oncourt("Rui Hachimura",   pid=1629060, team="LAL",
                                         pts=6,  reb=3,  ast=1,  oncourt=True),
                    _player_with_oncourt("Taurean Prince",  pid=1627752, team="LAL",
                                         pts=2,  reb=1,  ast=0,  starter=False,
                                         oncourt=False),
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    _player_with_oncourt("Nikola Jokic",    pid=203999, team="DEN",
                                         pts=20, reb=11, ast=8,  oncourt=True),
                    _player_with_oncourt("Jamal Murray",    pid=1628384, team="DEN",
                                         pts=14, reb=3,  ast=7,  oncourt=True),
                    _player_with_oncourt("Michael Porter",  pid=1629008, team="DEN",
                                         pts=12, reb=5,  ast=1,  oncourt=True),
                    _player_with_oncourt("Aaron Gordon",    pid=203932, team="DEN",
                                         pts=8,  reb=4,  ast=2,  oncourt=True),
                    _player_with_oncourt("Kentavious Pope", pid=203082, team="DEN",
                                         pts=6,  reb=1,  ast=2,  oncourt=True),
                    _player_with_oncourt("Reggie Jackson",  pid=202704, team="DEN",
                                         min_="6:15", pts=4, reb=1, ast=2,
                                         starter=False, oncourt=False),
                ],
            },
        }
    }


def test_snap_oncourt_flag_off_byte_identical(monkeypatch):
    """CV_SNAP_ONCOURT=OFF: snapshot player dicts must NOT contain `oncourt` key.

    The serve path is byte-identical when the flag is unset — no new keys
    appear, regardless of whether the CDN payload carries `oncourt`.
    """
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", False)
    payload = _fixture_payload_oncourt()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    # Baseline player keys (must be exactly these — no extras beyond the
    # standard set; do NOT include oncourt).
    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        assert "oncourt" not in p, (
            f"Player {p['name']!r} should NOT have `oncourt` when flag is OFF"
        )
        assert set(p.keys()) == _BASELINE_PLAYER_KEYS, (
            f"Player {p['name']!r} has unexpected keys: "
            f"{set(p.keys()) - _BASELINE_PLAYER_KEYS}"
        )


def test_snap_oncourt_flag_on_field_present_and_bool(monkeypatch):
    """CV_SNAP_ONCOURT=ON: every player row has `oncourt` as a bool."""
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", True)
    payload = _fixture_payload_oncourt()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    for p in snap["players"]:
        assert "oncourt" in p, f"Player {p['name']!r} missing `oncourt` key"
        assert isinstance(p["oncourt"], bool), (
            f"Player {p['name']!r}: oncourt should be bool, got {type(p['oncourt'])}"
        )


def test_snap_oncourt_midgame_8_to_12_oncourt_true(monkeypatch):
    """CV_SNAP_ONCOURT=ON: mid-game snapshot must have 8–12 oncourt=True players.

    The CDN reports oncourt=True for the 10 players currently on the floor
    (5 per side).  The acceptance criterion is 8–12 oncourt:true (handles
    any momentary substitution or ejection edge cases).
    """
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", True)
    payload = _fixture_payload_oncourt()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    n_oncourt = sum(1 for p in snap["players"] if p["oncourt"])
    assert 8 <= n_oncourt <= 12, (
        f"Expected 8–12 oncourt=True players mid-game, got {n_oncourt}"
    )


def test_snap_oncourt_values_match_cdn_payload(monkeypatch):
    """CV_SNAP_ONCOURT=ON: parsed oncourt value matches what the CDN sent."""
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", True)
    payload = _fixture_payload_oncourt()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    # Starters marked oncourt=True in the fixture
    assert by_name["LeBron James"]["oncourt"] is True
    assert by_name["Nikola Jokic"]["oncourt"] is True
    # Bench players marked oncourt=False
    assert by_name["Taurean Prince"]["oncourt"] is False
    assert by_name["Reggie Jackson"]["oncourt"] is False


def test_snap_oncourt_fallback_false_when_cdn_field_absent(monkeypatch):
    """CV_SNAP_ONCOURT=ON: if CDN omits `oncourt`, field defaults to False."""
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", True)
    # Use the baseline fixture (no `oncourt` field in player dicts)
    payload = _fixture_payload()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")
    for p in snap["players"]:
        assert "oncourt" in p, f"Player {p['name']!r} missing `oncourt` key"
        assert p["oncourt"] is False, (
            f"Player {p['name']!r}: expected oncourt=False when CDN field absent, "
            f"got {p['oncourt']}"
        )


def test_snap_oncourt_baseline_keys_still_present_when_on(monkeypatch):
    """CV_SNAP_ONCOURT=ON: existing baseline keys (pts, reb, ast, …) unaffected."""
    monkeypatch.setattr(lgp, "_SNAP_ONCOURT", True)
    payload = _fixture_payload_oncourt()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        missing = _BASELINE_PLAYER_KEYS - set(p.keys())
        assert not missing, (
            f"Player {p['name']!r} missing baseline keys: {missing}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CV_SNAP_REBSPLIT — W-003 oreb/dreb split + pf non-null capture tests
# ─────────────────────────────────────────────────────────────────────────────

def _player_with_rebsplit(name, *, pid=1001, team="LAL", min_="14:30", pts=12,
                           reb=4, oreb=1, dreb=3, ast=3, fg3m=2, stl=1, blk=0,
                           tov=1, pf=2, starter=True):
    """Player fixture that includes CDN reboundsOffensive / reboundsDefensive."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,
        "statistics": {
            "minutes":               f"PT{min_.split(':')[0]}M{min_.split(':')[1]}.00S",
            "points":                pts,
            "reboundsTotal":         reb,
            "reboundsOffensive":     oreb,
            "reboundsDefensive":     dreb,
            "assists":               ast,
            "threePointersMade":     fg3m,
            "steals":                stl,
            "blocks":                blk,
            "turnovers":             tov,
            "foulsPersonal":         pf,
        },
    }


def _fixture_payload_rebsplit(*, game_id="0022400123", status=2, period=2,
                               clock="PT05M42.00S", home_score=56, away_score=48):
    """CDN payload that includes reboundsOffensive / reboundsDefensive."""
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
                    _player_with_rebsplit("LeBron James",  pid=2544,   team="LAL",
                                          pts=22, reb=8,  oreb=2, dreb=6, ast=9, pf=1),
                    _player_with_rebsplit("Anthony Davis", pid=203076, team="LAL",
                                          pts=18, reb=10, oreb=3, dreb=7, ast=2, pf=3),
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    _player_with_rebsplit("Nikola Jokic",   pid=203999, team="DEN",
                                          pts=20, reb=11, oreb=4, dreb=7, ast=8, pf=2),
                    _player_with_rebsplit("Reggie Jackson", pid=202704, team="DEN",
                                          min_="6:15", pts=4, reb=1, oreb=0, dreb=1,
                                          ast=2, pf=0, starter=False),
                ],
            },
        }
    }


def test_snap_rebsplit_flag_off_byte_identical(monkeypatch):
    """CV_SNAP_REBSPLIT=OFF: player dicts must NOT contain `oreb` or `dreb` keys.

    Serve path is byte-identical when the flag is unset — new keys must not
    appear even when the CDN payload carries reboundsOffensive/reboundsDefensive.
    """
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", False)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        assert "oreb" not in p, (
            f"Player {p['name']!r} should NOT have `oreb` when flag is OFF"
        )
        assert "dreb" not in p, (
            f"Player {p['name']!r} should NOT have `dreb` when flag is OFF"
        )
        assert set(p.keys()) == _BASELINE_PLAYER_KEYS, (
            f"Player {p['name']!r} has unexpected keys: "
            f"{set(p.keys()) - _BASELINE_PLAYER_KEYS}"
        )


def test_snap_rebsplit_flag_on_fields_present_and_non_null(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: oreb and dreb are present and non-null on every player."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    for p in snap["players"]:
        assert "oreb" in p, f"Player {p['name']!r} missing `oreb` key"
        assert "dreb" in p, f"Player {p['name']!r} missing `dreb` key"
        assert p["oreb"] is not None, f"Player {p['name']!r}: oreb is None"
        assert p["dreb"] is not None, f"Player {p['name']!r}: dreb is None"
        assert isinstance(p["oreb"], int), (
            f"Player {p['name']!r}: oreb should be int, got {type(p['oreb'])}"
        )
        assert isinstance(p["dreb"], int), (
            f"Player {p['name']!r}: dreb should be int, got {type(p['dreb'])}"
        )


def test_snap_rebsplit_oreb_plus_dreb_equals_reb(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: oreb+dreb==reb for every player (CDN invariant)."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    for p in snap["players"]:
        assert p["oreb"] + p["dreb"] == p["reb"], (
            f"Player {p['name']!r}: oreb({p['oreb']})+dreb({p['dreb']}) "
            f"!= reb({p['reb']})"
        )


def test_snap_rebsplit_values_match_cdn_payload(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: parsed oreb/dreb match the CDN fixture values."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    # LeBron: oreb=2, dreb=6, reb=8
    assert by_name["LeBron James"]["oreb"] == 2
    assert by_name["LeBron James"]["dreb"] == 6
    assert by_name["LeBron James"]["reb"] == 8
    # Jokic: oreb=4, dreb=7, reb=11
    assert by_name["Nikola Jokic"]["oreb"] == 4
    assert by_name["Nikola Jokic"]["dreb"] == 7
    assert by_name["Nikola Jokic"]["reb"] == 11
    # Reggie Jackson: zero oreb, dreb=1, reb=1
    assert by_name["Reggie Jackson"]["oreb"] == 0
    assert by_name["Reggie Jackson"]["dreb"] == 1
    assert by_name["Reggie Jackson"]["reb"] == 1


def test_snap_rebsplit_missing_cdn_fields_default_to_zero(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: if CDN omits oreb/dreb fields they default to 0, no crash."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    # Use baseline fixture which has no reboundsOffensive/reboundsDefensive in statistics
    payload = _fixture_payload()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")
    for p in snap["players"]:
        assert p["oreb"] == 0, (
            f"Expected 0 for missing oreb on {p['name']!r}, got {p['oreb']}"
        )
        assert p["dreb"] == 0, (
            f"Expected 0 for missing dreb on {p['name']!r}, got {p['dreb']}"
        )


def test_snap_rebsplit_pf_non_null_in_baseline(monkeypatch):
    """pf (foulsPersonal) must always be non-null in the baseline schema.

    The W-003 sketch notes that `pf` is already parsed from `foulsPersonal` at
    row construction time — it should never be None even when the flag is OFF,
    because _safe_int defaults to 0 when the CDN field is absent.
    """
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", False)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    for p in snap["players"]:
        assert p["pf"] is not None, (
            f"Player {p['name']!r}: pf is None (must always be non-null)"
        )
        assert isinstance(p["pf"], int), (
            f"Player {p['name']!r}: pf should be int, got {type(p['pf'])}"
        )
        assert p["pf"] >= 0, f"Player {p['name']!r}: pf={p['pf']} is negative"


def test_snap_rebsplit_pf_correct_values(monkeypatch):
    """pf values from the CDN are correctly parsed into the baseline row."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", False)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    assert by_name["LeBron James"]["pf"] == 1
    assert by_name["Anthony Davis"]["pf"] == 3
    assert by_name["Nikola Jokic"]["pf"] == 2
    assert by_name["Reggie Jackson"]["pf"] == 0


def test_snap_rebsplit_baseline_keys_still_present_when_on(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: existing baseline keys (pts, reb, pf, …) are unaffected."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        missing = _BASELINE_PLAYER_KEYS - set(p.keys())
        assert not missing, (
            f"Player {p['name']!r} missing baseline keys: {missing}"
        )


def test_snap_rebsplit_oreb_dreb_non_negative(monkeypatch):
    """CV_SNAP_REBSPLIT=ON: oreb and dreb are always >= 0 (count stats)."""
    monkeypatch.setattr(lgp, "_SNAP_REBSPLIT", True)
    payload = _fixture_payload_rebsplit()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    for p in snap["players"]:
        assert p["oreb"] >= 0, f"Player {p['name']!r}: oreb={p['oreb']} is negative"
        assert p["dreb"] >= 0, f"Player {p['name']!r}: dreb={p['dreb']} is negative"


# ─────────────────────────────────────────────────────────────────────────────
# CV_SNAP_STARTER_FIX — W-004 is_starter all-true parse bug fix tests
# ─────────────────────────────────────────────────────────────────────────────

def _player_with_starter_str(name, *, pid=1001, team="LAL", min_="14:30", pts=12,
                              reb=4, ast=3, fg3m=2, stl=1, blk=0, tov=1, pf=2,
                              starter="1"):
    """Player fixture that uses CDN-realistic string "1"/"0" for the starter field."""
    return {
        "personId":  pid,
        "name":      name,
        "starter":   starter,  # CDN sends string "1" or "0", NOT a Python bool
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


def _fixture_payload_starter_str(*, game_id="0022400123", status=2, period=2,
                                  clock="PT05M42.00S", home_score=56, away_score=48):
    """CDN payload where starter is a string "1"/"0" (realistic CDN format).

    Home team: 5 starters (starter="1") + 1 bench (starter="0") = 6 players.
    Away team: 5 starters (starter="1") + 1 bench (starter="0") = 6 players.
    Total: 12 players, 10 starters, 2 bench.
    """
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
                    _player_with_starter_str("LeBron James",   pid=2544,    starter="1"),
                    _player_with_starter_str("Anthony Davis",  pid=203076,  starter="1"),
                    _player_with_starter_str("DAngelo Russell",pid=1626156, starter="1"),
                    _player_with_starter_str("Austin Reaves",  pid=1629750, starter="1"),
                    _player_with_starter_str("Rui Hachimura",  pid=1629060, starter="1"),
                    _player_with_starter_str("Taurean Prince", pid=1627752,
                                              min_="6:00", pts=2, reb=1, ast=0,
                                              starter="0"),  # bench
                ],
            },
            "awayTeam": {
                "teamTricode": "DEN",
                "score":       away_score,
                "players": [
                    _player_with_starter_str("Nikola Jokic",    pid=203999,  starter="1"),
                    _player_with_starter_str("Jamal Murray",    pid=1628384, starter="1"),
                    _player_with_starter_str("Michael Porter",  pid=1629008, starter="1"),
                    _player_with_starter_str("Aaron Gordon",    pid=203932,  starter="1"),
                    _player_with_starter_str("Kentavious Pope", pid=203082,  starter="1"),
                    _player_with_starter_str("Reggie Jackson",  pid=202704,
                                              min_="6:15", pts=4, reb=1, ast=2,
                                              starter="0"),  # bench
                ],
            },
        }
    }


def test_snap_starter_fix_flag_off_byte_identical_with_string_starter(monkeypatch):
    """CV_SNAP_STARTER_FIX=OFF: output is byte-identical to the old (buggy) behavior.

    When the flag is OFF, bool("0") == True — so bench players are incorrectly
    flagged as starters.  This test asserts that behavior is preserved when OFF
    (backward compat / byte-identical requirement).
    """
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", False)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    # With the bug (flag OFF), string "0" → bool("0") == True, so ALL players
    # including bench are flagged as starters.
    n_starter = sum(1 for p in snap["players"] if p["is_starter"])
    assert n_starter == 12, (
        f"Flag-OFF (bug-preserved) path: expected ALL 12 players flagged starter "
        f"due to bool('0')==True, got {n_starter}"
    )


def test_snap_starter_fix_flag_on_string_one_is_starter(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: starter='1' → is_starter=True."""
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    assert by_name["LeBron James"]["is_starter"] is True
    assert by_name["Nikola Jokic"]["is_starter"] is True


def test_snap_starter_fix_flag_on_string_zero_is_not_starter(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: starter='0' → is_starter=False (the core bug fix)."""
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    assert by_name["Taurean Prince"]["is_starter"] is False, (
        "bench player with starter='0' must have is_starter=False when fix is ON"
    )
    assert by_name["Reggie Jackson"]["is_starter"] is False, (
        "bench player with starter='0' must have is_starter=False when fix is ON"
    )


def test_snap_starter_fix_n_starter_assertion_2_to_12(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: 2 <= n_starter <= 12 per game (acceptance criterion).

    With 12 players (6/side), 10 starters and 2 bench: n_starter==10, within [2, 12].
    """
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    n_starter = sum(1 for p in snap["players"] if p["is_starter"])
    assert 2 <= n_starter <= 12, (
        f"Expected 2<=n_starter<=12 (acceptance criterion), got {n_starter}"
    )


def test_snap_starter_fix_approx_5_per_side(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: ~5 starters per side."""
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    home = [p for p in snap["players"] if p["team"] == "LAL"]
    away = [p for p in snap["players"] if p["team"] == "DEN"]
    home_starters = sum(1 for p in home if p["is_starter"])
    away_starters = sum(1 for p in away if p["is_starter"])
    # Exactly 5 starters per side in the fixture
    assert home_starters == 5, f"Expected 5 LAL starters, got {home_starters}"
    assert away_starters == 5, f"Expected 5 DEN starters, got {away_starters}"


def test_snap_starter_fix_native_bool_still_works(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: native bool True/False values also parse correctly.

    Some CDN variants or test fixtures pass Python bool directly (not string).
    The fix must handle both cases.
    """
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    # Use the original fixture which passes Python booleans (True/False)
    payload = _fixture_payload()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    by_name = {p["name"]: p for p in snap["players"]}
    # Reggie Jackson has starter=False (native bool) in the baseline fixture
    assert by_name["Reggie Jackson"]["is_starter"] is False
    assert by_name["Nikola Jokic"]["is_starter"] is True


def test_snap_starter_fix_none_starter_field_defaults_false(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: missing/None starter field → is_starter=False."""
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    # Inject a player dict with no 'starter' key at all
    payload = {
        "game": {
            "gameId": "0022400123",
            "gameStatus": 2,
            "period": 2,
            "gameClock": "PT05M42.00S",
            "homeTeam": {
                "teamTricode": "LAL",
                "score": 56,
                "players": [
                    {
                        "personId": 9999,
                        "name": "Mystery Player",
                        # no 'starter' key at all
                        "statistics": {
                            "minutes": "PT10M00.00S",
                            "points": 5,
                            "reboundsTotal": 2,
                            "assists": 1,
                            "threePointersMade": 0,
                            "steals": 0,
                            "blocks": 0,
                            "turnovers": 0,
                            "foulsPersonal": 1,
                        },
                    }
                ],
            },
            "awayTeam": {"teamTricode": "DEN", "score": 48, "players": []},
        }
    }
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")
    assert snap["players"][0]["is_starter"] is False, (
        "Missing starter field should default to False when fix is ON"
    )


def test_snap_starter_fix_baseline_keys_unchanged(monkeypatch):
    """CV_SNAP_STARTER_FIX=ON: is_starter still present; no extra keys added."""
    monkeypatch.setattr(lgp, "_SNAP_STARTER_FIX", True)
    payload = _fixture_payload_starter_str()
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-03T00:00:00+00:00")

    _BASELINE_PLAYER_KEYS = {
        "player_id", "name", "team", "min",
        "pts", "reb", "ast", "fg3m",
        "stl", "blk", "tov", "pf", "is_starter",
    }
    for p in snap["players"]:
        assert set(p.keys()) == _BASELINE_PLAYER_KEYS, (
            f"Player {p['name']!r} has unexpected keys: "
            f"{set(p.keys()) - _BASELINE_PLAYER_KEYS}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CV_MARGIN_SERIES — W-031 per-snapshot margin time-series tests
# ─────────────────────────────────────────────────────────────────────────────

def test_margin_series_flag_off_is_byte_identical(monkeypatch, tmp_path):
    """CV_MARGIN_SERIES=OFF: poll_once return dict identical to baseline; no JSONL written."""
    monkeypatch.setattr(lgp, "_MARGIN_SERIES", False)
    fetch_fn = MagicMock(side_effect=[_fixture_payload(game_id="0022400123")])
    cache_dir = str(tmp_path / "cache")
    results = lgp.poll_once(
        ["0022400123"],
        fetch_fn=fetch_fn,
        sleep_fn=lambda _s: None,
        api_sleep=0.0,
        live_dir=str(tmp_path / "live"),
        cache_dir=cache_dir,
    )
    # Snapshot return dict unchanged
    snap = results["0022400123"]
    assert "margin" not in snap, "margin key must NOT appear in snapshot when flag OFF"
    assert "home_score" in snap
    # No series file written
    import os as _os
    if _os.path.exists(cache_dir):
        series_files = [f for f in _os.listdir(cache_dir) if f.startswith("margin_series_")]
        assert series_files == [], f"Unexpected series files with flag OFF: {series_files}"


def test_margin_series_append_writes_record(tmp_path):
    """append_margin_series writes one valid JSON line to the JSONL file."""
    snap = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="0042500401", home_score=64, away_score=57,
                         period=2, clock="PT05M42.00S"),
        captured_at="2026-06-04T01:00:00+00:00",
    )
    cache_dir = str(tmp_path)
    path = lgp.append_margin_series(snap, cache_dir=cache_dir)

    assert path == lgp.margin_series_path("0042500401", cache_dir=cache_dir)
    assert os.path.exists(path)

    with open(path, encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if l.strip()]
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["captured_at"] == "2026-06-04T01:00:00+00:00"
    assert record["period"] == 2
    assert record["clock"] == "5:42"
    assert record["home_score"] == 64
    assert record["away_score"] == 57
    assert record["margin"] == 7   # 64 - 57


def test_margin_series_margin_sign_convention(tmp_path):
    """margin = home_score - away_score; positive when home leads."""
    # Home leading
    snap_home = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="g1", home_score=80, away_score=70))
    lgp.append_margin_series(snap_home, cache_dir=str(tmp_path))
    with open(lgp.margin_series_path("g1", cache_dir=str(tmp_path))) as fh:
        rec = json.loads(fh.readline())
    assert rec["margin"] == 10

    # Away leading
    snap_away = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="g2", home_score=60, away_score=75))
    lgp.append_margin_series(snap_away, cache_dir=str(tmp_path))
    with open(lgp.margin_series_path("g2", cache_dir=str(tmp_path))) as fh:
        rec = json.loads(fh.readline())
    assert rec["margin"] == -15

    # Tied
    snap_tied = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="g3", home_score=55, away_score=55))
    lgp.append_margin_series(snap_tied, cache_dir=str(tmp_path))
    with open(lgp.margin_series_path("g3", cache_dir=str(tmp_path))) as fh:
        rec = json.loads(fh.readline())
    assert rec["margin"] == 0


def test_margin_series_grows_monotonically(tmp_path):
    """Multiple polls append rows; file line count grows monotonically."""
    cache_dir = str(tmp_path)
    game_id = "0042500401"
    snaps = [
        lgp.parse_boxscore_payload(
            _fixture_payload(game_id=game_id, home_score=s, away_score=50),
            captured_at=f"2026-06-04T0{i}:00:00+00:00",
        )
        for i, s in enumerate([50, 52, 55, 60, 65])
    ]
    path = lgp.margin_series_path(game_id, cache_dir=cache_dir)

    for n, snap in enumerate(snaps, start=1):
        lgp.append_margin_series(snap, cache_dir=cache_dir)
        with open(path, encoding="utf-8") as fh:
            lines = [l for l in fh if l.strip()]
        assert len(lines) == n, f"Expected {n} lines after {n} appends, got {len(lines)}"


def test_margin_series_no_duplicate_on_same_game_multiple_polls(tmp_path):
    """Each poll adds exactly one line; never overwrites existing records."""
    cache_dir = str(tmp_path)
    game_id = "0042500401"
    snapshots = [
        lgp.parse_boxscore_payload(
            _fixture_payload(game_id=game_id, home_score=50 + 3 * i, away_score=50),
            captured_at=f"2026-06-04T00:{i:02d}:00+00:00",
        )
        for i in range(4)
    ]
    for snap in snapshots:
        lgp.append_margin_series(snap, cache_dir=cache_dir)

    path = lgp.margin_series_path(game_id, cache_dir=cache_dir)
    with open(path, encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if l.strip()]
    assert len(lines) == 4

    records = [json.loads(l) for l in lines]
    margins = [r["margin"] for r in records]
    assert margins == [0, 3, 6, 9], f"Expected monotonically increasing margins: {margins}"


def test_margin_series_poll_once_flag_on_writes_series_file(monkeypatch, tmp_path):
    """CV_MARGIN_SERIES=ON: poll_once writes the JSONL series alongside snapshot."""
    monkeypatch.setattr(lgp, "_MARGIN_SERIES", True)
    fetch_fn = MagicMock(side_effect=[
        _fixture_payload(game_id="0022400123", home_score=56, away_score=48)])
    cache_dir = str(tmp_path / "cache")
    live_dir = str(tmp_path / "live")
    results = lgp.poll_once(
        ["0022400123"],
        fetch_fn=fetch_fn,
        sleep_fn=lambda _s: None,
        api_sleep=0.0,
        live_dir=live_dir,
        cache_dir=cache_dir,
    )
    # Snapshot still returned normally
    assert "0022400123" in results
    snap = results["0022400123"]
    # Snapshot dict unchanged (no margin key injected)
    assert "margin" not in snap

    # Series file written
    series_path = lgp.margin_series_path("0022400123", cache_dir=cache_dir)
    assert os.path.exists(series_path)
    with open(series_path, encoding="utf-8") as fh:
        lines = [l.strip() for l in fh if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["margin"] == 8   # 56 - 48
    assert record["home_score"] == 56
    assert record["away_score"] == 48


def test_margin_series_snapshot_json_unchanged_when_flag_on(monkeypatch, tmp_path):
    """CV_MARGIN_SERIES=ON: the written snapshot JSON file is byte-identical to flag-OFF."""
    payload = _fixture_payload(game_id="0022400555", home_score=70, away_score=65)
    snap = lgp.parse_boxscore_payload(payload, captured_at="2026-06-04T02:00:00+00:00")

    # Write snapshot with flag ON
    monkeypatch.setattr(lgp, "_MARGIN_SERIES", True)
    live_dir = str(tmp_path / "live")
    cache_dir = str(tmp_path / "cache")
    snap_path = lgp.write_snapshot(snap, live_dir=live_dir)
    lgp.append_margin_series(snap, cache_dir=cache_dir)

    with open(snap_path, encoding="utf-8") as fh:
        written = json.load(fh)

    # The snapshot JSON must not contain a 'margin' key
    assert "margin" not in written
    # All baseline keys present
    expected_keys = {"game_id", "captured_at", "game_status", "period", "clock",
                     "home_team", "away_team", "home_score", "away_score", "players"}
    assert expected_keys.issubset(written.keys())
    assert written["home_score"] == 70
    assert written["away_score"] == 65


def test_margin_series_record_keys(tmp_path):
    """Each JSONL record has exactly the expected 6 keys."""
    snap = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="g7", home_score=100, away_score=98),
        captured_at="2026-06-04T03:00:00+00:00",
    )
    lgp.append_margin_series(snap, cache_dir=str(tmp_path))
    path = lgp.margin_series_path("g7", cache_dir=str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        record = json.loads(fh.readline())
    expected_keys = {"captured_at", "period", "clock", "home_score", "away_score", "margin"}
    assert set(record.keys()) == expected_keys, (
        f"Unexpected keys: {set(record.keys()) ^ expected_keys}"
    )


def test_margin_series_path_naming(tmp_path):
    """margin_series_path returns data/cache/ingame/margin_series_<gid>.jsonl."""
    path = lgp.margin_series_path("0042500401", cache_dir=str(tmp_path))
    assert os.path.basename(path) == "margin_series_0042500401.jsonl"
    assert path.startswith(str(tmp_path))


def test_margin_series_creates_cache_dir(tmp_path):
    """append_margin_series creates the cache dir if it does not exist."""
    cache_dir = str(tmp_path / "nonexistent" / "deep")
    snap = lgp.parse_boxscore_payload(
        _fixture_payload(game_id="g8"), captured_at="2026-06-04T04:00:00+00:00")
    lgp.append_margin_series(snap, cache_dir=cache_dir)
    assert os.path.isdir(cache_dir)
    assert os.path.exists(lgp.margin_series_path("g8", cache_dir=cache_dir))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
