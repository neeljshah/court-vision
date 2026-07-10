"""Per-file test for domains.basketball_nba.backfill_box_espn -- schema +
resumability, mocked http_get, no network, no real corpus reads/writes
(tmp_path only).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_backfill_box_espn.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.backfill_box_espn import _season_dates, backfill

_SCOREBOARD = {"20241101": {"events": [{"id": "401704698", "name": "BOS at CHA"}]}}

_SUMMARY = {
    "401704698": {
        "header": {"competitions": [{
            "status": {"type": {"name": "STATUS_FINAL"}},
            "competitors": [
                {"homeAway": "home", "team": {"id": "18", "abbreviation": "CHA"}, "score": "109"},
                {"homeAway": "away", "team": {"id": "2", "abbreviation": "BOS"}, "score": "124"},
            ],
        }]},
        "boxscore": {"teams": [
            {"homeAway": "home", "team": {"abbreviation": "CHA"}, "statistics": [
                {"name": "fastBreakPoints", "displayValue": "6"},
                {"name": "pointsInPaint", "displayValue": "44"},
            ]},
            {"homeAway": "away", "team": {"abbreviation": "BOS"}, "statistics": [
                {"name": "fastBreakPoints", "displayValue": "21"},
                {"name": "pointsInPaint", "displayValue": "56"},
            ]},
        ]},
    },
}


def _fake_getter(calls: list):
    def _get(url: str) -> dict:
        calls.append(url)
        if "scoreboard" in url:
            date = url.rsplit("=", 1)[-1]
            return _SCOREBOARD.get(date, {"events": []})
        eid = url.rsplit("=", 1)[-1]
        return _SUMMARY.get(eid, {})
    return _get


def _games_parquet(tmp_path):
    fp = tmp_path / "games.parquet"
    pd.DataFrame({
        "game_id": ["1"], "date": [pd.Timestamp("2024-11-01")], "season": ["2024-25"],
    }).to_parquet(fp, index=False)
    return fp


def test_season_dates(tmp_path):
    fp = _games_parquet(tmp_path)
    assert _season_dates("2024-25", games_parquet=fp) == ["20241101"]
    assert _season_dates("2099-00", games_parquet=fp) == []


def test_backfill_schema_and_write(tmp_path):
    games_fp = _games_parquet(tmp_path)
    out = tmp_path / "espn_boxscores_2024_25.parquet"
    calls: list = []
    c = backfill("2024-25", out, http_get=_fake_getter(calls), games_parquet=games_fp)

    assert c == {"dates_done": 1, "games_written": 1, "games_empty": 0}
    assert out.exists()
    df = pd.read_parquet(out)
    assert len(df) == 1
    assert df.loc[0, "event_id"] == "401704698"
    assert df.loc[0, "home_fast_break_pts"] == 6.0
    assert df.loc[0, "away_paint_pts"] == 56.0
    # never touches the live capture file's naming
    assert out.name != "espn_boxscores.parquet"


def test_backfill_resumable_skips_done_dates(tmp_path):
    games_fp = _games_parquet(tmp_path)
    out = tmp_path / "espn_boxscores_2024_25.parquet"

    calls_1: list = []
    backfill("2024-25", out, http_get=_fake_getter(calls_1), games_parquet=games_fp)
    n_calls_first_run = len(calls_1)
    assert n_calls_first_run > 0

    state_fp = out.with_name(out.stem + "_state.json")
    assert state_fp.exists()
    assert json.loads(state_fp.read_text())["done_dates"] == ["20241101"]

    # second run: same date already checkpointed -> zero new fetches
    calls_2: list = []
    c2 = backfill("2024-25", out, http_get=_fake_getter(calls_2), games_parquet=games_fp)
    assert calls_2 == []
    assert c2 == {"dates_done": 0, "games_written": 0, "games_empty": 0}
    # existing row still there, no duplication
    df = pd.read_parquet(out)
    assert len(df) == 1


def test_backfill_empty_summary_counted(tmp_path):
    games_fp = _games_parquet(tmp_path)
    out = tmp_path / "espn_boxscores_2024_25.parquet"

    def _empty_getter(url: str) -> dict:
        if "scoreboard" in url:
            return {"events": [{"id": "999", "name": "x"}]}
        return {}  # malformed/missing summary -> fetch_box parses to {}

    c = backfill("2024-25", out, http_get=_empty_getter, games_parquet=games_fp)
    assert c == {"dates_done": 1, "games_written": 0, "games_empty": 1}
    # no rows written -> no parquet created (mirrors ingest_espn_box's empty-df skip)
    assert not out.exists()
