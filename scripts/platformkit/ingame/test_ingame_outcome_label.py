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
    # no game_number + 2 same-day rows, HHMM equidistant from both in UTC
    # (18:15Z and 23:15Z are 1095/1395 min; a 16:45-ET ticket = 20:45Z = 1245,
    # 150min from each) -> genuinely ambiguous, never a guess. (A non-
    # equidistant HHMM DOES resolve -- see test_doubleheader_hhmm_tiebreak_*.)
    assert res.final_score("KXMLBGAME-26JUL071645MILSTL") is None
    # G3 does not exist -> None
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG3") is None


def test_doubleheader_g1_settles_off_single_final_row():
    # Live shape: G1 just went final, G2 not yet played -> only 1 row on disk.
    res = ol.MlbOutcomeResolver(box_df=_dh_df().iloc[:1])
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG1") == (2, 6)
    assert res.final_score("KXMLBGAME-26JUL071915MILSTLG2") is None  # waits


def test_next_day_ticker_never_settles_against_prior_day_final():
    # 2026-07-07 live incident: a bet on the NEXT day's game of the same series
    # settled against the just-final earlier game via a naive delta=-1 tolerance.
    # delta=-1 is now risk-scoped (age >=2 days + empty forward buckets + a single
    # unambiguous -1 final -- see test_delta_neg1_* below); right after the game
    # (today pinned to +1 day, age=1) the ingest-race guard still refuses.
    res = ol.MlbOutcomeResolver(box_df=_box_df())  # box has 06-24 PHI@WSH final
    today = dt.date(2026, 6, 26)
    assert res.final_score("KXMLBGAME-26JUN251845PHIWSH", today=today) is None
    assert res.home_win("KXMLBGAME-26JUN251845PHIWSH", today=today) is None


def test_delta_neg1_reinstated_when_risk_scoped():
    # AZSTL: ticker dated 2026-07-25, real final landed 2026-07-24 (delta=-1).
    # Forward buckets (07-25, 07-26) are empty, the -1 bucket has exactly one
    # final, and today is pinned 2 days past the ticker date -> resolves.
    df = pd.DataFrame([
        {"event_id": "20", "date": "2026-07-24", "home_abbr": "STL", "away_abbr": "ARI",
         "home_score": 3.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-24T23:15Z"},
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    today = dt.date(2026, 7, 27)  # ticker date + 2 days
    assert res.final_score("KXMLBGAME-26JUL251840AZSTL", today=today) == (3, 1)
    assert res.home_win("KXMLBGAME-26JUL251840AZSTL", today=today) == 1


def test_delta_neg1_age_guard_blocks_fresh_ticker():
    # Same shape as above but today is only 1 day past the ticker date -> the
    # ingest-race guard refuses (the correct forward game hasn't had time to land).
    df = pd.DataFrame([
        {"event_id": "21", "date": "2026-07-24", "home_abbr": "STL", "away_abbr": "ARI",
         "home_score": 3.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-24T23:15Z"},
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    today = dt.date(2026, 7, 26)  # only 1 day past ticker date -> age guard fails
    assert res.final_score("KXMLBGAME-26JUL251840AZSTL", today=today) is None


def test_delta_neg1_never_consulted_when_forward_bucket_nonempty():
    # Documented 07-07 incident shape: even though the -1 bucket is clean and the
    # age guard would pass, a NON-empty delta-0 bucket (here: 2 finals too close
    # together to break the HHMM tie, i.e. an unresolved-but-present bucket) means
    # -1 must never be consulted -- guard (a) fails before guard (b)/(c) matter.
    df = pd.DataFrame([
        {"event_id": "30", "date": "2026-07-08", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 2.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-08T18:15Z"},
        {"event_id": "31", "date": "2026-07-08", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 5.0, "away_score": 1.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-08T19:00Z"},  # only 45min apart -> tie-break refuses
        {"event_id": "32", "date": "2026-07-07", "home_abbr": "STL", "away_abbr": "MIL",
         "home_score": 9.0, "away_score": 0.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-07T18:15Z"},  # clean, unambiguous -1 bucket
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    today = dt.date(2026, 7, 11)  # well past the age guard
    assert res.final_score("KXMLBGAME-26JUL081415MILSTL", today=today) is None


def test_doubleheader_hhmm_tiebreak_resolves_postponement_dh():
    # Real MILPIT case (2026-07-11, grounded off data/domains/mlb/espn_boxscores.parquet):
    # Fri 07-10 MIL@PIT was postponed into a Sat straight DH, so both Kalshi
    # GAME tickers carry NO G-suffix; the HHMM tie-break (not a game_number) is
    # the only way to split the 2 same-date finals. Reverting the tie-break
    # (i.e. going back to unconditional None on 2 rows) fails closed again --
    # nothing here depends on game_number, only on _pick_by_hhmm.
    # start_times are UTC in the real parquet (opus judge 2026-07-12 proof:
    # a 22:10-ET ticker maps to a 02:10Z box row). 16:05 ET opener = 20:05Z;
    # 19:05 ET nightcap = 23:05Z. The tie-break must convert ET->UTC.
    df = pd.DataFrame([
        {"event_id": "40", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 7.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-11T20:05Z"},
        {"event_id": "41", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 3.0, "away_score": 2.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-11T23:05Z"},
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    # Fri-postponed ticket (18:40 ET -> 22:40Z): nearest = 23:05Z nightcap
    assert res.final_score("KXMLBGAME-26JUL101840MILPIT") == (3, 2)
    # Sat opener ticket (16:05 ET -> 20:05Z): nearest = opener
    assert res.final_score("KXMLBGAME-26JUL111605MILPIT") == (7, 6)
    # Nightcap ticket (19:05 ET -> 23:05Z): its OWN game, never the opener
    # (the raw-digit compare bug settled this one against the opener).
    assert res.final_score("KXMLBGAME-26JUL111905MILPIT") == (3, 2)


def test_doubleheader_hhmm_tiebreak_nightcap_crosses_midnight_utc():
    # 22:10 ET nightcap = 02:10Z NEXT UTC day (minutes-of-day wraps to 130);
    # circular distance must still bind it to its own game.
    df = pd.DataFrame([
        {"event_id": "44", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 7.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-11T20:05Z"},
        {"event_id": "45", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 3.0, "away_score": 2.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-12T02:10Z"},
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    assert res.final_score("KXMLBGAME-26JUL112210MILPIT") == (3, 2)
    assert res.final_score("KXMLBGAME-26JUL111605MILPIT") == (7, 6)


def test_doubleheader_hhmm_tiebreak_stays_closed_when_too_close():
    # Two finals only 45min apart -- below the 90min separation floor, so the
    # tie-break refuses rather than guess.
    df = pd.DataFrame([
        {"event_id": "42", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 7.0, "away_score": 6.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-11T16:05Z"},
        {"event_id": "43", "date": "2026-07-11", "home_abbr": "PIT", "away_abbr": "MIL",
         "home_score": 3.0, "away_score": 2.0, "status": "STATUS_FINAL",
         "start_time": "2026-07-11T16:50Z"},
    ])
    res = ol.MlbOutcomeResolver(box_df=df)
    assert res.final_score("KXMLBGAME-26JUL111605MILPIT") is None


def test_doubleheader_fails_closed_without_start_times():
    df = _dh_df().drop(columns=["start_time"])
    res = ol.MlbOutcomeResolver(box_df=df)
    # 2 rows but no ordering info -> cannot prove which is G1 -> no settle
    assert res.final_score("KXMLBGAME-26JUL071415MILSTLG1") is None
    assert res.final_score("KXMLBGAME-26JUL071915MILSTLG2") is None
