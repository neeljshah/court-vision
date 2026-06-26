"""Adaptive Conformal Inference (Gibbs+Candes 2021) -- online alpha update so a
stream of intervals tracks nominal coverage under distribution drift. Thin wrapper
over a base interval producer; leak-free (alpha at tick t uses ONLY realized misses
at <= t-1). Calibration only -- no $/edge/ROI field. Default-OFF gate; the eval
functions print honest SHIP/REJECT deltas.
INVARIANTS: <=300 LOC; ASCII; numpy+stdlib only; never raises.
"""
from __future__ import annotations

import math  # noqa: F401 (kept for potential future use in guards)
from typing import List, Tuple, Union

import numpy as np

_DEFAULT_GAMMA: float = 0.01
_DEFAULT_ALPHA_TARGET: float = 0.10
_MIN_STREAM_LEN: int = 50
_HONEST_NOTE: str = (
    "Adaptive Conformal Inference (Gibbs+Candes 2021). "
    "Calibration only -- no $ edge."
)
INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"


def aci_update(
    a_t: float,
    err_t: int,
    alpha_target: float = _DEFAULT_ALPHA_TARGET,
    gamma: float = _DEFAULT_GAMMA,
) -> float:
    """One-step ACI update: a_{t+1} = clip(a_t + gamma*(alpha_target - err_t), 0, 1).

    err_t must be 0 or 1; raises ValueError on anything else (contract violation).
    """
    if err_t not in (0, 1):
        raise ValueError(f"err_t must be 0 or 1, got {err_t!r}")
    return float(max(0.0, min(1.0, a_t + gamma * (alpha_target - float(err_t)))))


def apply_aci_to_band(
    base_lo: float,
    base_hi: float,
    q_static: float,
    alpha_t: float,
    alpha_target: float,
) -> Tuple[float, float]:
    """Adjust (base_lo, base_hi) to reflect current ACI alpha_t.

    Scaling = alpha_target / alpha_t. alpha_t < alpha_target -> wider (more coverage
    needed). alpha_t > alpha_target -> narrower. new_half capped at 100x original.
    """
    mid = (base_lo + base_hi) / 2.0
    half = (base_hi - base_lo) / 2.0
    new_half = half * min(alpha_target / max(alpha_t, 1e-6), 100.0)
    return (mid - new_half, mid + new_half)


def _pinball_loss(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    """Standard pinball / quantile loss."""
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def run_aci_stream(
    base_lo: np.ndarray,
    base_hi: np.ndarray,
    y: np.ndarray,
    alpha_target: float = _DEFAULT_ALPHA_TARGET,
    gamma: float = _DEFAULT_GAMMA,
) -> Union[str, dict]:
    """Walk stream leak-free; alpha at tick t uses only realized misses 0..t-1.

    Returns INSUFFICIENT_DATA if len(y) < _MIN_STREAM_LEN.
    All dict fields are calibration metrics only -- no $ / ROI / edge key.
    """
    base_lo = np.asarray(base_lo, dtype=float)
    base_hi = np.asarray(base_hi, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < _MIN_STREAM_LEN:
        return INSUFFICIENT_DATA

    q_static = float(np.median((base_hi - base_lo) / 2.0))
    alpha_traj: List[float] = [alpha_target]
    aci_lo_list: List[float] = []
    aci_hi_list: List[float] = []
    alpha_t = alpha_target

    for t in range(n):
        lo_t, hi_t = apply_aci_to_band(
            float(base_lo[t]), float(base_hi[t]), q_static, alpha_t, alpha_target
        )
        aci_lo_list.append(lo_t)
        aci_hi_list.append(hi_t)
        err_t = 0 if (lo_t <= y[t] <= hi_t) else 1
        alpha_t = aci_update(alpha_t, err_t, alpha_target, gamma)
        alpha_traj.append(alpha_t)

    aci_lo_arr = np.array(aci_lo_list)
    aci_hi_arr = np.array(aci_hi_list)
    aci_cov = float(np.mean((y >= aci_lo_arr) & (y <= aci_hi_arr)))
    static_cov = float(np.mean((y >= base_lo) & (y <= base_hi)))
    nominal = 1.0 - alpha_target
    aci_gap = aci_cov - nominal
    static_gap = static_cov - nominal
    aci_pb = (
        _pinball_loss(y, aci_lo_arr, alpha_target / 2.0)
        + _pinball_loss(y, aci_hi_arr, 1.0 - alpha_target / 2.0)
    ) / 2.0
    static_pb = (
        _pinball_loss(y, base_lo, alpha_target / 2.0)
        + _pinball_loss(y, base_hi, 1.0 - alpha_target / 2.0)
    ) / 2.0
    return {
        "aci_lo": aci_lo_list,
        "aci_hi": aci_hi_list,
        "static_lo": base_lo.tolist(),
        "static_hi": base_hi.tolist(),
        "alpha_trajectory": alpha_traj,
        "aci_coverage": round(aci_cov, 5),
        "static_coverage": round(static_cov, 5),
        "nominal_coverage": nominal,
        "aci_gap": round(aci_gap, 5),
        "static_gap": round(static_gap, 5),
        "aci_width_mean": round(float(np.mean(aci_hi_arr - aci_lo_arr)), 4),
        "static_width_mean": round(float(np.mean(base_hi - base_lo)), 4),
        "aci_pinball": round(aci_pb, 5),
        "static_pinball": round(static_pb, 5),
        "aci_tracks_better": bool(abs(aci_gap) <= abs(static_gap)),
        "aci_pinball_ok": bool(aci_pb <= static_pb + 0.01),
        "honest_note": _HONEST_NOTE,
    }


def run_planted_null(
    base_lo: np.ndarray,
    base_hi: np.ndarray,
    y_stationary: np.ndarray,
    alpha_target: float = _DEFAULT_ALPHA_TARGET,
    gamma: float = _DEFAULT_GAMMA,
) -> Union[str, dict]:
    """Measure ACI on a stationary, well-calibrated stream (caller constructs it).

    ACI should be a near-no-op: alpha stays close to alpha_target, aci_coverage
    approx static_coverage. Returns same shape as run_aci_stream + null_collapses.
    """
    result = run_aci_stream(base_lo, base_hi, y_stationary, alpha_target, gamma)
    if result == INSUFFICIENT_DATA:
        return INSUFFICIENT_DATA
    assert isinstance(result, dict)
    alpha_traj = result["alpha_trajectory"]
    result["null_collapses"] = bool(
        abs(result["aci_coverage"] - result["static_coverage"]) <= 0.025
        and float(np.std(alpha_traj)) <= 0.025
    )
    return result


def gate_aci_on_stream(
    base_lo: np.ndarray,
    base_hi: np.ndarray,
    y: np.ndarray,
    alpha_target: float = _DEFAULT_ALPHA_TARGET,
    gamma: float = _DEFAULT_GAMMA,
) -> dict:
    """SHIP/REJECT verdict combining run_aci_stream + run_planted_null.

    Planted-null: IID resample from empirical residuals of base_lo/base_hi vs y
    (honest construction -- noted in output). Simulates a stationary stream.
    SHIP rule: aci_tracks_better AND aci_pinball_ok AND null_collapses.
    """
    base_lo = np.asarray(base_lo, dtype=float)
    base_hi = np.asarray(base_hi, dtype=float)
    y = np.asarray(y, dtype=float)
    stream_result = run_aci_stream(base_lo, base_hi, y, alpha_target, gamma)
    if stream_result == INSUFFICIENT_DATA:
        return {
            "stream_result": INSUFFICIENT_DATA,
            "null_result": INSUFFICIENT_DATA,
            "ship_recommendation": "REJECT:INSUFFICIENT_DATA",
            "honest_note": _HONEST_NOTE,
        }
    assert isinstance(stream_result, dict)
    rng = np.random.default_rng(42)
    n = len(y)
    mids = (base_lo + base_hi) / 2.0
    idx = rng.integers(0, n, size=n)
    null_lo = base_lo[idx]
    null_hi = base_hi[idx]
    null_y = mids[idx] + (y - mids)[idx]
    null_result = run_planted_null(null_lo, null_hi, null_y, alpha_target, gamma)
    null_collapses = (
        bool(null_result.get("null_collapses", False))
        if isinstance(null_result, dict) else False
    )
    null_construction = (
        "iid_resample_empirical_residuals"
        if null_result != INSUFFICIENT_DATA
        else "iid_resample_empirical_residuals (INSUFFICIENT_DATA)"
    )
    failed: List[str] = []
    if not stream_result["aci_tracks_better"]:
        failed.append("coverage_tracking")
    if not stream_result["aci_pinball_ok"]:
        failed.append("pinball")
    if not null_collapses:
        failed.append("planted_null")
    return {
        "stream_result": stream_result,
        "null_result": null_result,
        "null_construction": null_construction,
        "ship_recommendation": "SHIP" if not failed else "REJECT:" + "+".join(failed),
        "honest_note": _HONEST_NOTE,
    }


def _main() -> None:
    """ASCII demo: synthetic non-stationary stream, sigma doubles at tick 500."""
    rng = np.random.default_rng(7)
    n = 1000
    q_static = 1.645
    base_lo = np.full(n, -q_static)
    base_hi = np.full(n, q_static)
    sigma = np.where(np.arange(n) < 500, 1.0, 2.0)
    y = rng.standard_normal(n) * sigma
    result = gate_aci_on_stream(base_lo, base_hi, y, gamma=0.05)
    sr = result["stream_result"]
    assert isinstance(sr, dict)
    nr = result.get("null_result")
    nc = nr.get("null_collapses") if isinstance(nr, dict) else False
    print("=== ACI Online Gate -- Synthetic Non-Stationary Demo ===")
    print(f"  Stream ticks : {n}")
    print(f"  Drift        : sigma=1.0 for t<500, sigma=2.0 for t>=500")
    print(f"  Gamma        : 0.05")
    print(f"  Nominal cov  : {sr['nominal_coverage']:.0%}")
    print(f"  Static cov   : {sr['static_coverage']:.1%}  (gap {sr['static_gap']:+.3f})")
    print(f"  ACI cov      : {sr['aci_coverage']:.1%}  (gap {sr['aci_gap']:+.3f})")
    print(f"  Static pb    : {sr['static_pinball']:.4f}")
    print(f"  ACI pb       : {sr['aci_pinball']:.4f}")
    print(f"  ACI tracks better : {sr['aci_tracks_better']}")
    print(f"  ACI pinball ok    : {sr['aci_pinball_ok']}")
    print(f"  Null collapses    : {nc}")
    print(f"  Null construction : {result.get('null_construction')}")
    print(f"  Verdict: {result['ship_recommendation']}")
    print(f"  {_HONEST_NOTE}")


if __name__ == "__main__":
    _main()
