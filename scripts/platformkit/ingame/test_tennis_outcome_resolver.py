"""Per-file tests for tennis_outcome_resolver (offline; injected disk frame + fake
live http_get; fixtures mirror REAL tickers/names fetched live from Kalshi/ESPN
2026-07-03 during Wimbledon)."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.ingame import tennis_outcome_resolver as tor
from scripts.platformkit.ingame import tennis_ticker_match as tm

_NOW = dt.datetime(2026, 7, 5, 12, 0, tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------- parsing
def test_parse_real_tickers():
    # Real tickers fetched live from the Kalshi public API 2026-07-03.
    got = tor.parse_tennis_ticker("KXATPMATCH-26JUL05AUGDAV-DAV")
    assert got == ("atp", dt.date(2026, 7, 5), "AUGDAV")
    got2 = tor.parse_tennis_ticker("KXWTAMATCH-26JUL05SABOSA-OSA")
    assert got2 == ("wta", dt.date(2026, 7, 5), "SABOSA")
    # event_ticker (no side suffix) parses identically to the market ticker.
    got3 = tor.parse_tennis_ticker("KXATPMATCH-26JUL03RINDJO")
    assert got3 == ("atp", dt.date(2026, 7, 3), "RINDJO")
    # variable-width tails verified live: 'Kwon'->KWON (4), 'de Minaur'->DE (2).
    got4 = tor.parse_tennis_ticker("KXATPMATCH-26JUL01KWONPAU-KWON")
    assert got4 == ("atp", dt.date(2026, 7, 1), "KWONPAU")
    got5 = tor.parse_tennis_ticker("KXATPMATCH-26JUL02DEMAN-DE")
    assert got5 == ("atp", dt.date(2026, 7, 2), "DEMAN")


def test_parse_rejects_garbage():
    assert tor.parse_tennis_ticker("not-a-ticker") is None
    assert tor.parse_tennis_ticker("KXMLBGAME-26JUN241845PHIWSH") is None  # wrong prefix
    assert tor.parse_tennis_ticker("KXATPMATCH-26ZZZ05AUGDAV-DAV") is None  # bad month


def test_surname_codes_hyphenated_and_multiword():
    # Real ESPN display names verified live 2026-07-03.
    assert "AUG" in tm.surname_codes("Felix Auger-Aliassime")
    assert "DAV" in tm.surname_codes("Alejandro Davidovich Fokina")
    assert "DJO" in tm.surname_codes("Novak Djokovic")


def test_surname_codes_short_and_particle_names():
    # Verified live 2026-07-03: 'Kwon' widens to KWON (whole surname, <=4 letters);
    # 'de Minaur'/'De Jong' contribute the bare particle and particle+1 codes.
    assert "KWON" in tm.surname_codes("Soonwoo Kwon")
    assert "DE" in tm.surname_codes("Alex de Minaur")
    assert "DEJ" in tm.surname_codes("Jesper De Jong")


# --------------------------------------------------------------------------- real ticker E2E
def test_variable_width_tickers_resolve_via_live_tier():
    # Real settled tickers (2026-07-01/02) that a fixed 3+3 split would have
    # mis-parsed (KWONPAU as KWO+NPA; DEMAN wouldn't even match a 6-char regex).
    b1 = _board([("Soonwoo Kwon", True, "Tommy Paul", False, "STATUS_FINAL")],
               date="2026-07-01", slug="mens-singles")
    r1 = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: b1, now=_NOW)
    assert r1.home_win("KXATPMATCH-26JUL01KWONPAU-KWON") == 1

    b2 = _board([("Alex de Minaur", True, "Adrian Mannarino", False, "STATUS_FINAL")],
               date="2026-07-02", slug="mens-singles")
    r2 = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: b2, now=_NOW)
    assert r2.home_win("KXATPMATCH-26JUL02DEMAN-DE") == 1


# --------------------------------------------------------------------------- disk tier
def _fresh_disk_df():
    """Rows shaped like espn_matches.parquet, dated close to `_NOW` (fresh)."""
    rows = []
    for cid, league, date, pa, wa, pb, wb in [
        (1, "atp", "2026-07-03", "Novak Djokovic", True, "Arthur Rinderknech", False),
        (2, "atp", "2026-07-03", "Shintaro Mochizuki", True, "Rafael Jodar", False),
        (3, "atp", "2026-07-05", "Roman Safiullin", False, "Novak Djokovic", True),
    ]:
        rows.append({"comp_id": cid, "date": date, "league": league,
                     "player_name": pa, "winner": wa, "status": "STATUS_FINAL"})
        rows.append({"comp_id": cid, "date": date, "league": league,
                     "player_name": pb, "winner": wb, "status": "STATUS_FINAL"})
    return pd.DataFrame(rows)


def test_disk_tier_resolves_real_pair():
    res = tor.TennisOutcomeResolver(espn_df=_fresh_disk_df(), now=_NOW)
    assert res._disk_ok
    # KXATPMATCH-26JUL03RINDJO-DJO: Djokovic won -> home(code_a=RIN) lost -> 0
    assert res.home_win("KXATPMATCH-26JUL03RINDJO-DJO") == 0
    # KXATPMATCH-26JUL03JODMOC-MOC: Mochizuki won -> home(code_a=JOD) lost -> 0
    assert res.home_win("KXATPMATCH-26JUL03JODMOC-MOC") == 0


def test_disk_tier_stale_falls_back_to_live(monkeypatch):
    stale_rows = _fresh_disk_df()
    stale_rows["date"] = "2025-12-01"  # far older than FRESHNESS_DAYS vs _NOW
    calls = {"n": 0}

    def fake_http_get(url):
        calls["n"] += 1
        return {"events": []}

    res = tor.TennisOutcomeResolver(espn_df=stale_rows, http_get=fake_http_get, now=_NOW)
    assert not res._disk_ok  # stale snapshot correctly rejected
    assert res.home_win("KXATPMATCH-26JUL03RINDJO-DJO") is None
    assert calls["n"] > 0  # confirms it actually tried the live tier


# --------------------------------------------------------------------------- live tier
def _board(matches, date="2026-07-05", slug="womens-singles"):
    """matches: list of (name_a, winner_a, name_b, winner_b, status_name).

    ESPN ignores the `dates=` query param and returns the WHOLE tournament (see
    tennis_outcome_resolver's module docstring) -- _live_board buckets by each
    competition's OWN `date` field, so the fixture must carry one, and by its
    `type.slug` (womens-singles/mens-singles) since the real payload was
    observed to mix disciplines/tours."""
    comps = []
    for na, wa, nb, wb, status in matches:
        comps.append({
            "date": "%sT12:00Z" % date,
            "type": {"slug": slug},
            "status": {"type": {"name": status, "completed": status != "STATUS_SCHEDULED"}},
            "competitors": [
                {"athlete": {"displayName": na}, "winner": wa},
                {"athlete": {"displayName": nb}, "winner": wb},
            ],
        })
    return {"events": [{"groupings": [{"competitions": comps}]}]}


def test_live_tier_resolves_real_match():
    board = _board([
        ("Felix Auger-Aliassime", True, "Alejandro Davidovich Fokina", False, "STATUS_FINAL"),
    ], date="2026-07-05", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    # KXATPMATCH-26JUL05AUGDAV-DAV ticker's game_id (event_ticker, no suffix):
    assert res.home_win("KXATPMATCH-26JUL05AUGDAV") == 1  # code_a=AUG won


def test_live_tier_retirement_counts_winner():
    board = _board([
        ("Pablo Carreno Busta", True, "Denis Shapovalov", False, "STATUS_RETIRED"),
    ], date="2026-07-03", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    got = tor.parse_tennis_ticker("KXATPMATCH-26JUL03CARSHA")
    assert got is not None
    assert res.home_win("KXATPMATCH-26JUL03CARSHA") == 1


def test_live_tier_walkover_blank_names_unresolved():
    board = _board([
        (None, True, None, False, "STATUS_WALKOVER"),
    ], date="2026-07-02", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    assert res.home_win("KXATPMATCH-26JUL02TIACHO") is None


def test_live_tier_scheduled_not_yet_final():
    board = _board([
        ("Novak Djokovic", False, "Arthur Rinderknech", False, "STATUS_SCHEDULED"),
    ], date="2026-07-03", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    assert res.home_win("KXATPMATCH-26JUL03RINDJO") is None


# --------------------------------------------------------------------------- ambiguity guards
def test_ambiguous_same_surname_code_never_guessed():
    # Two DIFFERENT real matches on the same day both containing a 'SIN'-coded
    # player (Sinner ATP-style collision simulated within one candidate pool).
    board = _board([
        ("Jannik Sinner", True, "Shintaro Mochizuki", False, "STATUS_FINAL"),
        ("Someone Sinclair", False, "Other Person", True, "STATUS_FINAL"),
    ], date="2026-07-05", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    # SIN matches BOTH "Sinner" and "Sinclair" -> ambiguous vs MOC-paired match;
    # code_b=MOC only pairs with the Sinner match, so this one is NOT ambiguous:
    assert res.home_win("KXATPMATCH-26JUL05SINMOC") == 1
    # But a code pair matching nothing uniquely -> None (no crash, no guess).
    assert res.home_win("KXATPMATCH-26JUL05SINXXX") is None


def test_no_winner_marked_returns_none():
    board = _board([
        ("Novak Djokovic", False, "Arthur Rinderknech", False, "STATUS_FINAL"),
    ], date="2026-07-03", slug="mens-singles")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: board, now=_NOW)
    assert res.home_win("KXATPMATCH-26JUL03RINDJO") is None


def test_unparseable_ticker_returns_none():
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=lambda u: {}, now=_NOW)
    assert res.home_win("garbage") is None


def test_resolver_never_raises_on_bad_http():
    def bad_get(url):
        raise RuntimeError("network down")
    res = tor.TennisOutcomeResolver(espn_df=pd.DataFrame(), http_get=bad_get, now=_NOW)
    assert res.home_win("KXATPMATCH-26JUL05AUGDAV-DAV") is None
