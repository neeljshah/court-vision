"""Per-file tests for nba_outcome_resolver (offline; synthetic games.parquet-shaped
frame).

Ticker fixtures below are REAL tickers fetched live 2026-07-04 from the Kalshi
public API (series_ticker=KXNBAGAME, status=settled) -- see the module docstring
for the full grounding (182 tickers fetched, 48 events, 15 teams, 2026 playoffs).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_outcome_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ingame import nba_outcome_resolver as nr


def _frame():
    return pd.DataFrame([
        {"game_id": "1", "date": "2026-06-13", "season": "2025-26",
         "home_team": "SAS", "away_team": "NYK", "home_win": 0.0},
        {"game_id": "2", "date": "2026-06-10", "season": "2025-26",
         "home_team": "NYK", "away_team": "SAS", "home_win": 1.0},
        {"game_id": "3", "date": "2026-06-20", "season": "2025-26",
         "home_team": "SAS", "away_team": "MIN", "home_win": None},  # not yet final
    ])


def _frame_with_scores():
    df = _frame()
    df = df[df["home_win"].notna()].copy()
    df["home_pts"] = [90.0, 101.0]
    df["away_pts"] = [95.0, 96.0]
    return df


# --------------------------------------------------------------------------------------- #
# ticker shape: REAL tickers fetched live -- KXNBAGAME-<YY><MON><DD><AWAY+HOME>-<SIDE>,
# NO HHMM field (same shape family as WNBA/NPB).
# --------------------------------------------------------------------------------------- #

def test_parse_nba_ticker_shape_real_settled_ticker():
    # KXNBAGAME-26JUN13NYKSAS-SAS: real settled ticker (Game 5: New York @ San Antonio),
    # fetched live 2026-07-04.
    parsed = nr.parse_nba_ticker("KXNBAGAME-26JUN13NYKSAS-SAS")
    assert parsed is not None
    date, tail, _ = parsed
    assert date.year == 2026 and date.month == 6 and date.day == 13
    assert tail == "NYKSAS"


def test_parse_nba_ticker_shape_real_settled_ticker_2():
    # KXNBAGAME-26JUN10SASNYK-NYK: real settled ticker (San Antonio @ New York).
    parsed = nr.parse_nba_ticker("KXNBAGAME-26JUN10SASNYK-NYK")
    assert parsed is not None
    date, tail, _ = parsed
    assert date.year == 2026 and date.month == 6 and date.day == 10
    assert tail == "SASNYK"


def test_parse_nba_ticker_no_hhmm_field():
    # a ticker WITH an HHMM field (the retracted WNBA-era assumed shape) must fail
    # to parse -- this shape has none, grounded live, not guessed.
    assert nr.parse_nba_ticker("KXNBAGAME-26JUN131930NYKSAS") is None


def test_parse_nba_ticker_bad_input_returns_none():
    assert nr.parse_nba_ticker("NOT-A-TICKER") is None
    assert nr.parse_nba_ticker("") is None


def test_home_win_resolves_real_game_away_win():
    res = nr.NbaOutcomeResolver(games_df=_frame())
    assert res.available
    # KXNBAGAME-26JUN13NYKSAS: New York @ San Antonio; San Antonio (home) lost -> home_win=0.
    assert res.home_win("KXNBAGAME-26JUN13NYKSAS-SAS") == 0
    assert res.home_win("KXNBAGAME-26JUN13NYKSAS-NYK") == 0  # side suffix does not change label


def test_home_win_resolves_real_game_home_win():
    res = nr.NbaOutcomeResolver(games_df=_frame())
    # KXNBAGAME-26JUN10SASNYK: San Antonio @ New York; New York (home) won -> home_win=1.
    assert res.home_win("KXNBAGAME-26JUN10SASNYK-NYK") == 1
    assert res.home_win("KXNBAGAME-26JUN10SASNYK-SAS") == 1


def test_home_win_unresolvable_ticker_returns_none():
    res = nr.NbaOutcomeResolver(games_df=_frame())
    assert res.home_win("KXNBAGAME-26JUL05ZZZQQQ") is None
    assert res.home_win("garbage") is None


def test_home_win_not_final_game_returns_none():
    res = nr.NbaOutcomeResolver(games_df=_frame())
    # SAS/MIN game has home_win=None (not yet final) -> excluded from _final entirely.
    assert res.home_win("KXNBAGAME-26JUN20MINSAS-SAS") is None


def test_final_score_resolves_when_scores_present():
    res = nr.NbaOutcomeResolver(games_df=_frame_with_scores())
    score = res.final_score("KXNBAGAME-26JUN13NYKSAS-SAS")
    assert score == (90, 95)


def test_final_score_none_when_no_score_columns():
    res = nr.NbaOutcomeResolver(games_df=_frame())  # no home_pts/away_pts columns
    assert res.final_score("KXNBAGAME-26JUN13NYKSAS-SAS") is None
    # home_win still resolves even without score columns
    assert res.home_win("KXNBAGAME-26JUN13NYKSAS-SAS") == 0


def test_resolver_inert_on_missing_parquet(tmp_path):
    res = nr.NbaOutcomeResolver(games_parquet=tmp_path / "missing.parquet")
    assert res.available is False
    assert res.home_win("KXNBAGAME-26JUN13NYKSAS-SAS") is None


def test_never_raises_on_malformed_ticker():
    res = nr.NbaOutcomeResolver(games_df=_frame())
    for bad in (None, 12345, "", "KXNBAGAME-", "KXNBAGAME-99XXX99AAA"):
        try:
            assert res.home_win(bad) is None  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            pytest.fail("home_win raised on %r: %s" % (bad, exc))


# --------------------------------------------------------------------------------------- #
# ALL 15 real 2026-playoff franchise codes (grounded off 182 fetched tickers) must
# resolve; the 15 unobserved-this-season codes must ALSO resolve when present in the
# parquet's own index (fallback discipline mirrors wnba_outcome_resolver).
# --------------------------------------------------------------------------------------- #

def test_all_observed_franchise_codes_split_uniquely():
    codes = ["ATL", "BOS", "CLE", "DEN", "DET", "HOU", "LAL", "MIN", "NYK",
              "OKC", "ORL", "PHI", "POR", "SAS", "TOR"]
    idx = nr._build_name_index(codes)
    for code in codes:
        assert nr._resolve_abbr(code, idx) == code, "code %s should resolve to itself" % code


def test_unobserved_franchise_codes_resolve_when_in_index():
    # unobserved-this-season codes (e.g. GSW, LAC, NOP) still resolve correctly when
    # the loaded parquet's own index contains them -- the override is accepted only
    # because it matches the parquet's own spelling, never a blind guess.
    all_30 = ["ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
              "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
              "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"]
    idx = nr._build_name_index(all_30)
    for code in all_30:
        assert nr._resolve_abbr(code, idx) == code


def test_real_settled_ticker_tails_split_to_known_franchises():
    # a sample of REAL settled ticker tails fetched live 2026-07-04 -- each must split
    # uniquely against the grounded code set (no ambiguity, no guess).
    codes = ["ATL", "BOS", "CLE", "DEN", "DET", "HOU", "LAL", "MIN", "NYK",
              "OKC", "ORL", "PHI", "POR", "SAS", "TOR"]
    idx = nr._build_name_index(codes)
    real_tails = [
        "ATLNYK", "BOSPHI", "CLEDET", "CLENYK", "CLETOR", "DENMIN", "DETCLE",
        "DETORL", "HOULAL", "LALHOU", "LALOKC", "MINSAS", "NYKATL", "NYKCLE",
        "NYKPHI", "NYKSAS", "OKCLAL", "OKCSAS", "ORLDET", "PHIBOS", "PHINYK",
        "PORSAS", "SASMIN", "SASNYK", "SASOKC", "TORCLE",
    ]
    for tail in real_tails:
        split = nr._split_tail(tail, idx)
        assert split is not None, "tail %s should split uniquely" % tail
        away, home = split
        assert away in codes and home in codes and away != home
