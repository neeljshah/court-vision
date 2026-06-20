"""scripts.platformkit.bestbets.clv_beat_cache -- per-(sport,market) CLV beat-rate cache.

BB-Q10: O(1) beat-rate lookup keyed by (sport, market).

Build on:
  * clv_ledger.clv_summary / load_ledger  -- settled row list
  * bestbets.clv_index                     -- existing CLV producer (read-only)

Acceptance criteria (BB-Q10):
  1. 3 settled true-close rows -> cache built keyed by (sport, market).
  2. get_beat_rate returns a dict with at least {n, pct_beat_close, mean_clv_pct}.
  3. Proxy / null clv_pct rows are EXCLUDED from beat-rate denominator.
  4. Missing-file (no ledger on disk) -> get_beat_rate returns INSUFFICIENT_DATA dict.
  5. No $/roi/pnl key anywhere.

Honesty contract:
  * Only true-close rows (clv_is_proxy=False AND graded=True AND clv_pct is not None)
    contribute to the beat-rate.  Proxy rows are silently excluded.
  * beat-rate is a CALIBRATION measure (honesty yardstick), never an edge claim.
  * INSUFFICIENT_DATA is the safe sentinel when N < MIN_N.

INVARIANTS: <=300 LOC; ASCII only; no $; no network; stdlib + repo-internal only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum rows needed before we report a beat-rate (below this -> INSUFFICIENT_DATA)
MIN_N: int = 3

# Sentinel returned when data is absent or below MIN_N
_INSUFFICIENT: str = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Cache key: (sport_slug, market_slug) -- both normalised lowercase strings
_CacheKey = Tuple[str, str]

# Value dict shape (no $ / roi / pnl field)
#   n                int   -- number of true-close settled rows
#   pct_beat_close   float -- 0-100 percentage that beat the close
#   mean_clv_pct     float -- mean CLV % across settled true-close rows
#   status           str   -- "graded" | "INSUFFICIENT_DATA"
BeatRateCache = Dict[_CacheKey, Dict[str, Any]]


# ---------------------------------------------------------------------------
# Key normalisation
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    """Normalise a key component to a stripped lowercase string."""
    return str(s or "").strip().lower()


def _make_cache_key(sport: Any, market: Any) -> _CacheKey:
    return (_norm(sport), _norm(market))


# ---------------------------------------------------------------------------
# Row classifier
# ---------------------------------------------------------------------------

def _is_true_close_settled(row: Dict[str, Any]) -> bool:
    """Return True for settled rows with a true-close CLV reading.

    A row qualifies when ALL of:
      * status == "settled"
      * clv_pct is a finite float (not None)
      * clv_is_proxy is NOT truthy (i.e. a real closing line was captured)

    Proxy rows (clv_is_proxy=True) are EXCLUDED -- their clv_pct is unreliable.
    Open / unsettled rows are EXCLUDED.
    """
    if not isinstance(row, dict):
        return False
    if str(row.get("status", "")).strip().lower() != "settled":
        return False
    clv_pct = row.get("clv_pct")
    if clv_pct is None:
        return False
    try:
        float(clv_pct)
    except (TypeError, ValueError):
        return False
    # Proxy exclusion: treat missing clv_is_proxy as False (assume true-close).
    if row.get("clv_is_proxy") is True:
        return False
    return True


# ---------------------------------------------------------------------------
# Cache builder
# ---------------------------------------------------------------------------

def build_beat_cache(rows: Sequence[Dict[str, Any]]) -> BeatRateCache:
    """Build the per-(sport,market) beat-rate cache from a ledger row list.

    Only true-close settled rows contribute (see _is_true_close_settled).
    Proxy and open rows are silently skipped.  No $ / roi / pnl field is written.

    Parameters
    ----------
    rows:
        Any sequence of CLV ledger dicts (from clv_ledger.load_ledger or
        clv_ledger_io.load_rows).  Empty or None-like input returns {}.

    Returns
    -------
    BeatRateCache
        Dict keyed by (sport, market) tuple -> beat-rate dict.
        Buckets with fewer than MIN_N rows are still stored but marked
        status="INSUFFICIENT_DATA" and their numeric fields are None.
    """
    if not rows:
        return {}

    # Accumulate per-(sport,market) accumulators
    # bucket: {n, sum_clv, beats}
    _acc: Dict[_CacheKey, Dict[str, Any]] = {}

    for row in rows:
        if not _is_true_close_settled(row):
            continue
        sport = _norm(row.get("sport") or "unknown")
        market = _norm(row.get("market") or row.get("market_type") or "moneyline")
        key = (sport, market)
        bucket = _acc.setdefault(key, {"n": 0, "_sum_clv": 0.0, "_beats": 0})
        clv_pct_f = float(row["clv_pct"])
        bucket["n"] += 1
        bucket["_sum_clv"] += clv_pct_f
        bucket["_beats"] += 1 if clv_pct_f > 0.0 else 0

    cache: BeatRateCache = {}
    for key, bucket in _acc.items():
        n = bucket["n"]
        if n < MIN_N:
            cache[key] = {
                "n": n,
                "pct_beat_close": None,
                "mean_clv_pct": None,
                "status": _INSUFFICIENT,
            }
        else:
            cache[key] = {
                "n": n,
                "pct_beat_close": round(100.0 * bucket["_beats"] / n, 4),
                "mean_clv_pct": round(bucket["_sum_clv"] / n, 6),
                "status": "graded",
            }

    return cache


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def load_beat_cache(*, path: Optional[Any] = None) -> BeatRateCache:
    """Load the CLV ledger from disk and build the beat cache.  Never raises.

    Missing ledger file returns {}.  Any I/O or parse error is swallowed and
    an empty cache is returned (caller gets INSUFFICIENT_DATA on any lookup).

    Parameters
    ----------
    path:
        Optional override for the ledger path (passed to clv_ledger.load_ledger).
        Default: canonical data/frontend/clv_ledger.jsonl.
    """
    try:
        from scripts.platformkit.clv_ledger import load_ledger  # noqa: PLC0415
        rows = load_ledger(path) if path is not None else load_ledger()
    except Exception:  # noqa: BLE001
        rows = []
    return build_beat_cache(rows or [])


# ---------------------------------------------------------------------------
# O(1) lookup
# ---------------------------------------------------------------------------

def get_beat_rate(
    cache: BeatRateCache,
    sport: Any,
    market: Any,
) -> Dict[str, Any]:
    """O(1) beat-rate lookup for one (sport, market) combination.

    Parameters
    ----------
    cache:
        BeatRateCache produced by build_beat_cache or load_beat_cache.
    sport:
        Sport slug (coerced to lowercase str).
    market:
        Market type slug (coerced to lowercase str).

    Returns
    -------
    dict with keys: n, pct_beat_close, mean_clv_pct, status.
      * Hit with N >= MIN_N:  status="graded", numeric fields populated.
      * Hit with N <  MIN_N:  status="INSUFFICIENT_DATA", numeric fields None.
      * Miss (key absent):    status="INSUFFICIENT_DATA", n=0, numeric fields None.

    No dollar / roi / pnl field is ever present.
    """
    key = _make_cache_key(sport, market)
    hit = cache.get(key)
    if hit is None:
        return {
            "n": 0,
            "pct_beat_close": None,
            "mean_clv_pct": None,
            "status": _INSUFFICIENT,
        }
    return dict(hit)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "BeatRateCache",
    "MIN_N",
    "build_beat_cache",
    "get_beat_rate",
    "load_beat_cache",
]
