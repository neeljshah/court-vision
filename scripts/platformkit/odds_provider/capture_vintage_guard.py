"""scripts.platformkit.odds_provider.capture_vintage_guard

Preserve the ORIGINAL ingest captured_at per (game_id, market_type, book,
price-tuple).  QA iter 11 P1: the serve layer re-stamps captured_at to now()
even when odds are unchanged, so consumers cannot distinguish a live tick from
a stale re-serve.  This module keeps an in-memory registry of the EARLIEST
known captured_at; identical odds return t0 (original), changed odds advance
to the new tick.  is_stale_capture=True when the original captured_at is past
the SLA.  No network, no I/O, no $ field; never raises.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from .freshness import _parse_utc  # shared ISO parser; re-uses established impl
from .markets import MarketQuote

logger = logging.getLogger(__name__)

# Default SLA: a captured_at older than this is flagged is_stale_capture=True.
# Matches the moneyline/spread freshness default in freshness.MARKET_MAX_AGE.
DEFAULT_SLA_SEC: float = 900.0  # 15 minutes


# ---------------------------------------------------------------------------
# Internal registry key + value types
# ---------------------------------------------------------------------------

_RegistryKey = Tuple[str, str, str, str]  # (game_id, market_type, book, price_key)
_RegistryValue = Tuple[str, datetime]      # (canonical_captured_at_iso, parsed_dt)


def _price_key(quote: MarketQuote) -> str:
    """A stable string fingerprint of the price-tuple (side, line, odds).

    Two quotes with the same side/line/odds produce the same key.  The key is
    intentionally INDEPENDENT of captured_at so price-unchanged re-serves hash
    identically.  Uses JSON serialisation to avoid float-repr ambiguity.
    """
    parts = {
        "side": quote.side,
        "line": quote.line,
        "odds": round(float(quote.odds), 6) if quote.odds is not None else None,
    }
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode()).hexdigest()[:16]  # noqa: S324 -- not crypto


def _registry_key(quote: MarketQuote) -> _RegistryKey:
    return (
        str(quote.game_id or ""),
        str(quote.market_type or ""),
        str(quote.book or ""),
        _price_key(quote),
    )


def _utc_now(now: Optional[datetime]) -> datetime:
    if now is not None:
        dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Result type (no $ field)
# ---------------------------------------------------------------------------

@dataclass
class VintageResult:
    """Result of a CaptureVintageGuard.guard() call.

    Fields
    ------
    captured_at      : ISO-8601 UTC string -- the EARLIEST known captured_at for
                       this (game,market,book,price-tuple).  Equals the current
                       quote's captured_at only when the price changed or this is
                       the first observation.
    is_stale_capture : True when captured_at is older than the SLA (the original
                       ingest is too old to trust as a live tick).
    age_sec          : Seconds since captured_at, or None when unparseable.
    price_changed    : True when the odds/line moved vs the previous observation
                       (registry advanced to the new captured_at).
    """
    captured_at: str
    is_stale_capture: bool
    age_sec: Optional[float]
    price_changed: bool


# ---------------------------------------------------------------------------
# Guard class
# ---------------------------------------------------------------------------

class CaptureVintageGuard:
    """In-memory registry that preserves the ORIGINAL ingest captured_at.

    Usage::

        guard = CaptureVintageGuard()
        result = guard.guard(quote, now=datetime.now(timezone.utc))

    The registry is per-instance.  Use a single shared instance per daemon
    process so that state accumulates across polling cycles.  On restart the
    registry resets and the next observed timestamp becomes the new baseline --
    this is correct behaviour (we never fabricate a prior history we did not see).
    """

    def __init__(self) -> None:
        # _registry: earliest-known (captured_at_iso, parsed_dt) per price key
        self._registry: Dict[_RegistryKey, _RegistryValue] = {}

    def guard(
        self,
        quote: MarketQuote,
        *,
        now: Optional[datetime] = None,
        sla_sec: float = DEFAULT_SLA_SEC,
    ) -> VintageResult:
        """Apply the vintage guard to *quote*.

        Returns a VintageResult whose captured_at is the EARLIEST known
        captured_at for this (game,market,book,price-tuple).  The quote's own
        captured_at is used as the baseline when:
          - this is the first observation for the price key, OR
          - the odds/line changed (price_changed=True).
        Otherwise the registry's earlier timestamp is returned.

        is_stale_capture is set True when the returned captured_at is >= sla_sec
        old relative to *now*.  This tells the consumer that the original ingest
        time is beyond the freshness SLA and should be surfaced as stale/red even
        though the serve-side wall-clock is recent.

        Never raises: a bad captured_at string falls back gracefully.
        """
        try:
            return self._guard_inner(quote, now=now, sla_sec=sla_sec)
        except Exception:  # noqa: BLE001 -- never sink a row
            logger.exception("CaptureVintageGuard.guard() unexpected error; returning fallback")
            return VintageResult(
                captured_at=str(getattr(quote, "captured_at", "") or ""),
                is_stale_capture=True,
                age_sec=None,
                price_changed=False,
            )

    def _guard_inner(
        self,
        quote: MarketQuote,
        *,
        now: Optional[datetime],
        sla_sec: float,
    ) -> VintageResult:
        reg_key = _registry_key(quote)
        incoming_ts = str(quote.captured_at or "").strip()
        incoming_dt = _parse_utc(incoming_ts)
        reference = _utc_now(now)

        existing = self._registry.get(reg_key)

        if existing is None:
            # First observation: register and return as-is.
            if incoming_dt is not None:
                self._registry[reg_key] = (incoming_ts, incoming_dt)
            canonical_ts = incoming_ts
            canonical_dt = incoming_dt
            price_changed = False
        else:
            # We have a prior observation.  Price key is the SAME (odds unchanged).
            # Use the EARLIER of the two timestamps as the canonical captured_at.
            prior_ts, prior_dt = existing
            price_changed = False  # price key identical -> price unchanged
            # Keep the earlier timestamp; the incoming tick cannot make the
            # canonical older (it is always >= the prior if the daemon is healthy,
            # but we guard both directions).
            if incoming_dt is not None and incoming_dt < prior_dt:
                # Incoming is somehow earlier (clock drift / backfill); advance registry.
                self._registry[reg_key] = (incoming_ts, incoming_dt)
                canonical_ts = incoming_ts
                canonical_dt = incoming_dt
            else:
                # prior is earlier (the common case): return the original timestamp.
                canonical_ts = prior_ts
                canonical_dt = prior_dt

        # Compute age and SLA flag.
        if canonical_dt is not None:
            age_sec = (reference - canonical_dt).total_seconds()
            is_stale = age_sec >= sla_sec
        else:
            age_sec = None
            is_stale = True  # unknown timestamp is conservatively stale

        return VintageResult(
            captured_at=canonical_ts,
            is_stale_capture=is_stale,
            age_sec=age_sec,
            price_changed=price_changed,
        )

    def advance(
        self,
        quote: MarketQuote,
        *,
        new_captured_at: str,
        now: Optional[datetime] = None,
        sla_sec: float = DEFAULT_SLA_SEC,
    ) -> VintageResult:
        """Force registry advancement when odds changed.  price_changed=True.  Never raises."""
        try:
            reg_key = _registry_key(quote)
            new_ts = str(new_captured_at or "").strip()
            new_dt = _parse_utc(new_ts)
            if new_dt is not None:
                self._registry[reg_key] = (new_ts, new_dt)
            reference = _utc_now(now)
            if new_dt is not None:
                age_sec: Optional[float] = (reference - new_dt).total_seconds()
                is_stale = age_sec >= sla_sec
            else:
                age_sec = None
                is_stale = True
            return VintageResult(
                captured_at=new_ts,
                is_stale_capture=is_stale,
                age_sec=age_sec,
                price_changed=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("CaptureVintageGuard.advance() unexpected error")
            return VintageResult(
                captured_at=str(new_captured_at or ""),
                is_stale_capture=True,
                age_sec=None,
                price_changed=True,
            )

    def clear(self) -> None:
        """Reset the registry (useful for tests or periodic GC)."""
        self._registry.clear()

    @property
    def registry_size(self) -> int:
        """Number of price keys currently tracked."""
        return len(self._registry)


# ---------------------------------------------------------------------------
# Module-level convenience (single shared guard for scripts that want a quick
# stateless call without managing their own instance)
# ---------------------------------------------------------------------------

_GLOBAL_GUARD = CaptureVintageGuard()


def guard_quote(
    quote: MarketQuote,
    *,
    now: Optional[datetime] = None,
    sla_sec: float = DEFAULT_SLA_SEC,
) -> VintageResult:
    """Apply the module-level shared guard to *quote*.

    Shortcut for scripts that do not need per-consumer isolation.  The shared
    guard persists for the process lifetime.  Not thread-safe; use your own
    CaptureVintageGuard() instance in a multi-threaded context.
    """
    return _GLOBAL_GUARD.guard(quote, now=now, sla_sec=sla_sec)


__all__ = [
    "DEFAULT_SLA_SEC",
    "CaptureVintageGuard",
    "VintageResult",
    "guard_quote",
]
