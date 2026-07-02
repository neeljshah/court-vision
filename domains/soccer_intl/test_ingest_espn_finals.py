"""Per-file tests for ingest_espn_finals (offline; injected http_get)."""
from __future__ import annotations

import pandas as pd

from domains.soccer_intl import ingest_espn_finals as ief


def _ev(eid, home, away, hs, as_, status_name="STATUS_FULL_TIME", completed=True):
    return {
        "id": eid,
        "competitions": [{
            "status": {"type": {"name": status_name, "completed": completed}},
            "competitors": [
                {"homeAway": "home", "score": str(hs), "team": {"displayName": home}},
                {"homeAway": "away", "score": str(as_), "team": {"displayName": away}},
            ],
        }],
    }


def test_fetch_finals_keeps_only_completed():
    payload = {"events": [
        _ev("1", "Germany", "Paraguay", 1, 1, "STATUS_FINAL_PEN", True),
        _ev("2", "Brazil", "Japan", 0, 0, "STATUS_SCHEDULED", False),
    ]}
    rows = ief.fetch_finals("20260629", http_get=lambda url: payload)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "1"
    assert rows[0]["home_team"] == "Germany" and rows[0]["home_score"] == 1.0
    assert rows[0]["away_team"] == "Paraguay" and rows[0]["away_score"] == 1.0


def test_fetch_finals_skips_malformed_event():
    payload = {"events": [{"id": "3", "competitions": [{"status": {"type": {}},
               "competitors": [{"homeAway": "home", "score": "1",
                                 "team": {"displayName": "Spain"}}]}]}]}
    rows = ief.fetch_finals("20260629", http_get=lambda url: payload)
    assert rows == []  # only one side present -> unusable, never a fabricated 0-0


def test_ingest_range_writes_and_dedups(tmp_path):
    out = tmp_path / "espn_finals.parquet"
    payload_a = {"events": [_ev("10", "England", "Congo DR", 2, 1)]}
    ief.ingest_range(["20260701"], http_get=lambda url: payload_a, out_path=out)
    df1 = pd.read_parquet(out)
    assert len(df1) == 1 and df1.iloc[0]["home_score"] == 2.0

    # re-ingest with an UPDATED score for the same event_id -> dedup keeps the latest
    payload_b = {"events": [_ev("10", "England", "Congo DR", 3, 1)]}
    ief.ingest_range(["20260701"], http_get=lambda url: payload_b, out_path=out)
    df2 = pd.read_parquet(out)
    assert len(df2) == 1 and df2.iloc[0]["home_score"] == 3.0


def test_ingest_range_empty_day_is_a_noop(tmp_path):
    out = tmp_path / "espn_finals.parquet"
    ief.ingest_range(["20260101"], http_get=lambda url: {"events": []}, out_path=out)
    assert not out.exists()
