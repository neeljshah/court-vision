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
    _date, away, home = got
    assert (away, home) == ("PHI", "WSH")
    assert _date == dt.date(2026, 6, 24)
    # AZ -> ARI alias resolves
    got2 = ol.parse_mlb_ticker("KXMLBGAME-26JUN261910AZTB", valid)
    assert got2 is not None and got2[1:] == ("ARI", "TB")


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
