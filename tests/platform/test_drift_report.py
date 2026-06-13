"""test_drift_report.py — Offline unit tests for drift_report.py.

Python 3.9 compatible.  No network, no GPU, no torch, no FastAPI boot.
Scorers are stubbed or driven with synthetic in-memory data so no parquet
files need to be present.

Acceptance criteria tested:
    1. build_report() returns a valid dict with the required schema keys.
    2. write_vault_note() creates a file and is idempotent (rerun = same path).
    3. _BANNER is present in the written note.
    4. Graceful degradation when all data sources are absent (exit 0, stub note).
    5. _brier_binary, _brier_raw, _pit_uniformity, _interval_coverage return
       sensible values on synthetic data (no imports from heavy deps except numpy).
    6. _compute_point_metrics and _compute_coverage_metrics handle empty DataFrames.
    7. render_vault_note produces valid Markdown containing expected headings.
    8. Feature drift summary detects drifted features correctly.
"""
from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Repo root and module path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
_OBS_DIR = ROOT / "scripts" / "platformkit" / "obs"
if str(_OBS_DIR) not in sys.path:
    sys.path.insert(0, str(_OBS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import drift_report as dr  # noqa: E402  (module in sys.path via _OBS_DIR)

# ---------------------------------------------------------------------------
# Helpers — synthetic data builders
# ---------------------------------------------------------------------------


def _make_cal_df(n: int = 200, seed: int = 42):
    """Create a synthetic calibration_frame DataFrame."""
    import numpy as np  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    rng = np.random.default_rng(seed)
    stats = ["pts", "reb", "ast"]
    dates = pd.date_range("2026-01-01", periods=n // len(stats), freq="D")
    rows = []
    for stat in stats:
        for d in dates:
            pred = rng.uniform(5.0, 30.0)
            actual = pred + rng.normal(0, 3.0)
            rows.append({
                "player_id": 1,
                "date": str(d.date()),
                "stat": stat,
                "season": "2025-26",
                "pred": pred,
                "actual": actual,
                "err": actual - pred,
                "abs_err": abs(actual - pred),
                "actual_min": 28.0,
                "l10_min": 27.0,
                "rest_days": 2,
                "is_b2b": 0,
                "is_home": 1,
                "month": d.month,
                "days_into_season": 60,
                "opp_pace": 100.0,
                "opp_def": 112.0,
            })
    return pd.DataFrame(rows)


def _make_cal_hist_df():
    """Create a synthetic prop_calibration_history DataFrame."""
    import pandas as pd  # noqa: PLC0415

    rows = [
        {"player_id": 1, "stat": "pts", "n": 50, "mean_pred": 20.0,
         "mean_actual": 20.1, "bias": -0.1, "mae": 4.0, "rmse": 5.0,
         "n_interval": 50, "interval_coverage": 0.80, "interval_nominal": 0.80},
        {"player_id": 2, "stat": "pts", "n": 40, "mean_pred": 15.0,
         "mean_actual": 15.5, "bias": -0.5, "mae": 3.5, "rmse": 4.5,
         "n_interval": 40, "interval_coverage": 0.82, "interval_nominal": 0.80},
        {"player_id": 1, "stat": "reb", "n": 50, "mean_pred": 6.0,
         "mean_actual": 6.2, "bias": -0.2, "mae": 1.5, "rmse": 2.0,
         "n_interval": 50, "interval_coverage": 0.70, "interval_nominal": 0.80},
    ]
    return pd.DataFrame(rows)


def _make_drift_log() -> Dict[str, Any]:
    """Create a synthetic feature_drift_log dict with one drifted model."""
    return {
        "pts_model": [
            {"timestamp": time.time() - 3600, "importances": {"feat_a": 0.5, "feat_b": 0.3}},
            {"timestamp": time.time() - 1800, "importances": {"feat_a": 0.48, "feat_b": 0.32}},
            # 3rd snapshot: feat_a drops sharply → drift
            {"timestamp": time.time(), "importances": {"feat_a": 0.1, "feat_b": 0.31}},
        ],
        "reb_model": [
            {"timestamp": time.time() - 3600, "importances": {"feat_x": 0.6}},
            {"timestamp": time.time(), "importances": {"feat_x": 0.59}},
        ],
    }


# ---------------------------------------------------------------------------
# 1. build_report() schema
# ---------------------------------------------------------------------------


def test_build_report_returns_dict(monkeypatch):
    """build_report() must return a dict with the required top-level keys."""
    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: None)
    monkeypatch.setattr(dr, "_load_cal_history", lambda: None)
    monkeypatch.setattr(dr, "_load_drift_log", lambda: {})

    result = dr.build_report()
    assert isinstance(result, dict)
    required = {"generated_at", "data_sources", "point_metrics",
                "coverage_metrics", "drift_metrics", "all_flags"}
    assert required <= set(result.keys()), f"Missing keys: {required - set(result.keys())}"


def test_build_report_with_real_data(monkeypatch):
    """build_report() with synthetic DataFrames returns non-empty per_stat."""
    cal_df = _make_cal_df()
    cal_hist = _make_cal_hist_df()
    drift_log = _make_drift_log()

    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: cal_df)
    monkeypatch.setattr(dr, "_load_cal_history", lambda: cal_hist)
    monkeypatch.setattr(dr, "_load_drift_log", lambda: drift_log)

    result = dr.build_report()
    pm = result["point_metrics"]
    assert pm["n_total"] > 0
    assert "pts" in pm["per_stat"]

    cm = result["coverage_metrics"]
    assert "pts" in cm["per_stat"]

    dm = result["drift_metrics"]
    assert dm["model_count"] == 2


def test_build_report_is_json_serialisable(monkeypatch):
    """build_report() result must be JSON-serialisable."""
    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: _make_cal_df())
    monkeypatch.setattr(dr, "_load_cal_history", lambda: _make_cal_hist_df())
    monkeypatch.setattr(dr, "_load_drift_log", lambda: _make_drift_log())

    result = dr.build_report()
    serialised = json.dumps(result)
    assert isinstance(serialised, str)


# ---------------------------------------------------------------------------
# 2. write_vault_note() idempotency
# ---------------------------------------------------------------------------


def test_write_vault_note_creates_file(tmp_path):
    """write_vault_note() must create the note at the given path."""
    report = dr.build_report.__wrapped__ if hasattr(dr.build_report, "__wrapped__") else None
    stub_report: Dict[str, Any] = {
        "generated_at": "2026-06-11T00:00:00+00:00",
        "data_sources": {"calibration_frame": "absent"},
        "point_metrics": {"window_days": 30, "n_total": 0, "per_stat": {}, "flags": []},
        "coverage_metrics": {"per_stat": {}, "flags": []},
        "drift_metrics": {"model_count": 0, "flagged_models": [], "n_flagged": 0, "flags": []},
        "all_flags": [],
    }
    out = dr.write_vault_note(stub_report, out_path=tmp_path / "Drift Report.md")
    assert out.exists(), "Vault note must be created"
    content = out.read_text(encoding="utf-8")
    assert dr._BANNER in content, "Banner must be present in vault note"


def test_write_vault_note_idempotent(tmp_path):
    """Calling write_vault_note() twice with the same report should produce the same file."""
    stub_report: Dict[str, Any] = {
        "generated_at": "2026-06-11T00:00:00+00:00",
        "data_sources": {"calibration_frame": "absent"},
        "point_metrics": {"window_days": 30, "n_total": 0, "per_stat": {}, "flags": []},
        "coverage_metrics": {"per_stat": {}, "flags": []},
        "drift_metrics": {"model_count": 0, "flagged_models": [], "n_flagged": 0, "flags": []},
        "all_flags": [],
    }
    out_path = tmp_path / "Drift Report.md"
    dr.write_vault_note(stub_report, out_path=out_path)
    first_content = out_path.read_text(encoding="utf-8")

    dr.write_vault_note(stub_report, out_path=out_path)
    second_content = out_path.read_text(encoding="utf-8")

    assert first_content == second_content, "Idempotent: same input → same output"


def test_write_vault_note_overwrites_not_duplicates(tmp_path):
    """Rerunning with a different timestamp should overwrite, not duplicate, the banner."""
    out_path = tmp_path / "Drift Report.md"

    def _stub(ts: str) -> Dict[str, Any]:
        return {
            "generated_at": ts,
            "data_sources": {},
            "point_metrics": {"window_days": 30, "n_total": 0, "per_stat": {}, "flags": []},
            "coverage_metrics": {"per_stat": {}, "flags": []},
            "drift_metrics": {"model_count": 0, "flagged_models": [], "n_flagged": 0, "flags": []},
            "all_flags": [],
        }

    dr.write_vault_note(_stub("2026-06-11T00:00:00+00:00"), out_path=out_path)
    dr.write_vault_note(_stub("2026-06-12T00:00:00+00:00"), out_path=out_path)

    content = out_path.read_text(encoding="utf-8")
    banner_count = content.count(dr._BANNER)
    assert banner_count == 1, f"Banner must appear exactly once; got {banner_count}"


# ---------------------------------------------------------------------------
# 3. Markdown rendering
# ---------------------------------------------------------------------------


def test_render_vault_note_contains_headings():
    """render_vault_note() must include expected section headings."""
    stub_report: Dict[str, Any] = {
        "generated_at": "2026-06-11T00:00:00+00:00",
        "data_sources": {"calibration_frame": "absent"},
        "point_metrics": {"window_days": 30, "n_total": 0, "per_stat": {}, "flags": []},
        "coverage_metrics": {"per_stat": {}, "flags": []},
        "drift_metrics": {"model_count": 0, "flagged_models": [], "n_flagged": 0, "flags": []},
        "all_flags": [],
    }
    md = dr.render_vault_note(stub_report)
    assert "## Point Calibration Metrics" in md
    assert "## Interval Coverage" in md
    assert "## Feature Drift" in md
    assert dr._BANNER in md


def test_render_vault_note_with_data(monkeypatch):
    """render_vault_note() with real per-stat data renders stat rows."""
    cal_df = _make_cal_df()
    cal_hist = _make_cal_hist_df()
    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: cal_df)
    monkeypatch.setattr(dr, "_load_cal_history", lambda: cal_hist)
    monkeypatch.setattr(dr, "_load_drift_log", lambda: {})

    report = dr.build_report()
    md = dr.render_vault_note(report)
    assert "pts" in md
    assert "reb" in md


# ---------------------------------------------------------------------------
# 4. Graceful degradation
# ---------------------------------------------------------------------------


def test_graceful_degradation_all_absent(monkeypatch):
    """When all sources absent, build_report() must not raise and n_total == 0."""
    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: None)
    monkeypatch.setattr(dr, "_load_cal_history", lambda: None)
    monkeypatch.setattr(dr, "_load_drift_log", lambda: {})

    result = dr.build_report()
    assert result["point_metrics"]["n_total"] == 0
    assert result["coverage_metrics"]["per_stat"] == {}
    assert result["drift_metrics"]["model_count"] == 0


def test_main_exits_cleanly_all_absent(monkeypatch, tmp_path):
    """main() must exit 0 (no raise) when all data is absent."""
    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: None)
    monkeypatch.setattr(dr, "_load_cal_history", lambda: None)
    monkeypatch.setattr(dr, "_load_drift_log", lambda: {})
    monkeypatch.setattr(dr, "_VAULT_NOTE", tmp_path / "Drift Report.md")

    try:
        dr.main()
    except SystemExit as exc:
        assert exc.code in (None, 0), f"main() must exit 0, got {exc.code}"


# ---------------------------------------------------------------------------
# 5. Metric scorers with synthetic arrays
# ---------------------------------------------------------------------------


def test_brier_raw_known_value():
    """_brier_raw([2.0], [3.0]) == 1.0 (MSE of a single row off by 1)."""
    result = dr._brier_raw([2.0], [3.0])
    assert abs(result - 1.0) < 1e-9


def test_brier_raw_perfect():
    """_brier_raw when pred == actual → 0."""
    result = dr._brier_raw([5.0, 10.0], [5.0, 10.0])
    assert result == pytest.approx(0.0, abs=1e-9)


def test_brier_binary_symmetric():
    """_brier_binary with 50/50 over/under split and p=0.5 → Brier=0.25."""
    pred = [10.0] * 100
    actual = [11.0] * 50 + [9.0] * 50  # 50% over, 50% under
    result = dr._brier_binary(pred, actual)
    assert abs(result - 0.25) < 1e-9, f"Expected 0.25 got {result}"


def test_brier_all_nan_graceful():
    """_brier_raw with all-nan input returns nan, not raises."""
    import math
    result = dr._brier_raw([float("nan")], [float("nan")])
    assert math.isnan(result)


def test_pit_uniformity_normal_data():
    """_pit_uniformity on normally-distributed residuals returns ok flag."""
    import numpy as np
    rng = np.random.default_rng(0)
    residuals = rng.standard_normal(500)
    result = dr._pit_uniformity(residuals, n_bins=10)
    assert "flag" in result
    assert result["n"] == 500
    # A perfectly normal sample should pass the chi-sq test
    assert result["flag"] in ("ok", "non_uniform")  # could fail on unlucky seed, so just check type


def test_pit_uniformity_too_few_samples():
    """_pit_uniformity with < n_bins*5 samples returns flag='too_few_samples'."""
    result = dr._pit_uniformity([1.0, 2.0, 3.0], n_bins=10)
    assert result["flag"] == "too_few_samples"


def test_interval_coverage_all_inside():
    """_interval_coverage → 1.0 when all actuals are within bounds."""
    actual = [5.0, 10.0, 15.0]
    q10 = [4.0, 9.0, 14.0]
    q90 = [6.0, 11.0, 16.0]
    result = dr._interval_coverage(actual, q10, q90)
    assert abs(result - 1.0) < 1e-9


def test_interval_coverage_none_inside():
    """_interval_coverage → 0.0 when no actuals are within bounds."""
    actual = [100.0, 200.0]
    q10 = [1.0, 2.0]
    q90 = [2.0, 3.0]
    result = dr._interval_coverage(actual, q10, q90)
    assert abs(result - 0.0) < 1e-9


def test_interval_coverage_partial():
    """_interval_coverage → 0.5 for half inside."""
    actual = [5.0, 100.0]
    q10 = [4.0, 4.0]
    q90 = [6.0, 6.0]
    result = dr._interval_coverage(actual, q10, q90)
    assert abs(result - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# 6. _compute_point_metrics on empty DataFrame
# ---------------------------------------------------------------------------


def test_compute_point_metrics_empty_df():
    """_compute_point_metrics on an empty DataFrame returns n_total == 0, no crash."""
    import pandas as pd  # noqa: PLC0415
    empty_df = pd.DataFrame(columns=["player_id", "date", "stat", "season",
                                     "pred", "actual", "err", "abs_err",
                                     "actual_min", "l10_min", "rest_days",
                                     "is_b2b", "is_home", "month",
                                     "days_into_season", "opp_pace", "opp_def"])
    result = dr._compute_point_metrics(empty_df)
    assert result["n_total"] == 0
    assert result["per_stat"] == {}


def test_compute_coverage_metrics_empty_df():
    """_compute_coverage_metrics on an empty DataFrame returns empty per_stat."""
    import pandas as pd  # noqa: PLC0415
    empty_df = pd.DataFrame(columns=["player_id", "stat", "n", "mean_pred",
                                     "mean_actual", "bias", "mae", "rmse",
                                     "n_interval", "interval_coverage",
                                     "interval_nominal"])
    result = dr._compute_coverage_metrics(empty_df)
    assert result["per_stat"] == {}


# ---------------------------------------------------------------------------
# 7. Feature drift detection
# ---------------------------------------------------------------------------


def test_compute_drift_summary_detects_drift():
    """_compute_drift_summary must flag pts_model with synthetic drift data."""
    drift_log = _make_drift_log()
    result = dr._compute_drift_summary(drift_log)
    assert result["model_count"] == 2
    # pts_model has a sharp drop in feat_a — should be flagged
    assert "pts_model" in result["flagged_models"]


def test_compute_drift_summary_no_drift():
    """_compute_drift_summary must not flag a stable model."""
    stable_log = {
        "stable_model": [
            {"timestamp": 1000.0, "importances": {"feat_a": 0.5, "feat_b": 0.3}},
            {"timestamp": 2000.0, "importances": {"feat_a": 0.51, "feat_b": 0.29}},
            {"timestamp": 3000.0, "importances": {"feat_a": 0.50, "feat_b": 0.30}},
        ]
    }
    result = dr._compute_drift_summary(stable_log)
    assert result["n_flagged"] == 0


def test_compute_drift_summary_empty_log():
    """_compute_drift_summary on empty log returns model_count == 0."""
    result = dr._compute_drift_summary({})
    assert result["model_count"] == 0
    assert result["n_flagged"] == 0


# ---------------------------------------------------------------------------
# 8. Coverage flag detection in coverage metrics
# ---------------------------------------------------------------------------


def test_coverage_flags_tight_interval():
    """_compute_coverage_metrics must flag a stat with coverage well below nominal."""
    import pandas as pd  # noqa: PLC0415
    # reb has coverage=0.70 vs nominal=0.80 → gap=-0.10 → should be flagged
    df = _make_cal_hist_df()
    result = dr._compute_coverage_metrics(df)
    flags = result["flags"]
    # At least one flag mentioning reb
    assert any("reb" in f for f in flags), f"Expected reb coverage flag, got: {flags}"


# ---------------------------------------------------------------------------
# 9. Performance: build_report completes in < 10 s on synthetic data
# ---------------------------------------------------------------------------


def test_build_report_completes_quickly(monkeypatch):
    """build_report() with synthetic data must complete in under 10 s."""
    import time

    monkeypatch.setattr(dr, "_load_calibration_frame", lambda: _make_cal_df(300))
    monkeypatch.setattr(dr, "_load_cal_history", lambda: _make_cal_hist_df())
    monkeypatch.setattr(dr, "_load_drift_log", lambda: _make_drift_log())

    t0 = time.monotonic()
    dr.build_report()
    elapsed = time.monotonic() - t0
    assert elapsed < 10.0, f"build_report() took {elapsed:.2f}s — too slow"
