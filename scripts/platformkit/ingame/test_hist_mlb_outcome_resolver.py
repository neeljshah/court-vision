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
    date, tail, gnum = parsed
    assert date == dt.date(2026, 7, 1)
    assert tail == "CWSBAL"
    assert gnum is None


def test_parse_mlb_ticker_with_side_suffix():
    parsed = parse_mlb_ticker("KXMLBGAME-26JUN281340AZTB-TB")
    assert parsed is not None
    date, tail, gnum = parsed
    assert date == dt.date(2026, 6, 28)
    assert tail.startswith("AZTB")
    assert gnum is None


def test_parse_mlb_ticker_doubleheader_suffix_stripped():
    # Real shape captured 2026-07-07: KXMLBGAME-26JUL071415MILSTLG1 / ...G2.
    p1 = parse_mlb_ticker("KXMLBGAME-26JUL071415MILSTLG1")
    p2 = parse_mlb_ticker("KXMLBGAME-26JUL071945MILSTLG2")
    assert p1 is not None and p2 is not None
    date1, tail1, gnum1 = p1
    date2, tail2, gnum2 = p2
    assert date1 == date2 == dt.date(2026, 7, 7)
    # The trailing G<n> must NOT bleed into the team tail (the pre-fix bug).
    assert tail1 == tail2 == "MILSTL"
    assert gnum1 == 1
    assert gnum2 == 2


def test_parse_mlb_ticker_sfg_abbr_keeps_its_g():
    # A real team code ending in "G" (SFG, Kalshi shorthand for SF) must never
    # lose its G to the doubleheader group when there is NO trailing digit.
    parsed = parse_mlb_ticker("KXMLBGAME-26JUL011235SFGATL")
    assert parsed is not None
    _date, tail, gnum = parsed
    assert tail == "SFGATL"
    assert gnum is None


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


def _doubleheader_boxscores() -> pd.DataFrame:
    # Real slate 2026-07-07: MIL@STL doubleheader. G1 (earlier start_time) MIL
    # won 3-2; G2 (later start_time) STL won 6-1 -- the two games have OPPOSITE
    # winners, so a mis-keyed lookup is guaranteed to disagree with one of them.
    return pd.DataFrame([
        {"date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 2.0, "away_score": 3.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T14:15:00Z"},   # G1: away (MIL) won
        {"date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 6.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T19:45:00Z"},   # G2: home (STL) won
    ])


def test_resolver_doubleheader_g1_g2_resolve_independently():
    r = MlbTickerOutcomeResolver(boxscore_df=_doubleheader_boxscores())
    assert r.available
    # G1 ticker -> away (MIL) won -> home_win == 0.
    assert r.home_win("KXMLBGAME-26JUL071415MILSTLG1") == 0
    # G2 ticker -> home (STL) won -> home_win == 1. Pre-fix, the dict-overwrite
    # bug made these two calls return the SAME (wrong-for-one-game) answer.
    assert r.home_win("KXMLBGAME-26JUL071945MILSTLG2") == 1


def test_resolver_doubleheader_no_gsuffix_fails_closed():
    # A ticker with no G-suffix on a 2-row doubleheader key is genuinely
    # ambiguous -- must return None, never guess either game's outcome.
    r = MlbTickerOutcomeResolver(boxscore_df=_doubleheader_boxscores())
    assert r.home_win("KXMLBGAME-26JUL071415MILSTL") is None


def test_resolver_doubleheader_gnum_beyond_available_rows_fails_closed():
    r = MlbTickerOutcomeResolver(boxscore_df=_doubleheader_boxscores())
    assert r.home_win("KXMLBGAME-26JUL071415MILSTLG3") is None


def test_real_corpus_smoke():
    if not DEFAULT_BOXSCORE_PARQUET.exists():
        pytest.skip("local MLB boxscore corpus absent (gitignored data/ dir)")
    r = MlbTickerOutcomeResolver()
    assert isinstance(r.available, bool)
    # A garbage ticker must never raise regardless of corpus state.
    assert r.home_win("not-a-real-ticker") is None


def test_games_fallback_is_off_by_default():
    """S95: the second outcome map stays EMPTY unless explicitly asked for."""
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    assert r._fb == {}
    assert r.home_win("KXMLBGAME-26JUL051235CWSBAL") is None


def test_games_fallback_map_answers_only_on_the_exact_date():
    """ESPN first; the fallback map resolves the exact ticker date and no other."""
    r = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    r._ingest(pd.DataFrame([
        {"date": "2026-07-05", "home_abbr": "BAL", "away_abbr": "CHW",
         "home_score": 2.0, "away_score": 7.0, "status": "STATUS_FINAL"},
    ]), into=r._fb)
    assert r.home_win("KXMLBGAME-26JUL051235CWSBAL") == 0     # exact date
    assert r.home_win("KXMLBGAME-26JUL041235CWSBAL") is None  # +1 hop not taken
    # the ESPN map still wins where it has the game
    assert r.home_win("KXMLBGAME-26JUL011235CWSBAL") == 1
