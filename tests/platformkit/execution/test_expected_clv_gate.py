"""Per-file tests for scripts.platformkit.execution.expected_clv_gate.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/execution/test_expected_clv_gate.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution import expected_clv_gate as g


def test_devig_two_way_normalizes_to_one():
    fa, fb = g.devig_two_way(0.60, 0.45)
    assert abs(fa + fb - 1.0) < 1e-9
    assert 0.50 < fa < 0.60


def test_devig_two_way_degenerate_returns_neutral():
    assert g.devig_two_way(0.0, 0.5) == (0.5, 0.5)
    assert g.devig_two_way(0.5, 0.0) == (0.5, 0.5)


def test_expected_clv_pct_matches_formula():
    assert abs(g.expected_clv_pct(2.0, 0.55) - 10.0) < 1e-9
    assert abs(g.expected_clv_pct(1.5, 0.5) - (-25.0)) < 1e-9


def test_gate_passes_above_threshold():
    out = g.gate(taken_decimal=2.0, fair_prob=0.55, threshold_pct=1.0)
    assert out["passed"] is True
    assert abs(out["expected_clv_pct"] - 10.0) < 1e-9
    assert out["threshold_pct"] == 1.0


def test_gate_fails_below_threshold():
    out = g.gate(taken_decimal=1.90, fair_prob=0.50, threshold_pct=5.0)
    assert out["passed"] is False
    assert out["expected_clv_pct"] is not None


def test_gate_degenerate_inputs_fail_closed():
    for taken, fair in [(1.0, 0.55), (2.0, 0.0), (2.0, 1.0), (2.0, -0.1)]:
        out = g.gate(taken_decimal=taken, fair_prob=fair, threshold_pct=1.0)
        assert out["passed"] is False
        assert out["reason"] == "degenerate"
        assert out["expected_clv_pct"] is None


def test_gate_non_numeric_inputs_fail_closed_no_raise():
    out = g.gate(taken_decimal="bad", fair_prob=0.5, threshold_pct=1.0)
    assert out["passed"] is False
    assert out["reason"] == "degenerate"
