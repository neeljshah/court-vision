"""Focused tests for the portable serving calibration artifact."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.serving_calibration import ServingCalibrator


def test_fit_save_load_roundtrip_and_monotone_apply(tmp_path: Path) -> None:
    calibrator = ServingCalibrator()
    points = calibrator.fit([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1])
    path = tmp_path / "calibrator.json"
    calibrator.save(path)
    loaded = ServingCalibrator.load(path)
    assert loaded.x_thresholds == points["x"]
    assert loaded.y_thresholds == points["y"]
    values = loaded.apply([0.0, 0.2, 0.5, 1.0])
    assert all(left <= right for left, right in zip(values, values[1:]))


def test_refit_policy_and_progressive_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "ab_reports" / "ledger.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"fitted_at": old}) + "\n", encoding="ascii")
    calibrator = ServingCalibrator(window=2)
    assert calibrator.refit_policy(ledger)
    recent = datetime.now(timezone.utc).isoformat()
    ledger.write_text(json.dumps({"fitted_at": recent}) + "\n", encoding="ascii")
    assert not calibrator.refit_policy(ledger)
    with ledger.open("a", encoding="ascii") as handle:
        for _ in range(501):
            handle.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "outcome": 1}) + "\n")
    assert calibrator.refit_policy(ledger)
    score = calibrator.score_online(0.8, 1.0, ledger_path=ledger)
    rows = [json.loads(line) for line in ledger.read_text(encoding="ascii").splitlines()]
    assert score == rows[-1]["rolling_brier"]
    assert score == pytest.approx(0.04)
    assert rows[-1]["pred"] == 0.8
