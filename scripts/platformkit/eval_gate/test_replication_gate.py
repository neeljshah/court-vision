"""Per-file test for the replication gate (S08). ASCII; stdlib + pytest.

The BAR is the two constructed verdicts at the SAME K (only n_corpora differs, so the
downgrade cannot be an artifact of a moved K). Cases (c) and (d) are invariance checks:
the rule must not touch a non-AHEAD verdict, and `verdict_of` must keep returning
exactly what master returns.

Run: python -m pytest scripts/platformkit/eval_gate/test_replication_gate.py -q
"""
from __future__ import annotations

from scripts.platformkit import hedge_trial_runner as R
from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.eval_gate.replication_gate import (
    replication_fields,
    replication_verdict,
)

K = 14  # last k_cumulative in data/cache/eval_gate/backtest_fwer.jsonl (read, never appended)


def test_a_ahead_single_corpus_downgrades():
    assert min_corpora_eff(1, K) == 2  # the floor in force at today's K
    assert replication_verdict("AHEAD", 1, K) == "SINGLE-WINDOW"


def test_b_ahead_two_corpora_same_k_unchanged():
    assert replication_verdict("AHEAD", 2, K) == "AHEAD"


def test_c_non_ahead_verdicts_pass_through_byte_identical():
    for verdict in ("BEHIND", "MATCH", "NULL", "INSUFFICIENT", "REJECT", "PAR"):
        assert replication_verdict(verdict, 1, K) == verdict


def test_d_verdict_of_unchanged_from_master():
    base = {"improvement_vs_raw": 0.0041, "dm_ci95_improvement": [0.0002, 0.009],
            "deflated_p": 0.01, "k_cumulative": K}
    assert R.verdict_of(base) == "AHEAD"
    assert R.verdict_of({**base, "improvement_vs_raw": 0.0039}) == "BEHIND"
    assert R.verdict_of({**base, "dm_ci95_improvement": [-0.001, 0.009]}) == "BEHIND"
    assert R.verdict_of({**base, "deflated_p": 0.05}) == "BEHIND"
    # the additive wrapper downgrades the same stats without mutating verdict_of
    assert R.verdict_of_replicated(base, 1) == "SINGLE-WINDOW"
    assert R.verdict_of_replicated(base, 2) == "AHEAD"
    assert R.verdict_of(base) == "AHEAD"


def test_prefixed_ahead_and_fields():
    assert replication_verdict("e4_AHEAD", 1, K) == "SINGLE-WINDOW"
    assert replication_fields("AHEAD", 1, K) == {
        "verdict_replicated": "SINGLE-WINDOW", "min_corpora_eff": 2,
        "n_corpora": 1, "k_cumulative": K}
