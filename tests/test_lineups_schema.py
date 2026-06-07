"""tests/test_lineups_schema.py — A3 fix (2026-05-26).

Verifies that src/data/lineups.build_starter_index() accepts BOTH lineup-feed
schemas: the cycle-61 nested-by-game payload written by scripts/fetch_lineups.py
AND the flat one-row-per-starter payload written by scripts/nba_lineup_daemon.py.

Before this fix, the daemon's file at data/lineups/<date>.json was unreadable
by build_starter_index (it expected the cycle-61 nested schema) and the
--lineups flag in predict_slate.py couldn't be wired up to the daemon feed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.data.lineups import (  # noqa: E402
    build_starter_index,
    classify_starter,
    lookup_starter,
    teams_playing,
    _is_daemon_schema,
    _alt_daemon_path_for,
)


# ── fixtures ──────────────────────────────────────────────────────────────────
def _legacy_payload():
    """cycle-61 fetch_lineups.py schema — nested games[]."""
    return {
        "date": "2026-05-26",
        "fetched_at": "2026-05-26T15:00:00",
        "source": "https://rotowire.com/x",
        "games": [
            {
                "away_team": "SAS", "home_team": "OKC",
                "away_lineup": {
                    "status": "Projected",
                    "starters": [
                        {"pos": "PG", "name": "De'Aaron Fox",
                         "play_pct": 100, "injury": None},
                        {"pos": "C", "name": "Victor Wembanyama",
                         "play_pct": 100, "injury": None},
                    ],
                },
                "home_lineup": {
                    "status": "Confirmed",
                    "starters": [
                        {"pos": "PG", "name": "Shai Gilgeous-Alexander",
                         "play_pct": 100, "injury": None},
                    ],
                },
            },
        ],
    }


def _daemon_payload():
    """R17 J1 nba_lineup_daemon.py schema — flat starters[]."""
    return {
        "date": "2026-05-26",
        "updated_at": "2026-05-26T15:01:58+00:00",
        "n_starters": 3,
        "source": "rotowire",
        "starters": [
            {
                "game_id": "SAS@OKC_2026-05-26",
                "team": "SAS", "player_id": None,
                "player_name": "De'Aaron Fox", "position": "PG", "slot": "PG",
                "status": "PROJECTED",
                "captured_at": "2026-05-26T15:01:52+00:00",
                "injury": None, "play_pct": 100, "home_away": "away",
            },
            {
                "game_id": "SAS@OKC_2026-05-26",
                "team": "SAS", "player_id": None,
                "player_name": "Victor Wembanyama", "position": "C", "slot": "C",
                "status": "PROJECTED",
                "captured_at": "2026-05-26T15:01:52+00:00",
                "injury": None, "play_pct": 100, "home_away": "away",
            },
            {
                "game_id": "SAS@OKC_2026-05-26",
                "team": "OKC", "player_id": None,
                "player_name": "Shai Gilgeous-Alexander",
                "position": "PG", "slot": "PG",
                "status": "CONFIRMED",
                "captured_at": "2026-05-26T15:01:52+00:00",
                "injury": None, "play_pct": 100, "home_away": "home",
            },
        ],
        "change_events": [],
    }


def _write_tmp(payload):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                     encoding="utf-8")
    json.dump(payload, fh)
    fh.close()
    return fh.name


# ── schema detection ──────────────────────────────────────────────────────────
def test_detects_legacy_schema():
    assert _is_daemon_schema(_legacy_payload()) is False


def test_detects_daemon_schema():
    assert _is_daemon_schema(_daemon_payload()) is True


def test_detects_neither_on_empty_or_malformed():
    assert _is_daemon_schema({}) is False
    assert _is_daemon_schema({"starters": []}) is False
    assert _is_daemon_schema({"starters": [{"name": "x"}]}) is False  # missing player_name


# ── build_starter_index across schemas ────────────────────────────────────────
def test_build_index_legacy_schema_unchanged():
    path = _write_tmp(_legacy_payload())
    try:
        idx = build_starter_index(path)
        assert len(idx) == 3
        fox = idx["de'aaron fox"]
        assert fox["team"] == "SAS"
        assert fox["pos"] == "PG"
        assert fox["play_pct"] == 100
        assert fox["lineup_status"] == "Projected"
        assert idx["shai gilgeous-alexander"]["lineup_status"] == "Confirmed"
    finally:
        os.unlink(path)


def test_build_index_daemon_schema():
    path = _write_tmp(_daemon_payload())
    try:
        idx = build_starter_index(path)
        assert len(idx) == 3
        fox = idx["de'aaron fox"]
        assert fox["team"] == "SAS"
        assert fox["pos"] == "PG"          # taken from slot/position
        assert fox["play_pct"] == 100
        assert fox["lineup_status"] == "PROJECTED"
        assert idx["shai gilgeous-alexander"]["lineup_status"] == "CONFIRMED"
        wemby = idx["victor wembanyama"]
        assert wemby["team"] == "SAS"
        assert wemby["pos"] == "C"
    finally:
        os.unlink(path)


def test_build_index_returns_equivalent_dict_across_schemas():
    """Both schemas must produce the SAME canonical keys + the same downstream
    fields the consumer (save_predictions_csv) actually reads."""
    legacy = build_starter_index(_write_tmp(_legacy_payload()))
    daemon = build_starter_index(_write_tmp(_daemon_payload()))
    assert set(legacy.keys()) == set(daemon.keys())
    for key in legacy:
        for col in ("team", "pos", "play_pct"):
            assert legacy[key][col] == daemon[key][col], (
                f"{col} mismatch for {key}: {legacy[key]} vs {daemon[key]}"
            )


# ── downstream consumers must work with daemon schema ─────────────────────────
def test_classify_starter_works_with_daemon_payload():
    path = _write_tmp(_daemon_payload())
    try:
        idx = build_starter_index(path)
        assert classify_starter("Shai Gilgeous-Alexander", idx) == "starter"
        # diacritic-insensitive lookup still works
        assert classify_starter("de'aaron fox", idx) == "starter"
        # an unknown player on a team that IS playing tonight → bench
        assert classify_starter("Random Bench Guy", idx,
                                  teams_tonight=["SAS", "OKC"],
                                  player_team="SAS") == "bench"
    finally:
        os.unlink(path)


def test_lookup_starter_works_with_daemon_payload():
    path = _write_tmp(_daemon_payload())
    try:
        idx = build_starter_index(path)
        rec = lookup_starter("Victor Wembanyama", idx)
        assert rec is not None
        assert rec["lineup_status"] == "PROJECTED"
        assert rec["team"] == "SAS"
    finally:
        os.unlink(path)


def test_teams_playing_works_with_daemon_payload():
    path = _write_tmp(_daemon_payload())
    try:
        teams = teams_playing(path)
        assert set(teams) == {"SAS", "OKC"}
    finally:
        os.unlink(path)


def test_teams_playing_works_with_legacy_payload():
    path = _write_tmp(_legacy_payload())
    try:
        teams = teams_playing(path)
        assert set(teams) == {"SAS", "OKC"}
    finally:
        os.unlink(path)


# ── auto-fallback: legacy path missing → daemon path used ─────────────────────
def test_alt_daemon_path_for_translates_correctly():
    legacy = "/x/y/data/lineups_2026-05-26.json"
    expected = os.path.join("/x/y/data", "lineups", "2026-05-26.json")
    assert _alt_daemon_path_for(legacy) == expected


def test_alt_daemon_path_for_non_lineup_name_returns_none():
    assert _alt_daemon_path_for("/data/injuries_2026-05-26.json") is None
    assert _alt_daemon_path_for("/data/anything.json") is None


def test_auto_fallback_to_daemon_path_when_legacy_missing(tmp_path):
    """build_starter_index gets the legacy path; only the daemon file exists.
    It should still find + parse the daemon file."""
    data_dir = tmp_path / "data"
    lineups_subdir = data_dir / "lineups"
    lineups_subdir.mkdir(parents=True)
    daemon_file = lineups_subdir / "2026-05-26.json"
    with open(daemon_file, "w", encoding="utf-8") as fh:
        json.dump(_daemon_payload(), fh)
    legacy_path = str(data_dir / "lineups_2026-05-26.json")
    assert not os.path.exists(legacy_path)
    idx = build_starter_index(legacy_path)
    assert len(idx) == 3
    assert idx["de'aaron fox"]["lineup_status"] == "PROJECTED"


# ── empty / malformed handling preserved ──────────────────────────────────────
def test_missing_file_returns_empty():
    assert build_starter_index("/no/such/file/here.json") == {}


def test_malformed_json_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert build_starter_index(str(p)) == {}
