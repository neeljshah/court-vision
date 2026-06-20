"""scripts.platformkit.pm_trading.clv_beatrate_rollup -- BE-R4-5.

Cross-sport per-(sport, market) CLV beat-rate summary surface.

DISTINCT FROM bestbets.clv_beat_cache (per-card O(1) lookup):
  * This is a CROSS-SPORT SUMMARY TABLE emitted as a list of row dicts.
  * It is HONEST about proxy provenance, offseason, and thin data:
      - All-proxy bucket  -> beat_rate=None, verdict="vs_close UNPROVEN"
      - N < MIN_N         -> beat_rate=None, verdict="INSUFFICIENT_DATA"
      - True-close N>=MIN_N -> beat_rate=float 0-100, verdict="graded"
  * No dollar / pnl / roi / edge field anywhere.
  * Missing ledger file -> safe empty rollup (empty list), never raises.

Build on:
  * clv_ledger.clv_summary / load_ledger  -- load + aggregate
  * clv_ledger_enrich.enrich_rows         -- fills clv_is_proxy / venue gaps
  * governance.policy.Provenance          -- PROXY / UNAVAILABLE sentinels

Acceptance criteria (BE-R4-5):
  1. 5 settled true-close kalshi rows -> beat_rate computed for that (sport,market).
  2. Fewer than MIN_N rows -> verdict=INSUFFICIENT_DATA, beat_rate=None.
  3. All-proxy bucket -> beat_rate=None, verdict="vs_close UNPROVEN" (not a number).
  4. No $ / dollar / roi / pnl / profit key anywhere in any output row.
  5. Missing ledger -> safe empty rollup (empty list), no exception.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no network; per-file test only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Minimum TRUE-close settled rows per bucket before we report a beat-rate.
MIN_N: int = 5

# Sentinel strings (ASCII, no $, no edge claim)
_VERDICT_GRADED = "graded"
_VERDICT_INSUFFICIENT = "INSUFFICIENT_DATA"
_VERDICT_PROXY_ONLY = "vs_close UNPROVEN"  # all-proxy bucket

# ---------------------------------------------------------------------------
# Provenance sentinels (read-only; imported gracefully)
# ---------------------------------------------------------------------------
try:
    from governance.policy import Provenance as _Provenance
    _PROXY_PROVENANCE_VALUES = frozenset({
        _Provenance.FILLED,
        _Provenance.UNAVAILABLE,
        _Provenance.UNKNOWN,
    })
    _PROVENANCE_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PROVENANCE_AVAILABLE = False
    _PROXY_PROVENANCE_VALUES = frozenset()  # type: ignore[assignment]


def _is_proxy_by_provenance(row: Dict[str, Any]) -> bool:
    """True if the row carries a proxy-class Provenance sentinel.

    Reads the "provenance" field; coerces string values to the Provenance enum.
    Gracefully returns False when the enum is unavailable or the field is absent.
    """
    if not _PROVENANCE_AVAILABLE:
        return False
    raw = row.get("provenance")
    if raw is None:
        return False
    try:
        from governance.policy import Provenance as _P  # noqa: PLC0415
        prov = _P(raw)
        return prov in _PROXY_PROVENANCE_VALUES
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Row classification helpers
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _is_settled(row: Dict[str, Any]) -> bool:
    return _norm(row.get("status")) == "settled"


def _clv_pct(row: Dict[str, Any]) -> Optional[float]:
    """Return clv_pct as float, or None if absent / non-finite."""
    raw = row.get("clv_pct")
    if raw is None:
        return None
    try:
        val = float(raw)
        return val if math.isfinite(val) else None
    except (TypeError, ValueError):
        return None


def _row_is_proxy(row: Dict[str, Any]) -> bool:
    """True when the CLV on this row is a proxy (not a real true close).

    Checks (in order):
      1. Explicit clv_is_proxy=True flag (most common stamp from graders).
      2. Provenance sentinel in PROXY_PROVENANCE_VALUES (governance.policy).
      3. clv_status field containing "proxy" (string variant).
    """
    if row.get("clv_is_proxy") is True:
        return True
    if _is_proxy_by_provenance(row):
        return True
    status = _norm(row.get("clv_status") or "")
    if status == "proxy":
        return True
    return False


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------

class _Bucket:
    """Accumulates rows for one (sport, market) key."""

    __slots__ = ("sport", "market", "n_true", "n_proxy", "n_settled",
                 "_sum_clv", "_beats")

    def __init__(self, sport: str, market: str) -> None:
        self.sport = sport
        self.market = market
        self.n_true: int = 0     # settled + true-close (clv_pct not None, not proxy)
        self.n_proxy: int = 0    # settled + proxy close (clv_is_proxy=True)
        self.n_settled: int = 0  # total settled (including proxy)
        self._sum_clv: float = 0.0
        self._beats: int = 0

    def add(self, row: Dict[str, Any]) -> None:
        """Incorporate one settled row into the bucket."""
        if not _is_settled(row):
            return
        self.n_settled += 1
        proxy = _row_is_proxy(row)
        clv = _clv_pct(row)
        if proxy:
            self.n_proxy += 1
            # Proxy rows do NOT contribute to the beat-rate numerator/denominator.
            return
        # True-close row requires a finite clv_pct.
        if clv is None:
            return
        self.n_true += 1
        self._sum_clv += clv
        if clv > 0.0:
            self._beats += 1

    def to_row(self) -> Dict[str, Any]:
        """Emit one summary row dict (no $ / roi / pnl field)."""
        n_true = self.n_true
        n_proxy = self.n_proxy
        n_settled = self.n_settled

        # Determine verdict
        if n_settled > 0 and n_true == 0:
            # Every settled row was a proxy -- can't report a real beat-rate.
            verdict = _VERDICT_PROXY_ONLY
            beat_rate: Optional[float] = None
            mean_clv_pct: Optional[float] = None
        elif n_true < MIN_N:
            # Too few true-close rows to be reliable.
            verdict = _VERDICT_INSUFFICIENT
            beat_rate = None
            mean_clv_pct = None
        else:
            verdict = _VERDICT_GRADED
            beat_rate = round(100.0 * self._beats / n_true, 4)
            mean_clv_pct = round(self._sum_clv / n_true, 6)

        return {
            "sport": self.sport,
            "market": self.market,
            "n_settled": n_settled,
            "n_true_close": n_true,
            "n_proxy": n_proxy,
            "beat_rate": beat_rate,       # None when verdict != graded
            "mean_clv_pct": mean_clv_pct, # None when verdict != graded
            "verdict": verdict,
            # Honesty flags
            "min_n": MIN_N,
            "real_money_deny": True,      # invariant: never authorizes a bet
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_rollup(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate settled CLV ledger rows into a per-(sport,market) summary table.

    Parameters
    ----------
    rows:
        Any sequence of CLV ledger dicts (from clv_ledger.load_ledger or a test
        fixture).  Open / unsettled rows are silently skipped.

    Returns
    -------
    List of row dicts sorted by (sport, market).  Each dict carries:
      sport, market, n_settled, n_true_close, n_proxy,
      beat_rate (float|None), mean_clv_pct (float|None), verdict (str),
      min_n (int), real_money_deny (True).

    Verdict values:
      "graded"             -- beat_rate is a float; N >= MIN_N true-close rows.
      "INSUFFICIENT_DATA"  -- N < MIN_N true-close rows (may still have proxies).
      "vs_close UNPROVEN"  -- all settled rows are proxy; no true-close grading.

    Never raises.  No $ / roi / pnl / profit / dollar field in any output row.
    """
    buckets: Dict[Tuple[str, str], _Bucket] = {}
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        if not _is_settled(row):
            continue
        sport = _norm(row.get("sport") or "unknown")
        market = _norm(row.get("market") or row.get("market_type") or "moneyline")
        key = (sport, market)
        if key not in buckets:
            buckets[key] = _Bucket(sport, market)
        buckets[key].add(row)

    result = [b.to_row() for b in buckets.values()]
    result.sort(key=lambda r: (r["sport"], r["market"]))
    return result


def load_and_rollup(*, path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Load the CLV ledger from disk, enrich rows, and return the rollup.

    Parameters
    ----------
    path:
        Optional override for the CLV ledger JSONL path.  Default: canonical
        data/frontend/clv_ledger.jsonl from clv_ledger.DEFAULT_LEDGER.

    Returns
    -------
    List of rollup rows (same shape as build_rollup).  Missing ledger file ->
    empty list, never raises.  Any I/O or parse error is swallowed.

    The enrich step fills clv_is_proxy / venue gaps on older rows before the
    rollup aggregates them so proxy detection is accurate even for legacy rows.
    """
    try:
        from scripts.platformkit.clv_ledger import load_ledger  # noqa: PLC0415
        from scripts.platformkit.clv_ledger_enrich import enrich_rows  # noqa: PLC0415
        raw = load_ledger(path) if path is not None else load_ledger()
        rows = enrich_rows(raw or [])
    except Exception:  # noqa: BLE001 -- safe empty rollup on any failure
        rows = []
    return build_rollup(rows)


__all__ = [
    "MIN_N",
    "build_rollup",
    "load_and_rollup",
    # Verdict constants (re-exported for tests / consumers)
    "_VERDICT_GRADED",
    "_VERDICT_INSUFFICIENT",
    "_VERDICT_PROXY_ONLY",
]
