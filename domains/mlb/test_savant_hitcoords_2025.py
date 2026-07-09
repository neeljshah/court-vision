"""Per-file test for domains.mlb.savant_hitcoords_2025. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_savant_hitcoords_2025.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.mlb import savant_hitcoords_2025 as s25  # noqa: E402

_STATCAST = Path(__file__).resolve().parents[2] / "data" / "cache" / "statcast"
_FP24 = _STATCAST / "savant_hitcoords__2024.parquet"
_FP25 = _STATCAST / "savant_hitcoords__2025.parquet"


def _planted(day: str) -> pd.DataFrame:
    return pd.DataFrame({
        "game_pk": [1], "game_date": [day], "batter": [660271],
        "bb_type": ["fly_ball"], "hc_x": [120.5], "hc_y": [88.2],
        "hit_location": [8], "launch_speed_angle": [6], "stand": ["L"],
    })


def test_pull_chunk_writes_state_and_is_resumable(tmp_path, monkeypatch):
    monkeypatch.setattr(s25, "_season_days",
                        lambda season: ["2025-04-01", "2025-04-02"])
    monkeypatch.setattr(s25, "_DELAY_S", 0.0)
    sfp = tmp_path / "state.json"
    res = s25.pull_chunk(max_seconds=999.0, cache_dir=tmp_path,
                         state_fp=sfp, fetch_fn=_planted)
    assert res["stopped_reason"] == "complete"
    assert res["last_completed_day"] == "2025-04-02"
    assert res["days_cached"] == 2 and res["fetched_this_run"] == 2
    assert s25.load_state(sfp)["last_completed_day"] == "2025-04-02"
    assert (tmp_path / "savant_hitcoords__2025.parquet").exists()

    # resume: cached days are NEVER refetched -- a failing fetch_fn proves it
    def _boom(day):
        raise AssertionError(f"refetched cached day {day}")
    res2 = s25.pull_chunk(max_seconds=999.0, cache_dir=tmp_path,
                          state_fp=sfp, fetch_fn=_boom)
    assert res2["stopped_reason"] == "complete" and res2["fetched_this_run"] == 0


def test_pull_chunk_stops_after_three_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(s25, "_season_days",
                        lambda season: [f"2025-04-{i:02d}" for i in range(1, 9)])
    monkeypatch.setattr(s25, "_DELAY_S", 0.0)
    calls = []

    def _fail(day):
        calls.append(day)
        return None
    res = s25.pull_chunk(max_seconds=999.0, cache_dir=tmp_path,
                         state_fp=tmp_path / "s.json", fetch_fn=_fail)
    assert res["stopped_reason"] == "consecutive_failures"
    assert len(calls) == 3  # honest BLOCKED stop, no hammering


def test_politeness_constants_within_rails():
    assert s25._DELAY_S >= 1.0          # max 1 req/s
    assert 30 <= s25._TIMEOUT_S <= 40   # census-verified client timeout band


@pytest.mark.skipif(not (_FP24.exists() and _FP25.exists()),
                    reason="on-disk 2024/2025 hitcoords parquets absent (clean clone)")
def test_2025_schema_matches_2024_so_profile_builders_consume_unchanged():
    cols24 = set(pd.read_parquet(_FP24).columns)
    cols25 = set(pd.read_parquet(_FP25).columns)
    assert cols25 == cols24
    # the exact columns ingredients_batter.py builders dropna/groupby on
    for c in ("hc_x", "hc_y", "hit_location", "launch_speed_angle",
              "stand", "batter", "game_date", "bb_type"):
        assert c in cols25


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
