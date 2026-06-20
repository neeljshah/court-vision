"""scripts/platformkit/resolution_collapse_guard.py -- Murphy RESOLUTION collapse guard.

A corpus with near-zero Murphy RESOLUTION is NON-DISCRIMINATING: calibrated but useless.
Classic degenerate case: every prediction == base_rate (1-2 distinct values) -> RES ~= 0.
This module is READOUT-ONLY. It MUTATES NOTHING.

Verdict taxonomy:
  DISCRIMINATING    -- RES above floor AND distinct_prob_ratio above floor
  COLLAPSED         -- RES below floor OR distinct_prob_ratio below floor (either trips)
  INSUFFICIENT_DATA -- n < MIN_N (never fabricates DISCRIMINATING)

Thresholds:
  RES_FLOOR=0.001  DISTINCT_PROB_FLOOR=0.05  MIN_N=30 (matches calib_decomp.MIN_N_TOTAL)

HONEST ANCHOR: CALIBRATION != EDGE. Low RES -> non-discriminating; edge off such a corpus
is fabricated. UNITS only. No dollar / ROI / P&L / edge / profit keys anywhere.

Build on (read-only):
  calib_decomp.decompose            -- Murphy decomposition (resolution/UNC)
  calibrator_select.load_sport_probs -- injectable loader seam
  recalibration._ece                -- (informational, not gating)

Per-file test: python -m pytest scripts/platformkit/test_resolution_collapse_guard.py -q
<=300 LOC. ASCII only. No src/kernel/api edits.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.calib_decomp import decompose as _decompose

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MIN_N: int = 30
RES_FLOOR: float = 0.001
DISTINCT_PROB_FLOOR: float = 0.05
PROB_ROUND_DIGITS: int = 4

_NOTE: str = (
    "CALIBRATION not edge. Low RES = non-discriminating corpus; "
    "any edge shown off a collapsed corpus is a fabricated artifact. "
    "Units only. No dollar / ROI / P&L / profit claim."
)

Loader = Callable[[str], Tuple[np.ndarray, np.ndarray]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _forecast_entropy(probs: np.ndarray) -> float:
    """Shannon entropy (bits) of the empirical forecast distribution. Informational only."""
    rounded = np.round(probs, PROB_ROUND_DIGITS)
    vals, counts = np.unique(rounded, return_counts=True)
    if len(vals) == 0:
        return 0.0
    freqs = counts / counts.sum()
    return max(-float(np.sum(freqs * np.log2(freqs + 1e-30))), 0.0)


def _distinct_prob_ratio(probs: np.ndarray) -> float:
    """distinct_rounded_probs / n. Near zero -> corpus collapsed."""
    n = len(probs)
    if n == 0:
        return 0.0
    return float(len(np.unique(np.round(probs, PROB_ROUND_DIGITS)))) / float(n)


# ---------------------------------------------------------------------------
# Core measurement
# ---------------------------------------------------------------------------

def measure(
    probs: Sequence[float],
    outcomes: Sequence[float],
) -> Dict:
    """Compute resolution-collapse diagnostics for one (sport, market) corpus.

    Returns dict with keys:
      verdict           -- "DISCRIMINATING" | "COLLAPSED" | "INSUFFICIENT_DATA"
      n                 -- corpus size
      resolution        -- float or None (Murphy RES)
      uncertainty       -- float or None (Murphy UNC)
      distinct_prob_count -- int
      distinct_prob_ratio -- float (distinct / n)
      forecast_entropy  -- float bits (informational)
      failing_reason    -- str or None (which threshold tripped for COLLAPSED)
      note              -- calibration-not-edge string
      decomp            -- raw calib_decomp.decompose output
    No dollar / ROI / P&L / edge / profit keys.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = int(len(p))

    sentinel: Dict = {
        "verdict": "INSUFFICIENT_DATA",
        "n": n,
        "resolution": None,
        "uncertainty": None,
        "distinct_prob_count": None,
        "distinct_prob_ratio": None,
        "forecast_entropy": None,
        "failing_reason": None,
        "note": _NOTE,
        "decomp": None,
    }

    if n < MIN_N:
        sentinel["failing_reason"] = (
            f"n={n} < MIN_N={MIN_N}; too few observations to judge"
        )
        return sentinel

    decomp = _decompose(p, y)
    if decomp.get("status") == "INSUFFICIENT_DATA":
        sentinel["decomp"] = decomp
        sentinel["failing_reason"] = f"calib_decomp returned INSUFFICIENT_DATA (n={n})"
        return sentinel

    res_val = float(decomp["resolution"])
    unc_val = float(decomp["uncertainty"])
    n_distinct = int(len(np.unique(np.round(p, PROB_ROUND_DIGITS))))
    dp_ratio = _distinct_prob_ratio(p)
    entropy = _forecast_entropy(p)

    # Either floor trips -> COLLAPSED
    failing: Optional[str] = None
    if res_val < RES_FLOOR:
        failing = (
            f"resolution={res_val:.6f} < RES_FLOOR={RES_FLOOR}; "
            "corpus is non-discriminating"
        )
    if dp_ratio < DISTINCT_PROB_FLOOR:
        dp_msg = (
            f"distinct_prob_ratio={dp_ratio:.6f} < DISTINCT_PROB_FLOOR={DISTINCT_PROB_FLOOR} "
            f"({n_distinct} distinct probs over n={n})"
        )
        failing = f"{failing}; ALSO {dp_msg}" if failing else dp_msg

    return {
        "verdict": "COLLAPSED" if failing else "DISCRIMINATING",
        "n": n,
        "resolution": res_val,
        "uncertainty": unc_val,
        "distinct_prob_count": n_distinct,
        "distinct_prob_ratio": round(dp_ratio, 6),
        "forecast_entropy": round(entropy, 6),
        "failing_reason": failing,
        "note": _NOTE,
        "decomp": decomp,
    }


# ---------------------------------------------------------------------------
# Per-sport runner (injectable loader)
# ---------------------------------------------------------------------------

def check_sport(
    sport: str,
    *,
    loader: Optional[Loader] = None,
) -> Dict:
    """Run the collapse guard for one sport via the injectable loader seam.

    loader defaults to calibrator_select.load_sport_probs (real adapter).
    Tests inject a synthetic loader. Load errors -> INSUFFICIENT_DATA sentinel.
    """
    if loader is None:
        from scripts.platformkit.calibrator_select import load_sport_probs  # noqa: PLC0415
        loader = load_sport_probs

    result: Dict = {
        "sport": sport,
        "verdict": "INSUFFICIENT_DATA",
        "n": 0,
        "resolution": None,
        "uncertainty": None,
        "distinct_prob_count": None,
        "distinct_prob_ratio": None,
        "forecast_entropy": None,
        "failing_reason": None,
        "note": _NOTE,
        "decomp": None,
    }

    try:
        p, y = loader(sport)
    except Exception as exc:  # noqa: BLE001
        result["failing_reason"] = f"loader error: {exc}"
        return result

    if len(p) == 0:
        result["failing_reason"] = "loader returned empty arrays"
        return result

    measured = measure(p, y)
    result.update(measured)
    result["sport"] = sport
    return result


def check_all_sports(
    sports: Optional[List[str]] = None,
    *,
    loader: Optional[Loader] = None,
) -> Dict[str, Dict]:
    """Run collapse guard over each sport; return {sport: result}. Never raises."""
    _sports = sports or ["nba", "mlb", "soccer", "tennis"]
    return {s: check_sport(s, loader=loader) for s in _sports}


# ---------------------------------------------------------------------------
# ASCII summary
# ---------------------------------------------------------------------------

def format_result(result: Dict) -> str:
    """Render one result as ASCII. No $ / ROI / edge keys. Calibration framing."""
    sport = result.get("sport", "?")
    v = result.get("verdict", "INSUFFICIENT_DATA")
    n = result.get("n", 0)
    res = result.get("resolution")
    dp = result.get("distinct_prob_ratio")
    ent = result.get("forecast_entropy")
    reason = result.get("failing_reason") or ""
    lines = [f"[resolution_collapse_guard] sport={sport}  verdict={v}  n={n}"]
    if res is not None:
        lines.append(
            f"  Murphy RES={res:.6f} (floor={RES_FLOOR})"
            f"  distinct_ratio={dp:.6f} (floor={DISTINCT_PROB_FLOOR})"
            f"  entropy={ent:.4f} bits"
        )
    if reason:
        lines.append(f"  FAILING REASON: {reason}")
    lines.append(f"  NOTE: {result.get('note', _NOTE)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI smoke-check
# ---------------------------------------------------------------------------

def main() -> int:
    """Quick smoke-check on synthetic data (no real corpus needed)."""
    rng = np.random.default_rng(0)
    n = 200
    p_good = rng.uniform(0.2, 0.8, n)
    y_good = (rng.uniform(size=n) < p_good).astype(float)
    r_good = measure(p_good, y_good)
    print(format_result({**r_good, "sport": "synthetic_healthy"}))

    base = 0.55
    p_degen = np.full(n, base)
    y_degen = (rng.uniform(size=n) < base).astype(float)
    r_degen = measure(p_degen, y_degen)
    print(format_result({**r_degen, "sport": "synthetic_degenerate"}))

    ok_good = r_good["verdict"] == "DISCRIMINATING"
    ok_degen = r_degen["verdict"] == "COLLAPSED"
    print(f"\nsmoke_check: healthy={'PASS' if ok_good else 'FAIL'}"
          f"  degenerate={'PASS' if ok_degen else 'FAIL'}")
    return 0 if (ok_good and ok_degen) else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
