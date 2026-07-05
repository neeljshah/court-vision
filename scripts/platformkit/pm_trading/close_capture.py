"""scripts.platformkit.pm_trading.close_capture -- closing-line capture per ledger row.

PT-3 workstream: resolves the closing line for a paper-bet row so
clv_ledger.settle_closing_line can fill clv_pct (currently null on all settled
rows because no close ever lands).

Resolution precedence (first non-None wins):
  1. Kalshi public REST  -- event_id / market_id on the row (is_proxy=False when
     the Kalshi market is already settled/resolved; is_proxy=True when still open).
  2. line_store snapshot -- get_close() from grade_paper_close (is_proxy mirrors
     is_true_close from the lock-window check).
  3. Proxy/degraded      -- last-observed line from the store (is_proxy=True).
     Emits a "close_source"="proxy" tag so downstream readers can distinguish.

HONESTY CONTRACT (binding):
  * is_proxy=False ONLY when a confirmed close is from a settled/resolved Kalshi
    market OR a true-close line_store snapshot (within the lock window). Every
    other path stamps is_proxy=True -- an honest acknowledgement that the price
    may not be the final cleared line.
  * CLV sign follows clv_ledger.compute_clv convention: POSITIVE = you got a
    BETTER NUMBER than the close (lower implied prob than fair close). Never
    reversed.
  * No $ / dollar / pnl / roi / profit field. Units only. CALIBRATION not edge.
  * Real-money gate stays DENY (never flipped here).
  * Never raises; degrades to None on every failure path.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only;
stdlib + project-internal imports only; no secrets.

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
# Public result type.
# ---------------------------------------------------------------------------

@dataclass
class CloseResult:
    """Resolved closing line for one two-way market.

    close_home_dec / close_away_dec: decimal odds (> 1.0).
    is_proxy: True when this is a degraded / inferred close rather than a
      confirmed settled-market price. Downstream CLV should note is_proxy on
      the ledger row so realmoney_gate and scoreboard can separate true closes
      from proxy closes honestly.
    close_source: descriptive tag ("kalshi", "line_store", "proxy") for audit.
    """
    close_home_dec: float
    close_away_dec: float
    is_proxy: bool
    close_source: str


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _event_id_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Best-effort Kalshi event_id from a ledger row. None if not present."""
    eid = str(row.get("event_id") or "").strip()
    return eid if eid else None


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
            provider = _KalshiProvider(use_cache=False)
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
    )


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------

def capture_close(
    row: Dict[str, Any],
    *,
    kalshi_fetch: Optional[Callable[[str], Any]] = None,
) -> Optional[CloseResult]:
    """Resolve a closing line for one ledger *row*.

    Resolution order:
      1. Kalshi public REST (is_proxy=False only when market is settled).
      2. line_store snapshot (is_proxy mirrors lock-window check).
      3. None -- no close available; caller must treat CLV as INSUFFICIENT_DATA.

    Parameters
    ----------
    row:
        A ledger row dict (as returned by clv_ledger.record_bet).
    kalshi_fetch:
        Optional callable(sport) -> list that replaces the live Kalshi network
        call (for tests / offline use). Receives the row's sport string and
        returns either a list of OddsEvent-like objects or raw market dicts.

    Returns
    -------
    CloseResult or None.
      * CloseResult.is_proxy=False -> confirmed settled close -> clv_is_proxy=False.
      * CloseResult.is_proxy=True  -> proxy / inferred close  -> clv_is_proxy=True.
      * None                       -> no close at all; CLV should be INSUFFICIENT_DATA.
    Never raises.
    """
    # Level 1: Kalshi.
    result = _kalshi_close(row, kalshi_fetch=kalshi_fetch)
    if result is not None:
        return result
    # Level 2 + 3: line_store (true-close or last-observed proxy).
    result = _line_store_close(row)
    return result


__all__ = [
    "CloseResult",
    "capture_close",
]
