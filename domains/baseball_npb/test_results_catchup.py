"""Per-file tests for results_catchup (offline; tmp_path parquet, no network).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_results_catchup.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from domains.baseball_npb import results_catchup as rc


def _write_parquet(path, dates):
    rows = [
        {"date": d, "season": d[:4], "home_team": "A", "away_team": "B",
         "home_score": 3.0, "away_score": 1.0, "home_win": 1.0, "tied": False}
        for d in dates
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_fresh_parquet_is_a_noop(tmp_path):
    out = tmp_path / "npb_results.parquet"
    _write_parquet(out, ["2026-07-04"])
    calls = []

    def fake_ingest_season(season, out_path=None):
        calls.append(season)

    today = dt.date(2026, 7, 4)
    result = rc._catchup_generic(
        label="npb_results", out_path=out, ingest_season_fn=fake_ingest_season,
        current_season_fn=lambda now: str(now.year), stale_after_days=1, today=today,
    )
    assert result["refreshed"] is False
    assert result["reason"] == "fresh"
    assert calls == []


def test_stale_parquet_triggers_refresh_and_reports_rows_added(tmp_path):
    out = tmp_path / "npb_results.parquet"
    _write_parquet(out, ["2026-07-01"])

    def fake_ingest_season(season, out_path=None):
        # simulate a real ingest appending missing rows
        _write_parquet(out_path, ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"])

    today = dt.date(2026, 7, 4)
    result = rc._catchup_generic(
        label="npb_results", out_path=out, ingest_season_fn=fake_ingest_season,
        current_season_fn=lambda now: str(now.year), stale_after_days=1, today=today,
    )
    assert result["refreshed"] is True
    assert result["reason"] == "stale"
    assert result["rows_before"] == 1
    assert result["rows_after"] == 4
    assert result["rows_added"] == 3
    assert result["max_date_after"] == "2026-07-04"


def test_missing_parquet_is_treated_as_stale(tmp_path):
    out = tmp_path / "does_not_exist.parquet"

    def fake_ingest_season(season, out_path=None):
        _write_parquet(out_path, ["2026-07-04"])

    today = dt.date(2026, 7, 4)
    result = rc._catchup_generic(
        label="npb_results", out_path=out, ingest_season_fn=fake_ingest_season,
        current_season_fn=lambda now: str(now.year), stale_after_days=1, today=today,
    )
    assert result["refreshed"] is True
    assert result["max_date_before"] is None
    assert result["rows_before"] == 0
    assert result["rows_after"] == 1


def test_fetch_failure_is_isolated_never_raises(tmp_path):
    out = tmp_path / "npb_results.parquet"
    _write_parquet(out, ["2026-07-01"])

    def broken_ingest_season(season, out_path=None):
        raise RuntimeError("network boom")

    today = dt.date(2026, 7, 4)
    result = rc._catchup_generic(
        label="npb_results", out_path=out, ingest_season_fn=broken_ingest_season,
        current_season_fn=lambda now: str(now.year), stale_after_days=1, today=today,
    )
    assert result["refreshed"] is False
    assert result["reason"] == "fetch_error"
    assert "network boom" in result["error"]


def test_catchup_npb_wires_real_ingest_module(tmp_path, monkeypatch):
    out = tmp_path / "npb_results.parquet"
    _write_parquet(out, ["2026-07-01"])
    calls = []

    def fake_ingest_season(season, out_path=None):
        calls.append((season, out_path))
        _write_parquet(out_path, ["2026-07-01", "2026-07-04"])

    monkeypatch.setattr(
        "domains.baseball_npb.ingest_npb.ingest_season", fake_ingest_season
    )
    today = dt.date(2026, 7, 4)
    result = rc.catchup_npb(out_path=out, today=today)
    assert result["refreshed"] is True
    assert calls and calls[0][0] == "2026"
