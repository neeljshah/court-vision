"""Per-file test: zone-share aggregation formulas on a synthetic shot frame,
plus a smoke pass over one real game fixture (copied into an isolated tmp dir
so build_diet_table only ever sees that one file -- deterministic row count).

Run: python -m pytest domains/basketball_nba/composition/test_shot_diet.py -q
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

import domains.basketball_nba.composition.shot_diet as shot_diet_mod
from domains.basketball_nba.composition.shot_diet import build_diet_table
from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_nba.lineups.pbp_lineups import _PBP_DIR

_FIXTURE = _PBP_DIR / "0022500003.json"


def test_zone_shares_and_assisted_share_synthetic(monkeypatch) -> None:
    # One team_id, one game: 2 rim (1 make assisted, 1 miss), 1 corner3 make
    # unassisted, 1 mid miss -- 4 total FGA.
    shots = pd.DataFrame([
        {"game_id": "g1", "team_id": 100, "defense_team_id": 200, "person_id": 1,
         "zone": "rim", "subtype_class": "Layup", "assisted": 1, "made": 1, "points": 2},
        {"game_id": "g1", "team_id": 100, "defense_team_id": 200, "person_id": 1,
         "zone": "rim", "subtype_class": "Layup", "assisted": 0, "made": 0, "points": 2},
        {"game_id": "g1", "team_id": 100, "defense_team_id": 200, "person_id": 1,
         "zone": "corner3", "subtype_class": "Jump Shot", "assisted": 0, "made": 1, "points": 3},
        {"game_id": "g1", "team_id": 100, "defense_team_id": 200, "person_id": 1,
         "zone": "mid", "subtype_class": "Jump Shot", "assisted": 0, "made": 0, "points": 2},
    ])
    monkeypatch.setattr(shot_diet_mod, "load_raw_shots", lambda pbp_dir, limit=None: shots)

    out = build_diet_table(games_src=Path("__no_such_games_file__.parquet"))
    assert len(out) == 1
    row = out.iloc[0]
    assert row["team_id"] == 100 and row["total_fga"] == 4
    assert row["rim_fga"] == 2 and abs(row["rim_share"] - 0.5) < 1e-9
    assert row["corner3_fga"] == 1 and abs(row["corner3_share"] - 0.25) < 1e-9
    assert row["mid_fga"] == 1 and abs(row["mid_share"] - 0.25) < 1e-9
    assert row["paint_fga"] == 0 and row["above_break_3_fga"] == 0
    # 2 makes total (rim + corner3), 1 of them assisted
    assert abs(row["assisted_share"] - 0.5) < 1e-9
    assert pd.isna(row["date"])  # honest gap when games.parquet is unavailable


@pytest.mark.skipif(not _FIXTURE.exists(), reason="local-only data not present")
def test_build_diet_table_real_fixture(tmp_path) -> None:
    shutil.copy(_FIXTURE, tmp_path / _FIXTURE.name)
    out = build_diet_table(pbp_dir=tmp_path, games_src=tmp_path / "no_games.parquet")

    assert len(out) == 2  # exactly 2 offenses in one game
    assert set(out["game_id"]) == {"0022500003"}
    assert out["date"].isna().all()  # isolated dir has no games.parquet -> honest NaT

    for z in ZONES:
        assert f"{z}_fga" in out.columns and f"{z}_share" in out.columns
    totals = out[[f"{z}_share" for z in ZONES]].sum(axis=1)
    assert (abs(totals - 1.0) < 1e-9).all()
    assert (out["total_fga"] > 0).all()
    assert out["assisted_share"].between(0, 1).all()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
