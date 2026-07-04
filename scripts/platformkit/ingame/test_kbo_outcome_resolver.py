"""Per-file test for the OFFLINE KBO Kalshi-ticker outcome resolver.

Tickers used below were fetched LIVE from the Kalshi public API 2026-07-06
(see kbo_outcome_resolver.py module docstring) -- this test exercises the
resolver purely OFFLINE against an injected in-memory frame; no network.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_kbo_outcome_resolver.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.ingame import kbo_outcome_resolver as R

# Real ticker samples fetched live 2026-07-06 (KXKBOGAME series, status=open).
T_NCDKIA = "KXKBOGAME-26JUL050500NCDKIA-NCD"  # NC Dinos vs Kia Tigers
T_LOTKTW = "KXKBOGAME-26JUL050500LOTKTW-LOT"  # Lotte Giants vs KT Wiz
T_SAMSSG = "KXKBOGAME-26JUL050500SAMSSG-SAM"  # Samsung Lions vs SSG Landers
T_HANLG = "KXKBOGAME-26JUL050500HANLG-HAN"    # Hanwha Eagles vs LG Twins (variable-width 3+2)
T_DOOKIW = "KXKBOGAME-26JUL050100DOOKIW-KIW"  # Doosan Bears vs Kiwoom Heroes


def _results_df() -> pd.DataFrame:
    # NOTE ON HOME/AWAY CONVENTION: same stable-but-arbitrary convention as
    # npb_outcome_resolver's fixture (Kalshi supplies no explicit home/away
    # signal) -- ticker tail's FIRST code = "away", SECOND = "home".
    return pd.DataFrame([
        # tail NCDKIA -> away=NC, home=KIA; KIA (home) wins 6-2.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "KIA",
         "away_team": "NC", "home_score": 6.0, "away_score": 2.0,
         "home_win": 1.0, "tied": False},
        # tail LOTKTW -> away=LOTTE, home=KT; KT (home) loses 3-5.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "KT",
         "away_team": "LOTTE", "home_score": 3.0, "away_score": 5.0,
         "home_win": 0.0, "tied": False},
        # tail SAMSSG -> away=SAMSUNG, home=SSG; SSG (home) wins 7-4.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "SSG",
         "away_team": "SAMSUNG", "home_score": 7.0, "away_score": 4.0,
         "home_win": 1.0, "tied": False},
        # tail HANLG (variable width 3+2) -> away=HANWHA, home=LG; LG (home) wins 4-1.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "LG",
         "away_team": "HANWHA", "home_score": 4.0, "away_score": 1.0,
         "home_win": 1.0, "tied": False},
        # tail DOOKIW -> away=DOOSAN, home=KIWOOM; tied 2-2, excluded from home_win.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "KIWOOM",
         "away_team": "DOOSAN", "home_score": 2.0, "away_score": 2.0,
         "home_win": float("nan"), "tied": True},
    ])


def _resolver() -> R.KboOutcomeResolver:
    return R.KboOutcomeResolver(results_df=_results_df())


def test_parse_real_ticker_fixed_width():
    codes = R.KboOutcomeResolver(results_df=_results_df())._valid_codes()
    parsed = R.parse_kbo_ticker(T_NCDKIA, codes)
    assert parsed is not None
    date, away, home = parsed
    assert date == dt.date(2026, 7, 5)
    assert away == "NC" and home == "KIA"


def test_parse_real_ticker_variable_width_3_plus_2():
    codes = R.KboOutcomeResolver(results_df=_results_df())._valid_codes()
    parsed = R.parse_kbo_ticker(T_HANLG, codes)
    assert parsed is not None
    date, away, home = parsed
    assert away == "HANWHA" and home == "LG"


def test_kalshi_code_alias_ktw_lot_resolves():
    codes = R.KboOutcomeResolver(results_df=_results_df())._valid_codes()
    parsed = R.parse_kbo_ticker(T_LOTKTW, codes)
    assert parsed is not None
    _, away, home = parsed
    assert away == "LOTTE" and home == "KT"


def test_home_win_resolves_kia_home_winner():
    res = _resolver()
    assert res.available
    assert res.home_win(T_NCDKIA) == 1


def test_home_win_resolves_kt_home_loser():
    res = _resolver()
    assert res.home_win(T_LOTKTW) == 0


def test_home_win_resolves_ssg_home_winner():
    res = _resolver()
    assert res.home_win(T_SAMSSG) == 1


def test_home_win_resolves_variable_width_hanlg():
    res = _resolver()
    assert res.home_win(T_HANLG) == 1


def test_tied_game_is_none():
    res = _resolver()
    assert res.home_win(T_DOOKIW) is None


def test_final_score_matches_parquet():
    res = _resolver()
    assert res.final_score(T_NCDKIA) == (6, 2)


def test_unresolvable_ticker_is_none():
    res = _resolver()
    assert res.home_win("KXKBOGAME-26JUL050500ZZZYYY-ZZZ") is None
    assert res.home_win("garbage") is None


def test_missing_parquet_is_inert_never_raises(tmp_path):
    res = R.KboOutcomeResolver(results_parquet=tmp_path / "does_not_exist.parquet")
    assert res.available is False
    assert res.home_win(T_NCDKIA) is None


def test_consecutive_day_same_matchup_never_borrows_prior_day_final():
    """REGRESSION (found live 2026-07-04): KBO reruns the SAME matchup
    (same home/away) on consecutive days in a series. Yesterday's game is
    FINAL; today's identical matchup is still in progress (0-0, home_win
    NaN). The resolver must return None for today's ticker, never silently
    settle it using yesterday's already-final score for the same pairing."""
    df = pd.DataFrame([
        # 07-04: KIWOOM(home) beat DOOSAN(away) 6-5 -- FINAL.
        {"date": pd.Timestamp("2026-07-04"), "season": "2026", "home_team": "KIWOOM",
         "away_team": "DOOSAN", "home_score": 6.0, "away_score": 5.0,
         "home_win": 1.0, "tied": False},
        # 07-05: SAME matchup, still in progress -- placeholder 0-0, NaN.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "KIWOOM",
         "away_team": "DOOSAN", "home_score": 0.0, "away_score": 0.0,
         "home_win": float("nan"), "tied": False},
    ])
    res = R.KboOutcomeResolver(results_df=df)
    ticker_today = "KXKBOGAME-26JUL050100DOOKIW-KIW"  # 07-05 ticket, in-progress
    assert res.home_win(ticker_today) is None
    assert res.final_score(ticker_today) is None
    # Yesterday's ticker (if one were captured) still resolves correctly.
    ticker_yesterday = "KXKBOGAME-26JUL040100DOOKIW-KIW"
    assert res.home_win(ticker_yesterday) == 1
    assert res.final_score(ticker_yesterday) == (6, 5)
    assert res.final_score(T_NCDKIA) is None
