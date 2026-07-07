"""Per-file tests for ingame_outcome_label (offline; injected box frame)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.ingame import ingame_outcome_label as ol


def _box_df():
    return pd.DataFrame([
        # PHI @ WSH on 2026-06-24, home WSH won 5-3
        {"event_id": "1", "date": "2026-06-24", "home_abbr": "WSH", "away_abbr": "PHI",
         "home_score": 5.0, "away_score": 3.0, "status": "STATUS_FINAL"},
        # AZ (Kalshi) @ TB on 2026-06-26; ESPN abbr ARI; away ARI won 2-7 -> home_win=0
        {"event_id": "2", "date": "2026-06-26", "home_abbr": "TB", "away_abbr": "ARI",
         "home_score": 2.0, "away_score": 7.0, "status": "STATUS_FINAL"},
        # a tie (suspended) must NOT produce a label
        {"event_id": "3", "date": "2026-06-27", "home_abbr": "NYY", "away_abbr": "BOS",
         "home_score": 4.0, "away_score": 4.0, "status": "STATUS_FINAL"},
        # a non-final game must NOT produce a label
        {"event_id": "4", "date": "2026-06-28", "home_abbr": "SF", "away_abbr": "LAD",
         "home_score": 1.0, "away_score": 0.0, "status": "STATUS_IN_PROGRESS"},
    ])


def test_parse_basic_and_alias():
    valid = {"WSH", "PHI", "TB", "ARI"} | set(ol._KALSHI_TO_ESPN.keys())
    got = ol.parse_mlb_ticker("KXMLBGAME-26JUN241845PHIWSH", valid)
    assert got is not None
    _date, away, home, gnum = got
    assert (away, home) == ("PHI", "WSH")
    assert _date == dt.date(2026, 6, 24)
    assert gnum is None  # single game -> no doubleheader index
    # AZ -> ARI alias resolves
    got2 = ol.parse_mlb_ticker("KXMLBGAME-26JUN261910AZTB", valid)
    assert got2 is not None and got2[1:] == ("ARI", "TB", None)


def test_parse_doubleheader_suffix():
    valid = {"MIL", "STL", "SF"} | set(ol._KALSHI_TO_ESPN.keys())
    got = ol.parse_mlb_ticker("KXMLBGAME-26JUL071415MILSTLG1", valid)
    assert got == (dt.date(2026, 7, 7), "MIL", "STL", 1)
    got2 = ol.parse_mlb_ticker("KXMLBGAME-26JUL071915MILSTLG2-MIL", valid)
    assert got2 == (dt.date(2026, 7, 7), "MIL", "STL", 2)
    # a tail ending in G (SFG alias -> SF) must NOT lose its G to the suffix
    got3 = ol.parse_mlb_ticker("KXMLBGAME-26JUL071415MILSFG", valid)
    assert got3 == (dt.date(2026, 7, 7), "MIL", "SF", None)


def test_parse_rejects_garbage():
    assert ol.parse_mlb_ticker("not-a-ticker", {"WSH"}) is None
    assert ol.parse_mlb_ticker("KXMLBGAME-26ZZZ241845PHIWSH", {"PHI", "WSH"}) is None


def test_resolver_home_and_away_win():
    res = ol.MlbOutcomeResolver(box_df=_box_df())
    assert res.available
    assert res.home_win("KXMLBGAME-26JUN241845PHIWSH") == 1  # home WSH won
    assert res.home_win("KXMLBGAME-26JUN261910AZTB") == 0     # away ARI won


def test_resolver_skips_tie_nonfinal_and_unknown():
    res = ol.MlbOutcomeResolver(box_df=_box_df())
    assert res.home_win("KXMLBGAME-26JUN271310BOSNYY") is None  # tie -> no label
    assert res.home_win("KXMLBGAME-26JUN281610LADSF") is None   # not final -> absent
    assert res.home_win("KXMLBGAME-26JUL011507NYMTOR") is None  # not in frame


def test_resolver_inert_without_parquet(tmp_path):
    res = ol.MlbOutcomeResolver(box_parquet=tmp_path / "nope.parquet")
    assert not res.available
    assert res.home_win("KXMLBGAME-26JUN241845PHIWSH") is None


def test_date_tolerance_one_day():
    # A game filed one ET day off still resolves via the +/-1 day join.
    res = ol.MlbOutcomeResolver(box_df=_box_df())
    # ticker says 06-23 but box has 06-24 -> +1 day tolerance matches
    assert res.home_win("KXMLBGAME-26JUN231845PHIWSH") == 1


def _dh_df():
    """A real-shaped doubleheader day: MIL @ STL twice on 2026-07-07."""
    return pd.DataFrame([
        {"event_id": "10", "date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 2.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T18:15Z"},
        {"event_id": "11", "date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 5.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T23:15Z"},
    ])


def test_doubleheader_g1_g2_pick_by_start_time():
    res = ol.MlbOutcomeResolver(box_df=_dh_df())
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG1") == (2, 6)  # earliest
    assert res.final_score("KXMLBGAME-26JUL071915MILSTLG2") == (5, 1)  # later
    assert res.home_win("KXMLBGAME-26JUL071415MILSTLG1") == 0
    assert res.home_win("KXMLBGAME-26JUL071915MILSTLG2") == 1


def test_doubleheader_fails_closed_on_ambiguity():
    res = ol.MlbOutcomeResolver(box_df=_dh_df())
    # no game_number + 2 same-day rows -> ambiguous, never a guess
    assert res.final_score("KXMLBGAME-26JUL071415MILSTL") is None
    # G3 does not exist -> None
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG3") is None


def test_doubleheader_g1_settles_off_single_final_row():
    # Live shape: G1 just went final, G2 not yet played -> only 1 row on disk.
    res = ol.MlbOutcomeResolver(box_df=_dh_df().iloc[:1])
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG1") == (2, 6)
    assert res.final_score("KXMLBGAME-26JUL071915MILSTLG2") is None  # waits


def test_next_day_ticker_never_settles_against_prior_day_final():
    # 2026-07-07 live incident: a bet on the NEXT day's game of the same series
    # settled against the just-final earlier game via a delta=-1 day tolerance.
    # Ticker and box dates are both ET -> a box row dated before the ticker date
    # is a DIFFERENT game; must stay unresolved until its own final lands.
    res = ol.MlbOutcomeResolver(box_df=_box_df())  # box has 06-24 PHI@WSH final
    assert res.final_score("KXMLBGAME-26JUN251845PHIWSH") is None
    assert res.home_win("KXMLBGAME-26JUN251845PHIWSH") is None


def test_doubleheader_fails_closed_without_start_times():
    df = _dh_df().drop(columns=["start_time"])
    res = ol.MlbOutcomeResolver(box_df=df)
    # 2 rows but no ordering info -> cannot prove which is G1 -> no settle
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG1") is None
    assert res.final_score("KXMLBGAME-26JUL071915MILSTLG2") is None
