"""Per-file tests for pinnacle_league_resolver -- hermetic, no network.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_pinnacle_league_resolver.py -q

Coverage:
  - static fast-path (nba/mlb/soccer) never calls http_get.
  - tennis filter: ATP/WTA singles kept; Doubles/ITF/Challenger/Mixed dropped;
    matchupCount==0 excluded; capped at top 4 by matchupCount.
  - soccer_intl filter: 'World Cup' name match, capped at 2.
  - disk cache: write then hit (second call within TTL never re-fetches).
  - TTL expiry re-fetches.
  - fetch failure falls back to a stale cached entry.
  - invalidate() drops the cache so the next resolve re-fetches.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.pinnacle_league_resolver import (
    invalidate,
    resolve_league_ids,
)


def _raise(url):
    raise AssertionError(f"should not fetch: {url}")


_WIMBLEDON_LEAGUES = [
    {"id": 3336, "name": "ATP Wimbledon - R3", "matchupCount": 20},
    {"id": 3824, "name": "WTA Wimbledon - R3", "matchupCount": 14},
    {"id": 4001, "name": "ATP Wimbledon - Doubles R2", "matchupCount": 8},
    {"id": 4002, "name": "WTA Wimbledon - Doubles R2", "matchupCount": 6},
    {"id": 4003, "name": "ATP Challenger Prague", "matchupCount": 12},
    {"id": 4004, "name": "ITF Women Lisbon", "matchupCount": 30},
    {"id": 4005, "name": "ATP Wimbledon - Mixed Doubles", "matchupCount": 4},
    {"id": 4006, "name": "UTR Pro Tennis Series", "matchupCount": 5},
    {"id": 4007, "name": "ATP Newport - R1", "matchupCount": 10},
    {"id": 4008, "name": "WTA Palermo - R1", "matchupCount": 9},
    {"id": 4009, "name": "ATP Bastad - R1", "matchupCount": 0},  # zero matchups
]

_WORLD_CUP_LEAGUES = [
    {"id": 2686, "name": "FIFA - World Cup", "matchupCount": 15},
    {"id": 2690, "name": "FIFA - World Cup Qualification", "matchupCount": 3},
    {"id": 2700, "name": "UEFA - Champions League", "matchupCount": 8},
    {"id": 2710, "name": "FIFA - World Cup Futures", "matchupCount": 0},
]


class TestStaticFastPath:
    def test_nba_no_network(self):
        assert resolve_league_ids("nba", http_get=_raise) == [487]

    def test_mlb_no_network(self):
        assert resolve_league_ids("mlb", http_get=_raise) == [246]

    def test_soccer_no_network(self):
        assert resolve_league_ids("soccer", http_get=_raise) == [1980]


class TestTennisFilter:
    def test_picks_atp_wta_singles_only(self, tmp_path):
        cache = tmp_path / "leagues.json"
        ids = resolve_league_ids(
            "tennis", http_get=lambda url: _WIMBLEDON_LEAGUES, cache_path=cache)
        assert 3336 in ids  # ATP Wimbledon - R3
        assert 3824 in ids  # WTA Wimbledon - R3
        assert 4001 not in ids  # Doubles
        assert 4002 not in ids  # Doubles
        assert 4003 not in ids  # Challenger
        assert 4004 not in ids  # ITF
        assert 4005 not in ids  # Mixed Doubles
        assert 4006 not in ids  # UTR
        assert 4009 not in ids  # matchupCount 0

    def test_capped_at_top_4_by_matchup_count(self, tmp_path):
        cache = tmp_path / "leagues.json"
        ids = resolve_league_ids(
            "tennis", http_get=lambda url: _WIMBLEDON_LEAGUES, cache_path=cache)
        assert len(ids) <= 4
        # top by matchupCount: 3336 (20), 3824 (14), 4007 (10), 4008 (9)
        assert ids == [3336, 3824, 4007, 4008]


class TestSoccerIntlFilter:
    def test_world_cup_name_match_capped_2(self, tmp_path):
        cache = tmp_path / "leagues.json"
        ids = resolve_league_ids(
            "soccer_intl", http_get=lambda url: _WORLD_CUP_LEAGUES,
            cache_path=cache)
        assert 2686 in ids  # FIFA - World Cup
        assert 2690 in ids  # FIFA - World Cup Qualification (also matches "World Cup")
        assert 2700 not in ids  # Champions League
        assert 2710 not in ids  # matchupCount 0
        assert len(ids) <= 2


class TestDiskCache:
    def test_write_then_cache_hit_within_ttl(self, tmp_path):
        cache = tmp_path / "leagues.json"
        calls = {"n": 0}

        def counting_get(url):
            calls["n"] += 1
            return _WIMBLEDON_LEAGUES

        clock = {"t": 1000.0}
        ids1 = resolve_league_ids(
            "tennis", http_get=counting_get, now=lambda: clock["t"],
            cache_path=cache)
        assert calls["n"] == 1
        assert ids1

        # Second call within TTL, http_get would raise if invoked.
        clock["t"] += 10.0
        ids2 = resolve_league_ids(
            "tennis", http_get=_raise, now=lambda: clock["t"], cache_path=cache)
        assert ids2 == ids1
        assert calls["n"] == 1

    def test_ttl_expiry_refetches(self, tmp_path, monkeypatch):
        cache = tmp_path / "leagues.json"
        monkeypatch.setenv("CV_PINNACLE_LEAGUE_TTL_SEC", "100")
        calls = {"n": 0}

        def counting_get(url):
            calls["n"] += 1
            return _WIMBLEDON_LEAGUES

        clock = {"t": 1000.0}
        resolve_league_ids("tennis", http_get=counting_get,
                            now=lambda: clock["t"], cache_path=cache)
        assert calls["n"] == 1

        clock["t"] += 200.0  # past the 100s TTL
        resolve_league_ids("tennis", http_get=counting_get,
                            now=lambda: clock["t"], cache_path=cache)
        assert calls["n"] == 2

    def test_fetch_failure_falls_back_to_stale_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "leagues.json"
        monkeypatch.setenv("CV_PINNACLE_LEAGUE_TTL_SEC", "100")

        clock = {"t": 1000.0}
        first = resolve_league_ids(
            "tennis", http_get=lambda url: _WIMBLEDON_LEAGUES,
            now=lambda: clock["t"], cache_path=cache)
        assert first

        clock["t"] += 500.0  # expired

        def failing_get(url):
            raise RuntimeError("network down")

        second = resolve_league_ids(
            "tennis", http_get=failing_get, now=lambda: clock["t"],
            cache_path=cache)
        assert second == first  # stale beats none

    def test_no_cache_and_fetch_failure_is_honest_empty(self, tmp_path):
        cache = tmp_path / "leagues.json"

        def failing_get(url):
            raise RuntimeError("network down")

        assert resolve_league_ids(
            "tennis", http_get=failing_get, cache_path=cache) == []


class TestInvalidate:
    def test_invalidate_forces_reresolve(self, tmp_path, monkeypatch):
        cache = tmp_path / "leagues.json"
        monkeypatch.setenv("CV_PINNACLE_LEAGUE_TTL_SEC", "3600")
        calls = {"n": 0}

        def counting_get(url):
            calls["n"] += 1
            return _WIMBLEDON_LEAGUES

        clock = {"t": 1000.0}
        resolve_league_ids("tennis", http_get=counting_get,
                            now=lambda: clock["t"], cache_path=cache)
        assert calls["n"] == 1

        clock["t"] += 5.0  # well within TTL
        invalidate("tennis", cache_path=cache)

        resolve_league_ids("tennis", http_get=counting_get,
                            now=lambda: clock["t"], cache_path=cache)
        assert calls["n"] == 2

    def test_invalidate_missing_entry_is_noop(self, tmp_path):
        cache = tmp_path / "leagues.json"
        invalidate("tennis", cache_path=cache)  # must not raise
        invalidate("nba", cache_path=cache)  # never cached (static) -- no-op
