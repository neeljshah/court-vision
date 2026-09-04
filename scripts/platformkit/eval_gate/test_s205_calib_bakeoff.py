"""Focused tests for the sealed S205 CPCV calibration bakeoff."""
from datetime import date, timedelta

import numpy as np

from scripts.platformkit.eval_gate.s205_calib_bakeoff import _metrics
from scripts.platformkit.eval_gate.s205_calib_oof import EMBARGO_DAYS, calibrate


def _rows(n=32):
    start = date(2024, 1, 1)
    return [{"event_id": "202401%02d-H%02d-A%02d-1" % (index % 28 + 1, index, index),
             "event_date": start + timedelta(days=index), "corpus_unit": "test"}
            for index in range(n)]


def test_cpcv_uses_one_oof_prediction_and_actual_regime_history():
    raw = np.linspace(0.05, 0.95, 32).tolist()
    outcomes, regimes = ([0.0, 1.0] * 16), ["confidence=T1"] * 32
    arms, history = calibrate(_rows(), raw, outcomes, regimes)
    assert set(arms) == {"isotonic", "temperature", "beta"}
    assert all(len(values) == len(raw) for values in arms.values())
    assert all(item["fit_history_source"] == "GLOBAL" for item in history)
    assert all(item["n_train_after_purge"] >= item["fit_history"] for item in history)
    assert any(item["fit_history"] != index for index, item in enumerate(history))
    assert EMBARGO_DAYS == 1


def test_metrics_keep_all_rows_and_all_ten_bins():
    raw = [0.1, 0.2, 0.8, 0.9] * 60
    calibrated = list(np.linspace(0.01, 0.99, len(raw)))
    outcomes = [0.0, 0.0, 1.0, 1.0] * 60
    metrics = _metrics(raw, calibrated, outcomes)
    assert sum(row["n"] for row in metrics["reliability_bins"]) == len(raw)
    assert len(metrics["reliability_bins"]) == 10
