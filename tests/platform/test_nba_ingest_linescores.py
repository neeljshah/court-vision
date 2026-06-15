"""Per-file test for domains/basketball_nba/ingest_linescores.py (stubbed HTTP).

Run: python -m pytest tests/platform/test_nba_ingest_linescores.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba import ingest_linescores as mod


def _summary(home_q, away_q):
    return {"header": {"competitions": [{"competitors": [
        {"homeAway": "home", "team": {"abbreviation": "BOS"},
         "linescores": [{"displayValue": str(v)} for v in home_q]},
        {"homeAway": "away", "team": {"abbreviation": "LAL"},
         "linescores": [{"displayValue": str(v)} for v in away_q]},
    ]}]}}


def test_fetch_linescores_parses_quarters():
    got = mod.fetch_linescores("1", http_get=lambda url: _summary([30, 28, 25, 31], [27, 30, 29, 26]))
    assert got["home_abbr"] == "BOS" and got["away_abbr"] == "LAL"
    assert [got[f"home_q{q}"] for q in range(1, 5)] == [30.0, 28.0, 25.0, 31.0]


def test_overtime_folds_into_q4():
    got = mod.fetch_linescores("1", http_get=lambda url: _summary([30, 28, 25, 28, 12], [27, 30, 29, 25, 12]))
    assert got["home_q4"] == 40.0   # 28 regulation + 12 OT
    assert got["away_q4"] == 37.0


def test_incomplete_game_rejected():
    assert mod.fetch_linescores("1", http_get=lambda url: _summary([30, 28], [27, 30])) == {}
    assert mod.fetch_linescores("1", http_get=lambda url: {"header": {}}) == {}


def test_daterange():
    dr = mod._daterange("20260120", "20260122")
    assert dr == ["20260120", "20260121", "20260122"]


def test_ingest_range_writes(tmp_path):
    out = tmp_path / "ls.parquet"
    def _get(url):
        return ({"items": [{"event_id": "1", "date": "20260120"}]}
                if "scoreboard" in url else _summary([30, 28, 25, 31], [27, 30, 29, 26]))
    # fetch_scoreboard expects a specific shape; patch it directly for the test
    import domains.basketball_nba.ingest_linescores as m
    orig = m.fetch_scoreboard
    m.fetch_scoreboard = lambda date, http_get=None: [{"event_id": "1"}]
    try:
        m.ingest_range(["20260120"], http_get=_get, out_path=out)
    finally:
        m.fetch_scoreboard = orig
    df = pd.read_parquet(out)
    assert len(df) == 1 and df.iloc[0]["home_abbr"] == "BOS"
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
