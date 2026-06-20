"""scripts.platformkit.bestbets.fresh_best_line -- stale-best-line gate (BBQ5-3).

PROBLEM (stale-never-green violation in the PRICE):
    bestbets_compute selects the highest decimal odds across all_books as
    best_odds / best_book.  A STALE book can carry a higher decimal than any
    FRESH book, and silently win the card's pricing -- a stale price feeding
    the edge divergence is a stale-never-green violation even if the card's
    tipoff is in the future.

THIS MODULE:
    Given the all_books list from a card (each entry: {book, decimal, ts}) and
    a max_age_sec window, return the best FRESH bettable decimal odds, or
    UNAVAILABLE when no fresh book exists.

    A higher STALE decimal NEVER beats a lower FRESH decimal.
    A Polymarket / prediction-market book is NEVER bettable (excluded always).
    A decimal <= 1.0 is invalid (excluded always).
    A missing or unparseable ts is treated as STALE (fail-closed, not fresh).

Public API
----------
best_fresh_line(books, *, now=None, max_age_sec=DEFAULT_MAX_AGE_SEC)
    -> {"status": "ok"|"UNAVAILABLE",
        "best_decimal": float|None,
        "best_book": str|None,
        "fresh_count": int,
        "total_count": int}

    "status" is "ok" when at least one bettable fresh book is available.
    "status" is "UNAVAILABLE" when no bettable fresh book is available.
    "best_decimal" is None when status is "UNAVAILABLE".
    Never raises; no $ / roi / pnl / profit / bankroll / usd / dollar field.

HONESTY RAILS:
  * No dollar field; odds/decimals/calibration only.
  * Fail-closed on missing ts (stale, not fresh).
  * Polymarket/binary excluded via odds_provider.base.is_prediction_market.
  * UNAVAILABLE is honest -- never fabricates a price.
  * Pure: no network, no global state, no file I/O.
  * ASCII only; <= 300 LOC.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_fresh_best_line.py -q
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Reuse the vetted PM-venue classifier -- a PM book is NOT a bettable line.
# Lazy import so the module can be used standalone; failures degrade safely.
def _is_prediction_market(book: str) -> bool:
    """True iff *book* is a Polymarket / Kalshi / PM venue (NOT bettable)."""
    try:
        from scripts.platformkit.odds_provider.base import is_prediction_market
        return is_prediction_market(book)
    except Exception:  # noqa: BLE001 -- classifier must never sink a row
        # Fallback: match known PM names by substring (conservative).
        book_lower = str(book).lower()
        return any(pm in book_lower for pm in ("polymarket", "kalshi", "predictit", "manifold"))


# Default freshness window: 15 minutes (same as odds_provider.freshness).
DEFAULT_MAX_AGE_SEC: float = 900.0

# Sentinel shape returned when no fresh bettable book is available.
_UNAVAILABLE: Dict[str, Any] = {
    "status": "UNAVAILABLE",
    "best_decimal": None,
    "best_book": None,
}


def _parse_utc(ts: Any) -> Optional[datetime]:
    """Parse an ISO-8601 / epoch-float timestamp to a UTC-aware datetime, or None.

    Returns None on any parse failure (fail-closed -> treated as stale).
    Accepts:
      - ISO-8601 string (with or without trailing Z or offset)
      - epoch float / int (seconds since UTC epoch)
    """
    if ts is None:
        return None
    # Numeric epoch seconds (float or int).
    if isinstance(ts, (int, float)):
        try:
            if not math.isfinite(ts):
                return None
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    # ISO-8601 string.
    try:
        s = str(ts).strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001 -- parse must never sink a row
        return None


def _is_fresh(ts: Any, now: datetime, max_age_sec: float) -> bool:
    """True iff *ts* is parseable AND within max_age_sec of *now*.

    Fail-closed: None / unparseable -> False (stale, never fresh).
    """
    dt = _parse_utc(ts)
    if dt is None:
        return False
    age_sec = (now - dt).total_seconds()
    return age_sec <= max_age_sec


def _valid_decimal(value: Any) -> Optional[float]:
    """Coerce *value* to a bettable decimal (> 1.0), else None."""
    try:
        d = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(d):
        return None
    return d if d > 1.0 else None


def best_fresh_line(
    books: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
) -> Dict[str, Any]:
    """Return the best FRESH bettable decimal odds from *books*, or UNAVAILABLE.

    Parameters
    ----------
    books:
        List of book-entry dicts, each shaped {book: str, decimal: float, ts: str|float}.
        The shape mirrors the all_books field on a BestBetCard produced by
        bestbets_compute (read-only from the compute layer).
        Extra keys are silently ignored.
    now:
        Injectable UTC reference datetime (default: datetime.now(timezone.utc)).
        Pass for deterministic tests.
    max_age_sec:
        Maximum age in seconds for a line to be considered fresh.
        Default: DEFAULT_MAX_AGE_SEC (900 s = 15 min).

    Returns
    -------
    Dict with keys:
        status       : "ok" | "UNAVAILABLE"
        best_decimal : float (best fresh bettable decimal) | None (when UNAVAILABLE)
        best_book    : str (name of the best fresh book) | None (when UNAVAILABLE)
        fresh_count  : int (how many fresh bettable books were found)
        total_count  : int (total valid entries processed)

    HONESTY INVARIANTS (never violated):
      - A higher STALE decimal NEVER beats a lower FRESH decimal.
      - A PM / Polymarket / Kalshi book is ALWAYS excluded (not bettable).
      - A decimal <= 1.0 is always invalid and excluded.
      - A missing or unparseable ts is treated as STALE (fail-closed).
      - "UNAVAILABLE" is returned honestly; no fabricated price is returned.
      - No $ / roi / pnl / profit / bankroll / usd / dollar field is ever emitted.
      - Never raises on any input (garbage in -> UNAVAILABLE out).
    """
    try:
        return _best_fresh_line_inner(books, now=now, max_age_sec=max_age_sec)
    except Exception:  # noqa: BLE001 -- gate must never raise
        return dict(_UNAVAILABLE, fresh_count=0, total_count=0)


def _best_fresh_line_inner(
    books: Any,
    now: Optional[datetime],
    max_age_sec: float,
) -> Dict[str, Any]:
    """Implementation -- called from best_fresh_line() which catches all exceptions."""
    ref: datetime = (
        now if (now is not None and getattr(now, "tzinfo", None) is not None)
        else datetime.now(timezone.utc)
        if now is None
        else now.replace(tzinfo=timezone.utc)
    )

    if not isinstance(books, list):
        return dict(_UNAVAILABLE, fresh_count=0, total_count=0)

    best_decimal: Optional[float] = None
    best_book: Optional[str] = None
    fresh_count: int = 0
    total_count: int = 0

    for entry in books:
        if not isinstance(entry, dict):
            continue

        book_name = str(entry.get("book") or "")

        # Exclude prediction-market / Polymarket / Kalshi venues.
        if _is_prediction_market(book_name):
            continue

        # Validate decimal odds: must be > 1.0.
        decimal = _valid_decimal(entry.get("decimal"))
        if decimal is None:
            total_count += 1
            continue

        total_count += 1

        # Freshness gate (fail-closed on missing / unparseable ts).
        ts = entry.get("ts")
        if not _is_fresh(ts, ref, max_age_sec):
            continue

        fresh_count += 1

        # Best = highest decimal (bettor-favourable); a stale higher price NEVER wins.
        if best_decimal is None or decimal > best_decimal:
            best_decimal = decimal
            best_book = book_name

    if best_decimal is None:
        return dict(_UNAVAILABLE, fresh_count=fresh_count, total_count=total_count)

    return {
        "status": "ok",
        "best_decimal": best_decimal,
        "best_book": best_book,
        "fresh_count": fresh_count,
        "total_count": total_count,
    }


__all__ = [
    "DEFAULT_MAX_AGE_SEC",
    "best_fresh_line",
]
