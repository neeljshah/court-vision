"""Per-file test for scripts.platformkit.data_frontier.profile_completeness.
Synthetic SHARED-SCHEMA frames only -- no real parquet reads, no network.
Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/data_frontier/test_profile_completeness.py -q
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.data_frontier import profile_completeness as PC


def test_active_window_set_picks_recent_windows():
    windows = ["season_2023_24", "season_2024_25", "season_2025_26", "last20_2025_26"]
    assert PC.active_window_set(windows, date(2026, 7, 9)) == {"season_2025_26", "last20_2025_26"}


def test_active_window_set_no_year_uses_everything():
    assert PC.active_window_set(["last10", "career"], date(2026, 7, 9)) == {"last10", "career"}


def test_active_window_set_keeps_last_full_season_alongside_sparse_current():
    """Regression: MLB's in-progress season_2026 (small fielding-only sample)
    must NOT crowd out the completed, much larger season_2025 -- a pure
    max-year cut would starve every season_2025 pitch-frame attribute."""
    windows = ["season_2023", "season_2024", "season_2025", "season_2026", "asof_2026-07-09"]
    assert PC.active_window_set(windows, date(2026, 7, 9)) == {
        "season_2025", "season_2026", "asof_2026-07-09"}


def test_staleness_days_asof_window():
    assert PC.staleness_days("asof_2026-07-01", date(2026, 7, 9)) == 8


def test_staleness_days_season_window():
    assert PC.staleness_days("season_2024", date(2026, 7, 9)) == 2 * 365


def test_staleness_days_no_year_is_none():
    assert PC.staleness_days("last10", date(2026, 7, 9)) is None


def _write_store(fp: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(fp, index=False)


def test_audit_sport_all_null_canary(tmp_path: Path):
    """n>0 rows but raw_value 100% null must flag all_null=True -- the
    'looks covered, isn't' bug this auditor exists to catch."""
    fp = tmp_path / "x_player_profiles.parquet"
    _write_store(fp, [
        {"entity_id": 1, "window": "season_2025", "attribute": "good_attr",
         "raw_value": 0.3, "status": "DESCRIPTIVE"},
        {"entity_id": 2, "window": "season_2025", "attribute": "good_attr",
         "raw_value": 0.5, "status": "DESCRIPTIVE"},
        {"entity_id": 1, "window": "season_2025", "attribute": "broken_attr",
         "raw_value": None, "status": "DESCRIPTIVE"},
        {"entity_id": 2, "window": "season_2025", "attribute": "broken_attr",
         "raw_value": None, "status": "DESCRIPTIVE"},
    ])
    r = PC.audit_sport("x", fp, date(2026, 7, 9))
    assert r["status"] == "OK"
    assert r["active_universe_n"] == 2
    assert r["all_null_count"] == 1
    assert r["all_null_attrs"] == ["broken_attr@season_2025"]
    good = next(a for a in r["attributes"] if a["attribute"] == "good_attr")
    assert good["coverage_pct_of_active"] == 100.0
    broken = next(a for a in r["attributes"] if a["attribute"] == "broken_attr")
    assert broken["all_null"] is True
    # a broken (all-null) attribute still COUNTS as covered by entity presence --
    # all_null is the separate canary that catches this, coverage_pct alone would not.
    assert broken["coverage_pct_of_active"] == 100.0


def test_audit_sport_partial_coverage_of_active_universe(tmp_path: Path):
    fp = tmp_path / "y_player_profiles.parquet"
    _write_store(fp, [
        {"entity_id": 1, "window": "season_2025", "attribute": "a", "raw_value": 1.0, "status": "DESCRIPTIVE"},
        {"entity_id": 2, "window": "season_2025", "attribute": "b", "raw_value": 1.0, "status": "DESCRIPTIVE"},
        # entity 2 has NO row for attribute 'a' this window -> a's coverage is 1/2
    ])
    r = PC.audit_sport("y", fp, date(2026, 7, 9))
    assert r["active_universe_n"] == 2
    a = next(x for x in r["attributes"] if x["attribute"] == "a")
    assert a["coverage_pct_of_active"] == 50.0


def test_audit_sport_no_store_is_honest_gap(tmp_path: Path):
    r = PC.audit_sport("soccer", tmp_path / "does_not_exist.parquet", date(2026, 7, 9))
    assert r["status"] == "NO_PLAYER_STORE"
    assert r["attributes"] == []


def test_build_report_covers_all_sports(tmp_path: Path):
    fp = tmp_path / "nba_player_profiles.parquet"
    _write_store(fp, [{"entity_id": 1, "window": "season_2025_26", "attribute": "a",
                       "raw_value": 1.0, "status": "DESCRIPTIVE"}])
    orig = dict(PC.SPORT_STORES)
    PC.SPORT_STORES = {"nba": "nba_player_profiles.parquet", "soccer": None}
    try:
        report = PC.build_report(profiles_dir=tmp_path, today=date(2026, 7, 9))
    finally:
        PC.SPORT_STORES = orig
    assert report["sports"]["nba"]["status"] == "OK"
    assert report["sports"]["soccer"]["status"] == "NO_PLAYER_STORE"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
