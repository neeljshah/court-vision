"""Per-file tests for wnba_outcome_resolver (offline; synthetic scoreboard frame).

Ticker fixtures below are REAL tickers fetched live 2026-07-03 from the Kalshi public
API (series_ticker=KXWNBAGAME, status=open and status=settled) -- see the module
docstring for the full grounding (330 tickers fetched, 326/330 uniquely resolved).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_wnba_outcome_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.ingame import wnba_outcome_resolver as wr


def _frame():
    return pd.DataFrame([
        {"event_id": "1", "date": "2026-07-02", "home_team": "Phoenix Mercury",
         "away_team": "Seattle Storm", "home_score": 90.0, "away_score": 67.0,
         "home_win": 1.0, "status_name": "STATUS_FINAL"},
        {"event_id": "2", "date": "2026-06-28", "home_team": "Chicago Sky",
         "away_team": "Las Vegas Aces", "home_score": 99.0,
         "away_score": 107.0, "home_win": 0.0, "status_name": "STATUS_FINAL"},
        {"event_id": "3", "date": "2026-07-07", "home_team": "Seattle Storm",
         "away_team": "Dallas Wings", "home_score": 75.0, "away_score": 75.0,
         "home_win": 0.0, "status_name": "STATUS_IN_PROGRESS"},  # not final
    ])


# --------------------------------------------------------------------------------------- #
# ticker shape: REAL tickers fetched live -- KXWNBAGAME-<YY><MON><DD><AWAY+HOME>[-<SIDE>],
# NO HHMM field (the module's earlier assumed shape had one; every real ticker disproves
# it). Tail codes are Kalshi's OWN city shorthand, not ESPN abbreviations.
# --------------------------------------------------------------------------------------- #

def test_parse_wnba_ticker_shape_real_open_ticker():
    # KXWNBAGAME-26JUL05DALTOR-TOR: real OPEN ticker (Dallas @ Toronto), fetched 2026-07-03.
    parsed = wr.parse_wnba_ticker("KXWNBAGAME-26JUL05DALTOR-TOR")
    assert parsed is not None
    date, tail, _ = parsed
    assert date.year == 2026 and date.month == 7 and date.day == 5
    assert tail == "DALTOR"


def test_parse_wnba_ticker_shape_real_settled_ticker():
    # KXWNBAGAME-26JUN28LVCHI-LV: real SETTLED ticker (Las Vegas @ Chicago), Las Vegas won.
    parsed = wr.parse_wnba_ticker("KXWNBAGAME-26JUN28LVCHI-LV")
    assert parsed is not None
    date, tail, _ = parsed
    assert date.year == 2026 and date.month == 6 and date.day == 28
    assert tail == "LVCHI"


def test_parse_wnba_ticker_no_longer_expects_hhmm():
    # the retracted assumed shape inserted a 4-digit HHMM before the tail; real tickers
    # have none, so a ticker WITH one must fail to parse (regex is now grounded, not guessed).
    assert wr.parse_wnba_ticker("KXWNBAGAME-26JUL051930LVACHI") is None


def test_parse_wnba_ticker_bad_input_returns_none():
    assert wr.parse_wnba_ticker("NOT-A-TICKER") is None
    assert wr.parse_wnba_ticker("") is None


def test_home_win_resolves_real_game():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    assert res.available
    # KXWNBAGAME-26JUL02SEAPHX: Seattle @ Phoenix; parquet/ticker both confirm Phoenix (home) won.
    assert res.home_win("KXWNBAGAME-26JUL02SEAPHX-PHX") == 1
    assert res.home_win("KXWNBAGAME-26JUL02SEAPHX-SEA") == 1  # side suffix does not change the label


def test_home_win_away_win():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    # KXWNBAGAME-26JUN28LVCHI: Las Vegas @ Chicago; Las Vegas (away) won.
    assert res.home_win("KXWNBAGAME-26JUN28LVCHI-LV") == 0
    assert res.home_win("KXWNBAGAME-26JUN28LVCHI-CHI") == 0


def test_home_win_unresolvable_ticker_returns_none():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    assert res.home_win("KXWNBAGAME-26JUL05ZZZQQQ") is None
    assert res.home_win("garbage") is None


def test_home_win_not_final_game_returns_none():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    # Dallas/Seattle game is STATUS_IN_PROGRESS -> filtered out of _final entirely.
    assert res.home_win("KXWNBAGAME-26JUL07DALSEA-DAL") is None


def test_final_score_resolves_tie():
    df = _frame().copy()
    df.loc[2, "status_name"] = "STATUS_FINAL"
    res = wr.WnbaOutcomeResolver(scoreboard_df=df)
    score = res.final_score("KXWNBAGAME-26JUL07DALSEA-DAL")
    assert score == (75, 75)
    # a tie is not a valid binary home_win label
    assert res.home_win("KXWNBAGAME-26JUL07DALSEA-DAL") is None


def test_resolver_inert_on_missing_parquet(tmp_path):
    res = wr.WnbaOutcomeResolver(scoreboard_parquet=tmp_path / "missing.parquet")
    assert res.available is False
    assert res.home_win("KXWNBAGAME-26JUL02SEAPHX-PHX") is None


def test_never_raises_on_malformed_ticker():
    res = wr.WnbaOutcomeResolver(scoreboard_df=_frame())
    for bad in (None, 12345, "", "KXWNBAGAME-", "KXWNBAGAME-99XXX99AAA"):
        try:
            assert res.home_win(bad) is None  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            pytest.fail("home_win raised on %r: %s" % (bad, exc))


# --------------------------------------------------------------------------------------- #
# ALL 15 real 2026-season franchise codes (grounded off 330 fetched tickers) must resolve;
# national-team exhibition legs (NGR/JNT) are correctly excluded (not real franchises).
# --------------------------------------------------------------------------------------- #

def test_all_real_franchise_codes_split_uniquely():
    names = [
        "Atlanta Dream", "Chicago Sky", "Connecticut Sun", "Dallas Wings",
        "Golden State Valkyries", "Indiana Fever", "Las Vegas Aces",
        "Los Angeles Sparks", "Minnesota Lynx", "New York Liberty",
        "Portland Fire", "Phoenix Mercury", "Seattle Storm", "Toronto Tempo",
        "Washington Mystics",
    ]
    idx = wr._build_name_index(names)
    # every real Kalshi code fetched live must resolve to its correct franchise.
    expected = {
        "ATL": "Atlanta Dream", "CHI": "Chicago Sky", "CONN": "Connecticut Sun",
        "DAL": "Dallas Wings", "GS": "Golden State Valkyries", "IND": "Indiana Fever",
        "LV": "Las Vegas Aces", "LA": "Los Angeles Sparks", "MIN": "Minnesota Lynx",
        "NY": "New York Liberty", "PDX": "Portland Fire", "PHX": "Phoenix Mercury",
        "SEA": "Seattle Storm", "TOR": "Toronto Tempo", "WSH": "Washington Mystics",
    }
    for code, team in expected.items():
        assert wr._resolve_abbr(code, idx) == team, "code %s should resolve %s" % (code, team)


def test_real_settled_ticker_tails_split_to_known_franchises():
    # a sample of REAL settled ticker tails fetched live 2026-07-03 -- each must split
    # uniquely against the grounded code set (no ambiguity, no guess).
    names = [
        "Atlanta Dream", "Chicago Sky", "Connecticut Sun", "Dallas Wings",
        "Golden State Valkyries", "Indiana Fever", "Las Vegas Aces",
        "Los Angeles Sparks", "Minnesota Lynx", "New York Liberty",
        "Portland Fire", "Phoenix Mercury", "Seattle Storm", "Toronto Tempo",
        "Washington Mystics",
    ]
    idx = wr._build_name_index(names)
    real_tails = [
        "SEAPHX", "DALCONN", "ATLWSH", "LVNY", "NYGS", "LVCHI", "PDXWSH",
        "MINDAL", "ATLSEA", "LAIND", "PHXTOR", "ATLGS", "WSHCONN", "PDXCHI",
        "NYSEA", "DALLV", "LATOR", "MINWSH", "PHXIND", "NYLV", "DALSEA",
        "TORATL", "CHICONN", "NYLA", "WSHMIN", "GSLV", "CHIDAL", "INDATL",
    ]
    for tail in real_tails:
        split = wr._split_tail(tail, idx)
        assert split is not None, "tail %s should split uniquely" % tail
        away, home = split
        assert away in names and home in names and away != home


def test_national_team_exhibition_tails_are_honestly_unresolved():
    # NGR (Nigeria) / JNT (Japan National Team) are exhibition legs, not real 2026
    # franchises -- an honest None (never a guess), matching the 4/330 fetched tickers
    # that did not resolve.
    names = [
        "Atlanta Dream", "Chicago Sky", "Connecticut Sun", "Dallas Wings",
        "Golden State Valkyries", "Indiana Fever", "Las Vegas Aces",
        "Los Angeles Sparks", "Minnesota Lynx", "New York Liberty",
        "Portland Fire", "Phoenix Mercury", "Seattle Storm", "Toronto Tempo",
        "Washington Mystics",
    ]
    idx = wr._build_name_index(names)
    assert wr._split_tail("NGRIND", idx) is None
    assert wr._split_tail("JNTPHX", idx) is None
