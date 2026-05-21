"""Tests for src/prediction/model_explainer.py."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, Ridge

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.prediction.model_explainer import explain_model  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FEATURE_NAMES = [f"feat_{i}" for i in range(8)]
N_SAMPLES = 120


@pytest.fixture()
def clf_data():
    X, y = make_classification(
        n_samples=N_SAMPLES, n_features=8, n_informative=5,
        n_redundant=1, random_state=0,
    )
    return X.astype(float), y


@pytest.fixture()
def reg_data():
    X, y = make_regression(
        n_samples=N_SAMPLES, n_features=8, n_informative=5, random_state=0,
    )
    return X.astype(float), y


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_report_valid(report: dict, model_name: str) -> None:
    """Common assertions for any valid explainability report."""
    assert "importances" in report, "Report missing 'importances'"
    assert "prune_candidates" in report, "Report missing 'prune_candidates'"
    assert "method" in report, "Report missing 'method'"
    assert "model_name" in report

    imps = report["importances"]
    assert isinstance(imps, dict), "importances should be a dict"
    assert len(imps) == len(FEATURE_NAMES), (
        f"Expected {len(FEATURE_NAMES)} features, got {len(imps)}"
    )
    assert set(imps.keys()) == set(FEATURE_NAMES), "Feature name mismatch"
    for v in imps.values():
        assert isinstance(v, float), f"Importance value should be float, got {type(v)}"

    pc = report["prune_candidates"]
    assert isinstance(pc, list), "prune_candidates should be a list"
    for name in pc:
        assert name in imps, f"Prune candidate '{name}' not in importances"

    # JSON file must exist and be valid
    json_path = os.path.join("data", "models", f"{model_name}_shap_report.json")
    assert os.path.exists(json_path), f"Report file not found: {json_path}"
    with open(json_path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["importances"] == imps


# ---------------------------------------------------------------------------
# Tests — tree-based model (uses feature_importances_)
# ---------------------------------------------------------------------------

def test_random_forest_classifier(clf_data):
    X, y = clf_data
    model = RandomForestClassifier(n_estimators=20, random_state=0).fit(X, y)
    report = explain_model(model, X, FEATURE_NAMES, "test_rf_clf")
    _assert_report_valid(report, "test_rf_clf")
    assert report["method"] in ("shap", "tree_importances"), (
        f"Unexpected method for tree model: {report['method']}"
    )


def test_gradient_boosting_classifier(clf_data):
    X, y = clf_data
    model = GradientBoostingClassifier(n_estimators=20, random_state=0).fit(X, y)
    report = explain_model(model, X, FEATURE_NAMES, "test_gb_clf")
    _assert_report_valid(report, "test_gb_clf")


# ---------------------------------------------------------------------------
# Tests — linear model (uses coefficient magnitude)
# ---------------------------------------------------------------------------

def test_logistic_regression_classifier(clf_data):
    X, y = clf_data
    model = LogisticRegression(max_iter=500, random_state=0).fit(X, y)
    report = explain_model(model, X, FEATURE_NAMES, "test_lr_clf")
    _assert_report_valid(report, "test_lr_clf")


def test_ridge_regression(reg_data):
    X, y = reg_data
    model = Ridge(alpha=1.0).fit(X, y)
    report = explain_model(model, X, FEATURE_NAMES, "test_ridge_reg")
    _assert_report_valid(report, "test_ridge_reg")


# ---------------------------------------------------------------------------
# Test — prune_candidates are correct
# ---------------------------------------------------------------------------

def test_prune_threshold(clf_data):
    """With threshold=1.0 every feature should be a prune candidate."""
    X, y = clf_data
    model = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
    report = explain_model(
        model, X, FEATURE_NAMES, "test_prune_all", prune_threshold=1.0
    )
    assert set(report["prune_candidates"]) == set(FEATURE_NAMES), (
        "All features should be prune candidates with threshold=1.0"
    )


def test_prune_threshold_zero(clf_data):
    """With threshold=0 no feature should be a prune candidate."""
    X, y = clf_data
    model = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
    report = explain_model(
        model, X, FEATURE_NAMES, "test_prune_none", prune_threshold=0.0
    )
    assert report["prune_candidates"] == [], (
        "No features should be pruned when threshold=0"
    )


# ---------------------------------------------------------------------------
# Test — graceful behaviour regardless of shap availability
# ---------------------------------------------------------------------------

def test_no_crash_regardless_of_shap(clf_data, monkeypatch):
    """explain_model must not crash even if shap is forcibly removed."""
    import src.prediction.model_explainer as me
    orig = me._SHAP_AVAILABLE
    monkeypatch.setattr(me, "_SHAP_AVAILABLE", False)
    try:
        X, y = clf_data
        model = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
        report = explain_model(model, X, FEATURE_NAMES, "test_no_shap")
        _assert_report_valid(report, "test_no_shap")
        assert report["shap_available"] is False
    finally:
        monkeypatch.setattr(me, "_SHAP_AVAILABLE", orig)


# ---------------------------------------------------------------------------
# Test — mismatched feature_names raises ValueError
# ---------------------------------------------------------------------------

def test_feature_name_length_mismatch(clf_data):
    X, y = clf_data
    model = RandomForestClassifier(n_estimators=5, random_state=0).fit(X, y)
    with pytest.raises(ValueError, match="feature_names length"):
        explain_model(model, X, FEATURE_NAMES[:4], "test_bad_names")
