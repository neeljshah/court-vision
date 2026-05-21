"""
drift_detector.py — Feature drift detector for CourtVision prediction batches.

Loads a 30-day rolling feature baseline (mean/std per feature) from
data/output/feature_baseline.json. For each incoming prediction batch
(DataFrame), flags any feature whose current mean deviates more than 2σ
from the baseline and fires an SLO alert via the ops alerter.

Usage:
    from src.prediction.drift_detector import DriftDetector
    detector = DriftDetector()
    flags = detector.check(batch_df)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

import pandas as pd

from src.ops.alerter import SLOBreach, check_and_alert, fire_alert

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DEFAULT_BASELINE_PATH = os.path.join(
    _PROJECT_DIR, "data", "output", "feature_baseline.json"
)

# σ multiplier that triggers a drift flag
DRIFT_SIGMA_THRESHOLD: float = 2.0


class DriftDetector:
    """Detects feature distribution drift against a stored baseline."""

    def __init__(self, baseline_path: Optional[str] = None) -> None:
        self.baseline_path = baseline_path or _DEFAULT_BASELINE_PATH
        self.baseline: Dict[str, Dict[str, float]] = {}
        self._load_baseline()

    # ── public ────────────────────────────────────────────────────────────────

    def check(
        self,
        batch: pd.DataFrame,
        send_telegram: bool = False,
    ) -> List[str]:
        """Check a prediction batch for feature drift.

        Parameters
        ----------
        batch:
            DataFrame of incoming predictions.  Each numeric column is tested.
        send_telegram:
            Forward alerts to Telegram when True (default False — keeps
            routine batch checks quiet).

        Returns
        -------
        List of feature names whose current mean exceeds 2σ from baseline.
        """
        if not self.baseline:
            log.info("No baseline loaded — skipping drift check.")
            return []

        flagged: List[str] = []

        for feature, stats in self.baseline.items():
            if feature not in batch.columns:
                continue

            baseline_mean: float = stats.get("mean", 0.0)
            baseline_std: float = stats.get("std", 0.0)

            if baseline_std == 0.0:
                continue  # constant feature — skip to avoid div-by-zero

            current_mean: float = float(batch[feature].mean())
            z_score = abs(current_mean - baseline_mean) / baseline_std

            if z_score > DRIFT_SIGMA_THRESHOLD:
                flagged.append(feature)
                log.warning(
                    "Drift detected: feature=%s z=%.2f (current_mean=%.4f "
                    "baseline_mean=%.4f baseline_std=%.4f)",
                    feature,
                    z_score,
                    current_mean,
                    baseline_mean,
                    baseline_std,
                )
                self._fire_drift_alert(
                    feature=feature,
                    z_score=z_score,
                    current_mean=current_mean,
                    baseline_mean=baseline_mean,
                    baseline_std=baseline_std,
                    send_telegram=send_telegram,
                )

        return flagged

    # ── private ───────────────────────────────────────────────────────────────

    def _load_baseline(self) -> None:
        """Load baseline JSON; silently no-ops if file is absent or malformed."""
        if not os.path.exists(self.baseline_path):
            log.info("Baseline file not found at %s — drift check disabled.", self.baseline_path)
            return
        try:
            with open(self.baseline_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.baseline = data
                log.info(
                    "Loaded feature baseline with %d features from %s.",
                    len(self.baseline),
                    self.baseline_path,
                )
            else:
                log.warning("Baseline JSON is not a dict — ignoring.")
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load baseline: %s", exc)

    def _fire_drift_alert(
        self,
        feature: str,
        z_score: float,
        current_mean: float,
        baseline_mean: float,
        baseline_std: float,
        send_telegram: bool,
    ) -> None:
        """Construct a SLOBreach and fire it through the ops alerter."""
        breach = SLOBreach(
            slo_name="feature_drift",
            measured=z_score,
            threshold=DRIFT_SIGMA_THRESHOLD,
            unit="sigma",
            message=(
                f"Feature '{feature}' drifted {z_score:.2f}σ "
                f"(current_mean={current_mean:.4f}, "
                f"baseline_mean={baseline_mean:.4f}, "
                f"baseline_std={baseline_std:.4f})"
            ),
        )
        fire_alert(breach, send_telegram=send_telegram)
