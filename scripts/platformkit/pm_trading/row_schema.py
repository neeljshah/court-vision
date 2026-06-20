"""row_schema.py -- canonical PM paper-ledger row schema for PT-2.

At placement time an EdgeSignal maps to a single canonical paper-ledger row
carrying venue + contract/market identifiers so PM paper bets are auditable and
never confused with sportsbook rows.

DESIGN RAILS (binding):
  * is_pm=True on every row this module emits.
  * market_id MUST be present and non-empty; missing -> status "REJECTED" with
    reason="MISSING_MARKET_ID" (never a silent default).
  * venue MUST be present; missing -> status "REJECTED" with
    reason="MISSING_VENUE".
  * Units (unit count), NEVER dollars.  No $/dollar/pnl/roi key anywhere.
  * channel="paper" and executed=False stamped on every accepted row.
  * The row is a plain dict (JSON-serialisable) so it can be appended to any
    JSONL ledger directly.
  * Calibration, not edge.  fair_prob and market_price (probabilities) are
    carried; no fabricated profit field.

Build only under scripts/platformkit/.  <=300 LOC.  ASCII only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Sibling-import fallback so the file is hermetically testable without the
# full repo installed.
try:
    from scripts.platformkit.pm_trading.edge_signal import Signal
    from scripts.platformkit.pm_trading.venues.base import Side
except ImportError:  # pragma: no cover -- flat-sibling hermetic test path
    from edge_signal import Signal          # type: ignore[no-redef]
    from venues.base import Side            # type: ignore[no-redef]

# The paper channel marker that distinguishes these rows from real orders.
CHANNEL_PAPER = "paper"

# Sentinel written when the row cannot be built.
STATUS_REJECTED = "REJECTED"
STATUS_OPEN = "open"

# Sentinel used when a required identifier is absent.
_UNAVAILABLE = "UNAVAILABLE"


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def canonical_pm_row(
    signal: Signal,
    *,
    venue: Optional[str] = None,
    sport: Optional[str] = None,
    matchup: Optional[str] = None,
    stake_units: float = 1.0,
    fair_prob: Optional[float] = None,
) -> Dict[str, Any]:
    """Map a Signal to a canonical PM paper-ledger row.

    Parameters
    ----------
    signal:
        An EdgeSignal carrying market_id, market_price, edge, side, etc.
    venue:
        Human-readable venue name ("kalshi", "polymarket", "paper", ...).
        REQUIRED -- missing or blank -> returns a REJECTED row.
    sport:
        Optional sport identifier for the bet board (e.g. "nba").
    matchup:
        Optional matchup string (e.g. "BOS@NYK").
    stake_units:
        Unit count (NOT dollars).  Default 1.0 (one unit).
    fair_prob:
        Calibrated model probability for the YES outcome.  If omitted,
        falls back to signal.fair_prob.

    Returns
    -------
    dict
        A canonical PM open-row or a REJECTED sentinel.  The row carries:
          is_pm          True
          market_id      from signal
          venue          as supplied
          channel        "paper"
          executed       False
          status         "open" | "REJECTED"
          rejection_reason  (only on REJECTED rows)
          side           "BUY" | "SELL"
          market_price   venue price in [0, 1] == implied prob
          fair_prob      calibrated model prob for YES
          edge           fair_prob - market_price (raw signal; NOT a claimed edge)
          edge_bps       edge * 10_000
          stake_units    unit count (NEVER $)
          sport          if supplied
          matchup        if supplied
          placed_at      UTC ISO timestamp

        Keys guaranteed ABSENT: dollar, pnl, roi, profit, dollar_stake.
    """
    # ---- validate required fields -----------------------------------------
    missing_market = not signal.market_id or signal.market_id.strip() == ""
    if missing_market:
        return _rejected("MISSING_MARKET_ID",
                         "signal.market_id is empty or blank; row cannot be "
                         "audited without a contract identifier",
                         venue=venue, sport=sport, matchup=matchup)

    missing_venue = not venue or str(venue).strip() == ""
    if missing_venue:
        return _rejected("MISSING_VENUE",
                         "venue must be supplied (e.g. 'kalshi', 'polymarket', "
                         "'paper'); cannot attribute this row to a trading venue",
                         market_id=signal.market_id,
                         sport=sport, matchup=matchup)

    # ---- build the canonical open row -------------------------------------
    fp = float(fair_prob) if fair_prob is not None else signal.fair_prob
    row: Dict[str, Any] = {
        "is_pm": True,
        "market_id": signal.market_id,
        "venue": str(venue).strip().lower(),
        "channel": CHANNEL_PAPER,
        "executed": False,
        "status": STATUS_OPEN,
        "side": signal.side.value if hasattr(signal.side, "value") else str(signal.side),
        "market_price": round(signal.market_price, 6),
        "fair_prob": round(fp, 6),
        "edge": round(signal.edge, 6),
        "edge_bps": round(signal.edge_bps, 4),
        "stake_units": round(float(stake_units), 6),
        "placed_at": _now_iso(),
    }
    # Optional contextual fields
    if sport is not None:
        row["sport"] = str(sport)
    if matchup is not None:
        row["matchup"] = str(matchup)
    if signal.devig_prob is not None:
        row["devig_prob"] = round(signal.devig_prob, 6)
    if signal.consensus_edge_bps is not None:
        row["consensus_edge_bps"] = round(signal.consensus_edge_bps, 4)
    row["thinness"] = signal.thinness
    row["honest_note"] = (
        "PAPER measurement only -- executed=False, channel=paper, "
        "no real orders, no dollar edge claimed. is_pm=True marks a "
        "prediction-market contract row."
    )
    _assert_no_dollar_keys(row)
    return row


def is_valid_pm_row(row: Dict[str, Any]) -> bool:
    """Return True when *row* is an accepted canonical PM open row.

    A row is valid when:
      * status == "open"
      * is_pm is True
      * market_id is a non-empty string
      * venue is a non-empty string
      * executed is False
      * channel == "paper"
      * no dollar/pnl/roi key is present
    """
    if row.get("status") != STATUS_OPEN:
        return False
    if not row.get("is_pm"):
        return False
    if not row.get("market_id") or not str(row["market_id"]).strip():
        return False
    if not row.get("venue") or not str(row["venue"]).strip():
        return False
    if row.get("executed") is not False:
        return False
    if row.get("channel") != CHANNEL_PAPER:
        return False
    try:
        _assert_no_dollar_keys(row)
    except AssertionError:
        return False
    return True


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------

_DOLLAR_KEYS = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl",
})


def _assert_no_dollar_keys(row: Dict[str, Any]) -> None:
    """Raise AssertionError if any forbidden dollar/pnl key appears in *row*."""
    bad = _DOLLAR_KEYS & set(row.keys())
    if bad:
        raise AssertionError(
            "PM row must never carry dollar/pnl keys; found: %s" % sorted(bad)
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rejected(
    reason: str,
    detail: str,
    *,
    market_id: Optional[str] = None,
    venue: Optional[str] = None,
    sport: Optional[str] = None,
    matchup: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a REJECTED sentinel row (never silently defaults)."""
    row: Dict[str, Any] = {
        "is_pm": True,
        "status": STATUS_REJECTED,
        "rejection_reason": reason,
        "rejection_detail": detail,
        "channel": CHANNEL_PAPER,
        "executed": False,
        "placed_at": _now_iso(),
    }
    if market_id:
        row["market_id"] = market_id
    else:
        row["market_id"] = _UNAVAILABLE
    if venue:
        row["venue"] = str(venue).strip().lower()
    else:
        row["venue"] = _UNAVAILABLE
    if sport is not None:
        row["sport"] = str(sport)
    if matchup is not None:
        row["matchup"] = str(matchup)
    _assert_no_dollar_keys(row)
    return row


__all__ = [
    "canonical_pm_row",
    "is_valid_pm_row",
    "CHANNEL_PAPER",
    "STATUS_REJECTED",
    "STATUS_OPEN",
]
