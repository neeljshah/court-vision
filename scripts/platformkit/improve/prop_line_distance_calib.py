"""scripts.platformkit.improve.prop_line_distance_calib -- NBA prop calibration by z-band.

Measures how model reliability varies by standardised line distance
  z = (line - oof_pred) / rolling_sigma
where ``line`` is the .5 line nearest oof_pred and ``rolling_sigma`` is the
empirical residual std computed from rows with game_date < current game ONLY
(fully leak-free), floored at _SIGMA_FLOOR[stat].

Bands
  pickem : |z| < 0.25  -- near-coin-flip, most error-prone
  near   : 0.25 <= |z| < 0.75  -- moderate distance
  far    : |z| >= 0.75  -- easy to price, often calibrated

Returns a list of dicts with keys {stat, band, n, brier, ece, bss, verdict}.
  Thin band (n < MIN_N) -> verdict==INSUFFICIENT_DATA, brier/ece/bss=None.
  CALIBRATION_PROVEN : brier < BRIER_GOOD and ece < ECE_GOOD.
  UNRELIABLE         : brier >= BRIER_UNRELIABLE or ece >= ECE_UNRELIABLE.
  MARGINAL           : otherwise.

Readout-only.  No $-edge, no ROI, no P&L.  Never raises.
CALIBRATION not edge; UNITS not $.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest
      tests/platformkit/improve/test_prop_line_distance_calib.py -q
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_N: int = 30
BANDS: List[str] = ["pickem", "near", "far"]
BAND_EDGES = (0.25, 0.75)  # |z| thresholds

# Verdict thresholds (calibration, not edge).
# BSS (Brier Skill Score vs empirical base-rate) is the primary signal:
# positive BSS means the model beats the null model in that band.
# ECE catches systematic miscalibration even when BSS looks reasonable.
BSS_GOOD: float = 0.5            # bss above this -> genuinely skilful
BSS_UNRELIABLE: float = 0.0      # bss below this -> model worse than or equal to null
ECE_GOOD: float = 0.08           # ece below this -> well-calibrated
ECE_UNRELIABLE: float = 0.15     # ece above this -> systematically miscalibrated

CALIBRATION_PROVEN = "CALIBRATION_PROVEN"
UNRELIABLE = "UNRELIABLE"
MARGINAL = "MARGINAL"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

_NO_METRICS: Dict[str, Any] = {"brier": None, "ece": None, "bss": None}


# ---------------------------------------------------------------------------
# Internal: sigma helpers (leak-free)
# ---------------------------------------------------------------------------

def _safe_float(v: Any) -> Optional[float]:
    """None on non-finite or type error."""
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _compute_rolling_sigma(
    sorted_dates: Sequence[str],
    sorted_preds: Sequence[float],
    sorted_actuals: Sequence[float],
    sigma_floor: float,
) -> List[float]:
    """Return leak-free sigma[i] = empirical residual std from rows[0..i-1].

    Uses rows with date strictly BEFORE sorted_dates[i]. When fewer than 2
    past rows exist falls back to sigma_floor.  Rows with the SAME date as
    sorted_dates[i] are excluded so same-day games do not leak.
    """
    n = len(sorted_dates)
    sigmas: List[float] = []
    residuals: List[float] = []
    prev_date: Optional[str] = None
    # Group rows by date so we can commit each group at once
    # We iterate forward; at each step, residuals accumulated are all rows
    # with date < current date.
    date_residuals: Dict[str, List[float]] = {}
    for i, (d, p, a) in enumerate(zip(sorted_dates, sorted_preds, sorted_actuals)):
        if d not in date_residuals:
            date_residuals[d] = []
        date_residuals[d].append(a - p)

    # Build running list of residuals seen on strictly earlier dates
    committed: List[float] = []
    date_order: List[str] = sorted(set(sorted_dates))
    committed_up_to: Optional[str] = None  # last date whose residuals we added

    # We need O(n) not O(n^2) -- build a prefix-sum approach
    # For each row, sigma = std(residuals from dates < this row's date)
    # We'll build a dict date -> cumulative list and cache by date
    cum_by_date: Dict[str, List[float]] = {}
    running: List[float] = []
    for d in date_order:
        cum_by_date[d] = list(running)  # all residuals from dates before d
        running.extend(date_residuals[d])

    for d, p, a in zip(sorted_dates, sorted_preds, sorted_actuals):
        past = cum_by_date[d]
        if len(past) < 2:
            sigmas.append(sigma_floor)
        else:
            mean_r = sum(past) / len(past)
            var = sum((r - mean_r) ** 2 for r in past) / (len(past) - 1)
            s = math.sqrt(max(var, 1e-9))
            sigmas.append(max(s, sigma_floor))
    return sigmas


# ---------------------------------------------------------------------------
# Internal: band assignment
# ---------------------------------------------------------------------------

def _band(abs_z: float) -> str:
    lo, hi = BAND_EDGES
    if abs_z < lo:
        return "pickem"
    if abs_z < hi:
        return "near"
    return "far"


def _nearest_half_line(pred: float) -> float:
    """Nearest .5 line to pred, clamped >= 0.5 (matches props_eval_nba logic)."""
    if not math.isfinite(pred) or pred < 0:
        return 0.5
    line = round(pred - 0.5) + 0.5
    return max(line, 0.5)


# ---------------------------------------------------------------------------
# Internal: verdict
# ---------------------------------------------------------------------------

def _verdict(brier: Optional[float], ece: Optional[float],
             bss: Optional[float]) -> str:
    """Derive a calibration verdict from Brier, ECE, and BSS.

    BSS (Brier Skill Score vs empirical base-rate) is the primary signal:
      CALIBRATION_PROVEN : high skill (bss >= BSS_GOOD) AND low ECE
      UNRELIABLE         : no skill / negative (bss < BSS_UNRELIABLE) OR high ECE
      MARGINAL           : in between
    """
    if brier is None or ece is None or bss is None:
        return INSUFFICIENT_DATA
    if bss >= BSS_GOOD and ece < ECE_GOOD:
        return CALIBRATION_PROVEN
    if bss < BSS_UNRELIABLE or ece >= ECE_UNRELIABLE:
        return UNRELIABLE
    return MARGINAL


# ---------------------------------------------------------------------------
# Internal: score a band
# ---------------------------------------------------------------------------

def _score_band(
    preds: List[dict],
) -> Dict[str, Any]:
    """Thin wrapper: call score_prop_predictions; return n + brier/ece/bss or None."""
    try:
        from scripts.platformkit.props_eval import score_prop_predictions
        if not preds:
            return {"n": 0, **_NO_METRICS}
        res = score_prop_predictions(preds)
        n = res.get("n", 0) or 0
        if n == 0:
            return {"n": 0, **_NO_METRICS}
        return {
            "n": n,
            "brier": res.get("brier"),
            "ece": res.get("ece"),
            "bss": res.get("brier_skill_score"),
        }
    except Exception:  # noqa: BLE001 -- never raise
        return {"n": 0, **_NO_METRICS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_line_distance_calib(
    df=None,
    *,
    oof_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
    min_n: int = MIN_N,
) -> List[Dict[str, Any]]:
    """Measure NBA prop calibration bucketed by standardised line distance.

    Parameters
    ----------
    df : optional pandas DataFrame with OOF data (pregame_oof.parquet schema).
         If None, loaded from oof_path or the default cache location.
    oof_path : override path to OOF parquet (ignored when df is provided).
    stats : restrict to these stats; defaults to all NBA stats.
    min_n : minimum band size for a reportable verdict (default 30).

    Returns
    -------
    list of dicts, one per (stat, band) pair, keys:
        stat, band, n, brier, ece, bss, verdict
    Absent/empty OOF -> all entries have verdict==INSUFFICIENT_DATA, brier/ece/bss=None.
    Never raises.  No $, roi, pnl, edge, or profit key.
    """
    from scripts.platformkit.props_eval_nba import NBA_STATS, _SIGMA_FLOOR  # noqa: PLC0415

    use_stats: List[str] = list(stats) if stats else list(NBA_STATS)
    _empty_table = _build_empty_table(use_stats)

    try:
        df = _load_oof(df, oof_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_line_distance_calib: OOF load failed: %s", exc)
        return _empty_table

    if df is None:
        return _empty_table

    try:
        import pandas as pd  # noqa: PLC0415
        if not hasattr(df, "columns"):
            return _empty_table
        if len(df) == 0:
            return _empty_table
        required = {"stat", "oof_pred", "actual", "game_date"}
        if not required.issubset(set(df.columns)):
            logger.warning(
                "prop_line_distance_calib: missing columns %s",
                required - set(df.columns),
            )
            return _empty_table
    except Exception:  # noqa: BLE001
        return _empty_table

    result: List[Dict[str, Any]] = []

    for stat in use_stats:
        sigma_floor = _SIGMA_FLOOR.get(stat, 1.0)
        rows = _extract_stat_rows(df, stat)
        if not rows:
            result.extend(_stat_empty(stat))
            continue

        # Sort by date for leak-free sigma
        rows.sort(key=lambda r: r["game_date"])

        dates = [r["game_date"] for r in rows]
        preds_v = [r["pred"] for r in rows]
        actuals_v = [r["actual"] for r in rows]

        sigmas = _compute_rolling_sigma(dates, preds_v, actuals_v, sigma_floor)

        # Build band -> [pred_dict]
        band_preds: Dict[str, List[dict]] = {b: [] for b in BANDS}
        for pred, actual, sigma in zip(preds_v, actuals_v, sigmas):
            line = _nearest_half_line(pred)
            z = (line - pred) / sigma if sigma > 0 else 0.0
            abs_z = abs(z)
            b = _band(abs_z)
            # Gaussian P(actual > line) -- mirrors props_eval_nba logic
            p_over = _phi_over(pred, sigma, line)
            outcome = 1 if actual > line else 0
            band_preds[b].append({"p_over": p_over, "outcome": outcome})

        for band in BANDS:
            bp = band_preds[band]
            scored = _score_band(bp)
            n = scored["n"]
            if n < min_n:
                result.append({
                    "stat": stat, "band": band, "n": n,
                    "brier": None, "ece": None, "bss": None,
                    "verdict": INSUFFICIENT_DATA,
                })
            else:
                brier = scored["brier"]
                ece = scored["ece"]
                bss = scored["bss"]
                result.append({
                    "stat": stat, "band": band, "n": n,
                    "brier": brier, "ece": ece, "bss": bss,
                    "verdict": _verdict(brier, ece, bss),
                })

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phi_over(pred: float, sigma: float, line: float) -> float:
    """P(X > line) under Gaussian(pred, sigma), clipped to (0,1)."""
    if sigma <= 0 or not math.isfinite(pred):
        return 0.5
    z = (line - pred) / sigma
    p = 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))
    return float(min(1.0, max(0.0, p)))


def _extract_stat_rows(df, stat: str) -> List[Dict[str, Any]]:
    """Return [{pred, actual, game_date}] for stat, skipping bad rows."""
    rows: List[Dict[str, Any]] = []
    try:
        sub = df[df["stat"] == stat]
        for _, r in sub.iterrows():
            pred = _safe_float(r.get("oof_pred"))
            actual = _safe_float(r.get("actual"))
            date = r.get("game_date")
            if pred is None or actual is None or date is None:
                continue
            rows.append({"pred": pred, "actual": actual, "game_date": str(date)})
    except Exception:  # noqa: BLE001
        pass
    return rows


def _load_oof(df, oof_path: Optional[str]):
    """Load OOF df if not provided.  Returns None if absent."""
    if df is not None:
        return df
    import os  # noqa: PLC0415
    path = oof_path or os.path.join("data", "cache", "pregame_oof.parquet")
    if not os.path.exists(path):
        logger.info("prop_line_distance_calib: OOF parquet absent: %s", path)
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_line_distance_calib: read_parquet failed: %s", exc)
        return None


def _stat_empty(stat: str) -> List[Dict[str, Any]]:
    return [
        {"stat": stat, "band": b, "n": 0,
         "brier": None, "ece": None, "bss": None,
         "verdict": INSUFFICIENT_DATA}
        for b in BANDS
    ]


def _build_empty_table(use_stats: List[str]) -> List[Dict[str, Any]]:
    out = []
    for stat in use_stats:
        out.extend(_stat_empty(stat))
    return out


__all__ = [
    "run_line_distance_calib",
    "MIN_N",
    "BANDS",
    "CALIBRATION_PROVEN",
    "UNRELIABLE",
    "MARGINAL",
    "INSUFFICIENT_DATA",
]
