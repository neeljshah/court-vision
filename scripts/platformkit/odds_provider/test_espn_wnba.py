"""Per-file test: ESPN provider wnba league-path wiring (LANE 2).

Probed live 2026-07-03: site.api.espn.com/.../basketball/wnba/scoreboard
returns real events, and .../summary?event=<id> pickcenter carries a real
DraftKings moneyline/spread/total node -- identical shape to nba/mlb. This
locks in the "wnba" -> "basketball/wnba" league-path entry and one parse.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_espn_wnba.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.espn import (
    EspnProvider, _LEAGUE_PATH, parse_pickcenter)

# Trimmed real shape captured live 2026-07-03 (MIN @ NY, event 401857037).
_WNBA_SUMMARY = {
    "pickcenter": [
        {
            "provider": {"name": "DraftKings"},
            "overUnder": 174.5,
            "spread": 2.5,
            "overOdds": -108.0,
            "underOdds": -112.0,
            "awayTeamOdds": {"moneyLine": -135, "spreadOdds": -112.0},
            "homeTeamOdds": {"moneyLine": 114, "spreadOdds": -108.0},
        }
    ]
}

_WNBA_SCOREBOARD = {
    "events": [
        {
            "id": "401857037",
            "date": "2026-07-03T23:30Z",
            "competitions": [{
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "New York Liberty"}},
                    {"homeAway": "away", "team": {"displayName": "Minnesota Lynx"}},
                ]
            }],
        }
    ]
}


def test_wnba_league_path_wired():
    assert _LEAGUE_PATH["wnba"] == "basketball/wnba"


def test_wnba_pickcenter_parses_moneyline_spread_total():
    venues = parse_pickcenter(_WNBA_SUMMARY, "New York Liberty", "Minnesota Lynx")
    assert "espn:DraftKings" in venues
    v = venues["espn:DraftKings"]
    assert "home" in v and "away" in v
    assert "spread" in v and "total" in v


def _stub(mapping):
    def _get(url):
        if "scoreboard" in url:
            return mapping["scoreboard"]
        return mapping["summary"]
    return _get


def test_wnba_fetch_builds_event():
    from datetime import datetime, timezone
    http = _stub({"scoreboard": _WNBA_SCOREBOARD, "summary": _WNBA_SUMMARY})
    # now= pinned near the canned event's date -- the stale-echo guard (espn.py
    # _MAX_EVENT_AGE_HOURS) would otherwise drop this old fixture date.
    now = datetime(2026, 7, 4, tzinfo=timezone.utc)
    events = EspnProvider(http_get=http, use_cache=False).fetch("wnba", now=now)
    assert isinstance(events, list) and len(events) == 1
    ev = events[0]
    assert ev.home == "New York Liberty" and ev.away == "Minnesota Lynx"
    assert "espn:DraftKings" in ev.prices
    assert ev.source == "espn"
