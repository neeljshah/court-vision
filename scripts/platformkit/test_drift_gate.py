"""Per-file tests for the adversarial-validation drift gate."""
from __future__ import annotations

import json

import numpy as np

from scripts.platformkit import drift_gate
from scripts.platformkit.drift_gate import check_drift


def _dates(n: int) -> np.ndarray:
    return np.datetime64("2026-01-01") + np.arange(n).astype("timedelta64[D]")


def test_stationary_features_are_green(tmp_path, monkeypatch):
    monkeypatch.setattr(drift_gate, "LEDGER_PATH", tmp_path / "drift_ledger.jsonl")
    matrix = np.random.default_rng(7).normal(size=(180, 3))
    report = check_drift(matrix, _dates(180), ["per36_rate", "load_state", "base_rate"], window_days=30)
    assert all(item["status"] == "GREEN" for item in report.values())
    assert all(0.25 <= item["auc"] < 0.75 for item in report.values())
    records = [json.loads(line) for line in drift_gate.LEDGER_PATH.read_text(encoding="utf-8").splitlines()]
    assert {item["family"] for item in records} == {"per36", "load", "base"}


def test_engineered_family_shift_fires_amber_or_red(tmp_path, monkeypatch):
    monkeypatch.setattr(drift_gate, "LEDGER_PATH", tmp_path / "drift_ledger.jsonl")
    rng = np.random.default_rng(8)
    matrix = rng.normal(size=(180, 2))
    matrix[-30:, 0] += 8.0
    report = check_drift(matrix, _dates(180), ["embedding_profile", "base_rate"], window_days=30)
    assert report["embedding"]["status"] in {"AMBER", "RED"}
    assert report["embedding"]["auc"] >= 0.75
    assert report["base"]["status"] == "GREEN"
