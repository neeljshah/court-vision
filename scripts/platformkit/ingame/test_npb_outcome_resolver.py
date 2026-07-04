"""Per-file test for the OFFLINE NPB Kalshi-ticker outcome resolver.

Tickers used below were fetched LIVE from the Kalshi public API 2026-07-06
(see npb_outcome_resolver.py module docstring) -- this test exercises the
resolver purely OFFLINE against an injected in-memory frame; no network.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_npb_outcome_resolver.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.ingame import npb_outcome_resolver as R

# Real ticker samples fetched live 2026-07-06 (KXNPBGAME series, status=open).
T_YOKYAK_YOK = "KXNPBGAME-26JUL050500YOKYAK-YOK"  # Yokohama DeNA BayStars vs Tokyo Yakult Swallows
T_HANLG_LIKE = "KXNPBGAME-26JUL050500HIRHAN-HIR"  # Hiroshima Toyo Carp vs Hanshin Tigers
T_HOKTOH = "KXNPBGAME-26JUL050400HOKTOH-HOK"      # Hokkaido Nippon-Ham Fighters vs Tohoku Rakuten
T_YOMCHU = "KXNPBGAME-26JUL050030YOMCHU-YOM"      # Yomiuri Giants vs Chunichi Dragons


def _results_df() -> pd.DataFrame:
    # NOTE ON HOME/AWAY CONVENTION: Kalshi supplies no explicit home/away signal
    # for NPB (verified live via GET /markets/<ticker> rules_primary/secondary --
    # neither mentions a home team); this resolver's stable convention (matching
    # _split_tail's (away, home) = (tail[:i], tail[i:]) return order) is that the
    # ticker tail's FIRST listed code is "away" and the SECOND is "home" -- an
    # arbitrary but CONSISTENT labeling (same discipline as
    # tennis_outcome_resolver's module docstring), so these fixture rows use
    # away_team=first-tail-code's team, home_team=second-tail-code's team.
    return pd.DataFrame([
        # tail YOKYAK -> away=DeNA(YOK), home=Yakult(YAK); Yakult(home) wins 5-3.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "ヤクルト",
         "away_team": "DeNA", "home_score": 5.0, "away_score": 3.0,
         "home_win": 1.0, "tied": False},
        # tail HIRHAN -> away=Hiroshima(HIR), home=Hanshin(HAN); Hanshin(home) loses 2-6.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "阪神",
         "away_team": "広島", "home_score": 2.0, "away_score": 6.0,
         "home_win": 0.0, "tied": False},
        # tail HOKTOH -> away=Nippon-Ham(HOK), home=Rakuten(TOH); Rakuten(home) wins 4-1.
        {"date": pd.Timestamp("2026-07-04"), "season": "2026", "home_team": "楽天",
         "away_team": "日本ハム", "home_score": 4.0, "away_score": 1.0,
         "home_win": 1.0, "tied": False},
        # tail YOMCHU -> away=Yomiuri(YOM), home=Chunichi(CHU); tied 3-3, excluded.
        {"date": pd.Timestamp("2026-07-05"), "season": "2026", "home_team": "中日",
         "away_team": "巨人", "home_score": 3.0, "away_score": 3.0,
         "home_win": float("nan"), "tied": True},
        # All-star noise rows (league names, not clubs) -- must never match any code.
        {"date": pd.Timestamp("2025-07-07"), "season": "2025", "home_team": "セ・リーグ",
         "away_team": "パ・リーグ", "home_score": 7.0, "away_score": 10.0,
         "home_win": 0.0, "tied": False},
    ])


def _resolver() -> R.NpbOutcomeResolver:
    return R.NpbOutcomeResolver(results_df=_results_df())


def test_parse_real_ticker_shape():
    parsed = R.parse_npb_ticker(T_YOKYAK_YOK)
    assert parsed is not None
    date, tail = parsed
    assert date == dt.date(2026, 7, 5)
    assert tail == "YOKYAK"


def test_home_win_resolves_yakult_as_home_winner():
    res = _resolver()
    assert res.available
    # tail YOKYAK -> away=DeNA, home=Yakult; Yakult (home) won 5-3.
    assert res.home_win(T_YOKYAK_YOK) == 1


def test_home_win_resolves_hanshin_home_loses_to_hiroshima():
    res = _resolver()
    # tail HIRHAN -> away=Hiroshima, home=Hanshin; Hanshin (home) lost 2-6.
    assert res.home_win(T_HANLG_LIKE) == 0


def test_home_win_resolves_rakuten_home_beats_nipponham():
    res = _resolver()
    # tail HOKTOH -> away=Nippon-Ham, home=Rakuten; Rakuten (home) won 4-1.
    assert res.home_win(T_HOKTOH) == 1


def test_tied_game_is_none():
    res = _resolver()
    assert res.home_win(T_YOMCHU) is None


def test_final_score_matches_parquet():
    res = _resolver()
    assert res.final_score(T_YOKYAK_YOK) == (5, 3)


def test_unresolvable_ticker_is_none():
    res = _resolver()
    assert res.home_win("KXNPBGAME-26JUL050500XXXYYY-XXX") is None
    assert res.home_win("garbage") is None


def test_league_name_rows_never_match_any_code():
    res = _resolver()
    # even if a ticker's tail happened to spell out something league-ish, the
    # code index only contains club codes (built from _CODE_TO_NAME) so a
    # league-name row can never be matched by any real ticker split.
    assert "セ・リーグ" not in res._code_index.values()


def test_missing_parquet_is_inert_never_raises(tmp_path):
    res = R.NpbOutcomeResolver(results_parquet=tmp_path / "does_not_exist.parquet")
    assert res.available is False
    assert res.home_win(T_YOKYAK_YOK) is None
    assert res.final_score(T_YOKYAK_YOK) is None


def test_date_grace_window_plus_minus_one_day():
    res = _resolver()
    # T_HOKTOH ticker embeds 26JUL05 (from the -0400 HHMM tail's date group is
    # actually 05, matching the fixture's 07-04 row via the +/-1 day grace).
    assert res.home_win(T_HOKTOH) == 1
