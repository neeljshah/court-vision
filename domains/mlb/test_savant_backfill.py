"""Per-file test for domains.mlb.savant_backfill. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_savant_backfill.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domains.mlb import savant_backfill as sb  # noqa: E402


def _planted_day_df() -> pd.DataFrame:
    return pd.DataFrame({
        "game_pk": [1, 1], "game_date": ["2024-05-01", "2024-05-01"],
        "on_1b": [None, 123], "on_2b": [None, None], "on_3b": [None, None],
        "launch_angle": [12.0, None], "bb_type": ["fly_ball", None],
        "description": ["hit_into_play", "ball"],
    })


def test_fetch_writes_cache_and_skips_already_cached(tmp_path, monkeypatch):
    """A day already on disk is NOT refetched (idempotent)."""
    raw_dir = tmp_path / "raw_days_savant"
    raw_dir.mkdir()
    cached_fp = raw_dir / "day__2024-05-01.parquet"
    _planted_day_df().to_parquet(cached_fp, index=False)

    calls = []

    def _fake_day_csv(day, timeout=90):
        calls.append(day)
        return _planted_day_df()

    monkeypatch.setattr(sb, "_day_csv_savant", _fake_day_csv)
    res = sb._fetch_new_days(["2024-05-01", "2024-05-02"], raw_dir, delay_s=0.0, max_seconds=None)
    assert calls == ["2024-05-02"]  # the cached day was skipped entirely
    assert res["fetched_days"] == ["2024-05-02"]
    assert (raw_dir / "day__2024-05-02.parquet").exists()


def test_stops_after_three_consecutive_failures(tmp_path, monkeypatch):
    """The politeness stop-rule: 3 failed days in a row halts the fetch loop rather
    than hammering the endpoint further."""
    raw_dir = tmp_path / "raw_days_savant"
    raw_dir.mkdir()
    calls = []

    def _always_fail(day, timeout=90):
        calls.append(day)
        return None

    monkeypatch.setattr(sb, "_day_csv_savant", _always_fail)
    days = [f"2024-05-{i:02d}" for i in range(1, 10)]
    res = sb._fetch_new_days(days, raw_dir, delay_s=0.0, max_seconds=None)
    assert res["stopped_reason"] == "consecutive_failures"
    assert len(calls) == 3  # stopped after exactly 3 attempts, did not try days 4-9
    assert res["fetched_days"] == []


def test_failure_between_successes_does_not_accumulate(tmp_path, monkeypatch):
    """A single failed day sandwiched between successes must NOT trip the stop-rule
    (only CONSECUTIVE failures count)."""
    raw_dir = tmp_path / "raw_days_savant"
    raw_dir.mkdir()
    sequence = [_planted_day_df(), None, _planted_day_df(), None, _planted_day_df()]
    calls = {"i": 0}

    def _mixed(day, timeout=90):
        r = sequence[calls["i"]]
        calls["i"] += 1
        return r

    monkeypatch.setattr(sb, "_day_csv_savant", _mixed)
    days = [f"2024-05-{i:02d}" for i in range(1, 6)]
    res = sb._fetch_new_days(days, raw_dir, delay_s=0.0, max_seconds=None)
    assert res["stopped_reason"] is None
    assert len(res["fetched_days"]) == 3


def test_coverage_reports_obtained_and_missing_columns():
    df = _planted_day_df()
    cov = sb._coverage(df)
    assert cov["on_1b"]["obtained"] is True
    assert cov["on_1b"]["coverage_pct"] == 50.0
    assert "sprint_speed" not in cov  # not a column this lane claims


def test_keep_is_strict_superset_of_fuller_keep():
    from domains.mlb.acquire_statcast_fuller import _KEEP as fuller_keep
    assert set(fuller_keep).issubset(set(sb._KEEP))
    for c in ("on_1b", "on_2b", "on_3b", "launch_angle", "bb_type", "description"):
        assert c in sb._KEEP


# --called-pitches mode (FRAMING_DATA_ACQ_2026-09-01) -----------------------

def test_called_pitches_filters_to_taken_only(monkeypatch):
    def _fake_day(day, timeout=90):
        return pd.DataFrame({"game_date": [day] * 3,
                             "description": ["ball", "swinging_strike", "called_strike"]})
    monkeypatch.setattr(sb, "_day_csv_savant", _fake_day)
    out = sb._day_csv_called_pitches("2024-05-01")
    assert list(out["description"]) == ["ball", "called_strike"]


def test_called_pitches_respects_byte_budget(tmp_path, monkeypatch):
    """A byte budget already met by pre-existing cached days stops the fetch
    loop before it makes a single new request (byte cap is honored)."""
    raw_dir = tmp_path / "raw_days_called_pitches"
    raw_dir.mkdir()
    planted = raw_dir / "day__2024-05-01.parquet"
    _planted_day_df().to_parquet(planted, index=False)
    calls = []

    def _fake(day, timeout=90):
        calls.append(day)
        return _planted_day_df()

    monkeypatch.setattr(sb, "_day_csv_called_pitches", _fake)
    res = sb.run_called_pitches(["2024-05-01", "2024-05-02", "2024-05-03"],
                                max_bytes=planted.stat().st_size, cache_dir=tmp_path)
    assert calls == []  # budget already met -- no new request attempted
    assert res["stopped_reason"] == "byte_budget"


def test_called_pitches_idempotent_resume_and_manifest(tmp_path, monkeypatch):
    """Re-running with the same days does not refetch (idempotent), and the
    first run produces a manifest with rows/bytes/date range/sha256."""
    def _fake(day, timeout=90):
        return _planted_day_df()

    monkeypatch.setattr(sb, "_day_csv_called_pitches", _fake)
    days = ["2024-05-01", "2024-05-02"]
    res1 = sb.run_called_pitches(days, max_bytes=10_000_000, cache_dir=tmp_path)
    assert res1["days_fetched_this_run"] == 2
    assert "sha256" in res1 and "manifest_path" in res1
    assert Path(res1["manifest_path"]).exists()

    calls_second = []

    def _fake2(day, timeout=90):
        calls_second.append(day)
        return _planted_day_df()

    monkeypatch.setattr(sb, "_day_csv_called_pitches", _fake2)
    res2 = sb.run_called_pitches(days, max_bytes=10_000_000, cache_dir=tmp_path)
    assert calls_second == []  # both days already cached
    assert res2["days_fetched_this_run"] == 0


def test_called_pitches_date_slice_excludes_uncached_extra_day(tmp_path, monkeypatch):
    """A cached day outside the requested date slice must not leak into output."""
    raw_dir = tmp_path / "raw_days_called_pitches"
    raw_dir.mkdir()
    extra = _planted_day_df().copy()
    extra["game_date"] = "2024-06-15"
    extra.to_parquet(raw_dir / "day__2024-06-15.parquet", index=False)

    monkeypatch.setattr(sb, "_day_csv_called_pitches", lambda day, timeout=90: _planted_day_df())
    res = sb.run_called_pitches(["2024-05-01"], max_bytes=10_000_000, cache_dir=tmp_path)
    assert res["date_range"] == ["2024-05-01", "2024-05-01"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
