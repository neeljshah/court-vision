"""Per-file tests for wnba_outcome_resolver (offline; synthetic scoreboard frame).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_wnba_outcome_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ingame import wnba_outcome_resolver as wr


def _frame():
    return pd.DataFrame([
        {"event_id": "1", "date": "2026-07-05", "home_team": "Chicago Sky",
         "away_team": "Las Vegas Aces", "home_score": 88.0, "away_score": 81.0,
         "home_win": 1.0, "status_name": "STATUS_FINAL"},
        {"event_id": "2", "date": "2026-07-06", "home_team": "New York Liberty",
         "away_team": "Golden State Valkyries", "home_score": 70.0,
         "away_score": 90.0, "home_win": 0.0, "status_name": "STATUS_FINAL"},
        {"event_id": "3", "date": "2026-07-07", "home_team": "Seattle Storm",
         "away_team": "Dallas Wings", "home_score": 75.0, "away_score": 75.0,
         "home_win": 0.0, "status_name": "STATUS_IN_PROGRESS"},  # not final
    ])


def test_parse_wnba_ticker_shape():
    parsed = wr.parse_wnba_ticker("KXWNBAGAME-26JUL051930LVACHI")
    assert parsed is not None
    date, tail, _ = parsed
    assert date.year == 2026 and date.month == 7 and date.day == 5
    assert tail == "LVACHI"


def test_parse_wnba_ticker_bad_input_returns_none():
    assert wr.parse_wnba_ticker("NOT-A-TICKER") is None
    assert wr.parse_wnba_ticker("") is None


def test_home_win_resolves_real_game():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    assert res.available
    assert res.home_win("KXWNBAGAME-26JUL051930LVACHI") == 1  # Chicago (home) won


def test_home_win_away_win():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    assert res.home_win("KXWNBAGAME-26JUL061930GSVNYL") == 0  # away (GSV) won


def test_home_win_unresolvable_ticker_returns_none():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    assert res.home_win("KXWNBAGAME-26JUL051930ZZZQQQ") is None
    assert res.home_win("garbage") is None


def test_home_win_not_final_game_returns_none():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    # Seattle/Dallas game is STATUS_IN_PROGRESS -> filtered out of _final entirely.
    assert res.home_win("KXWNBAGAME-26JUL071930DALSEA") is None


def test_final_score_resolves_tie():
    df = _frame().copy()
    df.loc[2, "status_name"] = "STATUS_FINAL"
    res = wr.WnbaOutcomeResolver(scoreboard_df=df)
    score = res.final_score("KXWNBAGAME-26JUL071930DALSEA")
    assert score == (75, 75)
    # a tie is not a valid binary home_win label
    assert res.home_win("KXWNBAGAME-26JUL071930DALSEA") is None


def test_resolver_inert_on_missing_parquet(tmp_path):
    res = wr.WnbaOutcomeResolver(scoreboard_parquet=tmp_path / "missing.parquet")
    assert res.available is False
    assert res.home_win("KXWNBAGAME-26JUL051930LVACHI") is None


def test_never_raises_on_malformed_ticker():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    for bad in (None, 12345, "", "KXWNBAGAME-", "KXWNBAGAME-99XXX99AAA"):
        try:
            assert res.home_win(bad) is None  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            pytest.fail("home_win raised on %r: %s" % (bad, exc))
