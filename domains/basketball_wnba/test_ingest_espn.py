"""Per-file tests for ingest_espn (offline; injected http_get, fixture JSON).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_espn.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_wnba import ingest_espn as ie


def _ev(eid, home, away, hs, as_, status_name="STATUS_FINAL", completed=True,
        neutral=False):
    return {
        "id": eid,
        "competitions": [{
            "status": {"type": {"name": status_name, "completed": completed}},
            "neutralSite": neutral,
            "competitors": [
                {"homeAway": "home", "score": str(hs), "team": {"displayName": home}},
                {"homeAway": "away", "score": str(as_), "team": {"displayName": away}},
            ],
        }],
    }


def test_fetch_day_keeps_only_completed_and_labels_home_win():
    payload = {"events": [
        _ev("1", "Las Vegas Aces", "Indiana Fever", 88, 80),
        _ev("2", "Dallas Wings", "Connecticut Sun", 70, 75),
        _ev("3", "New York Liberty", "Atlanta Dream", 0, 0, "STATUS_SCHEDULED", False),
    ]}
    rows = ie.fetch_day("20260705", "2026", http_get=lambda url: payload)
    assert len(rows) == 2
    assert rows[0]["event_id"] == "1"
    assert rows[0]["home_team"] == "Las Vegas Aces" and rows[0]["home_score"] == 88.0
    assert rows[0]["home_win"] == 1.0
    assert rows[1]["home_win"] == 0.0  # home 70 < away 75


def test_fetch_day_skips_malformed_event():
    payload = {"events": [{"id": "9", "competitions": [{"status": {"type": {}},
               "competitors": [{"homeAway": "home", "score": "1",
                                 "team": {"displayName": "Seattle Storm"}}]}]}]}
    rows = ie.fetch_day("20260705", "2026", http_get=lambda url: payload)
    assert rows == []  # only one side present -> unusable, never a fabricated 0-0


def test_season_calendar_parses_yearly_calendar_index():
    payload = {"leagues": [{"calendar": [
        "2024-05-03T07:00Z", "2024-05-04T07:00Z", "2024-10-20T07:00Z",
    ]}]}
    dates = ie.season_calendar("2024", http_get=lambda url: payload)
    assert dates == ["20240503", "20240504", "20241020"]


def test_season_calendar_empty_when_no_leagues():
    dates = ie.season_calendar("1999", http_get=lambda url: {"leagues": []})
    assert dates == []


def test_ingest_season_writes_and_dedups(tmp_path):
    out = tmp_path / "espn_scoreboard.parquet"
    cal_payload = {"leagues": [{"calendar": ["2026-07-05T00:00Z"]}]}
    day_payload = {"events": [_ev("10", "Chicago Sky", "Phoenix Mercury", 60, 55)]}

    def http_get(url):
        return cal_payload if "dates=2026" in url and "202607" not in url else day_payload

    ie.ingest_season("2026", http_get=http_get, out_path=out)
    df1 = pd.read_parquet(out)
    assert len(df1) == 1 and df1.iloc[0]["home_score"] == 60.0

    # re-ingest with an UPDATED score for the same event_id -> dedup keeps the latest
    day_payload_updated = {"events": [_ev("10", "Chicago Sky", "Phoenix Mercury", 65, 55)]}

    def http_get2(url):
        return cal_payload if "dates=2026" in url and "202607" not in url else day_payload_updated

    ie.ingest_season("2026", http_get=http_get2, out_path=out)
    df2 = pd.read_parquet(out)
    assert len(df2) == 1 and df2.iloc[0]["home_score"] == 65.0


def test_ingest_season_dates_override_skips_calendar_call():
    calls = []

    def http_get(url):
        calls.append(url)
        return {"events": [_ev("20", "Minnesota Lynx", "Golden State Valkyries", 90, 85)]}

    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.parquet")
        ie.ingest_season("2026", http_get=http_get, out_path=out,
                          dates_override=["20260701"])
    # Only ONE call (the single date), no calendar-index call.
    assert len(calls) == 1
    assert "dates=20260701" in calls[0]


def test_ingest_seasons_multiple_years_accumulate(tmp_path):
    out = tmp_path / "multi.parquet"

    def http_get_factory(year, eid, home, away, hs, as_):
        cal = {"leagues": [{"calendar": [f"{year}-07-05T00:00Z"]}]}
        day = {"events": [_ev(eid, home, away, hs, as_)]}

        def http_get(url):
            return cal if f"dates={year}" == url.split("?")[-1] else day
        return http_get

    ie.ingest_season("2024", http_get=http_get_factory("2024", "a", "Team A", "Team B", 70, 60),
                      out_path=out)
    ie.ingest_season("2025", http_get=http_get_factory("2025", "b", "Team C", "Team D", 80, 75),
                      out_path=out)
    df = pd.read_parquet(out)
    assert len(df) == 2
    assert set(df["season"].tolist()) == {"2024", "2025"}


def test_ingest_season_empty_calendar_is_a_noop(tmp_path):
    out = tmp_path / "empty.parquet"
    ie.ingest_season("1999", http_get=lambda url: {"leagues": []}, out_path=out)
    assert not out.exists()
