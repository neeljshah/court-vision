"""Eval-gate rows obey the nightly R1 false-discovery schema."""
from __future__ import annotations

from scripts.platformkit.eval_gate.false_discovery import (
    MIN_SURVIVORS_ALLOWED, accounting_row,
)


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
    # S40b / RT-21(a): `assert within_noise_floor is True` was tautological -- it PINNED
    # the ceil() hole (expectation 0.05, one survivor) as correct behaviour. Assert the
    # rule instead, derived here: allowed = max(MIN_SURVIVORS_ALLOWED, int(expected)).
    allowed = max(MIN_SURVIVORS_ALLOWED, int(row["expected_false_survivors"]))
    assert row["min_survivors_allowed"] == allowed
    assert row["within_noise_floor"] == (row["observed_survivors"] <= allowed)


def test_s40b_rt5_two_survivors_against_a_sub_one_expectation_is_not_within_the_floor():
    """RT-5: `len(survivors) <= math.ceil(expected)` made ONE survivor always 'within the
    noise floor' -- ceil of any expectation in (0,1] is 1. Measured before the fix: 85 rows,
    expected_false_survivors=0.050000, observed=1, within_noise_floor=True, with no field
    saying WHY 1 was allowed. The allowance is now the named MIN_SURVIVORS_ALLOWED."""
    from scripts.platformkit.eval_gate.false_discovery import MIN_SURVIVORS_ALLOWED

    def sweep(n_survivors: int) -> dict:
        return accounting_row([
            {"corpus": "c%d" % i, "n": 200, "n_trials_this_sweep": 85,
             "bonferroni_eps": 0.05 / 85, "ship_eligible": i < n_survivors}
            for i in range(85)
        ])

    one, two = sweep(1), sweep(2)
    # expectation stays well below 1 in both sweeps -- independently: 85 * 0.05/85 == 0.05.
    assert one["expected_false_survivors"] == 0.05 == two["expected_false_survivors"]
    assert one["min_survivors_allowed"] == MIN_SURVIVORS_ALLOWED == 1
    assert one["within_noise_floor"] is True     # the named, documented allowance
    assert two["within_noise_floor"] is False    # what ceil() used to hide is now visible


def test_s40b_rt5_rows_the_key_filter_drops_are_counted_not_silently_skipped():
    """A row missing `n` left n_tested AND survivor_ids without appearing anywhere."""
    row = accounting_row([
        {"corpus": "a", "n": 200, "n_trials_this_sweep": 2, "bonferroni_eps": 0.025},
        {"corpus": "skip", "n_trials_this_sweep": 2, "ship_eligible": True},
        {"corpus": "skip2"},
    ])
    assert row["n_tested"] == 1
    assert row["n_unscorable"] == 2              # 3 rows in, 1 scored -- denominator is honest
    assert row["survivor_ids"] == []
