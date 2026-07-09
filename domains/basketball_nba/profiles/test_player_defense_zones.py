"""Per-file test: floor enforcement + attribute-name shape for the 20
zone_def_* pass-through attributes, on a synthetic zone_onoff-shaped frame
(no disk I/O beyond a tmp_path parquet).

Run: python -m pytest domains/basketball_nba/profiles/test_player_defense_zones.py -q
"""
from __future__ import annotations

import pandas as pd

import domains.basketball_nba.profiles.player_defense_zones as pdz
import domains.basketball_nba.profiles.profile_compute as profile_compute


def _write_zone_onoff(tmp_path, season="2099_00"):
    df = pd.DataFrame([
        {  # qualified: both sides >=750
            "player_id": 1, "team_id": 100, "player_name": "Qualified Player",
            "min_on": 900.0, "min_off": 1000.0,
            "rim_share_allowed_on": 0.30, "rim_share_allowed_off": 0.40,
            "rim_efg_allowed_on": 0.55, "rim_efg_allowed_off": 0.60,
        },
        {  # below floor: min_off too low -- must be dropped entirely
            "player_id": 2, "team_id": 100, "player_name": "Bench Player",
            "min_on": 800.0, "min_off": 200.0,
            "rim_share_allowed_on": 0.30, "rim_share_allowed_off": 0.40,
            "rim_efg_allowed_on": 0.55, "rim_efg_allowed_off": 0.60,
        },
        {  # negative placeholder id -- must be excluded
            "player_id": -5, "team_id": 100, "player_name": "Unresolved",
            "min_on": 900.0, "min_off": 900.0,
            "rim_share_allowed_on": 0.30, "rim_share_allowed_off": 0.40,
            "rim_efg_allowed_on": 0.55, "rim_efg_allowed_off": 0.60,
        },
    ])
    lineups_dir = tmp_path / "lineups"
    lineups_dir.mkdir()
    df.to_parquet(lineups_dir / f"zone_onoff_{season}.parquet", index=False)
    return lineups_dir


def test_floor_and_negative_id_drop(tmp_path, monkeypatch):
    lineups_dir = _write_zone_onoff(tmp_path)
    monkeypatch.setattr(pdz, "_LINEUPS", lineups_dir)
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)  # rel_sources() needs a common root
    rows = pdz.build_player_defense_zones("2099_00")

    player_ids = {r["entity_id"] for r in rows}
    assert player_ids == {1}  # below-floor and negative-id rows both dropped

    attrs = {r["attribute"] for r in rows if r["entity_id"] == 1}
    assert "zone_def_rim_share_allowed_on" in attrs
    assert "zone_def_rim_share_allowed_off" in attrs
    assert "zone_def_rim_efg_allowed_on" in attrs


def test_missing_source_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pdz, "_LINEUPS", tmp_path / "nope")
    assert pdz.build_player_defense_zones("2099_00") == []
