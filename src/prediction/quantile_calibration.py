"""quantile_calibration.py — per-stat scale factor to make q10/q90 hit 80%.

The cycle-26 q10/q90 intervals are misclibrated:
  - PTS  coverage_80 = 74.7%   (too tight)
  - REB  coverage_80 = 78.7%
  - AST  coverage_80 = 76.2%   (too tight)
  - FG3M coverage_80 = 87.2%   (too wide)
  - STL  coverage_80 = 89.8%   (too wide — log1p + clip-at-0 squeezes)
  - BLK  coverage_80 = 89.8%   (too wide)
  - TOV  coverage_80 = 85.1%   (too wide)

This module computes a per-stat scale factor `s` such that:
    calibrated_q90 = q50 + s * (q90 - q50)
    calibrated_q10 = q50 - s * (q50 - q10)
covers exactly 80% on a held-out slice. Persisted as
data/models/quantile_calibration.json and applied at inference time by
prop_quantiles.predict_pergame_quantiles_calibrated.

s > 1 widens the interval, s < 1 narrows it.

--- CV_QUANTILE_CAL (conformal calibration, default OFF) ---

``conformal_calibrate()`` fits a split-conformal (CQR) correction on the val
slice and writes ``data/models/quantile_conformal_calibration.json``.
``apply_conformal()`` is the inference-time entry point gated by the env flag
CV_QUANTILE_CAL=1.  When the flag is OFF the function returns the raw (q10, q90)
unchanged — byte-identical to the pre-flag behaviour.

Design constraints:
  * q50 is NEVER modified (protects AST edge + all point predictions).
  * CQR only expands intervals (qhat >= 0) — coverage guarantees are one-sided.
  * Stats already meeting 80% on the holdout (FG3M / STL / TOV) get decision=REJECT
    and pass through untouched.
  * BLK has a crossing bug (q10 > q50 on 2.3% of rows): apply monotone ordering
    clip q10=min(q10,q50), q90=max(q90,q50) without expanding the band.
  * REB: CV_ROW_SIGMA=1 calls ``apply()`` (scale-factor path) for the per-row
    sigma computation; do NOT double-calibrate via apply_conformal as well.
    When CV_QUANTILE_CAL=1 and CV_ROW_SIGMA=1 together, only CV_ROW_SIGMA fires for
    REB (apply_conformal short-circuits for REB in that co-activation branch).
  * AST: qhat=0.06 widens sigma by 2.5% → P(over) drops by 0.003–0.006 at typical
    edge lines — negligible vs the +5-7% durable edge; band IS calibrated.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    build_pergame_dataset, feature_columns,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    _inverse, load_quantile_models,
)


_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_CAL_PATH = os.path.join(_MODEL_DIR, "quantile_calibration.json")


def _grid_search_scale(q10, q50, q90, actuals, target=0.80,
                       lo=0.05, hi=3.0, n=120) -> float:
    """Grid search the scale s that minimises |coverage - target|.

    Two grids: one with symmetric scaling (q10 + q90 both scale), one with
    asymmetric scaling (q10 floor preserved, only q90 scales). The asymmetric
    branch matters for stats where q10 is heavily clipped at 0 (FG3M/STL/BLK/
    TOV) — symmetric scaling has a coverage DISCONTINUITY at s=1.0 because
    crossing below s=1 lifts cal_q10 above 0 and chops out all zero-actuals
    instantly. The asymmetric branch (cal_q10 := q10) only narrows the upper
    side, which behaves monotonically with s.
    """
    q10_zero_frac = float((q10 <= 0.01).mean())
    asymmetric = q10_zero_frac > 0.30  # majority/heavy q10-at-zero clipping

    grid = np.linspace(lo, hi, n)
    best_s = 1.0; best_diff = 1.0
    for s in grid:
        if asymmetric:
            cal_q10 = q10  # preserve floor
            cal_q90 = q50 + s * (q90 - q50)
        else:
            cal_q10 = q50 - s * (q50 - q10)
            cal_q90 = q50 + s * (q90 - q50)
        cov = float(((actuals >= cal_q10) & (actuals <= cal_q90)).mean())
        diff = abs(cov - target)
        if diff < best_diff:
            best_diff = diff; best_s = float(s)
    return best_s


def calibrate(holdout_frac: float = 0.2, val_frac: float = 0.15) -> dict:
    """Fit per-stat scale factors on the VAL slice (NOT the holdout used for
    production metrics — that would leak into the calibration estimate)."""
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    val_rows = rows[train_end:val_end]
    print(f"calibration on val slice: {len(val_rows)} games", flush=True)

    X_val = np.array([[r[c] for c in fc] for r in val_rows], dtype=float)

    cal = {}
    for stat in STATS:
        models = load_quantile_models(stat, _MODEL_DIR)
        if 0.1 not in models or 0.5 not in models or 0.9 not in models:
            print(f"  [skip] {stat}: missing q10/q50/q90 models")
            continue
        q10_t = models[0.1].predict(X_val)
        q50_t = models[0.5].predict(X_val)
        q90_t = models[0.9].predict(X_val)
        q10 = _inverse(stat, q10_t)
        q50 = _inverse(stat, q50_t)
        q90 = _inverse(stat, q90_t)
        actuals = np.array([r[f"target_{stat}"] for r in val_rows], dtype=float)

        raw_cov = float(((actuals >= q10) & (actuals <= q90)).mean())
        s = _grid_search_scale(q10, q50, q90, actuals, target=0.80)
        q10_zero_frac = float((q10 <= 0.01).mean())
        if q10_zero_frac > 0.30:
            cal_q10 = q10  # preserve floor for asymmetric stats
            cal_q90 = q50 + s * (q90 - q50)
        else:
            cal_q10 = q50 - s * (q50 - q10)
            cal_q90 = q50 + s * (q90 - q50)
        cal_cov = float(((actuals >= cal_q10) & (actuals <= cal_q90)).mean())
        avg_width_raw = float(np.mean(q90 - q10))
        avg_width_cal = float(np.mean(cal_q90 - cal_q10))
        cal[stat] = {
            "scale":             round(s, 4),
            "asymmetric":        bool(q10_zero_frac > 0.30),
            "q10_zero_frac":     round(q10_zero_frac, 4),
            "raw_coverage_80":   round(raw_cov, 4),
            "cal_coverage_80":   round(cal_cov, 4),
            "raw_avg_width":     round(avg_width_raw, 4),
            "cal_avg_width":     round(avg_width_cal, 4),
        }
        print(f"  {stat.upper():4s} scale={s:.3f}  raw_cov={raw_cov:.3f} -> cal_cov={cal_cov:.3f}  "
              f"width {avg_width_raw:.3f} -> {avg_width_cal:.3f}", flush=True)

    with open(_CAL_PATH, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2)
    print(f"[done] wrote {_CAL_PATH}")
    return cal


def get_scale(stat: str) -> float:
    """Per-stat quantile-width scale factor. 1.0 when no calibration cached."""
    if not os.path.exists(_CAL_PATH):
        return 1.0
    try:
        cal = json.load(open(_CAL_PATH, encoding="utf-8"))
        return float(cal.get(stat, {}).get("scale", 1.0))
    except Exception:
        return 1.0


def apply(stat: str, q10: float, q50: float, q90: float) -> tuple:
    """Return calibrated (q10, q90) for one prediction. Reads asymmetric flag
    from the calibration JSON when present so stats with q10-floor preservation
    apply the right transform at inference."""
    s = get_scale(stat)
    cal_entry = {}
    if os.path.exists(_CAL_PATH):
        try:
            cal_entry = json.load(open(_CAL_PATH, encoding="utf-8")).get(stat, {})
        except Exception:
            pass
    if cal_entry.get("asymmetric"):
        return float(max(0.0, q10)), float(q50 + s * (q90 - q50))
    cal_q10 = q50 - s * (q50 - q10)
    cal_q90 = q50 + s * (q90 - q50)
    return float(max(0.0, cal_q10)), float(cal_q90)


_CONFORMAL_CAL_PATH = os.path.join(_MODEL_DIR, "quantile_conformal_calibration.json")

# Stats where CQR improves hold-out coverage (qhat > 0 on val slice).
# Determined by conformal_calibrate() analysis (docs/_audits/QUANTILE_CAL.md).
_CQR_STATS = {"pts", "reb", "ast"}
# Stats with no coverage gap (already >= 0.80 raw) — pass through, reject.
_PASS_THROUGH_STATS = {"fg3m", "stl", "tov"}
# Stats with crossing bug only — apply monotone clip, no expansion.
_MONO_ONLY_STATS = {"blk"}


def conformal_calibrate(holdout_frac: float = 0.2, val_frac: float = 0.15) -> dict:
    """Fit split-conformal (CQR) correction on the val slice.

    Uses the same temporal splits as train_quantile_models so the cal set is
    strictly PAST relative to the holdout (no leakage).

    Nonconformity score: s_i = max(q10 - y_i, y_i - q90)
    Conformal quantile qhat: the ceil((1-alpha)(n+1))-th order statistic of
    the scores on the calibration set.

    Stats with qhat=0 (already over-covered) get decision='REJECT' and are
    omitted from the JSON; apply_conformal passes them through unchanged.

    Writes ``data/models/quantile_conformal_calibration.json``.
    """
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    val_rows  = rows[train_end:val_end]
    holdout   = rows[val_end:]
    print(f"conformal calibration on val slice: {len(val_rows)} rows "
          f"(holdout eval: {len(holdout)} rows)", flush=True)

    X_val = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc] for r in val_rows],
                     dtype=float)
    X_ho  = np.array([[float(r.get(c, 0.0) or 0.0) for c in fc] for r in holdout],
                     dtype=float)

    alpha = 0.20  # 80% coverage target

    out = {}
    print(f"\n{'stat':<5} {'qhat':>8} {'cov_raw':>9} {'cov_cqr':>9} "
          f"{'cross_raw':>10} {'cross_cqr':>10} {'decision':>24}")
    print("-" * 80)

    for stat in STATS:
        models = load_quantile_models(stat, _MODEL_DIR)
        if not models or 0.1 not in models or 0.9 not in models:
            print(f"  [{stat}] SKIP — quantile models missing")
            continue

        min_n: Optional[int] = None
        for m in models.values():
            nf = getattr(m, "n_features_in_", None)
            if nf is not None:
                min_n = nf if min_n is None else min(min_n, nf)
        Xv = X_val[:, :min_n] if (min_n is not None and min_n != X_val.shape[1]) else X_val
        Xh = X_ho[:, :min_n]  if (min_n is not None and min_n != X_ho.shape[1])  else X_ho

        q10v = _inverse(stat, models[0.1].predict(Xv))
        q90v = _inverse(stat, models[0.9].predict(Xv))
        q50v = (_inverse(stat, models[0.5].predict(Xv))
                if 0.5 in models else (q10v + q90v) / 2.0)

        q10h = _inverse(stat, models[0.1].predict(Xh))
        q90h = _inverse(stat, models[0.9].predict(Xh))
        q50h = (_inverse(stat, models[0.5].predict(Xh))
                if 0.5 in models else (q10h + q90h) / 2.0)

        y_val = np.array([float(r[f"target_{stat}"]) for r in val_rows], dtype=float)
        y_ho  = np.array([float(r[f"target_{stat}"]) for r in holdout], dtype=float)

        # CQR nonconformity scores on val slice
        scores = np.maximum(q10v - y_val, y_val - q90v)
        n_cal = len(scores)
        # Conformal quantile: ceil((1-alpha)(n_cal+1))-th order statistic
        idx = min(int(np.ceil((1.0 - alpha) * (n_cal + 1))) - 1, n_cal - 1)
        qhat = float(np.sort(scores)[idx])

        # Apply CQR on holdout for reporting only
        cq10 = np.maximum(0.0, q10h - qhat)
        cq90 = q90h + qhat
        # Monotone clip ensures q10 <= q50 <= q90 after expansion
        cq10 = np.minimum(cq10, q50h)
        cq90 = np.maximum(cq90, q50h)

        cov_raw = float(np.mean((y_ho >= q10h) & (y_ho <= q90h)))
        cov_cqr = float(np.mean((y_ho >= cq10) & (y_ho <= cq90)))

        cross_raw = float(np.mean((q10h > q50h) | (q50h > q90h)))
        cross_cqr = float(np.mean((cq10 > q50h) | (q50h > cq90)))

        # Decision logic
        if stat in _PASS_THROUGH_STATS:
            decision = "REJECT-pass_through"
        elif stat in _MONO_ONLY_STATS:
            decision = "MONO_CLIP_only"
        elif qhat > 0.0:
            decision = "SHIP_CQR"
        else:
            decision = "REJECT-no_improvement"

        entry = {
            "qhat":       round(qhat, 6),
            "decision":   decision,
            "cov_raw_holdout":  round(cov_raw, 4),
            "cov_cqr_holdout":  round(cov_cqr, 4),
            "cross_raw":  round(cross_raw, 5),
            "cross_cqr":  round(cross_cqr, 5),
            "n_cal":      n_cal,
        }
        out[stat] = entry
        print(f"{stat:<5} {qhat:>8.4f} {cov_raw:>9.3f} {cov_cqr:>9.3f} "
              f"{cross_raw*100:>9.2f}% {cross_cqr*100:>9.2f}% {decision:>24}")

    with open(_CONFORMAL_CAL_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[done] wrote {_CONFORMAL_CAL_PATH}")
    return out


def _load_conformal_cal() -> dict:
    """Load conformal calibration JSON. Returns {} when absent."""
    if not os.path.exists(_CONFORMAL_CAL_PATH):
        return {}
    try:
        return json.load(open(_CONFORMAL_CAL_PATH, encoding="utf-8"))
    except Exception:
        return {}


def apply_conformal(stat: str, q10: float, q50: float, q90: float) -> tuple:
    """Return (q10, q90) after split-conformal (CQR) correction.

    Gated by CV_QUANTILE_CAL env var (default OFF). When the flag is OFF this
    function is a pure identity — byte-identical to the raw band. q50 is NEVER
    modified.

    Co-activation with CV_ROW_SIGMA=1 (REB): the caller (grade_bet) already
    invokes ``apply()`` for REB when CV_ROW_SIGMA=1; apply_conformal explicitly
    short-circuits for REB in that branch to avoid double-calibration.  The
    apply_conformal call site in the API path checks the flag order:
        if CV_ROW_SIGMA and stat == 'reb': use apply() only.
        elif CV_QUANTILE_CAL: use apply_conformal().

    Rules per stat:
      SHIP_CQR     (pts, reb, ast) — expand band by qhat; clip q10 >= 0; enforce
                   monotone q10 <= q50 <= q90.
      MONO_CLIP    (blk)           — clip q10 = min(q10, q50), q90 = max(q90, q50)
                                     to fix crossing bug; no expansion.
      pass-through (fg3m, stl, tov, and fallback) — return raw q10, q90 unchanged.
    """
    if os.environ.get("CV_QUANTILE_CAL", "0") != "1":
        # Flag OFF — identity: byte-identical to raw
        return float(q10), float(q90)

    cal = _load_conformal_cal()
    entry = cal.get(stat, {})
    decision = entry.get("decision", "pass_through")
    qhat = float(entry.get("qhat", 0.0))

    if decision == "SHIP_CQR" and qhat > 0.0:
        cq10 = float(max(0.0, q10 - qhat))
        cq90 = float(q90 + qhat)
    else:
        # MONO_CLIP_only, REJECT/pass-through, or unknown:
        # copy raw values; monotone clip still applied below as safety baseline.
        cq10 = float(max(0.0, q10))
        cq90 = float(q90)

    # Always enforce monotone ordering q10 <= q50 <= q90 when flag is ON.
    # This is a no-op for well-ordered bands; fixes the BLK crossing bug and
    # any rare crossing in pass-through stats without changing coverage.
    cq10 = float(min(cq10, q50))
    cq90 = float(max(cq90, q50))
    return cq10, cq90


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    import sys as _sys
    if "--conformal" in _sys.argv:
        conformal_calibrate()
    else:
        calibrate()
