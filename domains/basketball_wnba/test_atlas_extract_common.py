"""Per-file tests for domains.basketball_wnba.atlas_extract_common.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_common.py -q
"""
from __future__ import annotations

import json

from domains.basketball_wnba.atlas_extract_common import (
    atlas_write_path, effective_fg_pct, iso_minutes, iter_backfilled_games,
    load_game_pair, safe_get, team_pace_proxy, true_shooting_pct,
)


# ---------------------------------------------------------------------------
# iso_minutes -- ISO8601 duration parsing
# ---------------------------------------------------------------------------

def test_iso_minutes_full_duration():
    assert iso_minutes("PT12M23.00S") == 12.3833


def test_iso_minutes_zero_dnp():
    assert iso_minutes("PT00M") == 0.0


def test_iso_minutes_empty_string():
    assert iso_minutes("") == 0.0


def test_iso_minutes_none_is_none():
    assert iso_minutes(None) is None


def test_iso_minutes_malformed_is_none():
    assert iso_minutes("garbage") is None


# ---------------------------------------------------------------------------
# shooting formulas
# ---------------------------------------------------------------------------

def test_true_shooting_pct_normal():
    # 20 pts on 10 fga, 4 fta -> 20 / (2*(10+0.44*4)) = 20/23.52
    assert true_shooting_pct(20, 10, 4) == round(20 / (2 * (10 + 0.44 * 4)), 4)


def test_true_shooting_pct_zero_denom_is_none():
    assert true_shooting_pct(0, 0, 0) is None


def test_effective_fg_pct_normal():
    # 5 fgm (2 are 3pm) on 10 fga -> (5+0.5*2)/10 = 0.6
    assert effective_fg_pct(5, 2, 10) == 0.6


def test_effective_fg_pct_zero_fga_is_none():
    assert effective_fg_pct(0, 0, 0) is None


def test_team_pace_proxy_normal():
    # fga=80, fta=20, orb=10, tov=15 -> 80+0.44*20-10+15 = 93.8
    assert team_pace_proxy(80, 20, 10, 15) == 93.8


def test_team_pace_proxy_none_input_is_none():
    assert team_pace_proxy(None, 20, 10, 15) is None


# ---------------------------------------------------------------------------
# disk loaders -- tmp_path fixtures, no network
# ---------------------------------------------------------------------------

def test_load_game_pair_missing_dir_is_none(tmp_path, monkeypatch):
    import domains.basketball_wnba.atlas_extract_common as common
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    assert load_game_pair("nope") is None


def test_load_game_pair_happy_path(tmp_path, monkeypatch):
    import domains.basketball_wnba.atlas_extract_common as common
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    d = tmp_path / "g1"
    d.mkdir()
    (d / "boxscore.json").write_text(json.dumps({"game": {"a": 1}}), encoding="utf-8")
    (d / "playbyplay.json").write_text(json.dumps({"game": {"b": 2}}), encoding="utf-8")
    pair = load_game_pair("g1")
    assert pair["boxscore"] == {"a": 1}
    assert pair["playbyplay"] == {"b": 2}


def test_iter_backfilled_games_skips_malformed(tmp_path, monkeypatch):
    import domains.basketball_wnba.atlas_extract_common as common
    monkeypatch.setattr(common, "BACKFILL_DIR", tmp_path)
    good = tmp_path / "g1"
    good.mkdir()
    (good / "boxscore.json").write_text(json.dumps({"game": {"x": 1}}), encoding="utf-8")
    (good / "playbyplay.json").write_text(json.dumps({"game": {"y": 2}}), encoding="utf-8")
    bad = tmp_path / "g2"
    bad.mkdir()
    (bad / "boxscore.json").write_text(json.dumps({"game": {"x": 1}}), encoding="utf-8")
    # no playbyplay.json -> should be skipped, not raise

    found = list(iter_backfilled_games())
    ids = [gid for gid, _ in found]
    assert "g1" in ids
    assert "g2" not in ids


def test_safe_get_nested_and_missing():
    d = {"a": {"b": {"c": 5}}}
    assert safe_get(d, "a", "b", "c") == 5
    assert safe_get(d, "a", "z", "c", default="missing") == "missing"
    assert safe_get(None, "a") is None


def test_atlas_write_path_naming():
    p = atlas_write_path("player_shooting_profile")
    assert p.name == "atlas_wnba_player_shooting_profile.parquet"
