"""
test_signals_judge.py -- adversarial correctness tests for signals/judge.py

Covers:
  - sign_sanity: correct/incorrect/undeclared combinations
  - engine_redundancy: owned-node collision, empirical corr, short-vector bypass
  - engine_redundancy: NaN in vectors -> false orthogonal (confirmed bug)
  - judge_signal: pass/reject paths
  - run_trust_gate: two known CAVEAT auto-rejections hold
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system"))


class TestSignSanity:
    def test_same_sign_ok(self):
        from signals.judge import sign_sanity
        ok, reason = sign_sanity(1, 1)
        assert ok
        ok, reason = sign_sanity(-1, -1)
        assert ok

    def test_conflicting_sign_fails(self):
        from signals.judge import sign_sanity
        ok, reason = sign_sanity(1, -1)
        assert not ok
        assert "confound" in reason.lower()

    def test_undeclared_declared_ok(self):
        from signals.judge import sign_sanity
        # declared=0 means undeclared -> no claim to violate
        ok, _ = sign_sanity(0, -1)
        assert ok

    def test_none_both_ok(self):
        from signals.judge import sign_sanity
        ok, reason = sign_sanity(None, None)
        assert ok
        assert "undeclared" in reason

    def test_non_numeric_strings_ok(self):
        """Non-numeric sign values -> both resolve to 0 -> no claim to violate."""
        from signals.judge import sign_sanity
        ok, _ = sign_sanity("positive", "negative")
        assert ok  # _sign() returns 0 for non-numeric -> undeclared


class TestEngineRedundancy:
    def test_owned_node_collision(self):
        from signals.judge import engine_redundancy
        ok, corr, reason = engine_redundancy("oreb", {"oreb", "pts", "ast"})
        assert not ok
        assert corr == 1.0
        assert "double-count" in reason

    def test_no_collision(self):
        from signals.judge import engine_redundancy
        ok, corr, reason = engine_redundancy("transition_ppp", {"oreb", "pts"})
        assert ok

    def test_empirical_corr_above_cap_rejects(self):
        from signals.judge import engine_redundancy
        rng = np.random.default_rng(0)
        a = rng.standard_normal(100)
        b = a + 0.01 * rng.standard_normal(100)  # |corr| ~= 1.0
        ok, corr, reason = engine_redundancy("qty", set(), signal_vec=a, engine_pred_vec=b)
        assert not ok
        assert corr > 0.92

    def test_empirical_corr_below_cap_passes(self):
        from signals.judge import engine_redundancy
        rng = np.random.default_rng(42)
        a = rng.standard_normal(100)
        b = rng.standard_normal(100)  # independent -> |corr| << 0.92
        ok, corr, _ = engine_redundancy("qty", set(), signal_vec=a, engine_pred_vec=b)
        assert ok
        assert corr < 0.92

    def test_short_vector_bypasses_corr_check(self):
        """CONFIRMED BUG: n < 20 skips the empirical corr check -> nearly identical vectors pass."""
        from signals.judge import engine_redundancy
        rng = np.random.default_rng(0)
        a = rng.standard_normal(10)
        b = a + 0.001 * rng.standard_normal(10)  # would have |corr| ~= 1.0 if checked
        ok, corr, reason = engine_redundancy("qty", set(), signal_vec=a, engine_pred_vec=b)
        assert ok, (
            "BUG CONFIRMED: short vector (n<20) bypasses corr check -> nearly identical "
            "vectors pass as orthogonal. Fix recipe: require n >= 20 OR log a warning and "
            "mark as 'insufficient-data' rather than 'orthogonal'."
        )
        assert corr == 0.0, "returned corr is 0.0 (not computed)"

    def test_nan_in_vector_false_orthogonal(self):
        """CONFIRMED BUG: NaN in signal_vec -> corrcoef returns NaN -> abs(NaN) > cap is False -> ok=True."""
        from signals.judge import engine_redundancy
        a_nan = np.array([1.0, 2.0, float("nan"), 4.0] * 10)
        b = np.array([1.1, 2.1, 3.1, 4.1] * 10)
        ok, corr, reason = engine_redundancy("qty", set(), signal_vec=a_nan, engine_pred_vec=b)
        assert ok, (
            "BUG CONFIRMED: NaN in signal_vec causes corrcoef to return NaN. "
            "abs(NaN) > 0.92 evaluates to False so the check passes as orthogonal. "
            "Fix recipe: add np.isnan(c) guard -> return (False, 0.0, 'nan-corr: inconclusive') "
            "or mask out NaN rows before computing corrcoef."
        )
        # The corr is nan -- document this
        assert np.isnan(corr), "returned corr is NaN (a detectable sentinel)"


class TestJudgeSignal:
    def test_pass_path(self):
        from signals.judge import judge_signal
        row = {"declared_sign": 1, "measured_sign": 1, "quantity": "transition_ppp",
               "legacy_name": "test", "signal_id": "sig_test"}
        result = judge_signal(row, owned={"pts", "ast"})
        assert result["verdict"] == "pass"
        assert result["sign_ok"]
        assert result["engine_ortho_ok"]

    def test_sign_confound_reject(self):
        from signals.judge import judge_signal
        row = {"declared_sign": 1, "measured_sign": -1, "quantity": "test_qty",
               "legacy_name": "test", "signal_id": "sig_test"}
        result = judge_signal(row, owned=set())
        assert result["verdict"] == "reject"
        assert not result["sign_ok"]

    def test_engine_redundant_reject(self):
        from signals.judge import judge_signal
        row = {"declared_sign": 1, "measured_sign": 1, "quantity": "pts",
               "legacy_name": "test", "signal_id": "sig_test"}
        result = judge_signal(row, owned={"pts"})
        assert result["verdict"] == "reject"
        assert not result["engine_ortho_ok"]

    def test_both_fail(self):
        from signals.judge import judge_signal
        row = {"declared_sign": 1, "measured_sign": -1, "quantity": "pts",
               "legacy_name": "test", "signal_id": "sig_test"}
        result = judge_signal(row, owned={"pts"})
        assert result["verdict"] == "reject"
        assert len(result["reasons"]) == 2  # both sign + engine reasons


class TestTrustGate:
    def test_trust_gate_passes(self):
        """INVARIANT: the 2 known CAVEAT auto-rejections must hold on the live registry."""
        try:
            from signals.judge import run_trust_gate
            rep = run_trust_gate()
        except Exception as e:
            pytest.skip(f"Live registry not populated: {e}")

        assert rep["reb_rejected_by_sign"], (
            "opp_position_defense_reb must be auto-rejected by sign_sanity "
            "(declared +1, measured -1 = backward causal signal)"
        )
        assert rep["oreb_rejected_by_engine"], (
            "oreb_matchup must be auto-rejected by engine_redundancy "
            "(quantity 'oreb' is owned by four_factors engine)"
        )
        assert rep["false_rejects"] == [], (
            f"Validated signals must not be false-rejected: {rep['false_rejects']}"
        )
        assert rep["reproduced_both"], "TRUST GATE must PASS"
