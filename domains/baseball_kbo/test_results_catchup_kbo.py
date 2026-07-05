"""Per-file tests for results_catchup_kbo (offline; tmp_path parquet, no network).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_results_catchup_kbo.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from domains.baseball_kbo import results_catchup_kbo as rck


def _write_parquet(path, dates):
    rows = [
        {"date": d, "season": d[:4], "home_team": "A", "away_team": "B",
         "home_score": 3.0, "away_score": 1.0, "home_win": 1.0, "tied": False}
        for d in dates
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_catchup_kbo_fresh_is_noop(tmp_path, monkeypatch):
    out = tmp_path / "kbo_results.parquet"
    _write_parquet(out, ["2026-07-04"])
    calls = []

    def fake_ingest_season(season, out_path=None):
        calls.append(season)

    monkeypatch.setattr(
        "domains.baseball_kbo.ingest_kbo.ingest_season", fake_ingest_season
    )
    today = dt.date(2026, 7, 4)
    result = rck.catchup_kbo(out_path=out, today=today)
    assert result["refreshed"] is False
    assert calls == []


def test_catchup_kbo_stale_triggers_refresh(tmp_path, monkeypatch):
    out = tmp_path / "kbo_results.parquet"
    _write_parquet(out, ["2026-07-03"])

    def fake_ingest_season(season, out_path=None):
        _write_parquet(out_path, ["2026-07-03", "2026-07-04"])

    monkeypatch.setattr(
        "domains.baseball_kbo.ingest_kbo.ingest_season", fake_ingest_season
    )
    today = dt.date(2026, 7, 4)
    result = rck.catchup_kbo(out_path=out, today=today)
    assert result["refreshed"] is True
    assert result["reason"] == "stale"
    assert result["rows_added"] == 1
    assert result["max_date_after"] == "2026-07-04"


def test_catchup_kbo_fetch_error_isolated(tmp_path, monkeypatch):
    out = tmp_path / "kbo_results.parquet"
    _write_parquet(out, ["2026-07-01"])

    def broken(season, out_path=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "domains.baseball_kbo.ingest_kbo.ingest_season", broken
    )
    today = dt.date(2026, 7, 4)
    result = rck.catchup_kbo(out_path=out, today=today)
    assert result["refreshed"] is False
    assert result["reason"] == "fetch_error"
