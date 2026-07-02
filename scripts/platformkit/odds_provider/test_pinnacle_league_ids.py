"""Per-file test for Pinnacle sport -> league id mapping (regression guard).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_pinnacle_league_ids.py -q

Context: soccer_intl's Pinnacle league id rotated from 2764 (pre-kickoff
qualifying/futures container) to 2686 ("FIFA - World Cup", live-verified via
GET /sports/29/leagues on 2026-07-02) once the 2026 World Cup proper started.
The stale id 401s (delisted, not an auth/rate-limit problem) and feed_health
correctly flags it RED. This locks in the corrected id so a revert is caught.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.pinnacle import _LEAGUE_ID, PinnacleProvider


def test_soccer_intl_league_id_is_current_world_cup():
    assert _LEAGUE_ID["soccer_intl"] == 2686


def test_soccer_intl_league_id_not_stale_pre_kickoff_id():
    assert _LEAGUE_ID["soccer_intl"] != 2764


def test_unsupported_sport_still_degrades_honestly():
    res = PinnacleProvider(http_get=lambda url: (_ for _ in ()).throw(
        AssertionError("should not fetch for an unsupported sport"))).fetch("curling")
    assert res == {"status": "unavailable", "reason": "pinnacle: unsupported sport 'curling'"}
