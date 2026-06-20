"""scripts.platformkit.odds_provider.inplay_feed -- default in-play feed + liveness.

The NETWORK-touching defaults for inplay_snapshot_daemon, split out so the daemon
module stays loop-logic-only (and <=300 LOC). Both are INJECTABLE into the daemon;
these are merely the real keyless defaults. They REUSE the venue providers and the
ESPN scoreboard -- they never duplicate a fetcher.

  * default_fetch(sport)  -> list[in-play tick-dict] of CURRENT open Kalshi +
    Polymarket markets (the live YES prob each venue quotes RIGHT NOW). Each tick
    CARRIES the venue's own commence_time + close_time so liveness can be decided
    WITHOUT any ESPN cross-join. The price of an OPEN market mid-game IS the live
    in-game number; the daemon's is_live_fn gate drops any whose game is not live.
  * default_is_live_native(tick, now) -> VENUE-NATIVE liveness: is this market's
    game in progress using ONLY the venue's own data on the tick (commence_time /
    close_time / status)? This is the DEFAULT gate -- it never depends on an ESPN
    id cross-join (ESPN event_ids != Kalshi/Polymarket ids, the known landmine
    that gated out every real live tick).
  * default_is_live(game_id, sport=...) -> OPTIONAL ESPN-scoreboard corroborator
    (competitions[].status.type.state == "in"). Kept available for callers that
    can map ids, but NEVER the sole gate: the venue-native check is sufficient on
    its own. Unknown / unconfirmed liveness -> False.

INVARIANTS: build only under scripts/platformkit/; ASCII only; never fabricates;
never raises out of a default (degrades to [] / False).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Venue-native liveness tuning. A game counts as STARTED once its commence_time
# has passed (minus a small pre-tip grace, since venue start stamps can be a hair
# late vs the actual tip). It counts as UNSETTLED while its close/expiry time is
# still in the future. We additionally REQUIRE positive evidence the game is live
# right NOW, not merely "open with a past start": a venue's start stamp can be a
# market-CREATION date (Polymarket startDate is creation, not tip-off -- a futures
# contract opened months ago would otherwise read as 'started + unsettled'). So a
# start in the past only counts as live if it is within MAX_LIVE_SINCE_START of
# now (a single game runs at most a few hours). When a venue gives NO commence_time
# at all (e.g. Kalshi only exposes a close_time here), we fall back to a
# plausible-live WINDOW: the market is open AND its close_time is within the next
# LIVE_WINDOW_BEFORE_CLOSE (a sports game settles within hours of going live, so an
# open market closing soon is most likely live, not a far-future pregame contract).
START_GRACE = timedelta(minutes=5)
MAX_LIVE_SINCE_START = timedelta(hours=6)
LIVE_WINDOW_BEFORE_CLOSE = timedelta(hours=6)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse a venue timestamp (ISO-8601, possibly 'Z'-suffixed) to aware UTC.

    Tolerant: trailing 'Z' -> +00:00; a naive stamp is assumed UTC; anything
    unparseable -> None (the caller treats a missing stamp as 'unknown').
    """
    if value in (None, ""):
        return None
    try:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_scoreboard(sport: str) -> Optional[Dict[str, Any]]:
    """Fetch the ESPN scoreboard for *sport* (keyless). None on any failure.

    Back-compat shim returning the BODY only. Callers needing the TRUE body-fetch
    time (frozen-feed guard) use fetch_scoreboard_meta (LA-P0-a stale-never-green).
    """
    body, _ts = fetch_scoreboard_meta(sport)
    return body


def fetch_scoreboard_meta(sport: str) -> tuple:
    """(scoreboard_body, true_fetched_at_iso) for *sport* (keyless).

    Uses disk_cache_get_meta so a CACHED/frozen scoreboard carries its ORIGINAL
    fetch time (never now()), letting callers stamp source freshness so a stopped
    feed cannot re-stamp itself fresh. (None, None) on any failure.
    """
    try:
        from .espn import _LEAGUE_PATH, _SITE  # reuse the league map + base URL
        from .http_cache import disk_cache_get_meta
        path = _LEAGUE_PATH.get(str(sport).lower())
        if not path:
            return (None, None)
        body, fetched_at, _hit = disk_cache_get_meta(
            "%s/%s/scoreboard" % (_SITE, path))
        return (body, fetched_at)
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.debug("scoreboard fetch failed for %s: %s", sport, exc)
        return (None, None)


def default_is_live(game_id: str, *, sport: str = "",
                    scoreboard: Optional[Dict[str, Any]] = None) -> bool:
    """Is *game_id* IN PROGRESS per the ESPN scoreboard?

    A *scoreboard* payload may be injected (offline); otherwise fetched once via
    the keyless ESPN site API. Reads competitions[].status.type.state == "in"
    ("pre"=pregame, "post"=final). Never raises: a feed/parse failure returns False
    (we do NOT capture a game we cannot confirm is live).
    """
    try:
        board = scoreboard if scoreboard is not None else fetch_scoreboard(sport)
        if not isinstance(board, dict):
            return False
        for ev in board.get("events") or []:
            if str(ev.get("id") or "") != str(game_id):
                continue
            comp = (ev.get("competitions") or [{}])[0]
            state = ((comp.get("status") or {}).get("type") or {}).get("state")
            return str(state).lower() == "in"
    except Exception as exc:  # noqa: BLE001 -- unknown liveness -> not live
        logger.debug("is_live(%s) failed: %s", game_id, exc)
    return False


def default_is_live_native(tick: Dict[str, Any],
                           now: Optional[datetime] = None) -> bool:
    """VENUE-NATIVE liveness for one in-play *tick*, using ONLY its own fields.

    No ESPN id cross-join (ESPN event_ids != Kalshi/Polymarket ids -- that join
    gates out every real live tick). A market is IN-PLAY when, per the venue's own
    data on the tick:

      1. it is OPEN/tradeable -- venues only list open markets, and any explicit
         status on the tick must not say closed/settled/resolved; AND
      2. its game has STARTED RECENTLY -- now-MAX_LIVE_SINCE_START <= commence_time
         <= now+START_GRACE. The upper grace absorbs a hair-late tip stamp; the
         lower bound is the honesty guard: a start far in the PAST is treated as a
         market-CREATION date (e.g. a Polymarket futures contract), NOT a live game,
         so it is EXCLUDED; AND
      3. it is NOT yet settled -- close_time is in the future (or absent).

    Fallback when commence_time is MISSING (e.g. a Kalshi market here exposes only
    a close_time): treat as in-play iff the market is still open AND its close_time
    is within the next LIVE_WINDOW_BEFORE_CLOSE -- an open market settling soon is
    most likely live, not a far-future pregame contract. If BOTH commence_time and
    close_time are missing, liveness is unknown -> False (never capture a market we
    cannot confirm is live; a pregame/settled market must never leak through).
    """
    try:
        if not isinstance(tick, dict):
            return False
        nowdt = now or datetime.now(timezone.utc)
        if nowdt.tzinfo is None:
            nowdt = nowdt.replace(tzinfo=timezone.utc)
        nowdt = nowdt.astimezone(timezone.utc)

        status = str(tick.get("status") or "").strip().lower()
        if status in ("closed", "settled", "resolved", "finalized", "final"):
            return False
        # Explicit live status (ESPN scoreboard state == "in"): the source OWNS the
        # score state for this exact event, so it is authoritatively in-progress.
        # Admit it directly -- it carries no commence/close stamps (an in-progress
        # game must not be re-tested as 'recently started'). HONESTY GUARD (2c): a
        # 'in' body re-served off a FROZEN/cached feed must NOT stay live forever, so
        # if the tick carries a source_ts (the body's TRUE fetch time) we require it
        # to be non-stale. A missing source_ts is admitted (back-compat: native ESPN
        # ticks without freshness metadata behave as before).
        if status in ("in", "in_play", "live", "in_progress"):
            src = tick.get("source_ts")
            if src is None:
                return True
            from .inplay_freshness import source_fresh
            return source_fresh(src, nowdt)

        commence = _parse_ts(tick.get("commence_time"))
        close = _parse_ts(tick.get("close_time"))

        # Honesty guard: a market already past its settlement bound is NOT in-play.
        if close is not None and close <= nowdt:
            return False

        if commence is not None:
            # Recently started: within [now - MAX_LIVE_SINCE_START, now + grace].
            started = commence - START_GRACE <= nowdt
            recent = commence >= nowdt - MAX_LIVE_SINCE_START
            # close already handled above (None or future here).
            return bool(started and recent)

        # No commence_time: heuristic window off close_time only.
        if close is not None:
            return bool(nowdt <= close <= nowdt + LIVE_WINDOW_BEFORE_CLOSE)
    except Exception as exc:  # noqa: BLE001 -- unknown liveness -> not live
        logger.debug("is_live_native failed: %s", exc)
    return False


def _venue_times(venue: str, ev: Any) -> tuple:
    """(commence_time, close_time) strings for one OddsEvent, per venue semantics.

    The normalized OddsEvent.commence_time means DIFFERENT things per venue today:
      * polymarket -- it is the market startDate (the real game START).
      * kalshi     -- it is the market close_time (a future SETTLEMENT bound), the
                      only time Kalshi's two-leg parser surfaces; there is no
                      explicit start here, so we leave commence_time None and let
                      the venue-native heuristic use close_time's live-window.
    Returns plain strings (or None) so the tick stays JSON-serialisable. Unknown
    venue -> treat the stamp as a start (the common case).
    """
    raw = getattr(ev, "commence_time", None)
    v = str(venue or "").strip().lower()
    if v == "kalshi":
        return (None, raw)        # raw is a close_time, not a start
    return (raw, None)            # polymarket / default: raw is a start


def default_fetch(sport: str) -> List[Dict[str, Any]]:
    """Current LIQUID in-play ticks for *sport* (Kalshi PRIMARY) + DEGRADED corroborators.

    LIQUIDITY GATE (4b -- the honest fix for "listed but untraded"): the ONLY ticks
    emitted as TRADEABLE in-play prices come from inplay_kalshi.fetch_inplay, which
    applies the is_liquid gate (tight *_dollars spread + real volume_fp + real depth)
    on the LIVE fields. An ungated ESPN / Polymarket moneyline carries NO venue depth,
    so it can never be PROVEN tradeable -- a frozen ESPN:DraftKings line on a 7-1
    blowout must NOT be graded as an in-play price. We still surface ESPN/PM as
    CORROBORATORS, but tag each tradeable=False so the daemon does NOT persist them
    into the in-play store; they are DEGRADED context, not a tradeable in-play number.

    Reuses the venue providers (NOT a duplicated fetcher). Per-source error isolation:
    a Kalshi/ESPN/PM failure contributes nothing and never sinks the others. Never
    raises; never fabricates a price.
    """
    out: List[Dict[str, Any]] = []
    # PRIMARY: Kalshi liquid in-play (is_liquid-gated -> tradeable in-play prices).
    try:
        from .inplay_kalshi import fetch_inplay as fetch_kalshi_inplay
        for tick in (fetch_kalshi_inplay(sport) or []):
            t = dict(tick)
            t["tradeable"] = True   # cleared the is_liquid gate
            # Liveness for the daemon's native gate: a market that cleared is_liquid
            # (real traded volume + tight spread + 2-sided depth, status=open) is an
            # authoritatively-trading in-play market -> status="in". source_ts = the
            # fetch time (tick ts) so the 2c freshness guard keeps it live only while
            # the feed is actually refreshing (a frozen Kalshi body goes stale->RED).
            t.setdefault("status", "in")
            t.setdefault("source_ts", tick.get("ts"))
            out.append(t)
    except Exception as exc:  # noqa: BLE001 -- Kalshi must not sink the corroborators
        logger.debug("kalshi in-play feed failed for %s: %s", sport, exc)
    # CORROBORATORS (DEGRADED, never tradeable): ESPN live-moneyline has no depth.
    try:
        from .inplay_espn import fetch_espn_inplay
        for tick in (fetch_espn_inplay(sport) or []):
            t = dict(tick)
            t["tradeable"] = False  # ungated/depthless -> DEGRADED, not in-play
            out.append(t)
    except Exception as exc:  # noqa: BLE001 -- ESPN must not sink the other sources
        logger.debug("espn in-play feed failed for %s: %s", sport, exc)
    try:
        from .polymarket import PolymarketProvider
        for prov in (PolymarketProvider(),):
            try:
                events = prov.fetch(sport)
            except Exception as exc:  # noqa: BLE001 -- one venue must not sink the other
                logger.debug("%s fetch failed for %s: %s", prov.name, sport, exc)
                continue
            if not isinstance(events, list):
                continue  # UNAVAILABLE dict -> skip
            for ev in events:
                prices = (getattr(ev, "prices", {}) or {}).get(prov.name, {})
                ev_commence, ev_close = _venue_times(prov.name, ev)
                for side in ("home", "away"):
                    dec = prices.get(side)
                    prob = (1.0 / dec) if isinstance(dec, (int, float)) and dec > 1.0 else None
                    if prob is None:
                        continue
                    out.append({
                        "sport": sport, "game_id": getattr(ev, "event_id", ""),
                        "venue": prov.name, "market_type": "moneyline",
                        "side": side, "ticker": getattr(ev, "event_id", ""),
                        "prob": prob,
                        # Venue-native liveness fields (no ESPN cross-join needed).
                        "commence_time": ev_commence, "close_time": ev_close,
                        "status": "open",
                        # No venue depth on a PM moneyline here -> DEGRADED corroborator.
                        "tradeable": False,
                    })
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("default in-play fetch failed for %s: %s", sport, exc)
    return out


__all__ = ["fetch_scoreboard", "fetch_scoreboard_meta", "default_is_live",
           "default_is_live_native", "default_fetch"]
