"""
test_signals_gates.py -- adversarial correctness tests for signals/gates.py

Covers:
  - BH/BY correctness (planted null, edge cases)
  - family_seen anti-re-roll
  - gate_a_batch carry-forward (confirmed pessimism: strong candidate locked by weak prior)
  - gate_a_batch fresh vs carried p
  - log_tests append-only (duplicate accumulation documented bug)
  - NaN p-value handling in BH/BY
  - gate_a_batch with empty candidates
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "team_system"))


@pytest.fixture
def isolated_gates(tmp_path, monkeypatch):
    """Patch TEST_LOG_DIR and REGISTRY_DIR to tmp_path for isolated gate tests."""
    import scripts.team_system.registry.store as store_mod
    import scripts.team_system.signals.gates as gates_mod
    monkeypatch.setattr(store_mod, "REGISTRY_DIR", str(tmp_path))
    monkeypatch.setattr(store_mod, "_LOCK", str(tmp_path / ".lock"))
    monkeypatch.setattr(gates_mod, "TEST_LOG_DIR", str(tmp_path / "signal_test_log"))
    return gates_mod


# ---------------------------------------------------------------------------
# BH / BY correctness
# ---------------------------------------------------------------------------

class TestBHCorrectness:
    def test_empty(self):
        from signals.gates import benjamini_hochberg, benjamini_yekutieli
        assert len(benjamini_hochberg([])) == 0
        assert len(benjamini_yekutieli([])) == 0

    def test_all_zeros_all_discover(self):
        from signals.gates import benjamini_hochberg
        mask = benjamini_hochberg([0.0, 0.0, 0.0])
        assert mask.all()

    def test_single_below_alpha_discovers(self):
        from signals.gates import benjamini_hochberg
        assert benjamini_hochberg([0.01])[0]

    def test_single_above_alpha_rejects(self):
        from signals.gates import benjamini_hochberg
        assert not benjamini_hochberg([0.06])[0]

    def test_nan_treated_as_nonsignificant(self):
        """NaN p-values are sorted last by argsort -> never a discovery."""
        from signals.gates import benjamini_hochberg
        mask = benjamini_hochberg([float("nan"), 0.001, 0.05])
        assert not mask[0], "NaN should never be a discovery"
        assert mask[1], "p=0.001 should be discovered"

    def test_by_more_conservative_than_bh(self):
        """BY applies c(m) correction, so it discovers fewer signals than BH."""
        from signals.gates import benjamini_hochberg, benjamini_yekutieli
        pvals = [0.001, 0.01, 0.02, 0.05, 0.1, 0.2]
        bh_count = int(benjamini_hochberg(pvals).sum())
        by_count = int(benjamini_yekutieli(pvals).sum())
        assert by_count <= bh_count

    def test_planted_null_bh_controls_fwer(self):
        from signals.gates import planted_null_test
        res = planted_null_test(procedure="bh", batches=100, seed=7)
        assert res["planted_null_ok"], res["detail"]

    def test_planted_null_by_controls_fwer(self):
        from signals.gates import planted_null_test
        res = planted_null_test(procedure="by", batches=100, seed=7)
        assert res["planted_null_ok"], res["detail"]


# ---------------------------------------------------------------------------
# family_seen anti-re-roll
# ---------------------------------------------------------------------------

class TestFamilySeen:
    def test_fresh_family_not_seen(self, isolated_gates):
        gates = isolated_gates
        assert not gates.family_seen("fam_totally_new_xyz")

    def test_seen_after_gate_a_batch(self, isolated_gates):
        gates = isolated_gates
        candidates = [{"hash": "h1", "family_key": "fam_abc", "definition": "d1", "p": 0.001}]
        gates.gate_a_batch(candidates, batch_id="b1")
        assert gates.family_seen("fam_abc")

    def test_re_roll_same_family_carries_prior(self, isolated_gates):
        """Anti-re-roll: a second batch with same family_key carries the prior p (never fresh)."""
        gates = isolated_gates
        # First: weak candidate (fails)
        c1 = [{"hash": "h1", "family_key": "fam_test", "definition": "weak", "p": 0.80}]
        r1 = gates.gate_a_batch(c1, batch_id="b1")
        assert r1["n_survivors"] == 0

        # Second: strong candidate in same family -- carries weak prior (p=0.80 -> fails)
        c2 = [{"hash": "h2", "family_key": "fam_test", "definition": "strong", "p": 0.0001}]
        r2 = gates.gate_a_batch(c2, batch_id="b2")
        assert r2["n_survivors"] == 0, (
            "Anti-re-roll: strong candidate in the same family cannot escape the weak prior p. "
            "This is intentional pessimism to prevent cherry-picking within a family."
        )

    def test_carry_forward_uses_min_prior_p(self, isolated_gates):
        """Carry-forward p = min of ALL prior p values for that family (documented behavior)."""
        gates = isolated_gates
        # First: borderline candidate (p=0.04, barely significant)
        c1 = [{"hash": "h1", "family_key": "fam_min", "definition": "borderline", "p": 0.04}]
        r1 = gates.gate_a_batch(c1, batch_id="b1")
        # Whether it survives depends on m=1 threshold: 0.04 <= 0.05/1 = 0.05 -> True
        assert r1["n_survivors"] == 1

        # Second: weak candidate in same family -- carries min(0.04) which still passes
        c2 = [{"hash": "h2", "family_key": "fam_min", "definition": "weak", "p": 0.80}]
        r2 = gates.gate_a_batch(c2, batch_id="b2")
        # carried p = min(0.04, 0.04) = 0.04; in batch of 1: thresh = 0.05 -> 0.04 < 0.05 -> passes
        assert r2["n_survivors"] == 1, (
            "Carry-forward uses min prior, which here is 0.04 (the first good test). "
            "So the second (weak) candidate also passes because it inherits the strong prior."
        )


# ---------------------------------------------------------------------------
# gate_a_batch basic behavior
# ---------------------------------------------------------------------------

class TestGateABatch:
    def test_empty_batch(self, isolated_gates):
        gates = isolated_gates
        r = gates.gate_a_batch([], batch_id="empty")
        assert r["n"] == 0
        assert r["n_survivors"] == 0
        assert r["survivors"] == []

    def test_strong_signal_survives(self, isolated_gates):
        gates = isolated_gates
        c = [{"hash": "h1", "family_key": "fam_strong", "definition": "d", "p": 0.001}]
        r = gates.gate_a_batch(c, batch_id="b")
        assert r["n_survivors"] == 1
        assert r["survivors"][0]["hash"] == "h1"

    def test_weak_signal_rejected(self, isolated_gates):
        gates = isolated_gates
        c = [{"hash": "h1", "family_key": "fam_weak", "definition": "d", "p": 0.50}]
        r = gates.gate_a_batch(c)
        assert r["n_survivors"] == 0

    def test_log_written_for_both_pass_and_fail(self, isolated_gates):
        gates = isolated_gates
        c = [
            {"hash": "h_pass", "family_key": "fam_pass", "definition": "d1", "p": 0.001},
            {"hash": "h_fail", "family_key": "fam_fail", "definition": "d2", "p": 0.50},
        ]
        gates.gate_a_batch(c, batch_id="b1")
        log = gates.test_log()
        assert len(log) == 2
        verdicts = dict(zip(log["hash"], log["verdict"]))
        assert verdicts["h_pass"] == "survived"
        assert verdicts["h_fail"] == "rejected"

    def test_procedure_bh_vs_by(self, isolated_gates):
        """BY is more conservative, so it may reject signals BH would pass."""
        gates = isolated_gates
        # 10 signals, one strong, rest weak -- BH may pass the strong, BY definitely does
        pvals = [0.001] + [0.4] * 9
        c = [{"hash": f"h{i}", "family_key": f"fam_{i}", "definition": "d", "p": p}
             for i, p in enumerate(pvals)]
        r_bh = gates.gate_a_batch(c, procedure="bh", batch_id="bh_batch")
        r_by = gates.gate_a_batch([dict(x) for x in c], procedure="by", batch_id="by_batch")
        assert r_by["n_survivors"] <= r_bh["n_survivors"]


# ---------------------------------------------------------------------------
# log_tests duplicate accumulation (documented)
# ---------------------------------------------------------------------------

class TestLogTestsDedup:
    def test_duplicate_append_accumulates(self, isolated_gates):
        """DOCUMENTED BEHAVIOR: log_tests has no dedup, same rows can accumulate."""
        gates = isolated_gates
        import time
        rows = [{"hash": "h1", "family_key": "fam_dup", "definition": "d",
                 "p": 0.01, "batch_id": "b1", "asof": "2026-01-01", "verdict": "survived"}]
        gates.log_tests(rows)
        gates.log_tests(rows)  # same batch
        log = gates.test_log()
        assert len(log) == 2, (
            "DOCUMENTED BUG: log_tests does not dedup. Same rows appended twice => 2 entries. "
            "Impact: carry-forward p is still correct (min unchanged), but log grows. "
            "Fix recipe: add hash-based dedup in log_tests or in test_log() concat."
        )

    def test_carry_forward_p_unaffected_by_dups(self, isolated_gates):
        """Despite duplicate rows, carry-forward p = min(p) is still correct."""
        gates = isolated_gates
        import time
        rows = [{"hash": "h1", "family_key": "fam_dup2", "definition": "d",
                 "p": 0.01, "batch_id": "b1", "asof": "2026-01-01", "verdict": "survived"}]
        gates.log_tests(rows)
        gates.log_tests(rows)
        # Now gate_a_batch with same family: carried p should be 0.01 (min, even with dups)
        c = [{"hash": "h_new", "family_key": "fam_dup2", "definition": "new", "p": 0.50}]
        r = gates.gate_a_batch(c, batch_id="b2")
        # carried p = min(0.01, 0.01) = 0.01; batch of 1: threshold = 0.05; 0.01 < 0.05 -> passes
        assert r["n_survivors"] == 1, "dups don't corrupt the carry-forward p"
