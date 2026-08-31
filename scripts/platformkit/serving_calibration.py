"""Portable serving calibration artifacts with progressive validation.

The canonical dashboard Brier is the rolling online score, rather than a
one-off offline fit score.  This follows the Google CTR-trenches pattern:
keep appending delayed labels and evaluate the predictions as they arrive.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _REPO / "data" / "ab_reports" / "progressive_validation.jsonl"
_FIT_KEYS = ("fitted_at", "fit_at", "last_fit_at", "fit_timestamp")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _rows(path: Path) -> list[dict[str, Any]]:
    paths = list(path.glob("*.jsonl")) if path.is_dir() else [path]
    output: list[dict[str, Any]] = []
    for candidate in paths:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="ascii").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                output.append(row)
    return output


class ServingCalibrator:
    """Fit, persist, and apply an isotonic map separate from model artifacts."""

    def __init__(self, *, window: int = 500) -> None:
        self.window = int(window)
        self.x_thresholds: list[float] = []
        self.y_thresholds: list[float] = []
        self.fitted_at: str | None = None

    def fit(self, preds: Sequence[float], outcomes: Sequence[float]) -> dict[str, list[float]]:
        """Fit isotonic breakpoints and return their JSON-safe representation."""
        if len(preds) != len(outcomes) or not preds:
            raise ValueError("preds and outcomes must be non-empty and equally sized")
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit([float(value) for value in preds], [float(value) for value in outcomes])
        self.x_thresholds = [float(value) for value in model.X_thresholds_]
        self.y_thresholds = [float(value) for value in model.y_thresholds_]
        self.fitted_at = _utc_now().isoformat()
        return {"x": list(self.x_thresholds), "y": list(self.y_thresholds)}

    def apply(self, preds: Sequence[float]) -> list[float]:
        """Clip and calibrate predictions using the persisted isotonic steps."""
        if not self.x_thresholds:
            raise RuntimeError("fit or load a calibrator before apply")
        return [float(value) for value in np.interp(
            [float(value) for value in preds], self.x_thresholds, self.y_thresholds)]

    def save(self, path: Path) -> None:
        """Atomically save the calibration-only artifact as ASCII JSON."""
        if not self.x_thresholds:
            raise RuntimeError("fit a calibrator before save")
        artifact = {"method": "isotonic", "fitted_at": self.fitted_at,
                    "window": self.window, "x_thresholds": self.x_thresholds,
                    "y_thresholds": self.y_thresholds,
                    "breakpoints": {"x": self.x_thresholds, "y": self.y_thresholds}}
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="ascii")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "ServingCalibrator":
        """Load a previously saved calibration-only artifact."""
        artifact = json.loads(path.read_text(encoding="ascii"))
        points = artifact.get("breakpoints", {})
        calibrator = cls(window=int(artifact.get("window", 500)))
        calibrator.x_thresholds = [float(value) for value in artifact.get("x_thresholds", points.get("x", []))]
        calibrator.y_thresholds = [float(value) for value in artifact.get("y_thresholds", points.get("y", []))]
        if not calibrator.x_thresholds or len(calibrator.x_thresholds) != len(calibrator.y_thresholds):
            raise ValueError("invalid isotonic calibration artifact")
        calibrator.fitted_at = artifact.get("fitted_at")
        return calibrator

    def refit_policy(self, ledger_path: Path) -> bool:
        """Refit after seven days or 500 labels since the last recorded fit."""
        rows = _rows(Path(ledger_path))
        fits = [_parse_time(row[key]) for row in rows for key in _FIT_KEYS if key in row]
        last_fit = max((value for value in fits if value is not None), default=_parse_time(self.fitted_at))
        if last_fit is None or _utc_now() - last_fit > timedelta(days=7):
            return True
        return sum(1 for row in rows if "outcome" in row and (_parse_time(row.get("ts") or row.get("timestamp")) or _utc_now()) > last_fit) > 500

    def score_online(self, pred: float, outcome: float, *, ledger_path: Path | None = None) -> float:
        """Append one delayed label and return the canonical rolling-window Brier."""
        path = ledger_path or _DEFAULT_LEDGER
        path.parent.mkdir(parents=True, exist_ok=True)
        history = _rows(path)[-(self.window - 1):] if self.window > 1 else []
        scores = [(float(row["pred"]) - float(row["outcome"])) ** 2 for row in history if "pred" in row and "outcome" in row]
        scores.append((float(pred) - float(outcome)) ** 2)
        rolling_brier = sum(scores) / len(scores)
        row = {"ts": _utc_now().isoformat(), "pred": float(pred), "outcome": float(outcome),
               "rolling_window": self.window, "rolling_brier": rolling_brier}
        with path.open("a", encoding="ascii") as handle:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
        return rolling_brier
