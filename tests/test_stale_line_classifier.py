"""
tests/test_stale_line_classifier.py

Tests for StaleLineClassifier. No real model file dependency — monkeypatching
ensures all disk I/O goes to tmp_path.
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np
import pytest

import src.data.stale_line_classifier as slc_module
from src.data.stale_line_classifier import (
    FEATURES,
    StaleLineClassifier,
    train_from_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_records(n: int = 600, seed: int = 0) -> list:
    """
    Generate synthetic labeled records with a STRONG learnable signal.

    Signal design
    -------------
    score = 0.05 * time_since_move - 1.2 * news_in_window - 0.9 * lineup_status
            + N(0, 0.5)
    is_stale = 1 if score > median(score), else 0

    This creates a roughly 50/50 split driven by the features, giving
    LogisticRegression a very clear gradient to follow.
    """
    rng = np.random.default_rng(seed)

    time_since_move = rng.uniform(0, 120, n)           # 0–120 minutes
    news_in_window  = rng.poisson(lam=1.5, size=n).astype(float)
    lineup_status   = rng.integers(0, 3, size=n).astype(float)  # 0, 1, 2

    noise  = rng.normal(0, 0.5, n)
    score  = (
        0.05 * time_since_move
        - 1.2 * news_in_window
        - 0.9 * lineup_status
        + noise
    )
    # Label at median to guarantee ~50% positives (maximises signal)
    threshold = np.median(score)
    is_stale = (score > threshold).astype(int)

    records = []
    for i in range(n):
        records.append({
            "time_since_move": float(time_since_move[i]),
            "news_in_window":  float(news_in_window[i]),
            "lineup_status":   float(lineup_status[i]),
            "is_stale":        int(is_stale[i]),
        })
    return records


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fit_predict_synthetic():
    """LogisticRegression on strong synthetic signal should comfortably clear F1 > 0.6."""
    records = _make_records(n=600, seed=42)
    result = train_from_records(records)
    f1 = result["holdout"]["f1"]
    assert f1 > 0.6, f"Expected holdout F1 > 0.6, got {f1:.4f}"


def test_predict_proba_range(tmp_path, monkeypatch):
    """predict_proba must return a float in [0.0, 1.0]."""
    model_path = str(tmp_path / "stale_line_classifier.pkl")
    monkeypatch.setattr(slc_module, "_MODEL_PATH", model_path)

    records = _make_records(n=120, seed=7)
    clf = StaleLineClassifier()
    clf.fit([{f: r[f] for f in FEATURES} for r in records],
            [r["is_stale"] for r in records])

    sample = {f: records[0][f] for f in FEATURES}
    prob = clf.predict_proba(sample)
    assert isinstance(prob, float), "predict_proba must return a float"
    assert 0.0 <= prob <= 1.0, f"Probability out of range: {prob}"


def test_unfitted_fallback(tmp_path, monkeypatch):
    """An unfitted classifier must return exactly 0.5."""
    nonexistent = str(tmp_path / "does_not_exist.pkl")
    monkeypatch.setattr(slc_module, "_MODEL_PATH", nonexistent)

    clf = StaleLineClassifier()
    sample = {"time_since_move": 30.0, "news_in_window": 1.0, "lineup_status": 0.0}
    assert clf.predict_proba(sample) == 0.5


def test_persistence(tmp_path, monkeypatch):
    """
    After fitting, the pkl file must exist and a freshly loaded classifier
    must reproduce the same predict_proba (within floating-point epsilon).
    """
    model_path = str(tmp_path / "stale_line_classifier.pkl")
    monkeypatch.setattr(slc_module, "_MODEL_PATH", model_path)

    records = _make_records(n=200, seed=99)
    clf1 = StaleLineClassifier()
    clf1.fit([{f: r[f] for f in FEATURES} for r in records],
             [r["is_stale"] for r in records])

    assert os.path.exists(model_path), "Model file was not written to disk"

    # New instance — should load from the file written above
    clf2 = StaleLineClassifier()
    sample = {f: records[5][f] for f in FEATURES}

    p1 = clf1.predict_proba(sample)
    p2 = clf2.predict_proba(sample)
    assert abs(p1 - p2) < 1e-9, f"Loaded model diverges: {p1} vs {p2}"
