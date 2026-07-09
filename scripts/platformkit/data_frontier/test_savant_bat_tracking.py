"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_savant_bat_tracking.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.platformkit.data_frontier import savant_bat_tracking as sbt

_CSV = b'"id","name","avg_bat_speed","hard_swing_rate"\n1,"Player One",72.5,0.31\n2,"Player Two",70.1,0.28\n'


def test_pull_writes_csv_and_skips_cached(tmp_path):
    # catch_probability's year param genuinely works (per-year files differ on
    # disk) -- bat_tracking moved to snapshot capture, see tests below.
    calls = []

    def _fetcher(url, params=None, headers=None, timeout=None):
        calls.append((url, params["year"] if params else None))
        return SimpleNamespace(status_code=200, content=_CSV)

    out_dir = tmp_path / "leaderboards"
    # pre-seed one year as already cached
    out_dir.mkdir(parents=True)
    (out_dir / "catch_probability_2024.csv").write_bytes(_CSV)

    res = sbt.pull([2024, 2025], families=["catch_probability"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0)

    assert res["skipped_already_cached"]["catch_probability"] == [2024]
    assert res["landed"]["catch_probability"] == [2025]
    assert len(calls) == 1  # only the uncached year hit the network


def test_params_per_family_shape():
    assert sbt._params("bat_tracking", 2024)["type"] == "batter"
    assert sbt._params("outs_above_average", 2024)["startYear"] == "2024"
    assert sbt._params("catch_probability", 2024) == {"year": "2024", "csv": "true"}


def test_consolidated_parquet_concatenates_years(tmp_path):
    out_dir = tmp_path / "leaderboards"
    out_dir.mkdir(parents=True)

    def _fetcher(url, params=None, headers=None, timeout=None):
        return SimpleNamespace(status_code=200, content=_CSV)

    res = sbt.pull([2024, 2025], families=["catch_probability"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0)
    assert res["consolidated_rows"]["catch_probability"] == 4  # 2 rows x 2 years
    import pandas as pd
    df = pd.read_parquet(out_dir / "catch_probability_consolidated.parquet")
    assert set(df["year"].unique()) == {2024, 2025}


def test_snapshot_family_writes_dated_file_and_latest(tmp_path):
    """bat_tracking's endpoint ignores year/season params (confirmed live
    2026-07-09) -- pull() must capture ONE dated snapshot + a _latest copy,
    not one identical file per requested year."""
    calls = []

    def _fetcher(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return SimpleNamespace(status_code=200, content=_CSV)

    out_dir = tmp_path / "leaderboards"
    res = sbt.pull([2024, 2025, 2026], families=["bat_tracking"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0,
                    today="2026-07-11")

    assert len(calls) == 1  # one call total, not one per requested year
    assert res["landed"]["bat_tracking"] == ["2026-07-11"]
    assert (out_dir / "bat_tracking_2026-07-11.csv").read_bytes() == _CSV
    assert (out_dir / "bat_tracking_latest.csv").read_bytes() == _CSV


def test_snapshot_family_skips_if_already_captured_today(tmp_path):
    out_dir = tmp_path / "leaderboards"
    out_dir.mkdir(parents=True)
    (out_dir / "bat_tracking_2026-07-11.csv").write_bytes(_CSV)

    def _fetcher(url, params=None, headers=None, timeout=None):
        raise AssertionError("should not hit the network when today's snapshot exists")

    res = sbt.pull([2026], families=["bat_tracking"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0,
                    today="2026-07-11")
    assert res["skipped_already_cached"]["bat_tracking"] == ["2026-07-11"]


def test_snapshot_family_two_distinct_asof_dates_are_not_byte_identical_frames(tmp_path):
    """Data-quality guard: once two dated snapshots exist, the consolidated
    frame must carry two DISTINCT as_of stamps (the underlying CSV content can
    legitimately repeat -- the endpoint is snapshot-only -- but the capture
    dates must not collapse into one, which is what the year-param bug did)."""
    out_dir = tmp_path / "leaderboards"
    out_dir.mkdir(parents=True)
    (out_dir / "bat_tracking_2026-07-10.csv").write_bytes(_CSV)
    (out_dir / "bat_tracking_2026-07-11.csv").write_bytes(_CSV)

    def _fetcher(url, params=None, headers=None, timeout=None):
        raise AssertionError("both snapshots already on disk, no fetch needed")

    res = sbt.pull([2026], families=["bat_tracking"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0,
                    today="2026-07-11")
    import pandas as pd
    df = pd.read_parquet(out_dir / "bat_tracking_consolidated.parquet")
    assert res["consolidated_rows"]["bat_tracking"] == 4  # 2 rows x 2 snapshot days
    assert set(df["as_of"].unique()) == {"2026-07-10", "2026-07-11"}


def test_failed_fetch_is_reported_not_written(tmp_path):
    def _fetcher(url, params=None, headers=None, timeout=None):
        return SimpleNamespace(status_code=404, content=b"")

    out_dir = tmp_path / "leaderboards"
    res = sbt.pull([2024], families=["catch_probability"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0)
    assert res["failed"]["catch_probability"] == [2024]
    assert not (out_dir / "catch_probability_2024.csv").exists()


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
