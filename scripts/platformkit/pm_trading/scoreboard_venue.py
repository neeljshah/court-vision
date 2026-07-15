"""scripts.platformkit.pm_trading.scoreboard_venue -- per-venue CLV breakdown.

Reads the CLV ledger (via clv_ledger_io.load_rows) and aggregates settled
rows by venue/book (the ``taken_book`` field, normalised to lower-case).
Returns calibration stats in UNITS + CLV only -- NO $ / pnl / ROI field.

OUTPUT SHAPE
------------
{
  "as_of":      "<ISO-8601 UTC>",
  "n_settled":  <int>,               # total settled rows across all venues
  "min_n":      <int>,               # threshold below which INSUFFICIENT_DATA
  "by_venue": {
    "<venue_key>": {
      "n":              <int>,
      "mean_clv_pct":   <float | null>,   # ALL rows -- context only, may include proxy
      "median_clv_pct": <float | null>,   # true-close-preferred headline, see basis
      "basis":          <"true_close" | "proxy_only" | null>,
      "beat_close_rate":<float | null>,   # fraction in [0, 1] (NOT pct)
      "n_true_close":   <int>,
      "n_proxy_close":  <int>
    },
    ...
  },
  "insufficient_data_venues": ["<venue_key>", ...],   # venues below min_n
  "honest_note": "<string>"
}

Venues with n < min_n are reported as INSUFFICIENT_DATA in the
``insufficient_data_venues`` list; their ``by_venue`` entry still carries
the raw n but mean_clv_pct/median_clv_pct/basis and beat_close_rate are null.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no $ / pnl / ROI field;
build only under scripts/platformkit/; per-file test only.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger_io import load_rows

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
DEFAULT_MIN_N: int = 30

_HONEST_NOTE = (
    "CLV (closing-line value) is the honest track-record yardstick per venue. "
    "Positive mean_clv_pct means bets at that venue were placed at a better "
    "number than the closing price on average. beat_close_rate is the fraction "
    "of settled bets where clv_pct > 0. Venues below min_n are reported as "
    "INSUFFICIENT_DATA. No $ edge or ROI is claimed anywhere in this file."
)

# Canonical venue keys for common PM books -- input is normalised lower-case
_KNOWN_VENUES = {"kalshi", "polymarket", "sportsbook"}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_venue(raw: str) -> str:
    """Lower-case + strip. Unknown/empty falls back to 'unknown'."""
    v = raw.strip().lower()
    return v if v else "unknown"


def _settled_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter to rows that are settled and carry a clv_pct value."""
    return [
        r for r in rows
        if r.get("status") == "settled" and r.get("clv_pct") is not None
    ]


def _venue_key(row: Dict[str, Any]) -> str:
    """Derive the venue bucket key from a ledger row.

    Prefers ``venue`` field; falls back to ``taken_book``; finally ``book``.
    All normalised to lower-case string.
    """
    raw = (
        str(row.get("venue") or "").strip()
        or str(row.get("taken_book") or "").strip()
        or str(row.get("book") or "").strip()
    )
    return _normalise_venue(raw)


def _bucket_stats(
    rows: List[Dict[str, Any]], *, min_n: int
) -> Dict[str, Any]:
    """Compute CLV stats for a set of already-settled rows.

    Returns nulls for mean_clv_pct/median_clv_pct/beat_close_rate when n < min_n
    (INSUFFICIENT_DATA semantics).

    median_clv_pct is the true-close-preferred headline (basis="true_close"),
    falling back to all rows only when the venue has zero true-close rows yet
    (basis="proxy_only") -- see n_proxy_close. mean_clv_pct stays the all-rows
    mean: CONTEXT ONLY, may include proxy closes; prefer median_clv_pct/basis.
    """
    n = len(rows)
    n_true = sum(1 for r in rows if not r.get("clv_is_proxy", True))
    n_proxy = sum(1 for r in rows if r.get("clv_is_proxy", False))
    if n == 0 or n < min_n:
        return {
            "n": n,
            "mean_clv_pct": None,
            "median_clv_pct": None,
            "basis": None,
            "beat_close_rate": None,
            "n_true_close": n_true,
            "n_proxy_close": n_proxy,
        }
    clvs = [float(r["clv_pct"]) for r in rows]
    beats = sum(1 for c in clvs if c > 0.0)
    true_clvs = [float(r["clv_pct"]) for r in rows if not r.get("clv_is_proxy", False)]
    if true_clvs:
        median = round(statistics.median(true_clvs), 6)
        basis = "true_close"
    else:
        median = round(statistics.median(clvs), 6)
        basis = "proxy_only"
    return {
        "n": n,
        "mean_clv_pct": round(sum(clvs) / n, 6),
        "median_clv_pct": median,
        "basis": basis,
        "beat_close_rate": round(beats / n, 6),   # fraction [0, 1], not %
        "n_true_close": n_true,
        "n_proxy_close": n_proxy,
    }


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def build_venue_scoreboard(
    *,
    rows: Optional[List[Dict[str, Any]]] = None,
    min_n: int = DEFAULT_MIN_N,
) -> Dict[str, Any]:
    """Aggregate CLV by venue over the settled CLV ledger.

    Parameters
    ----------
    rows : list of dicts, optional
        Injected rows (for tests / deterministic use). When None, loads
        the canonical ledger via clv_ledger_io.load_rows.
    min_n : int
        Minimum number of settled rows required for a venue to report
        real CLV stats. Venues below this threshold return null CLV
        fields and appear in ``insufficient_data_venues``.

    Returns
    -------
    dict
        Output shape documented in the module docstring. Empty ledger
        returns zeros/empty dicts, never crashes.

    Notes
    -----
    NO $ / pnl / ROI field anywhere. CLV and counts only.
    """
    if rows is None:
        rows = load_rows()

    settled = _settled_rows(rows)
    n_total = len(settled)

    # Group by venue key
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for row in settled:
        key = _venue_key(row)
        buckets.setdefault(key, []).append(row)

    by_venue: Dict[str, Any] = {}
    insufficient: List[str] = []

    for venue_key in sorted(buckets):
        venue_rows = buckets[venue_key]
        stats = _bucket_stats(venue_rows, min_n=min_n)
        by_venue[venue_key] = stats
        if stats["mean_clv_pct"] is None and len(venue_rows) > 0:
            insufficient.append(venue_key)
        elif len(venue_rows) == 0:
            insufficient.append(venue_key)

    return {
        "as_of": _now_iso(),
        "n_settled": n_total,
        "min_n": min_n,
        "by_venue": by_venue,
        "insufficient_data_venues": insufficient,
        "honest_note": _HONEST_NOTE,
    }


__all__ = ["build_venue_scoreboard", "DEFAULT_MIN_N"]
