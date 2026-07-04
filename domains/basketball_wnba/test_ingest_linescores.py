"""Per-file tests for ingest_linescores (offline; injected http_get, fixture JSON).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_linescores.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_wnba import ingest_linescores as il


def _ls(q1, q2, q3, q4):
    return [{"value": q1}, {"value": q2}, {"value": q3}, {"value": q4}]


def _ev(eid, home, away, home_q, away_q, hs=None, as_=None,
        status_name="STATUS_FINAL", completed=True):
    hs = hs if hs is not None else sum(home_q)
    as_ = as_ if as_ is not None else sum(away_q)
    return {
        "id": eid,
        "competitions": [{
            "status": {"type": {"name": status_name, "completed": completed}},
            "competitors": [
                {"homeAway": "home", "score": str(hs), "team": {"displayName": home},
                 "linescores": _ls(*home_q)},
                {"homeAway": "away", "score": str(as_), "team": {"displayName": away},
                 "linescores": _ls(*away_q)},
            ],
        }],
    }


def test_fetch_day_linescores_builds_checkpoint_row():
    payload = {"events": [
        _ev("1", "Las Vegas Aces", "Indiana Fever", [22, 24, 20, 22], [18, 20, 22, 20]),
    ]}
    rows = il.fetch_day_linescores("20260705", "2026", http_get=lambda url: payload)
    assert len(rows) == 1
    r = rows[0]
    assert r["event_id"] == "1"
    assert r["home_end_q1"] == 22.0 and r["away_end_q1"] == 18.0
    assert r["home_half"] == 46.0 and r["away_half"] == 38.0
    assert r["home_end_q3"] == 66.0 and r["away_end_q3"] == 60.0
    assert r["home_score"] == 88.0 and r["away_score"] == 80.0
    assert r["home_win"] == 1.0


def test_fetch_day_linescores_skips_not_completed():
    payload = {"events": [
        _ev("2", "Dallas Wings", "Connecticut Sun", [10, 10, 10, 10], [10, 10, 10, 10],
            status_name="STATUS_SCHEDULED", completed=False),
    ]}
    rows = il.fetch_day_linescores("20260705", "2026", http_get=lambda url: payload)
    assert rows == []


def test_fetch_day_linescores_skips_malformed_period_count():
    payload = {"events": [{
        "id": "3",
        "competitions": [{
            "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
            "competitors": [
                {"homeAway": "home", "score": "50", "team": {"displayName": "Seattle Storm"},
                 "linescores": _ls(10, 10, 10, 10)[:3]},  # only 3 periods -- malformed
                {"homeAway": "away", "score": "48", "team": {"displayName": "Phoenix Mercury"},
                 "linescores": _ls(10, 10, 10, 10)},
            ],
        }],
    }]}
    rows = il.fetch_day_linescores("20260705", "2026", http_get=lambda url: payload)
    assert rows == []  # one side incomplete -> never faked/interpolated


def test_fetch_day_linescores_skips_missing_side():
    payload = {"events": [{
        "id": "4",
        "competitions": [{
            "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
            "competitors": [
                {"homeAway": "home", "score": "50", "team": {"displayName": "Seattle Storm"},
                 "linescores": _ls(10, 10, 10, 20)},
            ],
        }],
    }]}
    rows = il.fetch_day_linescores("20260705", "2026", http_get=lambda url: payload)
    assert rows == []


def test_ingest_season_linescores_writes_parquet(tmp_path):
    out = tmp_path / "linescores.parquet"
    payload_by_date = {
        "20260705": {"events": [
            _ev("10", "Aces", "Fever", [20, 20, 20, 20], [18, 18, 18, 18]),
        ]},
        "20260706": {"events": [
            _ev("11", "Wings", "Sun", [15, 15, 15, 15], [20, 20, 20, 20]),
        ]},
    }

    def fake_http_get(url):
        for date, payload in payload_by_date.items():
            if date in url:
                return payload
        return {}

    dest = il.ingest_season_linescores(
        "2026", http_get=fake_http_get, out_path=out,
        dates_override=["20260705", "20260706"],
    )
    df = pd.read_parquet(dest)
    assert len(df) == 2
    assert set(df["event_id"]) == {"10", "11"}
    assert set(il.LINESCORE_COLS).issubset(set(df.columns))


def test_ingest_season_linescores_dedups_on_rerun(tmp_path):
    out = tmp_path / "linescores.parquet"
    payload = {"events": [_ev("20", "Liberty", "Dream", [10, 10, 10, 10], [8, 8, 8, 8])]}

    il.ingest_season_linescores("2026", http_get=lambda url: payload, out_path=out,
                                 dates_override=["20260710"])
    il.ingest_season_linescores("2026", http_get=lambda url: payload, out_path=out,
                                 dates_override=["20260710"])
    df = pd.read_parquet(out)
    assert len(df) == 1  # re-run does not duplicate the same event_id


def test_ingest_seasons_linescores_merges_multiple_years(tmp_path):
    out = tmp_path / "linescores.parquet"
    p2024 = {"events": [_ev("30", "Aces", "Fever", [10, 10, 10, 10], [8, 8, 8, 8])]}
    p2025 = {"events": [_ev("31", "Wings", "Sun", [12, 12, 12, 12], [9, 9, 9, 9])]}

    def fake_http_get(url):
        if "20240501" in url:
            return p2024
        if "20250501" in url:
            return p2025
        return {}

    # ingest_seasons_linescores calls season_calendar (no override param), so
    # inject the calendar via the same http_get: the yearly query must return
    # a leagues[0].calendar payload for season_calendar's own call.
    def full_http_get(url):
        if url.endswith("dates=2024"):
            return {"leagues": [{"calendar": ["2024-05-01T07:00Z"]}]}
        if url.endswith("dates=2025"):
            return {"leagues": [{"calendar": ["2025-05-01T07:00Z"]}]}
        return fake_http_get(url)

    dest = il.ingest_seasons_linescores(["2024", "2025"], http_get=full_http_get, out_path=out)
    df = pd.read_parquet(dest)
    assert len(df) == 2
    assert set(df["season"]) == {"2024", "2025"}
