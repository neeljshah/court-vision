"""tests/test_R27_T3_drift_detector.py — R27_T3 feature drift detector.

Suite covers correctness, BLOCKED paths, dashboard hook graceful-degrade, and
daily_workflow integration. Uses synthetic DataFrames so the tests never
depend on on-disk season files.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.feature_drift_detector import (  # noqa: E402
    classify,
    compute_feature_drift,
    detect_drift,
    format_report_table,
    run,
    select_current_window,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


# --------------------------------------------------------------------------- #
# 1. Identical distributions => 0 drift                                        #
# --------------------------------------------------------------------------- #
class TestIdenticalDistributions:

    def test_identical_distributions_zero_drift(self):
        rng = _rng(42)
        x = rng.normal(0.0, 1.0, size=500)
        ref = pd.DataFrame({"a": x, "b": x * 2.0})
        cur = pd.DataFrame({"a": x.copy(), "b": x.copy() * 2.0})
        res = detect_drift(ref, cur, ["a", "b"])
        assert res["n_features_analyzed"] == 2
        assert res["n_drift_major"] == 0
        assert res["n_stable"] == 2
        for r in res["features"]:
            assert r["class"] == "stable"

    def test_independent_draws_same_dist_mostly_stable(self):
        rng_ref = _rng(1)
        rng_cur = _rng(2)
        ref = pd.DataFrame({"x": rng_ref.normal(0, 1, 1000)})
        cur = pd.DataFrame({"x": rng_cur.normal(0, 1, 1000)})
        res = detect_drift(ref, cur, ["x"])
        rec = res["features"][0]
        # Two same-distribution samples: KS p-value typically large, mean_z small.
        assert rec["class"] in ("stable", "drift_minor")
        assert abs(rec["mean_z"]) < 0.5


# --------------------------------------------------------------------------- #
# 2. Mean shift +1.5σ -> drift_major                                           #
# --------------------------------------------------------------------------- #
class TestMeanShiftMajor:

    def test_one_point_five_sigma_shift_is_major(self):
        rng = _rng(7)
        ref = pd.DataFrame({"feat": rng.normal(0.0, 1.0, size=500)})
        cur = pd.DataFrame({"feat": rng.normal(1.5, 1.0, size=200)})
        res = detect_drift(ref, cur, ["feat"])
        rec = res["features"][0]
        assert rec["class"] == "drift_major"
        assert abs(rec["mean_z"]) > 1.0
        assert res["n_drift_major"] == 1

    def test_three_sigma_shift_is_major(self):
        rng = _rng(9)
        ref = pd.DataFrame({"feat": rng.normal(10.0, 2.0, size=400)})
        cur = pd.DataFrame({"feat": rng.normal(16.0, 2.0, size=200)})
        res = detect_drift(ref, cur, ["feat"])
        rec = res["features"][0]
        assert rec["class"] == "drift_major"
        # ks should be huge for a +3σ shift
        assert rec["ks_stat"] > 0.5
        assert rec["p_value"] < 1e-10


# --------------------------------------------------------------------------- #
# 3. Synthetic drift detection (multi-feature mix)                             #
# --------------------------------------------------------------------------- #
class TestSyntheticMixedDrift:

    def test_one_drifted_one_stable_correctly_classified(self):
        rng = _rng(11)
        ref = pd.DataFrame({
            "stable_feat":  rng.normal(0.0, 1.0, 500),
            "drifted_feat": rng.normal(0.0, 1.0, 500),
        })
        cur = pd.DataFrame({
            "stable_feat":  rng.normal(0.0, 1.0, 200),
            # +2σ shift on drifted_feat
            "drifted_feat": rng.normal(2.0, 1.0, 200),
        })
        res = detect_drift(ref, cur, ["stable_feat", "drifted_feat"])
        by_name = {r["feature"]: r for r in res["features"]}
        assert by_name["drifted_feat"]["class"] == "drift_major"
        assert by_name["stable_feat"]["class"] in ("stable", "drift_minor")
        assert res["n_drift_major"] >= 1


# --------------------------------------------------------------------------- #
# 4. KS test correctness on known distributions                                #
# --------------------------------------------------------------------------- #
class TestKSCorrectness:

    def test_disjoint_supports_ks_equals_one(self):
        ref = pd.Series([1.0] * 100 + [2.0] * 100)
        cur = pd.Series([10.0] * 100 + [11.0] * 100)
        rec = compute_feature_drift(ref, cur)
        assert rec is not None
        assert rec["ks_stat"] == pytest.approx(1.0, abs=1e-6)
        assert rec["p_value"] < 1e-3
        assert rec["class"] == "drift_major"

    def test_same_constant_distribution_ks_zero(self):
        ref = pd.Series([5.0] * 200)
        cur = pd.Series([5.0] * 200)
        rec = compute_feature_drift(ref, cur)
        assert rec is not None
        assert rec["ks_stat"] == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# 5. Empty current window => BLOCKED                                           #
# --------------------------------------------------------------------------- #
class TestBlockedPaths:

    def test_empty_current_returns_blocked_status(self):
        ref = pd.DataFrame({"f": np.random.default_rng(0).normal(0, 1, 200)})
        cur = pd.DataFrame({"f": []})
        report = run(
            feature_set="m2",
            reference_df=ref, current_df=cur, feature_cols=["f"],
        )
        assert report["status"] == "BLOCKED"
        assert "current" in report["blocked_reason"].lower()

    def test_empty_reference_returns_blocked_status(self):
        ref = pd.DataFrame({"f": []})
        cur = pd.DataFrame({"f": np.random.default_rng(0).normal(0, 1, 200)})
        report = run(
            feature_set="m2",
            reference_df=ref, current_df=cur, feature_cols=["f"],
        )
        assert report["status"] == "BLOCKED"
        assert "reference" in report["blocked_reason"].lower()

    def test_no_feature_columns_returns_blocked(self):
        ref = pd.DataFrame({"f": np.random.default_rng(0).normal(0, 1, 200)})
        cur = pd.DataFrame({"f": np.random.default_rng(1).normal(0, 1, 200)})
        report = run(
            feature_set="m2",
            reference_df=ref, current_df=cur, feature_cols=[],
        )
        assert report["status"] == "BLOCKED"


# --------------------------------------------------------------------------- #
# 6. Missing reference features => graceful skip                               #
# --------------------------------------------------------------------------- #
class TestMissingReferenceFeatures:

    def test_missing_in_reference_is_skipped_not_crashed(self):
        rng = _rng(0)
        ref = pd.DataFrame({"only_ref": rng.normal(0, 1, 200)})
        cur = pd.DataFrame({"only_cur": rng.normal(0, 1, 200)})
        # Ask the orchestrator for a column missing on both sides
        res = detect_drift(ref, cur, ["does_not_exist", "only_ref", "only_cur"])
        # Nothing is analyzed because no column is present in both frames.
        assert res["n_features_analyzed"] == 0
        assert res["features"] == []

    def test_one_shared_one_missing_only_shared_is_analyzed(self):
        rng = _rng(0)
        ref = pd.DataFrame({
            "shared": rng.normal(0, 1, 200),
            "ref_only": rng.normal(0, 1, 200),
        })
        cur = pd.DataFrame({
            "shared": rng.normal(0, 1, 200),
            "cur_only": rng.normal(0, 1, 200),
        })
        res = detect_drift(ref, cur, ["shared", "ref_only", "cur_only"])
        assert res["n_features_analyzed"] == 1
        assert res["features"][0]["feature"] == "shared"


# --------------------------------------------------------------------------- #
# 7. All-NaN features => skip                                                  #
# --------------------------------------------------------------------------- #
class TestAllNaNFeatures:

    def test_all_nan_feature_is_skipped(self):
        rng = _rng(0)
        ref = pd.DataFrame({"good": rng.normal(0, 1, 200),
                            "all_nan": [np.nan] * 200})
        cur = pd.DataFrame({"good": rng.normal(0, 1, 200),
                            "all_nan": [np.nan] * 200})
        res = detect_drift(ref, cur, ["good", "all_nan"])
        # all_nan should be silently dropped — good is the only one analyzed.
        names = [r["feature"] for r in res["features"]]
        assert "all_nan" not in names
        assert "good" in names

    def test_too_few_samples_after_dropna_is_skipped(self):
        ref = pd.DataFrame({"sparse": [1.0, 2.0, 3.0] + [np.nan] * 500})
        cur = pd.DataFrame({"sparse": [1.0, 2.0, 3.0] + [np.nan] * 500})
        rec = compute_feature_drift(ref["sparse"], cur["sparse"])
        assert rec is None


# --------------------------------------------------------------------------- #
# 8. Threshold tuning (--major-threshold)                                      #
# --------------------------------------------------------------------------- #
class TestThresholdTuning:

    def test_major_threshold_relaxation_demotes_to_minor(self):
        # mean_z is +1.5 — strict default (1.0) flags MAJOR.
        rng = _rng(0)
        ref = pd.DataFrame({"f": rng.normal(0.0, 1.0, 400)})
        cur = pd.DataFrame({"f": rng.normal(1.5, 1.0, 200)})

        strict = detect_drift(ref, cur, ["f"], major_z=1.0)
        assert strict["features"][0]["class"] == "drift_major"

        relaxed = detect_drift(
            ref, cur, ["f"],
            stable_p=1.01,   # disable p-value path
            minor_p=0.0,
            stable_z=0.5,
            major_z=3.0,     # very high threshold demotes mean-z to non-major
        )
        # With major_z bumped to 3.0 and p-paths disabled, abs(mean_z)~1.5
        # is no longer major; falls to drift_minor.
        assert relaxed["features"][0]["class"] == "drift_minor"

    def test_classify_helper_explicit_thresholds(self):
        # Below stable p AND small mean_z: stable.
        assert classify(0.8, 0.1, stable_p=0.05, minor_p=0.01,
                        stable_z=0.5, major_z=1.0) == "stable"
        # Large mean_z dominates regardless of p.
        assert classify(0.99, 2.5) == "drift_major"
        # Low p triggers major even with tiny mean_z.
        assert classify(0.001, 0.05) == "drift_major"
        # Mid-range: minor.
        assert classify(0.02, 0.7) == "drift_minor"


# --------------------------------------------------------------------------- #
# 9. select_current_window                                                     #
# --------------------------------------------------------------------------- #
class TestSelectCurrentWindow:

    def test_last_14_days_window(self):
        dates = pd.date_range("2026-01-01", periods=60, freq="D")
        df = pd.DataFrame({"game_date": dates, "x": range(60)})
        cur = select_current_window(df, current_days=14)
        # Anchor is the last date; 14 days back inclusive = 14 rows.
        assert len(cur) == 14
        assert cur["game_date"].max() == df["game_date"].max()

    def test_current_days_zero_returns_full_frame(self):
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        df = pd.DataFrame({"game_date": dates, "x": range(30)})
        cur = select_current_window(df, current_days=0)
        assert len(cur) == 30


# --------------------------------------------------------------------------- #
# 10. Operator dashboard hook degrades gracefully                              #
# --------------------------------------------------------------------------- #
class TestDashboardHook:

    def test_fetch_feature_drift_missing_cache_returns_dict(self, tmp_path):
        from scripts.operator_dashboard import fetch_feature_drift  # noqa: PLC0415
        missing = tmp_path / "no_such_file.json"
        d = fetch_feature_drift(cache_path=missing, live_run=False)
        assert isinstance(d, dict)
        assert d["ok"] is False
        # Section renderer should produce safe HTML, never raise.
        from scripts.operator_dashboard import _section_feature_drift  # noqa: PLC0415
        html = _section_feature_drift(d)
        assert "Feature Drift" in html
        assert "(no drift report cached" in html

    def test_fetch_feature_drift_reads_cached_report(self, tmp_path):
        from scripts.operator_dashboard import (  # noqa: PLC0415
            fetch_feature_drift, _section_feature_drift,
        )
        payload = {
            "ts": "2026-05-26T00:00:00Z",
            "feature_set": "m2",
            "status": "OK",
            "n_features_analyzed": 10,
            "n_stable": 4,
            "n_drift_minor": 3,
            "n_drift_major": 3,
            "features": [
                {"feature": "f1", "class": "drift_major",
                 "ks_stat": 0.5, "p_value": 1e-9, "mean_z": 2.1},
                {"feature": "f2", "class": "drift_major",
                 "ks_stat": 0.3, "p_value": 1e-4, "mean_z": -1.5},
            ],
        }
        cache = tmp_path / "drift.json"
        cache.write_text(json.dumps(payload), encoding="utf-8")
        d = fetch_feature_drift(cache_path=cache, live_run=False)
        assert d["ok"] is True
        assert d["n_drift_major"] == 3
        assert len(d["top_drifted"]) == 2
        assert d["top_drifted"][0]["feature"] == "f1"
        html = _section_feature_drift(d)
        assert "Feature Drift" in html
        assert "f1" in html and "f2" in html


# --------------------------------------------------------------------------- #
# 11. daily_workflow _step_feature_drift integration                           #
# --------------------------------------------------------------------------- #
class TestDailyWorkflowStep:

    def test_step_writes_report_and_no_alert_below_warn(self, tmp_path):
        from scripts.daily_workflow import _step_feature_drift  # noqa: PLC0415
        fake_report = {
            "ts": "t", "feature_set": "m2", "status": "OK",
            "n_features_analyzed": 50, "n_stable": 48,
            "n_drift_minor": 2, "n_drift_major": 0,
            "features": [],
        }
        called = []

        def fake_run(**kw):
            return fake_report

        def fake_alert(*a, **kw):
            called.append((a, kw))
            return {"discord_sent": False, "vault_appended": True}

        out_path = tmp_path / "drift.json"
        ok, details, err = _step_feature_drift(
            cache_path=out_path, feature_set="m2", current_days=14,
            warn_threshold=5, critical_threshold=15,
            dry_run=False, alert_fn=fake_alert, run_fn=fake_run,
        )
        assert ok is True
        assert err is None
        assert out_path.exists()
        # No alert fired (n_major=0 below warn threshold).
        assert details["alert"]["fired"] is False
        assert called == []

    def test_step_fires_warn_alert_above_warn_threshold(self, tmp_path):
        from scripts.daily_workflow import _step_feature_drift  # noqa: PLC0415
        feats = [{"feature": f"f{i}", "class": "drift_major",
                  "ks_stat": 0.4, "p_value": 1e-3, "mean_z": 1.5}
                 for i in range(8)]
        fake_report = {
            "ts": "t", "feature_set": "m2", "status": "OK",
            "n_features_analyzed": 20, "n_stable": 10,
            "n_drift_minor": 2, "n_drift_major": 8, "features": feats,
        }
        fired = []

        def fake_run(**kw):
            return fake_report

        def fake_alert(message, **kw):
            fired.append((message, kw))
            return {"discord_sent": False, "vault_appended": True}

        out_path = tmp_path / "drift.json"
        ok, details, err = _step_feature_drift(
            cache_path=out_path, feature_set="m2", current_days=14,
            warn_threshold=5, critical_threshold=15,
            dry_run=False, alert_fn=fake_alert, run_fn=fake_run,
        )
        assert ok and err is None
        assert details["alert"]["fired"] is True
        assert details["alert"]["level"] == "warn"
        assert len(fired) == 1

    def test_step_fires_critical_above_critical_threshold(self, tmp_path):
        from scripts.daily_workflow import _step_feature_drift  # noqa: PLC0415
        feats = [{"feature": f"f{i}", "class": "drift_major",
                  "ks_stat": 0.4, "p_value": 1e-9, "mean_z": 2.0}
                 for i in range(20)]
        fake_report = {
            "ts": "t", "feature_set": "m2", "status": "OK",
            "n_features_analyzed": 30, "n_stable": 5,
            "n_drift_minor": 5, "n_drift_major": 20, "features": feats,
        }
        fired = []

        def fake_run(**kw):
            return fake_report

        def fake_alert(message, **kw):
            fired.append((message, kw.get("level")))
            return {"discord_sent": False, "vault_appended": True}

        out_path = tmp_path / "drift.json"
        ok, details, err = _step_feature_drift(
            cache_path=out_path, feature_set="m2", current_days=14,
            warn_threshold=5, critical_threshold=15,
            dry_run=False, alert_fn=fake_alert, run_fn=fake_run,
        )
        assert ok and err is None
        assert details["alert"]["fired"] is True
        assert details["alert"]["level"] == "critical"
        assert fired[0][1] == "critical"

    def test_step_dry_run_does_not_invoke_detector(self, tmp_path):
        from scripts.daily_workflow import _step_feature_drift  # noqa: PLC0415
        invoked = []

        def fake_run(**kw):
            invoked.append(kw)
            return {}

        ok, details, err = _step_feature_drift(
            cache_path=tmp_path / "x.json", feature_set="m2",
            current_days=14, warn_threshold=5, critical_threshold=15,
            dry_run=True, alert_fn=None, run_fn=fake_run,
        )
        assert ok and err is None and invoked == []
        assert details["would_call"] == "feature_drift_detector.run"


# --------------------------------------------------------------------------- #
# 12. Pretty-printer doesn't crash on empty report                             #
# --------------------------------------------------------------------------- #
class TestFormatReport:

    def test_format_report_table_blocked(self):
        report = {
            "ts": "t", "feature_set": "m2", "status": "BLOCKED",
            "blocked_reason": "no data",
            "n_reference": 0, "n_current": 0, "current_window_days": 14,
            "n_features_analyzed": 0, "n_stable": 0,
            "n_drift_minor": 0, "n_drift_major": 0, "features": [],
        }
        text = format_report_table(report)
        assert "BLOCKED" in text
        assert "feature_set" not in text.lower() or "m2" in text
