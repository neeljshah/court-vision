"""
stale_line_classifier.py — Distinguish a "stale" sportsbook line (lagging
true market value, i.e. exploitable) from a "trap" / sharp line (deliberately
off to attract square money) when Pinnacle and other books disagree.

Features
--------
FEATURES = ["time_since_move", "news_in_window", "lineup_status"]

- time_since_move : minutes since the line last moved. A stale line tends to
  be frozen while the market has moved elsewhere; a trap line is often freshly
  set.
- news_in_window  : count of relevant news items (injury, trade, weather, …)
  published in a recent window. Stale lines often precede a news burst; traps
  exploit existing public narrative.
- lineup_status   : encoded int — 0=confirmed, 1=projected, 2=questionable/
  unknown. Uncertainty inflates trap probability because books shade against
  uninformed bettors.

Label : 1 = stale (exploitable), 0 = trap/sharp.

TODO: production use needs real labeled line-movement data; the classifier
mechanism is delivered here, training data collection is a follow-up.

Persistence: data/models/stale_line_classifier.pkl
Convention  : StandardScaler + LogisticRegression(class_weight="balanced",
              max_iter=500), persisted as {"model", "scaler", "features"}.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from typing import List, Union

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

FEATURES: List[str] = ["time_since_move", "news_in_window", "lineup_status"]

_MODEL_PATH: str = os.path.join(PROJECT_DIR, "data", "models", "stale_line_classifier.pkl")


class StaleLineClassifier:
    """Logistic classifier: stale line (1) vs trap/sharp line (0)."""

    def __init__(self) -> None:
        self.model = None
        self.scaler = None
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load persisted model + scaler from disk if available."""
        if not os.path.exists(_MODEL_PATH):
            return
        try:
            with open(_MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)
            self.model = bundle["model"]
            self.scaler = bundle["scaler"]
        except Exception:
            # Corrupt / incompatible file — stay unfitted
            self.model = None
            self.scaler = None

    def _to_matrix(self, X: Union[List[dict], np.ndarray, list]) -> np.ndarray:
        """Convert list-of-dicts *or* 2-D array-like to (n, 3) float ndarray."""
        if isinstance(X, np.ndarray):
            arr = X.astype(float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            return arr
        # Check if it's a list of dicts
        if X and isinstance(X[0], dict):
            return np.array(
                [[row[f] for f in FEATURES] for row in X], dtype=float
            )
        # Assume 2-D list-of-lists / list-of-tuples
        return np.array(X, dtype=float)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, X, y) -> dict:
        """
        Fit scaler + logistic regression, persist to disk.

        Parameters
        ----------
        X : list[dict] or array-like (n, 3)
        y : array-like of int {0, 1}  (1 = stale)

        Returns
        -------
        dict with keys "n" (int) and "stale_rate" (float).
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        X_mat = self._to_matrix(X)
        y_arr = np.array(y, dtype=int)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_mat)

        model = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42)
        model.fit(X_scaled, y_arr)

        self.model = model
        self.scaler = scaler

        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"model": model, "scaler": scaler, "features": FEATURES}, f)

        return {"n": int(len(y_arr)), "stale_rate": float(y_arr.mean())}

    def predict_proba(self, x) -> float:
        """
        Return P(stale) for a single sample.

        Parameters
        ----------
        x : dict with FEATURES keys, or length-3 sequence.

        Returns
        -------
        float in [0.0, 1.0]. Returns 0.5 when the model is not fitted.
        """
        if self.model is None or self.scaler is None:
            return 0.5

        if isinstance(x, dict):
            row = np.array([[x[f] for f in FEATURES]], dtype=float)
        else:
            row = np.array(x, dtype=float).reshape(1, -1)

        row_scaled = self.scaler.transform(row)
        return float(self.model.predict_proba(row_scaled)[0, 1])

    def predict(self, x, threshold: float = 0.5) -> bool:
        """
        Return True if the line is classified as stale.

        Parameters
        ----------
        x         : same as predict_proba.
        threshold : decision boundary (default 0.5).
        """
        return self.predict_proba(x) >= threshold

    def evaluate(self, X, y) -> dict:
        """
        Compute F1, precision, recall on a labelled dataset.

        Returns
        -------
        dict with keys "f1", "precision", "recall", "n".
        """
        from sklearn.metrics import f1_score, precision_score, recall_score

        X_mat = self._to_matrix(X)
        y_arr = np.array(y, dtype=int)

        preds = np.array(
            [int(self.predict_proba(row) >= 0.5) for row in X_mat],
            dtype=int,
        )

        return {
            "f1":        float(f1_score(y_arr, preds, zero_division=0)),
            "precision": float(precision_score(y_arr, preds, zero_division=0)),
            "recall":    float(recall_score(y_arr, preds, zero_division=0)),
            "n":         int(len(y_arr)),
        }


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def train_from_records(records: list, test_size: float = 0.25) -> dict:
    """
    Fit a StaleLineClassifier from a list of feature dicts and return holdout metrics.

    Each record must contain the 3 FEATURES keys plus an ``is_stale`` or
    ``label`` key (int {0, 1}).

    Parameters
    ----------
    records   : list[dict]
    test_size : fraction held out for evaluation (default 0.25).

    Returns
    -------
    dict with keys "holdout" (evaluate dict), "train_n", "holdout_n".
    """
    from sklearn.model_selection import train_test_split

    X = [{f: r[f] for f in FEATURES} for r in records]
    y = np.array(
        [int(r.get("is_stale", r.get("label", 0))) for r in records], dtype=int
    )

    X_train, X_holdout, y_train, y_holdout = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=42
    )

    clf = StaleLineClassifier()
    clf.fit(X_train, y_train)
    holdout_metrics = clf.evaluate(X_holdout, y_holdout)

    return {
        "holdout":   holdout_metrics,
        "train_n":   int(len(y_train)),
        "holdout_n": int(len(y_holdout)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stale line classifier — train from records JSON.")
    parser.add_argument("--train", metavar="PATH", help="Path to JSON list of labeled records.")
    args = parser.parse_args()

    if args.train:
        with open(args.train, encoding="utf-8") as fh:
            data = json.load(fh)
        result = train_from_records(data)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
