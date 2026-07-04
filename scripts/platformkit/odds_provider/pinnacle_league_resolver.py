"""scripts.platformkit.odds_provider.pinnacle_league_resolver -- live league-id
resolution for Pinnacle's rotating tournament leagues.

Pinnacle DELISTS a league id when a tournament rotates (a delisted id 401s from
guest.api.arcadia.pinnacle.com -- not a 404, not an auth/rate-limit problem, just
gone from the live listing). Year-round leagues (NBA, MLB, EPL) are stable and
never rotate; round-specific tournament containers (ATP/WTA majors, FIFA World
Cup) rotate every few days to weeks and CANNOT be hardcoded and stay fresh.

resolve_league_ids(sport) returns the list of currently-live league ids for that
sport:
  - nba / mlb / soccer: static fast-path, no network (stable year-round leagues).
  - tennis / soccer_intl: dynamic -- GET the sport's live leagues listing and
    filter by name + matchupCount, cached to disk with a TTL so we do not
    re-list on every tick, with a stale-cache fallback on fetch failure (a stale
    id beats no id) and an honest [] when nothing is cached and the fetch fails.

invalidate(sport) drops the cached entry so the next resolve re-fetches -- the
caller (pinnacle.py) calls this when a league id 401s mid-fetch.

No $ / edge language. Never fabricates an id; an unresolvable sport degrades to
[] so the provider can emit its normal UNAVAILABLE sentinel.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .http_cache import http_get_json

logger = logging.getLogger(__name__)

_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"

# Static, stable, year-round leagues -- never rotate, no network needed.
# wnba=578 probed live 2026-07-03 (LANE 2): GET /sports shows WNBA as a
# persistent named league under sport id 4 (Basketball), matchupCount=3 live --
# same static shape as nba/mlb/soccer, not a rotating tournament container.
_STATIC_LEAGUE_IDS: Dict[str, List[int]] = {
    "nba":    [487],
    "mlb":    [246],
    "soccer": [1980],
    "wnba":   [578],
}

# Dynamic sports: sport_id to list leagues under + a name/count filter.
_DYNAMIC_SPORT_ID: Dict[str, int] = {
    "tennis": 33,
    "soccer_intl": 29,
}

_TENNIS_EXCLUDE = ("Doubles", "Mixed", "Challenger", "ITF", "UTR")
_TENNIS_CAP = 4
_SOCCER_INTL_CAP = 2

_DEFAULT_TTL_SEC = 3600.0
_DEFAULT_CACHE_PATH = (Path("data") / "cache" / "odds_transport" /
                        "pinnacle_leagues.json")


def _ttl_sec() -> float:
    try:
        return float(os.environ.get("CV_PINNACLE_LEAGUE_TTL_SEC", _DEFAULT_TTL_SEC))
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SEC


def _tennis_match(name: str, matchup_count: int) -> bool:
    if matchup_count <= 0:
        return False
    if not (name.startswith("ATP ") or name.startswith("WTA ")):
        return False
    return not any(bad in name for bad in _TENNIS_EXCLUDE)


def _soccer_intl_match(name: str, matchup_count: int) -> bool:
    if matchup_count <= 0:
        return False
    return "World Cup" in name


_DYNAMIC_FILTER: Dict[str, Callable[[str, int], bool]] = {
    "tennis": _tennis_match,
    "soccer_intl": _soccer_intl_match,
}
_DYNAMIC_CAP: Dict[str, int] = {
    "tennis": _TENNIS_CAP,
    "soccer_intl": _SOCCER_INTL_CAP,
}


def _select_ids(leagues: List[Dict[str, Any]], sport: str) -> List[int]:
    """Filter+sort a leagues listing payload down to this sport's live ids."""
    match = _DYNAMIC_FILTER[sport]
    cap = _DYNAMIC_CAP[sport]
    rows: List[Tuple[int, int]] = []  # (matchupCount, id)
    for league in leagues or []:
        try:
            name = str(league.get("name") or "")
            count = int(league.get("matchupCount") or 0)
            lid = league.get("id")
        except (TypeError, ValueError):
            continue
        if lid is None:
            continue
        if not match(name, count):
            continue
        rows.append((count, int(lid)))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [lid for _count, lid in rows[:cap]]


# --------------------------------------------------------------------------- #
# Disk cache -- keyed by sport, {"ids": [...], "fetched_epoch": float}.
# --------------------------------------------------------------------------- #

def _load_cache(cache_path: Path) -> Dict[str, Any]:
    try:
        with cache_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception as exc:  # noqa: BLE001 -- corrupt/missing cache is non-fatal
        logger.debug("pinnacle league cache read miss for %s: %s", cache_path, exc)
    return {}


def _save_cache(cache_path: Path, data: Dict[str, Any]) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(str(tmp), str(cache_path))
    except Exception as exc:  # noqa: BLE001 -- cache write must never sink a resolve
        logger.debug("pinnacle league cache write skipped for %s: %s", cache_path, exc)


def invalidate(sport: str, cache_path: Optional[Path] = None) -> None:
    """Drop the cached league ids for *sport* so the next resolve re-fetches.

    Called by pinnacle.py when a league id 401s (delisted) mid-fetch. Missing
    cache / missing entry is a no-op; never raises.
    """
    path = cache_path or _DEFAULT_CACHE_PATH
    data = _load_cache(path)
    if sport in data:
        del data[sport]
        _save_cache(path, data)


def resolve_league_ids(
    sport: str,
    *,
    http_get: Callable[[str], Any] = http_get_json,
    now: Callable[[], float] = time.time,
    cache_path: Optional[Path] = None,
) -> List[int]:
    """Return the currently-live Pinnacle league id(s) for *sport*.

    Static sports (nba/mlb/soccer) return immediately, no network. Dynamic
    sports (tennis/soccer_intl) consult a TTL disk cache; on expiry/miss they
    fetch the sport's live leagues listing and filter it. A fetch failure
    returns the cached ids even if stale (a stale id beats none); with no cache
    at all it returns [] (honest empty -- the provider degrades to UNAVAILABLE).
    Never raises.
    """
    sport = (sport or "").lower()
    if sport in _STATIC_LEAGUE_IDS:
        return list(_STATIC_LEAGUE_IDS[sport])
    if sport not in _DYNAMIC_SPORT_ID:
        return []

    path = cache_path or _DEFAULT_CACHE_PATH
    cache = _load_cache(path)
    entry = cache.get(sport) if isinstance(cache, dict) else None
    ttl = _ttl_sec()
    if isinstance(entry, dict):
        fetched_epoch = entry.get("fetched_epoch")
        ids = entry.get("ids")
        if isinstance(fetched_epoch, (int, float)) and isinstance(ids, list):
            if now() - float(fetched_epoch) < ttl:
                return [int(i) for i in ids]

    sport_id = _DYNAMIC_SPORT_ID[sport]
    url = f"{_BASE}/sports/{sport_id}/leagues?all=false"
    try:
        body = http_get(url)
    except Exception as exc:  # noqa: BLE001 -- degrade to stale cache / empty
        logger.warning("pinnacle league listing failed for %s: %s", sport, exc)
        if isinstance(entry, dict) and isinstance(entry.get("ids"), list):
            return [int(i) for i in entry["ids"]]
        return []

    if not isinstance(body, list):
        logger.warning("pinnacle league listing unexpected shape for %s", sport)
        if isinstance(entry, dict) and isinstance(entry.get("ids"), list):
            return [int(i) for i in entry["ids"]]
        return []

    ids = _select_ids(body, sport)
    if ids:
        cache[sport] = {"ids": ids, "fetched_epoch": float(now())}
        _save_cache(path, cache)
        return ids
    # Dynamic fetch succeeded but matched nothing live right now -- fall back to
    # a stale cached entry if one exists, else honest empty.
    if isinstance(entry, dict) and isinstance(entry.get("ids"), list):
        return [int(i) for i in entry["ids"]]
    return []


__all__ = ["resolve_league_ids", "invalidate"]
