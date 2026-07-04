"""Per-file tests for hist_mlb_outcome_resolver.py (LANE 3 sub-task B).

Hermetic synthetic fixtures for parse_mlb_ticker + MlbTickerOutcomeResolver;
no network. A real-parquet smoke test is included but SKIPPED (not failed) if
data/domains/mlb/espn_boxscores.parquet is absent (gitignored data/ dir).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_hist_mlb_outcome_resolver.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    DEFAULT_BOXSCORE_PARQUET,
    MlbTickerOutcomeResolver,
    parse_mlb_ticker,
)


def test_parse_mlb_ticker_basic():
    parsed = parse_mlb_ticker("KXMLBGAME-26JUL011235CWSBAL")
    assert parsed is not None
    date, tail = parsed
    assert date == dt.date(2026, 7, 1)
    assert tail == "CWSBAL"


def test_parse_mlb_ticker_with_side_suffix():
    parsed = parse_mlb_ticker("KXMLBGAME-26JUN281340AZTB-TB")
    assert parsed is not None
    date, tail = parsed
    assert date == dt.date(2026, 6, 28)
    assert tail.startswith("AZTB")


def test_parse_mlb_ticker_malformed_returns_none():
    assert parse_mlb_ticker("NOT-A-TICKER") is None
    assert parse_mlb_ticker("") is None
    assert parse_mlb_ticker("KXMLBGAME-26XXX011235CWSBAL") is None  # bad month


def _synthetic_boxscores() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-07-01", "home_abbr": "BAL", "away_abbr": "CHW",
         "home_score": 5.0, "away_score": 3.0, "status": "STATUS_FINAL"},
        {"date": "2026-07-01", "home_abbr": "ARI", "away_abbr": "SF",
         "home_score": 2.0, "away_score": 2.0, "status": "STATUS_FINAL"},  # tie
        {"date": "2026-07-02", "home_abbr": "TB", "away_abbr": "KC",
         "home_score": 1.0, "away_score": 6.0, "status": "STATUS_IN_PROGRESS"},
    ])


def test_resolver_resolves_with_abbr_override():
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    assert r.available
    # CWS (Kalshi) -> CHW (ESPN) override; away=CWS, home=BAL, BAL won.
    assert r.home_win("KXMLBGAME-26JUL011235CWSBAL") == 1


def test_resolver_returns_none_for_tie():
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    # AZ (Kalshi) -> ARI (ESPN) override; ARI vs SF is a tie in fixture -> None.
    assert r.home_win("KXMLBGAME-26JUL011500AZSF") is None


def test_resolver_returns_none_for_non_final_game():
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    assert r.home_win("KXMLBGAME-26JUL021940TBKC") is None  # STATUS_IN_PROGRESS excluded


def test_resolver_returns_none_for_unresolvable_ticker():
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    assert r.home_win("garbage-ticker") is None


def test_resolver_inert_without_data():
    empty = pd.DataFrame(columns=["date", "home_abbr", "away_abbr", "home_score",
                                   "away_score", "status"])
    r = MlbTickerOutcomeResolver(boxscore_df=empty)
    assert not r.available
    assert r.home_win("KXMLBGAME-26JUL011235CWSBAL") is None


def test_real_corpus_smoke():
    if not DEFAULT_BOXSCORE_PARQUET.exists():
        pytest.skip("local MLB boxscore corpus absent (gitignored data/ dir)")
    r = MlbTickerOutcomeResolver()
    assert isinstance(r.available, bool)
    # A garbage ticker must never raise regardless of corpus state.
    assert r.home_win("not-a-real-ticker") is None
