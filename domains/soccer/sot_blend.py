"""domains.soccer.sot_blend — Leak-free blended O/U 2.5 forecast (Poisson + SoT form).

WHAT THIS IS
------------
The W63 gate showed ``diff_sot_for_asof`` (rolling shots-on-target differential,
home minus away, computed leak-free from prior-match history) PASSES all walk-forward
accuracy criteria (all-folds improve, ablation pass, beats-null, calibrated, p=5.9e-05).
It REJECTS on CLV because the market already prices SoT form.

This module blends the Poisson baseline (``p_over25``) with the SoT asof feature via
a LEAK-FREE walk-forward logistic stack, then scores the blend against the baseline.

HONEST DISCIPLINE (BINDING)
---------------------------
  * Accuracy/calibration improvement ONLY.
  * This blend does NOT beat the closing line.
  * NO betting edge is claimed.
  * The market already prices SoT form → CLV remains negative; NO edge.

INVARIANTS
----------
  * Never edits src/ or kernel/.
  * Never edits existing soccer adapter/ratings/asof files.
  * Imports from domains.soccer.* read-only (no side-effects on loaded adapters).
  * Rows with NaN sot_for_asof pass through the Poisson baseline unchanged.
  * Every training window is STRICTLY prior rows (snapshot-before-update).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

# Read-only imports from platformkit helpers.
from scripts.platformkit.calibration_ladder import walk_forward_auto
from scripts.platformkit.scoreboard import score_forecaster

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASOF_PATH = _REPO_ROOT / "data" / "domains" / "soccer" / "asof_features.parquet"

_HONEST_NOTE = (
    "Accuracy/calibration improvement only; still REJECTs on CLV; "
    "NO market-beating claim; the market already prices SoT form."
)

_BANNED = ("guaranteed", "beat the market", "profit", "edge")

_EPS = 1e-15


def _logit(p: np.ndarray) -> np.ndarray:
    """Safe logit; NaN stays NaN."""
    out = np.full_like(p, np.nan, dtype=float)
    ok = np.isfinite(p) & (p > 0) & (p < 1)
    out[ok] = np.log(p[ok] / (1.0 - p[ok]))
    return out


def _walk_forward_logistic_stack(
    p_base: np.ndarray,
    sot_feat: np.ndarray,
    y: np.ndarray,
    min_history: int = 100,
) -> np.ndarray:
    """Leak-free expanding-window logistic blend.

    For each event i (chronological order):
      - Training rows  = 0 .. i-1  (strictly prior)
      - Features       = [logit(p_base), sot_feat] — NaN sot dropped from fit window
      - Prediction     = blend probability for event i
      - Rows where sot_feat[i] is NaN pass through p_base[i] unchanged.

    No row ever sees its own outcome (snapshot-before-update).
    """
    n = len(p_base)
    blend = np.array(p_base, dtype=float)  # default = pass-through

    logit_base = _logit(p_base)
    lr: Optional[LogisticRegression] = None

    for i in range(min_history, n):
        # Build strictly-prior training set (rows 0..i-1).
        lb = logit_base[:i]
        sf = sot_feat[:i]
        yy = y[:i]

        # Valid rows: finite logit AND finite sot AND finite outcome.
        valid = np.isfinite(lb) & np.isfinite(sf) & np.isfinite(yy)
        if valid.sum() >= 20 and len(np.unique(yy[valid])) >= 2:
            X_tr = np.column_stack([lb[valid], sf[valid]])
            lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
            lr.fit(X_tr, yy[valid])

        # Predict for event i — fall back to baseline if sot is NaN or no model yet.
        if lr is not None and np.isfinite(sot_feat[i]) and np.isfinite(logit_base[i]):
            X_q = np.array([[logit_base[i], sot_feat[i]]])
            blend[i] = float(lr.predict_proba(X_q)[0, 1])
        # else: blend[i] already = p_base[i] (pass-through)

    return np.clip(blend, 0.0, 1.0)


def build_blended_forecast(
    seasons: Optional[Sequence[int]] = None,
    asof_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Build a leak-free blended O/U 2.5 soccer forecast and compare to baseline.

    Parameters
    ----------
    seasons:
        Optional list of season ints to filter the soccer corpus. None = all seasons.
    asof_df:
        Pre-loaded asof_features DataFrame (for testing without parquet I/O).
        If None, reads ``data/domains/soccer/asof_features.parquet``.

    Returns
    -------
    dict with keys:
        n              : int — rows scored (both baseline and blend valid)
        baseline       : dict{brier, log_loss, ece, ...}
        blend          : dict{brier, log_loss, ece, ...}
        dBrier         : float — blend_brier - baseline_brier  (negative = improvement)
        dECE           : float — blend_ece - baseline_ece
        improves       : bool — dBrier < 0
        note           : str — honest discipline note

    HONEST NOTE: accuracy/calibration improvement only; still REJECTs on CLV;
    NO betting edge claimed; the market already prices SoT form.
    """
    # --- load the soccer bundle (p_over25, target, dates, event_id) ---
    from domains.soccer.adapter import SoccerAdapter
    adapter = SoccerAdapter()
    bundle = adapter.feature_bundle(hypothesis=None, seasons=list(seasons or []))

    p_base = np.asarray(bundle.signal_col, dtype=float)
    target = np.asarray(bundle.target, dtype=float)
    dates = list(bundle.dates)

    # We need event_id to join asof; rebuild it from the adapter's matches parquet.
    matches = adapter._get_matches()
    if seasons:
        matches = matches[matches["season"].isin(seasons)]

    # The bundle rows are in the same chronological order as walk_forward_goals output.
    # Re-derive event_id in the same order (date-sorted, then merged with odds).
    from domains.soccer.ratings import walk_forward_goals as _wfg
    wf = _wfg(matches)

    # Filter to rows that have a valid target (same filter as adapter.feature_bundle).
    wf = wf[wf["target_over25"].notna()].reset_index(drop=True)

    # Sanity: row counts must match.
    if len(wf) != len(p_base):
        raise RuntimeError(
            f"Bundle/walk-forward row mismatch: {len(p_base)} vs {len(wf)}. "
            "Ensure the same seasons filter is applied."
        )

    event_ids = wf["event_id"].astype(str).values

    # --- load asof features and join by event_id ---
    if asof_df is None:
        if not _ASOF_PATH.exists():
            raise FileNotFoundError(
                f"asof_features.parquet not found at {_ASOF_PATH}. "
                "Run: python -m domains.soccer.asof_features"
            )
        asof_df = pd.read_parquet(_ASOF_PATH)

    asof_indexed = asof_df.set_index("event_id")["diff_sot_for_asof"]
    sot_feat = np.array(
        [asof_indexed.get(eid, np.nan) for eid in event_ids], dtype=float
    )

    # --- walk-forward logistic blend (leak-free) ---
    blend_raw = _walk_forward_logistic_stack(p_base, sot_feat, target)

    # --- recalibrate both via walk_forward_auto ---
    base_cal, _bm = walk_forward_auto(p_base, target)
    blend_cal, _blm = walk_forward_auto(blend_raw, target)

    # --- score on the full set (NaN-safe via score_forecaster) ---
    baseline_scores = score_forecaster(base_cal, target)
    blend_scores = score_forecaster(blend_cal, target)

    d_brier = blend_scores["brier"] - baseline_scores["brier"]
    d_ece = blend_scores["ece"] - baseline_scores["ece"]

    return {
        "n": baseline_scores["n"],
        "baseline": baseline_scores,
        "blend": blend_scores,
        "dBrier": d_brier,
        "dECE": d_ece,
        "improves": bool(d_brier < 0),
        "note": _HONEST_NOTE,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Blended soccer O/U 2.5 forecast: Poisson + SoT form (accuracy only)")
    parser.add_argument("--seasons", nargs="*", type=int, default=None,
                        help="Season ints to filter (default: all)")
    args = parser.parse_args()

    result = build_blended_forecast(seasons=args.seasons)

    b = result["baseline"]
    bl = result["blend"]
    print("=" * 62)
    print("SOCCER O/U 2.5 — BLENDED FORECAST (Poisson + SoT form)")
    print("=" * 62)
    print(f"  N rows scored  : {result['n']}")
    print(f"  {'Metric':<18} {'Baseline':>10} {'Blend':>10} {'Delta':>10}")
    print(f"  {'-'*50}")
    print(f"  {'Brier':<18} {b['brier']:>10.5f} {bl['brier']:>10.5f} "
          f"{result['dBrier']:>+10.5f}")
    print(f"  {'ECE':<18} {b['ece']:>10.5f} {bl['ece']:>10.5f} "
          f"{result['dECE']:>+10.5f}")
    print(f"  {'LogLoss':<18} {b['log_loss']:>10.5f} {bl['log_loss']:>10.5f} "
          f"{bl['log_loss'] - b['log_loss']:>+10.5f}")
    print("=" * 62)
    improves_str = "YES (blend lowers Brier)" if result["improves"] else "NO"
    print(f"  Accuracy improves: {improves_str}")
    print(f"\nHONEST VERDICT: {result['note']}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
