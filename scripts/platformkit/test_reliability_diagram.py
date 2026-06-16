"""Per-file test for reliability_diagram.py.

Run with:
  python -m pytest scripts/platformkit/test_reliability_diagram.py -q
"""
from __future__ import annotations

import numpy as np
import pytest


def _import():
    from scripts.platformkit import reliability_diagram as rd
    return rd


def test_compute_diagram_perfect_calibration():
    rd = _import()
    # Perfectly calibrated: uniform probs, outcomes = bernoulli draws with matching rate.
    rng = np.random.default_rng(42)
    probs = np.linspace(0.05, 0.95, 200)
    outcomes = rng.binomial(1, probs).astype(float)
    diag = rd.compute_diagram(probs, outcomes, bins=10)
    assert diag["n_total"] == 200
    assert len(diag["bin_centers"]) == 10
    assert len(diag["n_per_bin"]) == 10
    assert len(diag["sparse_flags"]) == 10
    assert 0.0 <= diag["ece"] <= 1.0
    assert diag["sharpness"] > 0.0


def test_compute_diagram_sparse_flag():
    rd = _import()
    # Only 5 predictions, all in one bin -> that bin must be sparse.
    probs = np.array([0.05, 0.06, 0.07, 0.08, 0.09])
    outcomes = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
    diag = rd.compute_diagram(probs, outcomes, bins=10)
    # First bin (0.0-0.1) should contain all 5 and be flagged sparse.
    assert diag["sparse_flags"][0] is True
    # All other bins empty (also sparse/flagged) - check n_per_bin
    assert sum(diag["n_per_bin"]) == 5


def test_compute_diagram_empty_bins():
    rd = _import()
    # All probs near 0.5 -> only middle bin populated.
    probs = np.full(100, 0.5)
    outcomes = np.random.default_rng(0).binomial(1, 0.5, 100).astype(float)
    diag = rd.compute_diagram(probs, outcomes, bins=10)
    empty = [n == 0 for n in diag["n_per_bin"]]
    assert any(empty), "Some bins should be empty when all probs are at 0.5"


def test_format_ascii_no_edge_language():
    rd = _import()
    diag = rd.compute_diagram(np.array([0.3, 0.5, 0.7]), np.array([0.0, 1.0, 1.0]))
    text = rd.format_ascii(diag, title="Test", verdict="MATCHES_CLOSE -- no edge / MARKET-EFFICIENT HERE")
    # Must contain honesty note.
    assert "calibration" in text.lower()
    assert "edge" in text.lower()
    assert "MARKET-EFFICIENT" in text


def test_format_ascii_brier_fields():
    rd = _import()
    diag = rd.compute_diagram(np.full(50, 0.5), np.random.default_rng(1).binomial(1, 0.5, 50).astype(float))
    text = rd.format_ascii(diag, brier=0.2108, brier_close=0.1980,
                           verdict="BEHIND -- market efficient",
                           source_badge="model-in-corpus vs devigged-market")
    assert "0.2108" in text
    assert "0.1980" in text
    assert "devigged" in text


def test_main_ledger_missing(tmp_path, monkeypatch):
    """When the fixture is absent, main returns 1 gracefully."""
    rd = _import()
    monkeypatch.setattr(rd, "_LEDGER_FIXTURE", tmp_path / "nonexistent.csv")
    rc = rd.run_ledger()
    assert rc == 1


def test_main_golden_missing(tmp_path, monkeypatch):
    rd = _import()
    monkeypatch.setattr(rd, "_GOLDEN_FIXTURE", tmp_path / "nonexistent.json")
    rc = rd.run_golden()
    assert rc == 1
