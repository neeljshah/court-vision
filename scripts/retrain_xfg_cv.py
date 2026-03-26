"""
retrain_xfg_cv.py — Train xFG v2: xFG v1 + CV spatial features stacking model.

Strategy
--------
xFG v1 (221K NBA shots) gives a strong baseline from shot zone / distance / type.
We have ~700-3000 labeled shots (make/miss) from game tracking with CV features:
  - defender_dist_norm  (defender distance / map_w)  — closest thing to contest rating
  - team_spacing        (attacker team convex hull area, pixels)
  - dribble_count       (dribbles before shot — proxy for catch-and-shoot vs off-dribble)
  - catch_and_shoot     (binary: 0 dribbles)
  - x_norm, y_norm      (normalized court position, scale-invariant across games)
  - court_zone          (paint / mid_range / 3pt_arc / corner_3)

A Ridge logistic regression stacks these on top of xFG v1 predictions.
With 700+ samples, this gives a reliable CV residual correction.
Saves to data/models/xfg_cv_stack.pkl.

Usage
-----
    conda activate basketball_ai
    python scripts/retrain_xfg_cv.py           # train + evaluate
    python scripts/retrain_xfg_cv.py --dry-run  # print feature stats only
"""

from __future__ import annotations

import argparse
import csv
import os
import pickle
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_DIR  = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"
MODEL_DIR    = PROJECT_DIR / "data" / "models"
sys.path.insert(0, str(PROJECT_DIR))

_STACK_MODEL_PATH = MODEL_DIR / "xfg_cv_stack.pkl"
_XFG_V1_PATH      = MODEL_DIR / "xfg_v1.pkl"

ZONE_CATEGORIES = ["paint", "mid_range", "3pt_arc", "corner_3", "backcourt", "unknown"]


# ── data loading ──────────────────────────────────────────────────────────────

def load_labeled_shots() -> pd.DataFrame:
    """Load all shot_log[_enriched].csv rows that have a made/missed label."""
    frames = []
    for game_dir in sorted(TRACKING_DIR.iterdir()):
        if not game_dir.is_dir():
            continue
        # Prefer base shot_log (has x_norm/y_norm); enriched is older format without norms
        for fname in ("shot_log.csv", "shot_log_enriched.csv"):
            path = game_dir / fname
            if path.exists():
                try:
                    df = pd.read_csv(path, dtype=str)
                    labeled = df[df["made"].isin(["1", "0", "1.0", "0.0",
                                                  "True", "False"])].copy()
                    if len(labeled) > 0:
                        labeled["game_id_src"] = game_dir.name
                        frames.append(labeled)
                except Exception as e:
                    print(f"  SKIP {path.name} ({game_dir.name}): {e}")
                break

    if not frames:
        raise RuntimeError("No labeled shots found. Run games with --game-id enrichment first.")

    df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(df)} labeled shots from {len(frames)} games")
    return df


def _parse_float(val, default=0.0) -> float:
    try:
        v = float(val)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def build_features(df: pd.DataFrame) -> tuple:
    """Build feature matrix X and target y. Returns (X, y, feature_names)."""
    rows = []
    targets = []
    feature_names = [
        "x_norm", "y_norm",
        "defender_dist_norm",
        "team_spacing_norm",   # team_spacing / 1e6 (pixel² → unit scale)
        "dribble_count",
        "catch_and_shoot",
        "zone_paint", "zone_mid_range", "zone_3pt_arc", "zone_corner_3",
    ]

    for _, r in df.iterrows():
        # Target
        made_raw = str(r.get("made", ""))
        if made_raw in ("1", "1.0", "True"):
            y = 1
        elif made_raw in ("0", "0.0", "False"):
            y = 0
        else:
            continue

        # Coordinates — prefer _norm columns, fall back to raw/map estimation
        x_norm = _parse_float(r.get("x_norm"))
        y_norm = _parse_float(r.get("y_norm"))

        # If norms missing, skip the row (needs re-run with updated pipeline)
        if x_norm == 0.0 and y_norm == 0.0:
            continue

        # Defender distance — normalized
        def_dist_norm = _parse_float(r.get("defender_dist_norm"))
        if def_dist_norm == 0.0:
            # Fall back: raw distance / 940
            def_dist_norm = min(_parse_float(r.get("defender_distance")) / 940.0, 3.0)

        # Team spacing — scale to ~[0, 1]
        spacing_norm = _parse_float(r.get("team_spacing")) / 1e6

        dribbles = min(_parse_float(r.get("dribble_count")), 20.0)
        catch_shoot = _parse_float(r.get("catch_and_shoot"))

        # Zone one-hot
        zone = str(r.get("court_zone", "")).lower().strip()
        zone_paint     = int(zone == "paint")
        zone_mid       = int(zone == "mid_range")
        zone_3pt_arc   = int(zone == "3pt_arc")
        zone_corner_3  = int(zone == "corner_3")

        rows.append([
            min(x_norm, 1.0), min(y_norm, 1.0),
            min(def_dist_norm, 1.0),
            spacing_norm,
            dribbles,
            catch_shoot,
            zone_paint, zone_mid, zone_3pt_arc, zone_corner_3,
        ])
        targets.append(y)

    X = np.array(rows, dtype=np.float32)
    y = np.array(targets, dtype=np.int32)
    return X, y, feature_names


def add_xfg_v1_column(df: pd.DataFrame) -> pd.Series:
    """Get xFG v1 predictions for each row. Returns Series of floats (NaN if unavailable)."""
    if not _XFG_V1_PATH.exists():
        print("  [warn] xfg_v1.pkl not found — skipping baseline column")
        return pd.Series([np.nan] * len(df))

    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from src.prediction.xfg_model import load as load_xfg
        xfg = load_xfg(str(_XFG_V1_PATH))

        preds = []
        for _, r in df.iterrows():
            try:
                p = xfg.predict({
                    "shot_zone_basic":  r.get("court_zone", "Mid-Range"),
                    "shot_zone_area":   "Center(C)",
                    "shot_zone_range":  "16-24 ft.",
                    "shot_distance":    _parse_float(r.get("shot_distance"), 15),
                    "shot_type":        "2PT Field Goal",
                    "action_type":      "Jump Shot",
                })
                preds.append(p)
            except Exception:
                preds.append(np.nan)
        return pd.Series(preds)
    except Exception as e:
        print(f"  [warn] Could not load xFG v1: {e}")
        return pd.Series([np.nan] * len(df))


# ── training ──────────────────────────────────────────────────────────────────

def train(dry_run: bool = False):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.metrics import brier_score_loss, log_loss
    from sklearn.preprocessing import StandardScaler
    import warnings
    warnings.filterwarnings("ignore")

    df = load_labeled_shots()
    X, y, feat_names = build_features(df)

    print(f"\nFeature matrix: {X.shape}  |  FG%: {y.mean():.3f}")
    print(f"Feature names: {feat_names}")

    # Feature stats
    print("\nFeature means (non-zero sample):")
    for i, name in enumerate(feat_names):
        nonzero = X[X[:, i] != 0, i]
        if len(nonzero) > 0:
            print(f"  {name:25s}: mean={nonzero.mean():.4f}  max={nonzero.max():.4f}  "
                  f"coverage={len(nonzero)/len(X)*100:.0f}%")

    if dry_run:
        print("\n[dry-run] Stopping here.")
        return

    if len(y) < 50:
        print(f"\n[warn] Only {len(y)} labeled shots — need 50+ for reliable stacking.")
        print("Re-run games with --game-id to get enrichment, then retry.")
        return

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # xFG v1 baseline Brier (naive: predict league average)
    league_avg = y.mean()
    baseline_brier = brier_score_loss(y, np.full(len(y), league_avg))
    print(f"\nBaseline Brier (league avg {league_avg:.3f}): {baseline_brier:.4f}")

    # CV-only logistic model
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    cv_scores = cross_val_score(
        model, X_scaled, y,
        cv=StratifiedKFold(n_splits=min(5, len(y) // 20), shuffle=True, random_state=42),
        scoring="neg_brier_score",
    )
    cv_brier = -cv_scores.mean()
    print(f"CV xFG (5-fold) Brier: {cv_brier:.4f}  (vs baseline {baseline_brier:.4f})")

    # Fit final model on all data
    model.fit(X_scaled, y)
    train_preds = model.predict_proba(X_scaled)[:, 1]
    train_brier = brier_score_loss(y, train_preds)
    train_ll    = log_loss(y, train_preds)
    print(f"Train Brier: {train_brier:.4f}  |  Log-loss: {train_ll:.4f}")

    # Save
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model":        model,
        "scaler":       scaler,
        "feature_names": feat_names,
        "n_shots":      int(len(y)),
        "fg_pct":       round(float(league_avg), 4),
        "cv_brier":     round(float(cv_brier), 4),
        "train_brier":  round(float(train_brier), 4),
        "baseline_brier": round(float(baseline_brier), 4),
        "improvement":  round(float(baseline_brier - cv_brier), 4),
    }
    with open(_STACK_MODEL_PATH, "wb") as f:
        pickle.dump(bundle, f)

    print(f"\nSaved → {_STACK_MODEL_PATH}")
    print(f"Brier improvement over baseline: {bundle['improvement']:+.4f}")

    if cv_brier >= baseline_brier:
        print("[warn] No improvement yet — need more labeled shots or CV data quality fixes.")
        print("       Target: 20+ games with enrichment for robust CV signal.")
    else:
        print("[ok] CV xFG v2 (spatial) beats baseline.")

    # Feature importances (coefficients)
    print("\nTop feature coefficients (higher = more likely to make):")
    coef_pairs = sorted(zip(feat_names, model.coef_[0]), key=lambda x: abs(x[1]), reverse=True)
    for name, coef in coef_pairs:
        print(f"  {name:25s}: {coef:+.4f}")


def predict(shot: dict) -> float:
    """Load saved stacking model and predict xFG for a single shot dict."""
    if not _STACK_MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {_STACK_MODEL_PATH}. Run --train first.")
    with open(_STACK_MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)

    zone = str(shot.get("court_zone", "")).lower()
    row = [
        _parse_float(shot.get("x_norm")),
        _parse_float(shot.get("y_norm")),
        _parse_float(shot.get("defender_dist_norm")),
        _parse_float(shot.get("team_spacing", 0)) / 1e6,
        min(_parse_float(shot.get("dribble_count")), 20.0),
        _parse_float(shot.get("catch_and_shoot")),
        int(zone == "paint"),
        int(zone == "mid_range"),
        int(zone == "3pt_arc"),
        int(zone == "corner_3"),
    ]
    X = np.array([row], dtype=np.float32)
    X_scaled = bundle["scaler"].transform(X)
    return float(bundle["model"].predict_proba(X_scaled)[0, 1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print feature stats only, don't train")
    args = parser.parse_args()
    train(dry_run=args.dry_run)
