"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_savant_bat_tracking.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

from scripts.platformkit.data_frontier import savant_bat_tracking as sbt

_CSV = b'"id","name","avg_bat_speed","hard_swing_rate"\n1,"Player One",72.5,0.31\n2,"Player Two",70.1,0.28\n'


def test_pull_writes_csv_and_skips_cached(tmp_path):
    calls = []

    def _fetcher(url, params=None, headers=None, timeout=None):
        calls.append((url, params["year"] if params else None))
        return SimpleNamespace(status_code=200, content=_CSV)

    out_dir = tmp_path / "leaderboards"
    # pre-seed one year as already cached
    out_dir.mkdir(parents=True)
    (out_dir / "bat_tracking_2024.csv").write_bytes(_CSV)

    res = sbt.pull([2024, 2025], families=["bat_tracking"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0)

    assert res["skipped_already_cached"]["bat_tracking"] == [2024]
    assert res["landed"]["bat_tracking"] == [2025]
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

    res = sbt.pull([2024, 2025], families=["bat_tracking"], fetcher=_fetcher,
                    out_dir=out_dir, log_path=tmp_path / "log.txt", delay_s=0.0)
    assert res["consolidated_rows"]["bat_tracking"] == 4  # 2 rows x 2 years
    import pandas as pd
    df = pd.read_parquet(out_dir / "bat_tracking_consolidated.parquet")
    assert set(df["year"].unique()) == {2024, 2025}


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
