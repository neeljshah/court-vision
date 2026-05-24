"""Tests for src/data/lineups.py (cycle 62)."""
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
    _name_key, _strip_accents, default_path,
    load_lineups, build_starter_index, lookup_starter,
    teams_playing, classify_starter,
)


def _starter(pos, name, play_pct=100, injury=None):
    return {"pos": pos, "name": name, "play_pct": play_pct, "injury": injury}


def _payload(games):
    return {"date": "2026-05-24", "fetched_at": "2026-05-24T17:00:00",
            "source": "https://rotowire.com/x", "games": games}


def _write_tmp(payload):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                     encoding="utf-8")
    json.dump(payload, fh); fh.close()
    return fh.name


# ── basics ────────────────────────────────────────────────────────────────────

def test_name_key_strips_diacritics_and_case():
    assert _name_key("Nikola Jokić") == "nikola jokic"
    assert _name_key("Luka Dončić") == "luka doncic"
    assert _name_key("  LEBRON JAMES  ") == "lebron james"
    assert _name_key(None) == ""


def test_load_lineups_returns_empty_on_missing_or_malformed():
    assert load_lineups(None) == {}
    assert load_lineups("") == {}
    assert load_lineups("/tmp/never_exists_xyz.json") == {}
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                     encoding="utf-8")
    fh.write("{not-json"); fh.close()
    try:
        assert load_lineups(fh.name) == {}
    finally:
        os.unlink(fh.name)


def test_default_path_uses_data_dir():
    from datetime import date
    p = default_path(date(2026, 5, 24))
    assert p.endswith(os.path.join("data", "lineups_2026-05-24.json"))


# ── starter index ─────────────────────────────────────────────────────────────

def test_build_starter_index_flattens_all_games():
    payload = _payload([
        {
            "away_team": "OKC", "home_team": "SAS",
            "away_lineup": {"status": "Expected", "starters": [
                _starter("PG", "Shai Gilgeous-Alexander"),
                _starter("SG", "Luguentz Dort"),
                _starter("SF", "Jalen Williams", play_pct=50, injury="Ques"),
            ]},
            "home_lineup": {"status": "Confirmed", "starters": [
                _starter("PG", "De'Aaron Fox"),
                _starter("C",  "Victor Wembanyama"),
            ]},
        },
        {
            "away_team": "DEN", "home_team": "LAL",
            "away_lineup": {"status": "Projected", "starters": [
                _starter("C", "Nikola Jokić"),
            ]},
            "home_lineup": {"status": "Expected", "starters": [
                _starter("SF", "LeBron James"),
            ]},
        },
    ])
    path = _write_tmp(payload)
    try:
        idx = build_starter_index(path)
    finally:
        os.unlink(path)
    # 7 unique starters total
    assert len(idx) == 7
    # Team + position + play_pct propagated correctly
    sga = idx["shai gilgeous-alexander"]
    assert sga["team"] == "OKC"
    assert sga["pos"] == "PG"
    assert sga["play_pct"] == 100
    assert sga["injury"] is None
    assert sga["lineup_status"] == "Expected"
    # Williams keeps the injury tag + low play_pct
    williams = idx["jalen williams"]
    assert williams["play_pct"] == 50
    assert williams["injury"] == "Ques"
    # Diacritic-stripped Jokić matches plain 'jokic'
    jokic = idx["nikola jokic"]
    assert jokic["team"] == "DEN"
    assert jokic["lineup_status"] == "Projected"


def test_lookup_starter_diacritic_insensitive():
    idx = {"nikola jokic": {"team": "DEN", "pos": "C", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    assert lookup_starter("Nikola Jokić", idx)["team"] == "DEN"
    assert lookup_starter("nikola jokic", idx)["team"] == "DEN"
    assert lookup_starter("Stephen Curry", idx) is None


def test_teams_playing_returns_unique_abbrevs():
    payload = _payload([
        {"away_team": "OKC", "home_team": "SAS",
         "away_lineup": {"status": "Expected", "starters": []},
         "home_lineup": {"status": "Expected", "starters": []}},
        {"away_team": "DEN", "home_team": "LAL",
         "away_lineup": {"status": "Expected", "starters": []},
         "home_lineup": {"status": "Expected", "starters": []}},
    ])
    path = _write_tmp(payload)
    try:
        teams = teams_playing(path)
    finally:
        os.unlink(path)
    assert sorted(teams) == ["DEN", "LAL", "OKC", "SAS"]


# ── classify_starter ──────────────────────────────────────────────────────────

def test_classify_starter_recognizes_full_starter():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    assert classify_starter("LeBron James", idx) == "starter"


def test_classify_starter_marks_questionable_when_play_pct_below_80():
    idx = {"jalen williams": {"team": "OKC", "pos": "SF", "play_pct": 50,
                                "injury": "Ques", "lineup_status": "Expected"}}
    assert classify_starter("Jalen Williams", idx) == "questionable"


def test_classify_starter_marks_questionable_when_injury_tag_present():
    """play_pct=85 still counts as questionable when the rotowire injury flag is set."""
    idx = {"x player": {"team": "LAL", "pos": "SF", "play_pct": 85,
                          "injury": "GTD", "lineup_status": "Expected"}}
    assert classify_starter("X Player", idx) == "questionable"


def test_classify_starter_returns_bench_when_team_playing_but_not_starting():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    assert classify_starter("Austin Reaves", idx,
                              teams_tonight=["LAL", "DEN"],
                              player_team="LAL") == "bench"


def test_classify_starter_returns_no_game_when_team_not_playing():
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    assert classify_starter("Joel Embiid", idx,
                              teams_tonight=["LAL", "DEN"],
                              player_team="PHI") == "no-game"


def test_classify_starter_returns_unknown_when_lineup_data_missing():
    assert classify_starter("LeBron James", {}) == "unknown"


def test_classify_starter_defaults_to_bench_when_caller_omits_schedule():
    """If caller doesn't pass teams_tonight/player_team, we can't tell if
    the player has a game — assume bench so the caller doesn't silently
    swallow a no-game scenario."""
    idx = {"lebron james": {"team": "LAL", "pos": "SF", "play_pct": 100,
                              "injury": None, "lineup_status": "Confirmed"}}
    assert classify_starter("Austin Reaves", idx) == "bench"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
