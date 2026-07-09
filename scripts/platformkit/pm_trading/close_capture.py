"""scripts.platformkit.pm_trading.close_capture -- closing-line capture per ledger row.

PT-3 workstream: resolves the closing line for a paper-bet row so
clv_ledger.settle_closing_line can fill clv_pct (currently null on all settled
rows because no close ever lands).

JOIN KEY (2026-07-08b): event_id is the ESPN/FanDuel id, NEVER a Kalshi ticker
-- _event_id_for_row derives the real ticker from market_id instead.
Resolution precedence (first non-None wins):
  1. Kalshi public REST  -- settled/resolved market (is_proxy=False); open (True).
  2. Kalshi own-venue quote, kalshi-taken rows ONLY -- reuses
     kx_close_fallback.venue_close_for_row (itself reusing kx_ticker_close);
     close_venue="kalshi", close_kind="kalshi_lock". Fixes the cross-venue-
     basis bug (2026-07-06 audit): a kalshi-taken row's close was silently
     falling through to a DIFFERENT book's line_store snapshot.
  3. line_store snapshot -- close_venue="book" (may differ from taken venue).
  4. Proxy/degraded      -- last-observed line, is_proxy=True, close_source="proxy".
HONESTY CONTRACT (binding):
  * is_proxy=False ONLY for a settled Kalshi market or a true-close line_store
    snapshot (lock window). Every other path stamps is_proxy=True.
  * close_venue ALWAYS present: "kalshi" (levels 1-2, own taken venue) or
    "book" (level 3 fallback). Never inferred silently.
  * CLV sign per clv_ledger.compute_clv: POSITIVE = better number than close.
  * No $ / dollar / pnl / roi / profit field. Units only. CALIBRATION not edge.
  * Real-money gate stays DENY. Never raises; degrades to None on failure.
  * FORWARD-ONLY: never rewrites a previously-stamped ledger row.
INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; stdlib + repo-internal.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_close_capture.py -q
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kalshi import (guarded -- absent when running tests without network deps).
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.odds_provider.kalshi import (
        KalshiProvider as _KalshiProvider,
        parse_events as _parse_events,
    )
    from scripts.platformkit.odds_provider.base import is_unavailable as _is_unavailable
    _KALSHI_OK = True
except Exception:  # noqa: BLE001 -- degrade, never bubble
    _KalshiProvider = None  # type: ignore[assignment,misc]
    _parse_events = None    # type: ignore[assignment]
    _is_unavailable = None  # type: ignore[assignment]
    _KALSHI_OK = False

# ---------------------------------------------------------------------------
# line_store import (guarded).
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.grade_paper_close import close_from_store as _close_from_store
    _LINE_STORE_OK = True
except Exception:  # noqa: BLE001
    _close_from_store = None  # type: ignore[assignment]
    _LINE_STORE_OK = False

# ---------------------------------------------------------------------------
# kx_close_fallback import (guarded) -- REUSES the existing Kalshi-ticker
# own-venue close plumbing; no fetch logic duplicated here.
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.clv.kx_close_fallback import (
        venue_close_for_row as _venue_close_for_row,
    )
    _KX_FALLBACK_OK = True
except Exception:  # noqa: BLE001
    _venue_close_for_row = None  # type: ignore[assignment]
    _KX_FALLBACK_OK = False

_KX_LOCK_KIND = "kalshi_lock"


# ---------------------------------------------------------------------------
# Public result type.
# ---------------------------------------------------------------------------

@dataclass
class CloseResult:
    """Resolved closing line for one two-way market.

    close_home_dec / close_away_dec: decimal odds (> 1.0).
    is_proxy: True = degraded/inferred close, not a confirmed settled price.
    close_source: tag ("kalshi", "kalshi_venue", "line_store", "proxy").
    close_venue: venue that supplied the price -- "kalshi" (own taken venue,
      levels 1-2) or "book" (level 3 fallback, may differ). ALWAYS present.
    close_kind: finer tag, e.g. "kalshi_lock"; None for pre-existing tiers.
    """
    close_home_dec: float
    close_away_dec: float
    is_proxy: bool
    close_source: str
    close_venue: str = "book"
    close_kind: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _event_id_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Kalshi event_ticker: market_id minus trailing "-<TEAM>", else a
    "KX"-shaped event_id (see module join-key note). None if neither fits."""
    mid = str(row.get("market_id") or "").strip()
    if mid and "-" in mid:
        return mid.rsplit("-", 1)[0]
    eid = str(row.get("event_id") or "").strip()
    return eid if eid.upper().startswith("KX") else None


def _sport_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Sport string from a ledger row. None if absent."""
    sp = str(row.get("sport") or "").strip().lower()
    return sp if sp else None


def _kalshi_close(
    row: Dict[str, Any],
    *,
    kalshi_fetch: Optional[Callable[[str], Any]] = None,
) -> Optional[CloseResult]:
    """Try to resolve a closing line from Kalshi public REST.

    Uses the row's event_id (Kalshi event ticker) to match against the fetched
    Kalshi market list for the row's sport. A resolved market that is still
    'open' on Kalshi is treated as a proxy close (is_proxy=True) because we
    cannot confirm it is the final settled price. A market that is 'resolved'
    or has a status field indicating settlement yields is_proxy=False.

    Never raises; returns None on any failure.
    """
    if not _KALSHI_OK or _KalshiProvider is None:
        return None
    event_id = _event_id_for_row(row)
    if not event_id:
        return None
    sport = _sport_for_row(row)
    if not sport:
        return None
    try:
        if kalshi_fetch is not None:
            # Injected for tests: kalshi_fetch(sport) -> list[dict] raw markets
            markets: Any = kalshi_fetch(sport)
        else:
            # governor_caller: m18 hammered Kalshi ungoverned (kalshi_rate_governor.py).
            provider = _KalshiProvider(use_cache=False, governor_caller="close_capture")
            markets = provider.fetch(sport)
        if _is_unavailable is not None and _is_unavailable(markets):
            return None
        if not isinstance(markets, list):
            return None
        # Find the matching event by event_id / event_ticker.
        matched: List[Dict[str, Any]] = []
        for ev_obj in markets:
            # markets is list[OddsEvent] when using provider directly.
            # In tests it may be raw dicts. Normalize both.
            if hasattr(ev_obj, "event_id"):
                if str(ev_obj.event_id) == event_id:
                    matched.append(ev_obj)
            elif isinstance(ev_obj, dict):
                if str(ev_obj.get("event_ticker", "")) == event_id:
                    matched.append(ev_obj)
    except Exception:  # noqa: BLE001 -- degrade, never bubble
        logger.debug("Kalshi fetch failed for row event_id=%r", event_id, exc_info=True)
        return None
    if not matched:
        return None
    ev_obj = matched[0]
    # Extract home/away decimal odds.
    try:
        if hasattr(ev_obj, "prices"):
            prices = ev_obj.prices.get("kalshi", {})
            h_dec = prices.get("home")
            a_dec = prices.get("away")
            # Determine if the market is settled (status field if raw).
            is_settled = False  # OddsEvent objects are open markets
        else:
            # Raw dict market -- not a normalized OddsEvent.
            h_dec = ev_obj.get("close_home_dec")
            a_dec = ev_obj.get("close_away_dec")
            status = str(ev_obj.get("status", "")).lower()
            is_settled = status in ("resolved", "settled", "finalized")
        if h_dec is None or a_dec is None:
            return None
        if float(h_dec) <= 1.0 or float(a_dec) <= 1.0:
            return None
        # is_proxy=False ONLY for confirmed settled markets; open = proxy.
        return CloseResult(
            close_home_dec=float(h_dec),
            close_away_dec=float(a_dec),
            is_proxy=not is_settled,
            close_source="kalshi",
            close_venue="kalshi",
        )
    except Exception:  # noqa: BLE001
        logger.debug("Kalshi price parse failed for event_id=%r", event_id, exc_info=True)
        return None

def _line_store_close(row: Dict[str, Any]) -> Optional[CloseResult]:
    """Try to resolve a closing line from the line_store snapshot.

    is_proxy mirrors the line_store is_true_close flag: True = within lock
    window before tipoff (confirmed close); False = last-observed quote (proxy).
    Never raises; returns None when no history exists.
    """
    if not _LINE_STORE_OK or _close_from_store is None:
        return None
    try:
        res = _close_from_store(row)
    except Exception:  # noqa: BLE001
        logger.debug("line_store close_from_store failed", exc_info=True)
        return None
    if res is None:
        return None
    home_dec, away_dec, is_true_close = res[0], res[1], res[2]
    if home_dec <= 1.0 or away_dec <= 1.0:
        return None
    # line_store: is_true_close=True -> within lock window -> NOT proxy.
    return CloseResult(
        close_home_dec=float(home_dec),
        close_away_dec=float(away_dec),
        is_proxy=not is_true_close,
        close_source="line_store",
        close_venue="book",
    )


def _kx_venue_close(row: Dict[str, Any]) -> Optional[CloseResult]:
    """Kalshi's OWN pre-commence venue quote for a kalshi-taken row.

    Thin CloseResult wrapper -- ALL gating (taken_book=="kalshi" check) and the
    actual REUSED lookup (clv.kx_close_fallback.lookup_close_legs_kx, which
    itself reuses clv.kx_ticker_close.get_close_prob; no fetch logic
    duplicated) live in kx_close_fallback.venue_close_for_row. Always
    is_proxy=True (the underlying module's own last-tick convention -- never
    promoted to a confirmed true close here). Never raises.
    """
    if not _KX_FALLBACK_OK or _venue_close_for_row is None:
        return None
    try:
        legs = _venue_close_for_row(row)
    except Exception:  # noqa: BLE001 -- degrade, never bubble
        logger.debug("kx_close_fallback venue_close_for_row failed", exc_info=True)
        return None
    if legs is None:
        return None
    home_dec, away_dec = legs[0], legs[1]
    return CloseResult(
        close_home_dec=float(home_dec),
        close_away_dec=float(away_dec),
        is_proxy=True,
        close_source="kalshi_venue",
        close_venue="kalshi",
        close_kind=_KX_LOCK_KIND,
    )


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------

def capture_close(
    row: Dict[str, Any],
    *,
    kalshi_fetch: Optional[Callable[[str], Any]] = None,
) -> Optional[CloseResult]:
    """Resolve a closing line for one ledger *row*. See module docstring for
    the 4-level resolution precedence.

    kalshi_fetch: optional callable(sport) -> list replacing the live Kalshi
    network call (for tests / offline use).

    Returns CloseResult or None (no close at all -> caller treats CLV as
    INSUFFICIENT_DATA). Never raises.
    """
    # Level 1: Kalshi public REST (settled market -- best possible close).
    result = _kalshi_close(row, kalshi_fetch=kalshi_fetch)
    if result is not None:
        return result
    # Level 2: Kalshi's own pre-commence venue quote, kalshi-taken rows only.
    result = _kx_venue_close(row)
    if result is not None:
        return result
    # Level 3 + 4: line_store (true-close or last-observed proxy) -- unchanged
    # for every row, kalshi-taken or not, when levels 1-2 found nothing.
    result = _line_store_close(row)
    return result


__all__ = [
    "CloseResult",
    "capture_close",
]
