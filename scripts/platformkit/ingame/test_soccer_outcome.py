"""Per-file tests for soccer_outcome (offline; injected finals frame)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts.platformkit.ingame import soccer_outcome as so


def _finals_df():
    return pd.DataFrame([
        # GER 1-1 PAR on 2026-06-29 (draw, decided on penalties -- 90-min score kept)
        {"event_id": "1", "date": "2026-06-29", "home_team": "Germany",
         "away_team": "Paraguay", "home_score": 1.0, "away_score": 1.0,
         "status_name": "STATUS_FINAL_PEN", "completed": True},
        # Ivory Coast 1-2 Norway on 2026-06-30 (away win; CIV needs an override)
        {"event_id": "2", "date": "2026-06-30", "home_team": "Ivory Coast",
         "away_team": "Norway", "home_score": 1.0, "away_score": 2.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        # England 2-1 Congo DR on 2026-07-01 (home win; COD needs an override,
        # and ESPN spells it "Congo DR" -- NOT the historical corpus's "DR Congo")
        {"event_id": "3", "date": "2026-07-01", "home_team": "England",
         "away_team": "Congo DR", "home_score": 2.0, "away_score": 1.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        # a scheduled (not completed) game must never produce a label
        {"event_id": "4", "date": "2026-07-02", "home_team": "Brazil",
         "away_team": "Japan", "home_score": 0.0, "away_score": 0.0,
         "status_name": "STATUS_SCHEDULED", "completed": False},
    ])


def test_parse_ticker_basic():
    got = so.parse_wc_ticker("KXWCGAME-26JUN29GERPAR")
    assert got == (dt.date(2026, 6, 29), "GER", "PAR")


def test_parse_ticker_rejects_garbage():
    assert so.parse_wc_ticker("not-a-ticker") is None
    assert so.parse_wc_ticker("KXWCGAME-26ZZZ29GERPAR") is None
    assert so.parse_wc_ticker("KXMLBGAME-26JUN241845PHIWSH") is None  # wrong prefix


def test_resolver_home_and_away_win_and_draw():
    res = so.SoccerOutcomeResolver(finals_df=_finals_df())
    assert res.available
    # draw -> tied score returned as-is (grade_paper pushes soccer draws downstream)
    assert res.final_score("KXWCGAME-26JUN29GERPAR") == (1, 1)
    # away win, requires the CIV override (Ivory Coast != first-3 "IVO")
    assert res.final_score("KXWCGAME-26JUN30CIVNOR") == (1, 2)
    # home win, requires the COD override AND the ESPN "Congo DR" spelling
    # (not the historical corpus's "DR Congo")
    assert res.final_score("KXWCGAME-26JUL01ENGCOD") == (2, 1)


def test_resolver_ticker_order_is_irrelevant():
    # NORCIV (order swapped vs the real ticker) resolves to the SAME real pair.
    res = so.SoccerOutcomeResolver(finals_df=_finals_df())
    assert res.final_score("KXWCGAME-26JUN30NORCIV") == (1, 2)


def test_resolver_skips_not_completed_and_unknown():
    res = so.SoccerOutcomeResolver(finals_df=_finals_df())
    assert res.final_score("KXWCGAME-26JUL02BRAJPN") is None  # not completed
    assert res.final_score("KXWCGAME-26JUN29ARGBRA") is None  # not in frame


def test_resolver_inert_without_parquet(tmp_path):
    res = so.SoccerOutcomeResolver(finals_parquet=tmp_path / "nope.parquet")
    assert not res.available
    assert res.final_score("KXWCGAME-26JUN29GERPAR") is None


def test_date_tolerance_one_day():
    res = so.SoccerOutcomeResolver(finals_df=_finals_df())
    # ticker says 06-28 but the frame has 06-29 -> +1 day tolerance matches
    assert res.final_score("KXWCGAME-26JUN28GERPAR") == (1, 1)


def _lane5_finals_df():
    """Real failing tickers from the 2026-07-03 Lane 5 soccer resolver audit
    (32/39 captured soccer_intl games were unresolved -- root cause: 6 FIFA
    codes had no override and no unique first-3-letter match)."""
    rows = [
        # AUT: "Austria"[:3]="AUS" != "AUT" -- no natural match, needs override.
        # Also exercises the AUS/AUT prefix collision (both start "AUS").
        {"event_id": "10", "date": "2026-06-22", "home_team": "Argentina",
         "away_team": "Austria", "home_score": 2.0, "away_score": 0.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        # AUS: "AUS" prefix-collides Austria/Australia -- needs override to
        # disambiguate to Australia specifically.
        {"event_id": "11", "date": "2026-07-03", "home_team": "Australia",
         "away_team": "Egypt", "home_score": 1.0, "away_score": 1.0,
         "status_name": "STATUS_FINAL_PEN", "completed": True},
        # DZA: "Algeria"[:3]="ALG" != "DZA".
        {"event_id": "12", "date": "2026-06-22", "home_team": "Jordan",
         "away_team": "Algeria", "home_score": 1.0, "away_score": 2.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        # HTI: "Haiti"[:3]="HAI" != "HTI".
        {"event_id": "13", "date": "2026-06-24", "home_team": "Morocco",
         "away_team": "Haiti", "home_score": 4.0, "away_score": 2.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        # IRQ/IRI: "Iraq"[:3]="IRA" != "IRQ", "Iran"[:3]="IRA" != "IRI" --
        # both collide on "IRA" with each other, needs two separate overrides.
        {"event_id": "14", "date": "2026-06-22", "home_team": "France",
         "away_team": "Iraq", "home_score": 3.0, "away_score": 0.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        {"event_id": "15", "date": "2026-06-26", "home_team": "Egypt",
         "away_team": "Iran", "home_score": 1.0, "away_score": 1.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
    ]
    return pd.DataFrame(rows)


def test_lane5_previously_unresolved_codes_now_resolve():
    # Real tickers from data/cache/ingame_grade/soccer_intl/ that were
    # CODE-RESOLVE-FAIL before the AUT/AUS/DZA/HTI/IRQ/IRI overrides were added.
    res = so.SoccerOutcomeResolver(finals_df=_lane5_finals_df())
    assert res.available
    assert res.final_score("KXWCGAME-26JUN22ARGAUT") == (2, 0)   # AUT -> Austria
    assert res.final_score("KXWCGAME-26JUL03AUSEGY") == (1, 1)   # AUS -> Australia (draw)
    assert res.final_score("KXWCGAME-26JUN22JORDZA") == (1, 2)   # DZA -> Algeria
    assert res.final_score("KXWCGAME-26JUN24MARHTI") == (4, 2)   # HTI -> Haiti
    assert res.final_score("KXWCGAME-26JUN22FRAIRQ") == (3, 0)   # IRQ -> Iraq
    assert res.final_score("KXWCGAME-26JUN26EGYIRI") == (1, 1)   # IRI -> Iran (draw)


def test_ambiguous_code_never_guessed():
    # a code with no unique match anywhere in the loaded corpus -> None, not a guess
    df = pd.concat([_finals_df(), pd.DataFrame([
        {"event_id": "5", "date": "2026-06-15", "home_team": "Norway",
         "away_team": "North Korea", "home_score": 1.0, "away_score": 0.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
    ])], ignore_index=True)
    res = so.SoccerOutcomeResolver(finals_df=df)
    # "NOR" now matches BOTH Norway and "North Korea" by first-3 -- ambiguous,
    # no override disambiguates it -> ticker referencing NOR must resolve None.
    assert res.final_score("KXWCGAME-26JUN15NORXXX") is None
