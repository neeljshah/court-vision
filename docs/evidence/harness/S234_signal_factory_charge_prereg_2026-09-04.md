# S234 Signal Factory Screen Charge Preregistration

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a13` on branch `track-a13` because
the required comparison is a deterministic CONSTRUCT fixture and the shared
counter module is human-gated. No production corpus, video, pod, data store,
register, feature flag, or real FWER ledger will be opened or changed.

## Inputs and premise

The direct source inputs are read one file at a time:

```text
scripts/platformkit/foundry/tiers.py, 11905 bytes, no resolution
scripts/platformkit/foundry/charge_path_followups.py, 4735 bytes, no resolution
scripts/platformkit/eval_gate/backtest_runner.py, 14510 bytes, no resolution
scripts/platformkit/eval_gate/cpcv_engine.py, 5341 bytes, no resolution
scripts/platformkit/combo/fwer_budget.py, 4411 bytes, no resolution
```

Before the construct, run the existing foundry tier test. Reproduce SF-1's
disjoint partition, off-side rejection, and required `screened_n`. Also survey
every `_charge_ledger` call site for a screen-derived increment. The expected
current source behavior is the literal `cumulative_k(prior, 1)` in
`backtest_runner.py`.

## Predeclared construct and comparison

Use exactly three isolated one-charge fixtures, with `screened_n` values 0, 1,
and 200. Each fixture begins from a new empty temporary JSONL path. The sole
headline comparison is `K_true` from `k_increment(screened_n, 1)` against
`K_currently_charged` from the unmodified `_charge_ledger` implementation.
The construct is exhaustive: no rows are excluded and no real family is used.

The shared evaluation rail will run `cpcv_evaluate` over eight synthetic,
timestamp-distinct, redacted states using `n_groups=4`, `n_test_groups=1`, and
`embargo_days=1`. That route applies its imported purge plus symmetric,
nonzero calendar-day embargo. It is an isolation check only, not a predictive
comparison; its records are archived with the construct results.

The scratch-only source copy changes `_charge_ledger` to accept
`k_increment: int = 1` and replaces its literal `1` in `cumulative_k` with
that parameter. The three fixtures must show the proposed copy matches
`K_true`; the zero-screen fixture must still advance by one.

## Immutable bar and reporting

The bar is exactly `k_increment(200, 1) == 200`; the zero-screen floor is
exactly one. No threshold is changed. The evidence will state the current and
proposed K values for all three construct fixtures, the shared evaluator
configuration, and the CLOSED AT LIMIT coupling if the gated shared counter
cannot receive the increment without an edit to `backtest_runner.py`.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Seal SHA-256 of the pre-seal content above: `CA1F27779B9B4A8EC918219ABCA7B4270258DD957F9B994E51E62D84091A8060`.
