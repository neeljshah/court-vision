"""
calibrate_game_conformal.py — Calibrate split-conformal intervals for 5 game-level models.

Steps:
1. Load the 2024-25 holdout set via game_models._fetch_scored_games (uses cached JSON).
2. Run each saved LightGBM model on the holdout features.
3. Also load blowout_v2.pkl + ot_v2.pkl for the two classification outputs.
4. Compute per-output conformity scores and persist quantiles to
   data/models/conformal_games.json.
5. Print coverage check: empirical 80% coverage on holdout vs target.

Usage
-----
    conda run -n basketball_ai python scripts/calibrate_game_conformal.py
    conda run -n basketball_ai python scripts/calibrate_game_conformal.py --season 2023-24
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_BLOWOUT_MARGIN = 15


def _load_lgb_model(filename: str, is_classifier: bool = False):
    """Load a LightGBM booster from text file."""
    try:
        import lightgbm as lgb
    except ImportError:
        raise ImportError("lightgbm required: conda run -n basketball_ai pip install lightgbm")
    path = os.path.join(_MODEL_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"LGB model not found: {path} — run game_models.train() first")
    return lgb.Booster(model_file=path)


def _load_blowout_ot_preds(X_ho: np.ndarray, feature_cols_bo: list) -> Dict[str, np.ndarray]:
    """
    Try to load blowout_v2.pkl + ot_v2.pkl for holdout predictions.
    Falls back to the blowout/OT columns from game_models if pkl not available.
    """
    result: Dict[str, Optional[np.ndarray]] = {"blowout_prob": None, "ot_prob": None}

    # Try dedicated v2 pkl models first
    for key, fname in [("blowout_prob", "blowout_v2.pkl"), ("ot_prob", "ot_v2.pkl")]:
        pkl_path = os.path.join(_MODEL_DIR, fname)
        if os.path.exists(pkl_path):
            try:
                import pickle
                with open(pkl_path, "rb") as fh:
                    model = pickle.load(fh)
                probs = model.predict_proba(X_ho)[:, 1]
                result[key] = probs.astype(float)
                print(f"  [{key}] loaded from {fname}")
            except Exception as e:
                print(f"  [{key}] pkl load failed ({e}); will fall back to lgb")

    # Fall back to blowout lgb if pkl unavailable
    if result["blowout_prob"] is None:
        try:
            bo_lgb = _load_lgb_model("game_blowout_lgb.txt", is_classifier=True)
            probs = bo_lgb.predict(X_ho)
            result["blowout_prob"] = probs.astype(float)
            print("  [blowout_prob] loaded from game_blowout_lgb.txt")
        except Exception as e:
            print(f"  [blowout_prob] skipped: {e}")

    if result["ot_prob"] is None:
        print("  [ot_prob] no model available — skipping OT conformal calibration")

    return {k: v for k, v in result.items() if v is not None}


def calibrate(holdout_season: str = "2024-25", verbose: bool = True) -> dict:
    """
    Main calibration routine. Returns the quantile dict that was saved.
    """
    # ── 1. Build holdout dataset ───────────────────────────────────────────────
    from src.prediction.game_models import (
        _fetch_scored_games, FEATURE_COLS, _HOLDOUT_SEASON
    )
    import pandas as pd

    if verbose:
        print(f"[calibrate_game_conformal] Building holdout set for {holdout_season} ...")

    rows = _fetch_scored_games(holdout_season)
    if not rows:
        raise RuntimeError(
            f"No scored games for {holdout_season}. "
            "The NBA cache may be empty — run a batch pipeline pass first."
        )

    df = pd.DataFrame(rows)
    required_targets = {"game_total", "spread"}
    missing = required_targets - set(df.columns)
    if missing:
        raise RuntimeError(f"Holdout dataset missing columns: {missing}")

    # Drop rows with NaN in features or targets
    all_needed = FEATURE_COLS + ["game_total", "spread"]
    df = df.dropna(subset=[c for c in all_needed if c in df.columns]).reset_index(drop=True)

    if len(df) < 50:
        print(f"  WARNING: Only {len(df)} holdout rows — intervals may be unreliable.")
    if verbose:
        print(f"  Holdout rows after dropna: {len(df)}")

    # Build feature matrix
    X_ho = df[FEATURE_COLS].values.astype(np.float32)

    # ── 2. Regression model predictions ────────────────────────────────────────
    predictions: Dict[str, np.ndarray] = {}
    actuals:     Dict[str, np.ndarray] = {}

    # game_total
    try:
        bo_total = _load_lgb_model("game_game_total_lgb.txt")
        predictions["total"] = bo_total.predict(X_ho).astype(float)
        actuals["total"]     = df["game_total"].values.astype(float)
        if verbose:
            print(f"  [total]      {len(predictions['total'])} predictions loaded")
    except Exception as e:
        print(f"  [total] FAILED: {e}")

    # spread
    try:
        bo_spread = _load_lgb_model("game_spread_lgb.txt")
        predictions["spread"] = bo_spread.predict(X_ho).astype(float)
        actuals["spread"]     = df["spread"].values.astype(float)
        if verbose:
            print(f"  [spread]     {len(predictions['spread'])} predictions loaded")
    except Exception as e:
        print(f"  [spread] FAILED: {e}")

    # first_half
    fh_col = "first_half_actual" if "first_half_actual" in df.columns else "first_half_proxy"
    if fh_col in df.columns:
        try:
            bo_fh = _load_lgb_model("game_first_half_lgb.txt")
            predictions["first_half"] = bo_fh.predict(X_ho).astype(float)
            actuals["first_half"]     = df[fh_col].values.astype(float)
            if verbose:
                print(f"  [first_half] {len(predictions['first_half'])} predictions loaded "
                      f"(label={fh_col})")
        except Exception as e:
            print(f"  [first_half] FAILED: {e}")

    # ── 3. Classification model predictions ────────────────────────────────────
    clf_preds = _load_blowout_ot_preds(X_ho, FEATURE_COLS)

    if "blowout_prob" in clf_preds:
        predictions["blowout_prob"] = clf_preds["blowout_prob"]
        actuals["blowout_prob"]     = (np.abs(df["spread"].values) > _BLOWOUT_MARGIN).astype(float)

    # OT label: if ot column present use it, otherwise skip
    if "ot_prob" in clf_preds:
        ot_col = next((c for c in ("ot_actual", "ot_label", "overtime") if c in df.columns), None)
        if ot_col:
            predictions["ot_prob"] = clf_preds["ot_prob"]
            actuals["ot_prob"]     = df[ot_col].values.astype(float)
            if verbose:
                print(f"  [ot_prob]    {len(predictions['ot_prob'])} predictions loaded "
                      f"(label={ot_col})")
        else:
            # Try to derive from MIN column (team minutes > 252 → OT)
            if "home_min" in df.columns and "away_min" in df.columns:
                ot_label = ((df["home_min"].fillna(240) > 252) |
                            (df["away_min"].fillna(240) > 252)).astype(float).values
            elif "game_minutes" in df.columns:
                ot_label = (df["game_minutes"].fillna(48) > 50).astype(float).values
            else:
                ot_label = None
                if verbose:
                    print("  [ot_prob] no OT label column found — skipping OT calibration")
            if ot_label is not None:
                predictions["ot_prob"] = clf_preds["ot_prob"]
                actuals["ot_prob"]     = ot_label

    if not predictions:
        raise RuntimeError("No predictions generated — check that LGB models exist in data/models/")

    # ── 4. Fit conformal intervals ──────────────────────────────────────────────
    from src.prediction.conformal_games import GameConformalIntervals

    gc = GameConformalIntervals(model_dir=_MODEL_DIR)
    gc.fit(predictions, actuals)

    # ── 5. Print results ────────────────────────────────────────────────────────
    if verbose:
        print("\n[conformal quantiles]")
        print(f"  {'output':<16}  {'q10':>8}  {'q90':>8}  {'q025':>8}  {'q975':>8}  {'n':>6}")
        print("  " + "-" * 60)
        for key, qt in gc._quantiles.items():
            if "q10" in qt:
                print(f"  {key:<16}  {qt['q10']:>8.3f}  {qt['q90']:>8.3f}  "
                      f"{qt['q025']:>8.3f}  {qt['q975']:>8.3f}  {qt['n']:>6}")
            else:
                print(f"  {key:<16}  (classification) q90={qt.get('q90_residual', '?'):.4f}  "
                      f"q975={qt.get('q975_residual', '?'):.4f}  n={qt.get('n', '?')}")

        # Coverage check on holdout
        print("\n[coverage check — 80% target]")
        cov = gc.coverage_check(predictions, actuals, level=0.80)
        for key, c in cov.items():
            flag = "OK" if abs(c - 0.80) <= 0.06 else "WARN"
            print(f"  {key:<16}  {c:.1%}  [{flag}]")

    # ── 6. Persist ──────────────────────────────────────────────────────────────
    out_path = gc.save()
    if verbose:
        print(f"\n[calibrate_game_conformal] Saved -> {out_path}")

    return gc._quantiles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate game-level conformal prediction intervals."
    )
    parser.add_argument(
        "--season", default="2024-25",
        help="Holdout season for calibration (default: 2024-25)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    try:
        calibrate(holdout_season=args.season, verbose=not args.quiet)
    except Exception as e:
        print(f"[calibrate_game_conformal] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
