"""Per-file test for domains.mlb.savant_backfill_hitcoords. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_savant_backfill_hitcoords.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.mlb import savant_backfill_hitcoords as sh  # noqa: E402


def _planted_day_df() -> pd.DataFrame:
    return pd.DataFrame({
        "game_pk": [1, 1, 1], "game_date": ["2023-05-01", "2023-05-01", "2023-05-01"],
        "bb_type": ["ground_ball", "fly_ball", None],  # None row = a non-batted-ball pitch
        "hc_x": [120.5, 88.2, None], "hc_y": [180.1, 90.4, None],
        "hit_location": [6, 8, None], "launch_speed_angle": [2, 5, None],
    })


def test_keep_is_strict_superset_of_savant_backfill_keep():
    from domains.mlb.savant_backfill import _KEEP as savant_keep
    assert set(savant_keep).issubset(set(sh._KEEP))
    for c in ("hc_x", "hc_y", "hit_location", "launch_speed_angle"):
        assert c in sh._KEEP


def test_fetch_writes_cache_and_skips_already_cached(tmp_path, monkeypatch):
    """A day already on disk is NOT refetched (idempotent, own raw_days_hitcoords
    namespace -- must not collide with raw_days_savant/'s narrower cached days)."""
    raw_dir = tmp_path / "raw_days_hitcoords"
    raw_dir.mkdir()
    cached_fp = raw_dir / "day__2023-05-01.parquet"
    _planted_day_df().to_parquet(cached_fp, index=False)

    calls = []

    def _fake_day_csv(day, timeout=90):
        calls.append(day)
        return _planted_day_df()

    monkeypatch.setattr(sh, "_day_csv_hitcoords", _fake_day_csv)
    res = sh._fetch_new_days(["2023-05-01", "2023-05-02"], raw_dir, delay_s=0.0, max_seconds=None)
    assert calls == ["2023-05-02"]
    assert res["fetched_days"] == ["2023-05-02"]
    assert (raw_dir / "day__2023-05-02.parquet").exists()


def test_stops_after_three_consecutive_failures(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw_days_hitcoords"
    raw_dir.mkdir()
    calls = []

    def _always_fail(day, timeout=90):
        calls.append(day)
        return None

    monkeypatch.setattr(sh, "_day_csv_hitcoords", _always_fail)
    days = [f"2023-05-{i:02d}" for i in range(1, 10)]
    res = sh._fetch_new_days(days, raw_dir, delay_s=0.0, max_seconds=None)
    assert res["stopped_reason"] == "consecutive_failures"
    assert len(calls) == 3
    assert res["fetched_days"] == []


def test_coverage_splits_raw_vs_in_play_rate():
    """hc_x/hc_y are only populated on batted-ball rows -- the in-play rate must be
    near 100% even though the raw (all-pitches) rate is lower, so a low raw rate
    alone is never mistaken for a fetch bug."""
    df = _planted_day_df()
    cov = sh._coverage(df)
    assert cov["hc_x"]["obtained"] is True
    assert cov["hc_x"]["coverage_pct"] < cov["hc_x"]["coverage_pct_in_play"]
    assert cov["hc_x"]["coverage_pct_in_play"] == 100.0  # both batted-ball rows have hc_x
    assert "sprint_speed" not in cov


def test_run_days_writes_named_parquet_not_savant_full(tmp_path, monkeypatch):
    """Output must land in savant_hitcoords__<season>.parquet -- NEVER
    savant_full__<season>.parquet (that file belongs to a different lane)."""
    def _fake_day_csv(day, timeout=90):
        return _planted_day_df()

    monkeypatch.setattr(sh, "_day_csv_hitcoords", _fake_day_csv)
    res = sh.run_days(["2023-05-01"], 2023, cache_dir=tmp_path)
    assert res["status"] == "OK"
    out_fp = Path(res["parquet"])
    assert out_fp.name == "savant_hitcoords__2023.parquet"
    assert not (tmp_path / "savant_full__2023.parquet").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
