"""Per-file test for the BROADER Statcast pull (NO network -- stubs the per-day fetch).

Verifies:
  (1) _day_csv_fuller keeps only requested cols present in the raw response (honest
      subsetting, same pattern as the base _day_csv).
  (2) acquire_season_fuller is per-day cached + idempotent under raw_days_fuller/ (does
      not touch the narrower sample's raw_days/ namespace).
  (3) max_seconds caps a run and reports capped=True + partial progress honestly.
  (4) run_season_fuller writes a parquet + honest coverage report (obtained vs missing,
      per-column non-null pct).
  (5) run_all writes the JSON materialization report with the expected keys.

CLI: python -m pytest tests/test_acquire_statcast_fuller.py -q
"""
from __future__ import annotations

import json

import pandas as pd

import domains.mlb.acquire_statcast_fuller as F


def _fake_day(day: str, with_new_cols: bool = True) -> pd.DataFrame:
    base = {
        "game_pk": [1, 1], "game_date": [day, day], "inning": [1, 1],
        "inning_topbot": ["Top", "Top"], "at_bat_number": [1, 1],
        "pitch_number": [1, 2], "pitcher": [100, 100], "batter": [200, 200],
        "events": ["", "strikeout"], "release_speed": [92.0, 93.0],
        "release_spin_rate": [2200.0, 2300.0],
        "estimated_woba_using_speedangle": [0.3, 0.0], "pitch_type": ["FF", "SL"],
        "balls": [0, 1], "strikes": [0, 2], "outs_when_up": [0, 0],
        "home_team": ["NYY", "NYY"], "away_team": ["BOS", "BOS"],
        "home_score": [0, 0], "away_score": [0, 0], "bat_score": [0, 0],
        "post_home_score": [0, 0], "post_away_score": [0, 0],
        "launch_speed": [None, None],
    }
    if with_new_cols:
        base.update({
            "zone": [5, 9], "type": ["B", "S"], "des": ["ball", "called_strike"],
            "fielder_2": [300, 300], "stand": ["R", "R"], "p_throws": ["L", "L"],
            "if_fielding_alignment": ["Standard", "Standard"],
            "of_fielding_alignment": ["Standard", "Standard"],
            "plate_x": [0.1, -0.2], "plate_z": [2.5, 2.6],
            "sz_top": [3.4, 3.4], "sz_bot": [1.5, 1.5],
        })
    return pd.DataFrame(base)


def test_day_csv_fuller_subsets_columns(monkeypatch):
    import io
    import requests

    class _Resp:
        status_code = 200
        content = b"x" * 300
        text = _fake_day("2023-05-01").to_csv(index=False)

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    df = F._day_csv_fuller("2023-05-01")
    assert df is not None
    assert "zone" in df.columns and "fielder_2" in df.columns
    assert set(df.columns) <= set(F._KEEP)


def test_acquire_season_fuller_caches_and_is_idempotent(tmp_path, monkeypatch):
    calls = []

    def stub(day, timeout=90):
        calls.append(day)
        return _fake_day(day)

    monkeypatch.setattr(F, "_day_csv_fuller", stub)
    monkeypatch.setattr(F, "_WINDOWS", {2023: ["2023-05-01"]})
    acq1 = F.acquire_season_fuller(2023, days=2, delay_s=0.0, cache_dir=tmp_path)
    assert not acq1["df"].empty
    assert acq1["days_fetched_this_run"] == 2
    raw_fuller = tmp_path / "raw_days_fuller"
    assert raw_fuller.exists()
    assert not (tmp_path / "raw_days").exists()  # separate namespace, untouched
    n_calls_after_first = len(calls)
    acq2 = F.acquire_season_fuller(2023, days=2, delay_s=0.0, cache_dir=tmp_path)
    assert acq2["days_fetched_this_run"] == 0  # idempotent, no re-fetch
    assert len(calls) == n_calls_after_first


def test_acquire_season_fuller_respects_max_seconds(tmp_path, monkeypatch):
    def slow_stub(day, timeout=90):
        import time
        time.sleep(0.05)
        return _fake_day(day)

    monkeypatch.setattr(F, "_day_csv_fuller", slow_stub)
    monkeypatch.setattr(F, "_WINDOWS", {2023: ["2023-05-01"]})
    acq = F.acquire_season_fuller(2023, days=100, delay_s=0.0, cache_dir=tmp_path,
                                  max_seconds=0.12)
    assert acq["capped"] is True
    assert acq["days_fetched_this_run"] < 100


def test_run_season_fuller_writes_parquet_and_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "_day_csv_fuller", lambda day, timeout=90: _fake_day(day))
    monkeypatch.setattr(F, "_WINDOWS", {2023: ["2023-05-01"]})
    res = F.run_season_fuller(2023, days=1, cache_dir=tmp_path)
    assert res["status"] == "OK"
    assert "zone" in res["cols_obtained"]
    out = pd.read_parquet(res["raw_parquet"])
    assert "fielder_2" in out.columns
    cov = res["coverage"]
    assert cov["zone"]["obtained"] is True
    assert cov["zone"]["coverage_pct"] == 100.0


def test_run_season_fuller_reports_missing_columns_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "_day_csv_fuller",
                        lambda day, timeout=90: _fake_day(day, with_new_cols=False))
    monkeypatch.setattr(F, "_WINDOWS", {2023: ["2023-05-01"]})
    res = F.run_season_fuller(2023, days=1, cache_dir=tmp_path)
    assert res["status"] == "OK"
    assert "zone" not in res["cols_obtained"]
    assert res["coverage"]["zone"]["obtained"] is False
    assert res["coverage"]["zone"]["coverage_pct"] == 0.0


def test_run_all_writes_json_report(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "_day_csv_fuller", lambda day, timeout=90: _fake_day(day))
    monkeypatch.setattr(F, "_WINDOWS", {2022: ["2022-05-02"], 2023: ["2023-05-01"]})
    monkeypatch.setattr(F, "_CACHE", tmp_path)
    report_fp = tmp_path / "statcast_fuller_report.json"
    monkeypatch.setattr(F, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(F, "_REPORT_FP", report_fp)
    res = F.run_all(seasons=[2022, 2023], days=1)
    assert res["verdict"] in {"MATERIALIZED", "PARTIAL_CAPPED"}
    assert report_fp.exists()
    loaded = json.loads(report_fp.read_text(encoding="ascii"))
    assert loaded["cols_requested"] == list(F._NEW_COLS.keys())
    assert "2022" in loaded["seasons"] and "2023" in loaded["seasons"]
