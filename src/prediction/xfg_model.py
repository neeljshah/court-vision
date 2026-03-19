"""
xfg_model.py — Expected Field Goal % model v1 (NBA API shot charts only).

Trains an XGBoost classifier on ~340K shots from ShotChartDetail across all
569 scraped players. Predicts xFG for any shot given zone/distance/type —
no CV data required.

Features
--------
    shot_zone_basic    (7 zones, one-hot)
    shot_zone_area     (6 areas, one-hot)
    shot_zone_range    (5 ranges, one-hot)
    shot_distance      (int, feet)
    is_3pt             (binary)
    action_type_enc    (label-encoded — top-20 action types, rest → "Other")

Output
------
    data/models/xfg_v1.pkl          — trained XGBClassifier + encoder state
    data/nba/xfg_calibration.json   — zone-level calibration check

Public API
----------
    train(output_path)  -> XFGModel
    load(model_path)    -> XFGModel
    predict(shot_dict)  -> float          # xFG in [0, 1]
    predict_batch(df)   -> pd.Series      # xFG for each row
    evaluate()          -> dict           # Brier + log-loss + zone breakdown

Usage
-----
    python src/prediction/xfg_model.py --train
    python src/prediction/xfg_model.py --evaluate
    python src/prediction/xfg_model.py --predict --zone "Right Corner 3" --distance 23
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "xfg_v1.pkl")

# Top action types to keep as categories; everything else → "Other"
_TOP_ACTION_TYPES = [
    "Jump Shot", "Layup Shot", "Driving Layup Shot", "Dunk Shot",
    "Pullup Jump shot", "Fadeaway Jump Shot", "Running Layup Shot",
    "Step Back Jump shot", "Turnaround Jump Shot", "Floating Jump shot",
    "Hook Shot", "Tip Shot", "Alley Oop Dunk Shot", "Alley Oop Layup shot",
    "Cutting Layup Shot", "Cutting Dunk Shot", "Driving Hook Shot",
    "Turnaround Fadeaway shot", "Driving Floating Jump Shot", "Other",
]

_ZONE_BASIC_CATS  = ["Above the Break 3", "Backcourt", "In The Paint (Non-RA)",
                     "Left Corner 3", "Mid-Range", "Restricted Area",
                     "Right Corner 3"]
_ZONE_AREA_CATS   = ["Back Court(BC)", "Center(C)", "Left Side Center(LC)",
                     "Left Side(L)", "Right Side Center(RC)", "Right Side(R)"]
_ZONE_RANGE_CATS  = ["16-24 ft.", "24+ ft.", "8-16 ft.", "Less Than 8 ft.", "Back Court Shot"]


# ── data loading ─────────────────────────────────────────────────────────────

def load_all_shot_charts() -> pd.DataFrame:
    """Load and concatenate all shotchart_*.json files from data/nba/."""
    files = sorted(f for f in os.listdir(_NBA_CACHE) if f.startswith("shotchart_"))
    if not files:
        raise FileNotFoundError(f"No shot chart files in {_NBA_CACHE}")

    frames: List[pd.DataFrame] = []
    for fname in files:
        path = os.path.join(_NBA_CACHE, fname)
        try:
            data = json.load(open(path))
            if data:
                frames.append(pd.DataFrame(data))
        except Exception:
            continue

    if not frames:
        raise ValueError("All shot chart files were empty or unreadable.")

    df = pd.concat(frames, ignore_index=True)
    print(f"[xfg] Loaded {len(df):,} shots from {len(files)} files")
    return df


# ── feature engineering ───────────────────────────────────────────────────────

def _encode_features(df: pd.DataFrame, encoders: Optional[dict] = None) -> tuple[np.ndarray, dict]:
    """
    Encode raw shot chart columns into ML features.

    Returns (X, encoders) where encoders is a dict with label maps for
    categorical columns (needed for inference on single shots).
    """
    df = df.copy()

    # Normalise action_type to top-20 + Other
    df["action_type_clean"] = df["action_type"].where(
        df["action_type"].isin(_TOP_ACTION_TYPES), other="Other"
    )

    # Shot distance as numeric
    df["shot_distance"] = pd.to_numeric(df["shot_distance"], errors="coerce").fillna(0).astype(float)

    # is_3pt binary
    df["is_3pt"] = (df["shot_type"] == "3PT Field Goal").astype(int)

    # Label-encode categoricals
    cat_cols = {
        "shot_zone_basic":   _ZONE_BASIC_CATS,
        "shot_zone_area":    _ZONE_AREA_CATS,
        "shot_zone_range":   _ZONE_RANGE_CATS,
        "action_type_clean": _TOP_ACTION_TYPES,
    }

    if encoders is None:
        encoders = {}
        for col, cats in cat_cols.items():
            # Build map from unseen values too
            unique_vals = sorted(df[col].dropna().unique().tolist())
            all_cats = sorted(set(cats) | set(unique_vals))
            encoders[col] = {v: i for i, v in enumerate(all_cats)}

    for col in cat_cols:
        enc = encoders[col]
        df[col + "_enc"] = df[col].map(lambda v, e=enc: e.get(str(v), 0))

    feature_cols = [
        "shot_zone_basic_enc", "shot_zone_area_enc", "shot_zone_range_enc",
        "action_type_clean_enc", "shot_distance", "is_3pt",
    ]
    X = df[feature_cols].values.astype(float)
    return X, encoders


# ── model class ───────────────────────────────────────────────────────────────

class XFGModel:
    """Expected Field Goal % model v1 — NBA shot chart data only."""

    def __init__(self):
        self.model    = None
        self.encoders = None
        self.meta: dict = {}

    # ── training ──────────────────────────────────────────────────────────────

    def train(self, output_path: str = _MODEL_PATH) -> "XFGModel":
        """Train on all scraped shot charts and save to output_path."""
        from xgboost import XGBClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import log_loss, brier_score_loss

        df = load_all_shot_charts()

        # Drop rows without outcome
        df = df.dropna(subset=["shot_made_flag"])
        df["shot_made_flag"] = df["shot_made_flag"].astype(int)

        X, encoders = _encode_features(df)
        y = df["shot_made_flag"].values

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=y
        )

        self.model = XGBClassifier(
            n_estimators=400,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        self.encoders = encoders

        y_prob = self.model.predict_proba(X_val)[:, 1]
        brier  = brier_score_loss(y_val, y_prob)
        ll     = log_loss(y_val, y_prob)
        league_avg = y.mean()

        self.meta = {
            "n_shots": int(len(df)),
            "league_fg_pct": round(float(league_avg), 4),
            "val_brier": round(float(brier), 4),
            "val_log_loss": round(float(ll), 4),
        }

        print(f"[xfg] Trained on {len(df):,} shots")
        print(f"[xfg] League avg FG%: {league_avg:.3f}")
        print(f"[xfg] Val Brier: {brier:.4f}  |  Log-loss: {ll:.4f}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._save(output_path)
        self._write_calibration(df, X_val, y_val, y_prob)
        return self

    # ── inference ─────────────────────────────────────────────────────────────

    def predict(self, shot: dict) -> float:
        """
        Predict xFG for a single shot.

        Args:
            shot: dict with keys matching shot chart schema
                  (shot_zone_basic, shot_zone_area, shot_zone_range,
                   shot_distance, shot_type, action_type)

        Returns:
            xFG probability in [0, 1].
        """
        df = pd.DataFrame([shot])
        X, _ = _encode_features(df, encoders=self.encoders)
        return float(self.model.predict_proba(X)[0, 1])

    def predict_batch(self, df: pd.DataFrame) -> pd.Series:
        """Predict xFG for each row in a DataFrame."""
        X, _ = _encode_features(df, encoders=self.encoders)
        probs = self.model.predict_proba(X)[:, 1]
        return pd.Series(probs, index=df.index, name="xfg")

    # ── evaluation ────────────────────────────────────────────────────────────

    def evaluate(self) -> dict:
        """Zone-level calibration: expected vs actual FG% by zone."""
        from sklearn.metrics import brier_score_loss

        df = load_all_shot_charts()
        df = df.dropna(subset=["shot_made_flag"])
        df["shot_made_flag"] = df["shot_made_flag"].astype(int)

        X, _ = _encode_features(df, encoders=self.encoders)
        df["xfg"] = self.model.predict_proba(X)[:, 1]

        zone_report = {}
        for zone, grp in df.groupby("shot_zone_basic"):
            zone_report[zone] = {
                "n":          int(len(grp)),
                "actual_fg":  round(float(grp["shot_made_flag"].mean()), 4),
                "mean_xfg":   round(float(grp["xfg"].mean()), 4),
            }

        overall_brier = brier_score_loss(
            df["shot_made_flag"].values, df["xfg"].values
        )
        return {"brier": round(float(overall_brier), 4), "zones": zone_report}

    # ── persistence ───────────────────────────────────────────────────────────

    def _save(self, path: str) -> None:
        payload = {"model": self.model, "encoders": self.encoders, "meta": self.meta}
        with open(path, "wb") as f:
            pickle.dump(payload, f)
        print(f"[xfg] Saved → {path}")

    def _write_calibration(
        self,
        df: pd.DataFrame,
        X_val: np.ndarray,
        y_val: np.ndarray,
        y_prob: np.ndarray,
    ) -> None:
        df_val = df.iloc[-len(y_val):].copy()
        df_val["xfg"] = y_prob
        cal: Dict[str, dict] = {}
        for zone, grp in df_val.groupby("shot_zone_basic"):
            cal[zone] = {
                "n": int(len(grp)),
                "actual_fg": round(float(grp["shot_made_flag"].mean()), 4),
                "mean_xfg":  round(float(grp["xfg"].mean()), 4),
            }
        out = os.path.join(_NBA_CACHE, "xfg_calibration.json")
        with open(out, "w") as f:
            json.dump({**self.meta, "zones": cal}, f, indent=2)
        print(f"[xfg] Calibration → {out}")


def load(model_path: str = _MODEL_PATH) -> XFGModel:
    """Load a saved XFGModel from disk."""
    with open(model_path, "rb") as f:
        payload = pickle.load(f)
    m = XFGModel()
    m.model    = payload["model"]
    m.encoders = payload["encoders"]
    m.meta     = payload.get("meta", {})
    return m


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="xFG v1 model")
    ap.add_argument("--train",    action="store_true")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--predict",  action="store_true")
    ap.add_argument("--zone",     default="Above the Break 3")
    ap.add_argument("--area",     default="Center(C)")
    ap.add_argument("--range",    default="24+ ft.")
    ap.add_argument("--distance", type=int, default=25)
    ap.add_argument("--shot-type", default="3PT Field Goal")
    ap.add_argument("--action",   default="Jump Shot")
    args = ap.parse_args()

    if args.train:
        m = XFGModel()
        m.train()

    elif args.evaluate:
        m = load()
        report = m.evaluate()
        print(f"\nOverall Brier: {report['brier']}")
        print(f"\n{'Zone':<30} {'N':>7} {'Actual':>8} {'xFG':>8} {'Delta':>8}")
        print("-" * 65)
        for zone, s in sorted(report["zones"].items()):
            delta = s["mean_xfg"] - s["actual_fg"]
            print(f"{zone:<30} {s['n']:>7,} {s['actual_fg']:>8.3f} {s['mean_xfg']:>8.3f} {delta:>+8.3f}")

    elif args.predict:
        m = load()
        shot = {
            "shot_zone_basic":  args.zone,
            "shot_zone_area":   args.area,
            "shot_zone_range":  args.range,
            "shot_distance":    args.distance,
            "shot_type":        args.shot_type,
            "action_type":      args.action,
        }
        xfg = m.predict(shot)
        print(f"xFG: {xfg:.3f} ({xfg*100:.1f}%)")
