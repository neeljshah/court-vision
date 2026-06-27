"""Per-file test for the bounded ESPN-overlap Statcast acquisition (NO network).

Stubs the per-day fetch so no HTTP happens. Verifies:
  (1) espn_base_dates reads the ESPN base's own dates (or [] honestly when absent).
  (2) acquire_dates is per-day cached + idempotent and re-fetches a slim cached day that
      lacks score cols (so the wider score-bearing _KEEP lands).
  (3) run_overlap writes a season overlap parquet WITH the score cols, or TIER3_BLOCKED
      honestly when no ESPN base is present.

CLI: python -m pytest tests/test_acquire_statcast_overlap.py -q
"""
from __future__ import annotations

import pandas as pd

import domains.mlb.acquire_statcast_overlap as O


def _fake_day(day: str):
    return pd.DataFrame({
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
    })


def test_overlap_no_espn_base_is_blocked(tmp_path, monkeypatch):
    # point the ESPN base lookup at an empty repo subtree -> no base -> blocked
    monkeypatch.setattr(O, "espn_base_dates", lambda season: [])
    res = O.run_overlap(2099, cache_dir=tmp_path)
    assert res["status"] == "TIER3_BLOCKED"
    assert res["reason"] == "NO_ESPN_BASE_ON_DISK"


def test_acquire_dates_caches_and_includes_scores(tmp_path, monkeypatch):
    calls = []

    def stub(day, timeout=90):
        calls.append(day)
        return _fake_day(day)

    monkeypatch.setattr(O, "_day_csv", stub)
    dates = ["2022-04-07", "2022-04-08"]
    df1 = O.acquire_dates(dates, 2022, delay_s=0.0, cache_dir=tmp_path)
    assert not df1.empty
    assert "home_score" in df1.columns and "post_away_score" in df1.columns
    assert len(calls) == 2  # fetched both days
    # second call: both days cached + score-bearing -> no new fetch
    df2 = O.acquire_dates(dates, 2022, delay_s=0.0, cache_dir=tmp_path)
    assert len(calls) == 2  # idempotent, no re-fetch
    assert len(df2) == len(df1)


def test_run_overlap_writes_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "espn_base_dates", lambda season: ["2022-04-07"])
    monkeypatch.setattr(O, "_day_csv", lambda day, timeout=90: _fake_day(day))
    res = O.run_overlap(2022, cache_dir=tmp_path)
    assert res["status"] == "OK"
    assert "home_score" in res["score_cols"]
    out = pd.read_parquet(res["raw_parquet"])
    assert "post_home_score" in out.columns
