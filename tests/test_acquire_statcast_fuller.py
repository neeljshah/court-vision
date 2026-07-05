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


def test_full_season_days_falls_back_to_calendar_range(monkeypatch):
    monkeypatch.setattr(F, "_PROBABLES_FP", F._REPO / "nonexistent_probables.parquet")
    days = F._full_season_days(2023)
    assert days[0] == "2023-03-30"
    assert days[-1] == "2023-10-01"
    assert len(days) == 186  # full calendar span, no schedule to skip off-days


def test_full_season_days_reads_real_schedule_and_skips_off_days(tmp_path, monkeypatch):
    dates = pd.to_datetime(
        ["2023-03-30", "2023-03-31", "2023-07-10", "2023-10-01", "2022-04-07"])
    fp = tmp_path / "probables.parquet"
    pd.DataFrame({"game_date": dates}).to_parquet(fp, index=False)
    monkeypatch.setattr(F, "_PROBABLES_FP", fp)
    days = F._full_season_days(2023)
    assert days == ["2023-03-30", "2023-03-31", "2023-07-10", "2023-10-01"]
    assert "2022-04-07" not in days  # season-filtered via _FULL_SEASON_BOUNDS


def test_acquire_season_fuller_full_season_uses_wider_day_list(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "_full_season_days", lambda season: ["2023-03-30", "2023-10-01"])

    def stub(day, timeout=90):
        return _fake_day(day)

    monkeypatch.setattr(F, "_day_csv_fuller", stub)

    def fake_acquire(season, days=18, delay_s=0.0, cache_dir=None, max_seconds=None,
                     full_season=False):
        all_days = F._full_season_days(season) if full_season else ["2023-05-01"]
        return {"df": pd.concat([stub(d) for d in all_days], ignore_index=True),
                "days_requested": len(all_days), "days_fetched_this_run": len(all_days),
                "days_available_total": len(all_days), "capped": False}

    monkeypatch.setattr(F, "acquire_season_fuller", fake_acquire)
    res = F.run_season_fuller(2023, full_season=True, cache_dir=tmp_path)
    assert res["days_requested"] == 2  # the wide 2-day stub list, not the 1-day default


def test_materialize_includes_all_cached_days_even_past_budget_cap(tmp_path, monkeypatch):
    """REGRESSION for the wave-39/wave-40 stranded-checkpoint bug: acquire_season_fuller
    must MATERIALIZE every already-cached day in raw_days_fuller/, even ones that sit
    AFTER the day a wall-clock budget cap breaks the FETCH loop on. Pre-fix, the single
    fetch+collect loop would `break` at the capped day and never read back any cache file
    for days later in all_days -- silently dropping rows that were sitting on disk the
    whole time. This test pre-populates cache files for days 1, 3, and 5 (day 2 and 4
    intentionally UNCACHED so the run must fetch them), caps max_seconds at ~0 so the
    fetch loop caps out immediately at day 2, and asserts the day-5 (post-cap) cached
    file is still present in the output -- this MUST fail on the pre-fix implementation."""
    monkeypatch.setattr(F, "_WINDOWS", {2023: ["2023-05-01"]})
    all_days = ["2023-05-01", "2023-05-02", "2023-05-03", "2023-05-04", "2023-05-05"]
    monkeypatch.setattr(F, "_date_range", lambda start, n: all_days)

    raw_dir = tmp_path / "raw_days_fuller"
    raw_dir.mkdir(parents=True)
    # pre-cache day 1, day 3, and day 5 (day 5 is the one AFTER where the cap will bite)
    for day in ("2023-05-01", "2023-05-03", "2023-05-05"):
        fp = raw_dir / f"day__{day}.parquet"
        _fake_day(day).to_parquet(fp, index=False)

    def slow_stub(day, timeout=90):
        raise AssertionError("fetch must not run once the budget is already exhausted")

    monkeypatch.setattr(F, "_day_csv_fuller", slow_stub)
    # a negative max_seconds means the budget is exhausted BEFORE the first uncached
    # day (2023-05-02) is even attempted, so the fetch loop caps immediately without
    # ever reaching day 5 via fetch (and _day_csv_fuller must never be called).
    acq = F.acquire_season_fuller(2023, days=5, delay_s=0.0, cache_dir=tmp_path,
                                  max_seconds=-1.0)
    assert acq["capped"] is True
    got_dates = set(pd.to_datetime(acq["df"]["game_date"]).dt.strftime("%Y-%m-%d"))
    # day 5 was cached on disk BEFORE this run and must be materialized regardless of
    # the budget cap breaking the fetch walk at day 2.
    assert "2023-05-05" in got_dates, (
        "cached day AFTER the budget-capped day was stranded -- materialize must "
        "include every cached day unconditionally"
    )
    assert "2023-05-01" in got_dates
    assert "2023-05-03" in got_dates
    # day 2 and day 4 were never cached and the fetch loop capped before fetching them.
    assert "2023-05-02" not in got_dates
    assert "2023-05-04" not in got_dates


def test_cli_priority_flag_defaults_to_2023_first(monkeypatch):
    seen = {}

    def fake_run_all(seasons=(2022, 2023), days=18, max_seconds=None, full_season=False):
        seen["seasons"] = seasons
        return {"verdict": "MATERIALIZED"}

    monkeypatch.setattr(F, "run_all", fake_run_all)
    F._main([])
    assert seen["seasons"] == [2023, 2022]
