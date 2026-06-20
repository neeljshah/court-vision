"""scripts.platformkit.odds_provider.inplay_espn -- ESPN live-moneyline in-play feed.

A THIRD keyless in-play source alongside the Kalshi/Polymarket prediction markets
(scripts.platformkit.odds_provider.inplay_feed.default_fetch). ESPN's free site API
republishes a sportsbook moneyline (pickcenter[]) on a game's `summary` endpoint,
and the scoreboard carries the game's live STATE (status.type.state == "in"). So for
a game that is IN PROGRESS RIGHT NOW, ESPN gives us a live, keyless, sportsbook
moneyline -- the single most-covered live team-market source across all four sports
(NBA / MLB / soccer / tennis), whereas the PM venues are sparse and offseason-gappy.

WHY THIS IS HONEST IN-PLAY (no ESPN<->PM cross-join landmine): ESPN owns BOTH the
score state AND the line on the SAME event id, so liveness is decided natively on
ESPN's own `state == "in"`. We stamp each emitted tick status="in" so the daemon's
default venue-native liveness gate (which excludes anything settled) admits it, and
we DO NOT stamp a future commence_time (which would make the native gate's "recently
started" test reject an in-progress game). A pre/post game contributes nothing.

  fetch_espn_inplay(sport) -> list[in-play tick-dict] of CURRENT in-progress ESPN
  games' moneylines, one YES-prob tick per side per book, venue="espn:<Book>".
  Reuses EspnProvider's league map + pickcenter parser + the http cache -- never
  duplicates a fetcher. Never raises (degrades to []); never fabricates a price.

INVARIANTS: build only under scripts/platformkit/; ASCII only; <=300 LOC; stdlib +
repo-internal only; reuses espn.parse_pickcenter (no duplicated parse).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ESPN site-API league paths for the IN-PLAY feed. Mirrors espn._LEAGUE_PATH for the
# team sports and ADDS tennis (atp/wta) so a live tennis match's moneyline is caught
# when ESPN exposes one. A sport absent here simply yields no ESPN in-play ticks.
_INPLAY_LEAGUE_PATHS: Dict[str, List[str]] = {
    "nba": ["basketball/nba"],
    "mlb": ["baseball/mlb"],
    "soccer": ["soccer/eng.1"],
    "soccer_intl": ["soccer/fifa.world"],
    "tennis": ["tennis/atp", "tennis/wta"],
}


def _decimal_to_prob(dec: Any) -> Optional[float]:
    """Implied YES prob from decimal odds (>1.0); None if unusable. No vig removal
    here -- the in-play tick schema stores the raw implied prob per side, mirroring
    the PM-venue path in inplay_feed (which also stores 1/decimal per side)."""
    try:
        d = float(dec)
    except (TypeError, ValueError):
        return None
    return (1.0 / d) if d > 1.0 else None


def _live_events(board: Any) -> List[Dict[str, Any]]:
    """In-progress events (status.type.state == 'in') from a scoreboard payload."""
    out: List[Dict[str, Any]] = []
    if not isinstance(board, dict):
        return out
    for ev in board.get("events") or []:
        if not isinstance(ev, dict):
            continue
        comp = (ev.get("competitions") or [{}])[0]
        state = ((comp.get("status") or {}).get("type") or {}).get("state")
        if str(state).lower() == "in":
            out.append(ev)
    return out


def _teams(comp: Dict[str, Any]) -> tuple:
    """(home, away) display names from a competition's competitors."""
    from .espn import _team_name
    home = away = ""
    for c in comp.get("competitors", []) or []:
        if c.get("homeAway") == "home":
            home = _team_name(c)
        elif c.get("homeAway") == "away":
            away = _team_name(c)
    return home, away


def _ticks_for_event(sport: str, path: str, ev: Dict[str, Any]
                     ) -> List[Dict[str, Any]]:
    """Flatten one in-progress ESPN event's pickcenter moneylines into in-play ticks.

    One tick per (book, side); venue="espn:<Book>"; status="in" so the daemon's
    venue-native gate admits it; NO commence_time (an in-progress game must not be
    re-tested as 'recently started'). Never raises -- a bad event yields []."""
    try:
        from .espn import _SITE, parse_pickcenter
        from .http_cache import disk_cache_get_meta
        comp = (ev.get("competitions") or [{}])[0]
        home, away = _teams(comp)
        eid = str(ev.get("id") or "")
        if not eid or not home or not away:
            return []
        # disk_cache_get_meta carries the TRUE wall-clock fetch time of the BODY
        # (never now() on a cache hit). We attach it as source_ts so the daemon can
        # drop a tick re-served off a frozen/cached feed instead of re-stamping it
        # fresh -- the stale-never-green rail (LA-P0-a).
        summary, source_ts, _hit = disk_cache_get_meta(
            "%s/%s/summary?event=%s" % (_SITE, path, eid))
        if not isinstance(summary, dict):
            return []
        prices = parse_pickcenter(summary, home, away)
        out: List[Dict[str, Any]] = []
        for venue, sides in prices.items():
            for side in ("home", "away"):
                prob = _decimal_to_prob(sides.get(side))
                if prob is None:
                    continue
                out.append({
                    "sport": sport, "game_id": eid, "venue": venue,
                    "market_type": "moneyline", "side": side, "ticker": eid,
                    "prob": prob,
                    # Liveness: ESPN owns the score state; stamp it native-live.
                    "commence_time": None, "close_time": None, "status": "in",
                    # TRUE body-fetch time (cache-hit safe): a frozen feed keeps its
                    # OLD source_ts so the daemon drops it stale, never re-stamps now.
                    "source_ts": source_ts,
                })
        return out
    except Exception as exc:  # noqa: BLE001 -- one bad event must not sink the feed
        logger.debug("espn in-play event flatten failed: %s", exc)
        return []


def fetch_espn_inplay(sport: str) -> List[Dict[str, Any]]:
    """Current IN-PROGRESS ESPN games' moneylines for *sport* as in-play ticks.

    Pulls the keyless scoreboard(s) for the sport, keeps only events whose
    status.type.state == "in", and flattens each one's pickcenter moneyline into
    per-side YES-prob ticks (status="in" so the daemon's native gate admits them).
    A sport with no ESPN league path, or no live game, contributes []. Never raises;
    never fabricates a price."""
    paths = _INPLAY_LEAGUE_PATHS.get(str(sport).lower())
    if not paths:
        return []
    out: List[Dict[str, Any]] = []
    for path in paths:
        try:
            from .http_cache import disk_cache_get
            from .espn import _SITE
            board = disk_cache_get("%s/%s/scoreboard" % (_SITE, path))
        except Exception as exc:  # noqa: BLE001 -- one league must not sink the rest
            logger.debug("espn in-play scoreboard failed for %s/%s: %s",
                         sport, path, exc)
            continue
        for ev in _live_events(board):
            out.extend(_ticks_for_event(sport, path, ev))
    return out


__all__ = ["fetch_espn_inplay"]
