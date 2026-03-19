"""
Tests for src/analytics/prop_correlation.py — Prop correlation matrices.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.analytics.prop_correlation import get_correlation_penalty, _pearsonr


# ── _pearsonr ────────────────────────────────────────────────────────────────

class TestPearsonr:
    def test_perfect_positive_correlation(self):
        x = list(range(1, 20))
        y = [v * 2 for v in x]
        r = _pearsonr(x, y)
        assert abs(r - 1.0) < 0.001

    def test_perfect_negative_correlation(self):
        x = list(range(1, 20))
        y = [-v for v in x]
        r = _pearsonr(x, y)
        assert abs(r + 1.0) < 0.001

    def test_insufficient_data_returns_zero(self):
        # Less than 10 points
        x = [1, 2, 3]
        y = [2, 4, 6]
        assert _pearsonr(x, y) == 0.0

    def test_result_in_range(self):
        import random
        random.seed(42)
        x = [random.random() for _ in range(30)]
        y = [random.random() for _ in range(30)]
        r = _pearsonr(x, y)
        assert -1.0 <= r <= 1.0


# ── get_correlation_penalty ──────────────────────────────────────────────────

class TestGetCorrelationPenalty:
    def test_returns_float(self):
        result = get_correlation_penalty(203999, 201939)
        assert isinstance(result, float)

    def test_result_in_range(self):
        result = get_correlation_penalty(203999, 201939)
        assert -1.0 <= result <= 1.0

    def test_missing_cache_returns_zero(self, monkeypatch, tmp_path):
        """Returns 0.0 when lineup_correlations.json doesn't exist."""
        import src.analytics.prop_correlation as corr_mod
        # Point to nonexistent file via monkeypatching _NBA_CACHE
        monkeypatch.setattr(corr_mod, "_NBA_CACHE", str(tmp_path))
        result = corr_mod.get_correlation_penalty(203999, 201939)
        assert result == 0.0

    def test_unknown_player_pair_returns_zero(self):
        # Nonsense IDs should return 0.0 gracefully
        result = get_correlation_penalty(999999998, 999999999)
        assert result == 0.0


# ── Cache files integration ──────────────────────────────────────────────────

class TestCorrelationCaches:
    def test_prop_correlations_file_exists(self):
        path = os.path.join(PROJECT_DIR, "data", "nba", "prop_correlations.json")
        if not os.path.exists(path):
            pytest.skip("prop_correlations.json not built yet")
        d = json.load(open(path))
        assert len(d) > 50
        # Check keys
        pid = list(d.keys())[0]
        assert "pts_reb_r" in d[pid]
        assert "pts_ast_r" in d[pid]
        assert "reb_ast_r" in d[pid]
        assert "n_games" in d[pid]

    def test_lineup_correlations_file_exists(self):
        path = os.path.join(PROJECT_DIR, "data", "nba", "lineup_correlations.json")
        if not os.path.exists(path):
            pytest.skip("lineup_correlations.json not built yet")
        d = json.load(open(path))
        assert len(d) > 0
        # At least some teams should have pairs
        total_pairs = sum(len(v) for v in d.values())
        assert total_pairs > 100

    def test_all_correlation_values_in_range(self):
        path = os.path.join(PROJECT_DIR, "data", "nba", "prop_correlations.json")
        if not os.path.exists(path):
            pytest.skip("prop_correlations.json not built yet")
        d = json.load(open(path))
        for pid, feats in d.items():
            for key in ("pts_reb_r", "pts_ast_r", "reb_ast_r"):
                val = feats[key]
                assert -1.0 <= val <= 1.0, f"{key} OOB for {pid}: {val}"
