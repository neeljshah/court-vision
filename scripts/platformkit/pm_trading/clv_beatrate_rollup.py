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

Build on: clv_ledger.load_ledger, clv_ledger_enrich.enrich_rows,
governance.policy.Provenance (PROXY / UNAVAILABLE sentinels).

Acceptance (BE-R4-5): >=MIN_N true-close rows -> graded beat_rate; fewer ->
INSUFFICIENT_DATA; all-proxy -> "vs_close UNPROVEN"; no $/roi/pnl/profit key
anywhere; missing ledger -> safe empty list, never raises.

EXECUTION-MODE AXIS (S1f, matrix R9): build_mode_rollup() splits settled rows
into maker / taker / legacy so the CLV series reads per mode, not blended.
TRUTH as of 2026-09-01 (EXECUTION_ENFORCEMENT_MATRIX R9 / NOW.md #3): the
maker pool is EMPTY -- real paper_ingame rows carry taken_book=="paper_ingame"
(the channel default, pre-maker-conversion) = "legacy" here, NOT "maker". No
taker path exists yet either (R1). An empty mode reports n_settled=0 /
INSUFFICIENT_DATA -- never another mode's numbers.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no network; per-file test only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Execution-mode axis: reuses inplay_breaker's CHANNEL/MAKER_SERIES/_row_series
# (read-only; this module does not own inplay_breaker.py) so it can never
# disagree with what the live breaker sees.
try:
    from scripts.platformkit.ingame.inplay_breaker import (
        CHANNEL as _INGAME_CHANNEL, MAKER_SERIES as _MAKER_SERIES,
        _row_series as _breaker_row_series)
except Exception:  # noqa: BLE001 -- graceful: mode axis degrades to all-"taker"
    _INGAME_CHANNEL, _MAKER_SERIES = "paper_ingame", "paper_ingame_maker"
    _breaker_row_series = None

MODE_MAKER = "maker"
MODE_TAKER = "taker"
MODE_LEGACY = "legacy"
EXEC_MODES: Tuple[str, str, str] = (MODE_MAKER, MODE_TAKER, MODE_LEGACY)

def _row_exec_mode(row: Dict[str, Any]) -> str:
    """maker/taker/legacy for one row. Only paper_ingame writes maker fills;
    every other channel is an immediate fill -> "taker". Within paper_ingame:
    series==MAKER_SERIES -> "maker", else "legacy" (untagged is NOT assumed
    maker -- see module docstring / matrix R9)."""
    if _breaker_row_series is not None and row.get("channel") == _INGAME_CHANNEL:
        return MODE_MAKER if _breaker_row_series(row) == _MAKER_SERIES else MODE_LEGACY
    return MODE_TAKER

#: Minimum TRUE-close settled rows per bucket before we report a beat-rate.
MIN_N: int = 5

# Sentinel strings (ASCII, no $, no edge claim)
_VERDICT_GRADED = "graded"
_VERDICT_INSUFFICIENT = "INSUFFICIENT_DATA"
_VERDICT_PROXY_ONLY = "vs_close UNPROVEN"  # all-proxy bucket

# Provenance sentinels (read-only; imported gracefully)
try:
    from governance.policy import Provenance as _Provenance
    _PROXY_PROVENANCE_VALUES = frozenset(
        {_Provenance.FILLED, _Provenance.UNAVAILABLE, _Provenance.UNKNOWN})
    _PROVENANCE_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PROVENANCE_AVAILABLE = False
    _PROXY_PROVENANCE_VALUES = frozenset()  # type: ignore[assignment]

def _is_proxy_by_provenance(row: Dict[str, Any]) -> bool:
    """True if row["provenance"] is a proxy-class Provenance sentinel (False
    if the enum is unavailable or the field is absent)."""
    if not _PROVENANCE_AVAILABLE:
        return False
    raw = row.get("provenance")
    if raw is None:
        return False
    try:
        from governance.policy import Provenance as _P  # noqa: PLC0415
        return _P(raw) in _PROXY_PROVENANCE_VALUES
    except Exception:  # noqa: BLE001
        return False

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

# Internal accumulator
class _Bucket:
    """Accumulates settled rows for one grouping key (sport+market, or mode)."""

    __slots__ = ("n_true", "n_proxy", "n_settled", "_sum_clv", "_beats",
                 "_sum_unit_result", "n_unit_result")

    def __init__(self) -> None:
        self.n_true: int = 0     # settled + true-close (clv_pct not None, not proxy)
        self.n_proxy: int = 0    # settled + proxy close (clv_is_proxy=True)
        self.n_settled: int = 0  # total settled (including proxy)
        self._sum_clv: float = 0.0
        self._beats: int = 0
        self._sum_unit_result: float = 0.0
        self.n_unit_result: int = 0  # rows with a finite fees-netted unit_result

    def add(self, row: Dict[str, Any]) -> None:
        """Incorporate one settled row into the bucket."""
        if not _is_settled(row):
            return
        self.n_settled += 1

        # unit_result (grade_paper_one) is ALREADY fees-netted; context only,
        # not MIN_N-gated, orthogonal to proxy/true-close status.
        raw_ur = row.get("unit_result")
        if raw_ur is not None:
            try:
                ur = float(raw_ur)
                if math.isfinite(ur):
                    self._sum_unit_result += ur
                    self.n_unit_result += 1
            except (TypeError, ValueError):
                pass

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

    def summary(self) -> Dict[str, Any]:
        """CLV + fees-netted summary fields (no $ / roi / pnl field)."""
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
            # Too few true-close rows (also the n_settled==0 empty-pool case):
            # honestly INSUFFICIENT_DATA, never another bucket's numbers.
            verdict = _VERDICT_INSUFFICIENT
            beat_rate = None
            mean_clv_pct = None
        else:
            verdict = _VERDICT_GRADED
            beat_rate = round(100.0 * self._beats / n_true, 4)
            mean_clv_pct = round(self._sum_clv / n_true, 6)

        mean_unit_result = (round(self._sum_unit_result / self.n_unit_result, 6)
                             if self.n_unit_result else None)

        return {
            "n_settled": n_settled,
            "n_true_close": n_true,
            "n_proxy": n_proxy,
            "beat_rate": beat_rate,       # None when verdict != graded
            "mean_clv_pct": mean_clv_pct, # None when verdict != graded
            "n_unit_result": self.n_unit_result,
            "mean_unit_result": mean_unit_result,  # fees netted; context only
            "verdict": verdict,
            # Honesty flags
            "min_n": MIN_N,
            "real_money_deny": True,      # invariant: never authorizes a bet
        }

# Public API
def build_rollup(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate settled CLV ledger rows into a per-(sport,market) summary table.

    Open rows are silently skipped. "legacy" execution-mode rows (see
    _row_exec_mode) are ALSO skipped here -- they predate maker/taker tagging
    and would otherwise silently blend into this headline series; use
    build_mode_rollup() to see them explicitly. Row shape: sport, market,
    n_settled, n_true_close, n_proxy, beat_rate (float|None), mean_clv_pct
    (float|None), n_unit_result, mean_unit_result (float|None, fees netted),
    verdict (graded|INSUFFICIENT_DATA|vs_close UNPROVEN), min_n,
    real_money_deny. Never raises. No $ / roi / pnl / profit field anywhere.
    """
    buckets: Dict[Tuple[str, str], _Bucket] = {}
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        if not _is_settled(row):
            continue
        if _row_exec_mode(row) == MODE_LEGACY:
            continue
        sport = _norm(row.get("sport") or "unknown")
        market = _norm(row.get("market") or row.get("market_type") or "moneyline")
        key = (sport, market)
        if key not in buckets:
            buckets[key] = _Bucket()
        buckets[key].add(row)

    result = [{"sport": sport, "market": market, **bucket.summary()}
              for (sport, market), bucket in buckets.items()]
    result.sort(key=lambda r: (r["sport"], r["market"]))
    return result

def build_mode_rollup(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per-execution-mode (maker / taker / legacy) CLV summary, fees netted.

    Independent of build_rollup()'s (sport, market) headline table -- answers
    "how is the maker channel doing" without mixing in taker/pregame volume.
    An empty mode (maker, as of 2026-09-01 -- matrix R9) reports n_settled=0 /
    INSUFFICIENT_DATA; it never substitutes another mode's numbers. Returns a
    dict keyed "maker"/"taker"/"legacy", each the build_rollup() summary shape
    (minus sport/market, plus "mode"). Never raises.
    """
    buckets: Dict[str, _Bucket] = {mode: _Bucket() for mode in EXEC_MODES}
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        buckets[_row_exec_mode(row)].add(row)  # add() itself skips non-settled

    return {mode: {"mode": mode, **bucket.summary()}
            for mode, bucket in buckets.items()}

def _load_enriched_rows(path: Optional[Any]) -> List[Dict[str, Any]]:
    """Shared load+enrich step for load_and_rollup* -- [] on any failure."""
    try:
        from scripts.platformkit.clv_ledger import load_ledger  # noqa: PLC0415
        from scripts.platformkit.clv_ledger_enrich import enrich_rows  # noqa: PLC0415
        raw = load_ledger(path) if path is not None else load_ledger()
        return enrich_rows(raw or [])
    except Exception:  # noqa: BLE001 -- safe empty rollup on any failure
        return []

def load_and_rollup(*, path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Load the CLV ledger (default clv_ledger.DEFAULT_LEDGER), enrich, roll up.

    Missing ledger file -> empty list, never raises. Enrich fills clv_is_proxy
    / venue gaps on older rows first so proxy detection is accurate.
    """
    return build_rollup(_load_enriched_rows(path))

def load_and_rollup_by_mode(*, path: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
    """load_and_rollup(), but build_mode_rollup() shape (maker/taker/legacy)."""
    return build_mode_rollup(_load_enriched_rows(path))

__all__ = [
    "MIN_N", "build_rollup", "load_and_rollup",
    "MODE_MAKER", "MODE_TAKER", "MODE_LEGACY", "EXEC_MODES",
    "build_mode_rollup", "load_and_rollup_by_mode",
    "_VERDICT_GRADED", "_VERDICT_INSUFFICIENT", "_VERDICT_PROXY_ONLY",
]
