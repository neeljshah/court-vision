"""tests/conformance/nba/test_nba_league_client.py — NBALeagueClient conformance.

Scope: protocol isinstance check + offline-cache tests for 0042500401 (G1)
and 0042500402 (G2).  Network is poisoned via ``socket.socket`` monkeypatch.

Known gap — G3 NOT CACHED
Game 0042500403 (SAS win 115-111, 2026-06-08) is absent from
data/cache/team_system/pbp|box/.  It requires a live CDN call → excluded.
Seed ``data/cache/team_system/{pbp,box}/0042500403.json`` and add
TestOfflineG3 mirroring TestOfflineG1 to complete coverage.

Python 3.9 floor.  ``NBA_OFFLINE=1`` set by autouse fixture.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CDN_PBP = _PROJECT_ROOT / "data" / "cache" / "team_system" / "pbp"
_CDN_BOX = _PROJECT_ROOT / "data" / "cache" / "team_system" / "box"
_CACHED_GAMES = ("0042500401", "0042500402")


# ---------------------------------------------------------------------------
# CDN → nba_stats format converters
# ---------------------------------------------------------------------------

def _cdn_box_to_parsed(cdn: dict, game_id: str) -> dict:
    """Convert CDN liveData boxscore to ``fetch_full_boxscore`` cache format."""
    game = cdn.get("game", {})

    def _i(v: Any) -> int:
        try:
            return int(v) if v is not None else 0
        except (ValueError, TypeError):
            return 0

    def _min(v: Any) -> float:
        if v is None:
            return 0.0
        s = str(v).strip()
        try:
            if s.startswith("PT") and "M" in s:
                s = s[2:]
                m = float(s[: s.index("M")])
                sec = s[s.index("M") + 1 :].rstrip("S")
                return round(m + float(sec or 0) / 60, 2)
            if ":" in s:
                mm, ss = s.split(":", 1)
                return round(float(mm) + float(ss) / 60, 2)
            return round(float(s), 2)
        except (ValueError, TypeError):
            return 0.0

    ht = game.get("homeTeam", {}).get("teamTricode", "")
    at = game.get("awayTeam", {}).get("teamTricode", "")
    players = []
    for key, tri in [("homeTeam", ht), ("awayTeam", at)]:
        for p in game.get(key, {}).get("players", []):
            st = p.get("statistics", {})
            players.append({
                "player_id": _i(p.get("personId")),
                "player_name": str(p.get("name", "") or ""),
                "team_abbreviation": tri,
                "min": _min(st.get("minutes")),
                "pts": _i(st.get("points")), "reb": _i(st.get("reboundsTotal")),
                "oreb": _i(st.get("reboundsOffensive")),
                "dreb": _i(st.get("reboundsDefensive")),
                "ast": _i(st.get("assists")), "stl": _i(st.get("steals")),
                "blk": _i(st.get("blocks")), "tov": _i(st.get("turnovers")),
                "fgm": _i(st.get("fieldGoalsMade")),
                "fga": _i(st.get("fieldGoalsAttempted")),
                "fg3m": _i(st.get("threePointersMade")),
                "fg3a": _i(st.get("threePointersAttempted")),
                "ftm": _i(st.get("freeThrowsMade")),
                "fta": _i(st.get("freeThrowsAttempted")),
                "pf": _i(st.get("foulsPersonal")),
                "plus_minus": _i(st.get("plusMinusPoints")),
            })
    gs = _i(game.get("gameStatus", 3)) or 3
    return {
        "game_id": game_id, "game_status": gs, "players": players,
        "home_team": ht, "away_team": at,
        "home_score": _i(game.get("homeTeam", {}).get("score")),
        "away_score": _i(game.get("awayTeam", {}).get("score")),
        "total_players": len(players),
        "total_fga": sum(p["fga"] for p in players),
    }


def _cdn_pbp_to_list(cdn: dict) -> list:
    """Extract actions list from CDN liveData PBP JSON."""
    return cdn.get("game", {}).get("actions", [])


# ---------------------------------------------------------------------------
# Session-scoped fixture: temp cache pre-seeded from CDN files
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seeded_nba_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Temp dir seeded with box + PBP JSON in nba_stats cache format."""
    cache_dir = tmp_path_factory.mktemp("nba_cache")
    now = time.time()
    for gid in _CACHED_GAMES:
        box_src = _CDN_BOX / f"{gid}.json"
        if box_src.exists():
            cdn = json.loads(box_src.read_text(encoding="utf-8"))
            dst = cache_dir / f"boxscore_{gid}.json"
            dst.write_text(json.dumps(_cdn_box_to_parsed(cdn, gid)), encoding="utf-8")
            os.utime(dst, (now, now))
        pbp_src = _CDN_PBP / f"{gid}.json"
        if pbp_src.exists():
            cdn = json.loads(pbp_src.read_text(encoding="utf-8"))
            dst = cache_dir / f"pbp_{gid}.json"
            dst.write_text(json.dumps(_cdn_pbp_to_list(cdn)), encoding="utf-8")
            os.utime(dst, (now, now))
    return cache_dir


# ---------------------------------------------------------------------------
# Autouse: NBA_OFFLINE=1 for every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NBA_OFFLINE", "1")


# ---------------------------------------------------------------------------
# Network poison
# ---------------------------------------------------------------------------

@pytest.fixture()
def poisoned_socket(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Raise OSError on any socket.socket instantiation; return call-count."""
    count: dict = {"n": 0}

    class _Poison:
        def __init__(self, *a, **kw):
            count["n"] += 1
            raise OSError("no network — offline conformance test")

    monkeypatch.setattr(socket, "socket", _Poison)
    return count


# ---------------------------------------------------------------------------
# Client fixture (module-scoped — imports once, patches _NBA_CACHE)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(seeded_nba_cache: Path) -> Any:
    """NBALeagueClient with _NBA_CACHE patched to seeded temp dir."""
    import src.data.nba_stats as _ns
    import src.data.pbp_scraper as _ps

    _ns._NBA_CACHE = str(seeded_nba_cache)
    _ps._NBA_CACHE = str(seeded_nba_cache)

    from domains.basketball_nba.league_client import NBALeagueClient

    return NBALeagueClient(offline=True)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestLeagueClientProtocol:
    def test_isinstance(self, client: Any) -> None:
        from kernel.config.pbp import LeagueClient
        assert isinstance(client, LeagueClient)

    def test_sport_id(self, client: Any) -> None:
        assert client.sport_id == "basketball_nba"

    def test_offline_flag(self, client: Any) -> None:
        assert client._offline is True


# ---------------------------------------------------------------------------
# Offline cache — G1 (0042500401)
# ---------------------------------------------------------------------------

class TestOfflineG1:
    GAME_ID = "0042500401"

    def test_box_returns_data(self, client: Any, poisoned_socket: dict) -> None:
        r = client.get_box_score(self.GAME_ID)
        assert isinstance(r, dict) and r
        assert "players" in r or r.get("game_id") == self.GAME_ID

    def test_box_no_network(self, client: Any, poisoned_socket: dict) -> None:
        client.get_box_score(self.GAME_ID)
        assert poisoned_socket["n"] == 0

    def test_pbp_returns_data(self, client: Any, poisoned_socket: dict) -> None:
        r = client.get_pbp(self.GAME_ID)
        assert r is not None and len(r) > 0

    def test_pbp_no_network(self, client: Any, poisoned_socket: dict) -> None:
        client.get_pbp(self.GAME_ID)
        assert poisoned_socket["n"] == 0

    def test_box_second_call_cache_hit(self, client: Any, poisoned_socket: dict) -> None:
        r1, r2 = client.get_box_score(self.GAME_ID), client.get_box_score(self.GAME_ID)
        assert r1 and r2
        assert poisoned_socket["n"] == 0

    def test_pbp_second_call_cache_hit(self, client: Any, poisoned_socket: dict) -> None:
        r1, r2 = client.get_pbp(self.GAME_ID), client.get_pbp(self.GAME_ID)
        assert r1 and r2
        assert poisoned_socket["n"] == 0


# ---------------------------------------------------------------------------
# Offline cache — G2 (0042500402)
# ---------------------------------------------------------------------------

class TestOfflineG2:
    GAME_ID = "0042500402"

    def test_box_returns_data(self, client: Any, poisoned_socket: dict) -> None:
        r = client.get_box_score(self.GAME_ID)
        assert isinstance(r, dict) and r

    def test_box_no_network(self, client: Any, poisoned_socket: dict) -> None:
        client.get_box_score(self.GAME_ID)
        assert poisoned_socket["n"] == 0

    def test_pbp_returns_data(self, client: Any, poisoned_socket: dict) -> None:
        r = client.get_pbp(self.GAME_ID)
        assert r is not None and len(r) > 0

    def test_pbp_no_network(self, client: Any, poisoned_socket: dict) -> None:
        client.get_pbp(self.GAME_ID)
        assert poisoned_socket["n"] == 0


# ---------------------------------------------------------------------------
# G3 known gap — documented, not tested online
# ---------------------------------------------------------------------------
# 0042500403 absent from data/cache/team_system/{pbp,box}/.
# Seed both files and add TestOfflineG3 mirroring TestOfflineG1 above.

class TestKnownGapG3:
    G3 = "0042500403"

    def test_g3_not_cached(self) -> None:
        """Assert G3 cache absent — documents the known gap."""
        pbp_missing = not (_CDN_PBP / f"{self.G3}.json").exists()
        box_missing = not (_CDN_BOX / f"{self.G3}.json").exists()
        assert pbp_missing or box_missing, (
            "G3 cache files now exist — replace TestKnownGapG3 with TestOfflineG3."
        )
