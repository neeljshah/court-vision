"""Tests for scripts.platformkit.venue_history.espn_tipoff_backfill.
Offline synthetic fixtures only -- no live network calls."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.venue_history import espn_tipoff_backfill as etb


def _espn_doc(yyyymmdd: str, home: str, away: str, iso_utc: str) -> dict:
    return {
        "events": [{
            "date": iso_utc,
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home}},
                    {"homeAway": "away", "team": {"displayName": away}},
                ]
            }],
        }]
    }


def test_dates_needed_from_pm_pilot_extracts_unique_leading_dates(tmp_path: Path) -> None:
    pm_dir = tmp_path / "pm23"
    pm_dir.mkdir()
    (pm_dir / "2023-02-23_nba-dailies-2023-02-23.jsonl").write_text("{}\n", encoding="utf-8")
    (pm_dir / "2023-02-24_nba-dailies-2023-02-24.jsonl").write_text("{}\n", encoding="utf-8")
    (pm_dir / "_progress.json").write_text("{}", encoding="utf-8")  # not a date-named file
    dates = etb.dates_needed_from_pm_pilot(pm_dir)
    assert dates == ["20230223", "20230224"]


def test_ensure_cached_is_idempotent_and_never_refetches(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "espn_cache"
    calls = []

    def fake_fetch(yyyymmdd):
        calls.append(yyyymmdd)
        return _espn_doc(yyyymmdd, "Boston Celtics", "Miami Heat", "2024-11-16T00:00Z")

    monkeypatch.setattr(etb, "_fetch_scoreboard", fake_fetch)
    counts1 = etb.ensure_cached(["20241115"], cache_dir=cache_dir, pace_sec=0.0)
    assert counts1 == {"fetched": 1, "already_cached": 0, "fetch_failed": 0}
    assert len(calls) == 1

    counts2 = etb.ensure_cached(["20241115"], cache_dir=cache_dir, pace_sec=0.0)
    assert counts2 == {"fetched": 0, "already_cached": 1, "fetch_failed": 0}
    assert len(calls) == 1  # no re-fetch


def test_ensure_cached_counts_fetch_failure_honestly(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "espn_cache2"
    monkeypatch.setattr(etb, "_fetch_scoreboard", lambda yyyymmdd: None)
    counts = etb.ensure_cached(["20230101"], cache_dir=cache_dir, pace_sec=0.0)
    assert counts == {"fetched": 0, "already_cached": 0, "fetch_failed": 1}
    assert not (cache_dir / "20230101.json").exists()


def test_espn_commence_index_loads_home_away_and_matches(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    doc = _espn_doc("20230223", "Indiana Pacers", "Boston Celtics", "2023-02-23T23:00Z")
    (cache_dir / "20230223.json").write_text(json.dumps(doc), encoding="utf-8")

    idx = etb.EspnCommenceIndex.load(cache_dir)
    assert idx.n_events == 1
    m = idx.match("2023-02-23", "Pacers", "Celtics")
    assert m == datetime(2023, 2, 23, 23, 0, tzinfo=timezone.utc)
    assert idx.match("2023-02-23", "Lakers", "Warriors") is None


def test_espn_commence_index_skips_events_missing_home_or_away(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache_bad"
    cache_dir.mkdir()
    bad_doc = {"events": [{"date": "2023-02-23T23:00Z", "competitions": [{"competitors": []}]}]}
    (cache_dir / "20230223.json").write_text(json.dumps(bad_doc), encoding="utf-8")
    idx = etb.EspnCommenceIndex.load(cache_dir)
    assert idx.n_events == 0


def test_backfill_2023_pilot_end_to_end_report(tmp_path: Path, monkeypatch) -> None:
    pm_dir = tmp_path / "pm23"
    pm_dir.mkdir()
    (pm_dir / "2023-02-23_nba-dailies-2023-02-23.jsonl").write_text("{}\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(
        etb, "_fetch_scoreboard",
        lambda yyyymmdd: _espn_doc(yyyymmdd, "Indiana Pacers", "Boston Celtics", "2023-02-23T23:00Z"))

    rep = etb.backfill_2023_pilot(pm_dir=pm_dir, cache_dir=cache_dir, pace_sec=0.0)
    assert rep["n_dates_needed"] == 1
    assert rep["fetched"] == 1
    assert rep["n_events_indexed"] == 1
