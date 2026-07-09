"""Per-file test: profiles/player_offense_zones.py -- floor enforcement on a
synthetic per-game-per-player table (no PBP parsing, no real season data).

Run: python -m pytest domains/basketball_nba/profiles/test_player_offense_zones.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles import player_offense_zones as pz


def _base_row(player_id: int) -> dict:
    return {
        "game_id": "1", "player_id": player_id, "player_name": f"P{player_id}",
        "total_fga": 100, "total_fgm": 50,
        "rim_fga": 0, "rim_fgm": 0, "rim_assisted": 0,
        "paint_fga": 0, "paint_fgm": 0, "paint_assisted": 0,
        "mid_fga": 0, "mid_fgm": 0, "mid_assisted": 0,
        "corner3_fga": 0, "corner3_fgm": 0, "corner3_assisted": 0,
        "above_break_3_fga": 0, "above_break_3_fgm": 0, "above_break_3_assisted": 0,
        "transition_fga": 0, "transition_fgm": 0, "transition_fg3m": 0,
        "halfcourt_fga": 0, "halfcourt_fgm": 0, "halfcourt_fg3m": 0,
        "late_clock_fga": 0, "late_clock_fgm": 0, "late_clock_fg3m": 0,
        "clutch_fga": 0, "clutch_fgm": 0, "clutch_fg3m": 0, "clutch_fta": 0,
    }


def _patch_source(tmp_path, monkeypatch, rows: list[dict]):
    p = tmp_path / "fake_season.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    monkeypatch.setattr(pz, "_season_src", lambda season: p)
    monkeypatch.setattr(pz, "rel_sources", lambda *paths: ";".join(str(x) for x in paths))


def test_zone_floor_drops_below_25_keeps_at_25(tmp_path, monkeypatch):
    below, at = _base_row(1), _base_row(2)
    below["rim_fga"], below["rim_fgm"] = 24, 12
    at["rim_fga"], at["rim_fgm"] = 25, 13
    _patch_source(tmp_path, monkeypatch, [below, at])

    out = pz.build_zone_shooting("9999_00")
    ids = {r["entity_id"] for r in out if r["attribute"] == "zone_efg_rim"}
    assert 1 not in ids
    assert 2 in ids


def test_context_floor_drops_below_25_keeps_at_25(tmp_path, monkeypatch):
    below, at = _base_row(1), _base_row(2)
    below["transition_fga"], below["transition_fgm"] = 24, 10
    at["transition_fga"], at["transition_fgm"] = 25, 12
    _patch_source(tmp_path, monkeypatch, [below, at])

    out = pz.build_play_context("9999_00")
    ids = {r["entity_id"] for r in out if r["attribute"] == "transition_efg"}
    assert 1 not in ids
    assert 2 in ids


def test_clutch_floor_drops_below_30_keeps_at_30(tmp_path, monkeypatch):
    below, at = _base_row(1), _base_row(2)
    below["clutch_fga"], below["clutch_fgm"] = 29, 15
    at["clutch_fga"], at["clutch_fgm"] = 30, 16
    _patch_source(tmp_path, monkeypatch, [below, at])

    out = pz.build_clutch("9999_00")
    ids = {r["entity_id"] for r in out if r["attribute"] == "clutch_efg"}
    assert 1 not in ids
    assert 2 in ids
