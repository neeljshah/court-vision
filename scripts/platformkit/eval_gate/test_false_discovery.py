"""Eval-gate rows obey the nightly R1 false-discovery schema."""
from __future__ import annotations

from scripts.platformkit.eval_gate.false_discovery import accounting_row


def test_eval_gate_accounting_uses_bonferroni_expectation():
    rows = [
        {"corpus": "a", "n": 200, "n_trials_this_sweep": 2,
         "bonferroni_eps": 0.025, "ship_eligible": False},
        {"corpus": "b", "n": 200, "n_trials_this_sweep": 2,
         "bonferroni_eps": 0.025, "ship_eligible": True},
        {"corpus": "skip", "n_trials_this_sweep": 2},
    ]
    row = accounting_row(rows)
    assert row["n_tested"] == 2
    assert row["families_touched"] == ["eval_gate"]
    assert row["expected_false_survivors"] == 0.05
    assert row["survivor_ids"] == ["b"]
    assert row["within_noise_floor"] is True
