# S234 Signal Factory Screen Charge Evidence

## Verdict

CLOSED AT LIMIT for direct application. The required shared-counter change is
outside this lane's permitted edit surface. The additive helper, isolated
construct test, fixture JSON, and proposed diff are committed so a
human-gated follow-up can apply the exact reviewed edit.

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a13` on branch `track-a13`. This
uses only source files and deterministic temporary fixture paths. No data
store, video, pod, register, feature flag, or real FWER ledger was opened or
changed.

## Preregistration

The comparison was preregistered and sealed before the first construct metric:

```text
docs/evidence/harness/S234_signal_factory_charge_prereg_2026-09-04.md
CA1F27779B9B4A8EC918219ABCA7B4270258DD957F9B994E51E62D84091A8060
```

The seal is SHA-256 over the preregistration's pre-seal bytes. Its listed
source byte sizes were corrected at measurement time below; that descriptor
correction does not alter the preregistered construct, evaluator, or bar.

## Source identity

Each source was opened separately. Resolution is not applicable.

| Source | Bytes | SHA-256 |
|---|---:|---|
| `scripts/platformkit/foundry/tiers.py` | 13431 | `86E2415208C6CF0B99809E7A7AC9467E47CC2A295FD697FBA8B5BDACA12BF481` |
| `scripts/platformkit/foundry/charge_path_followups.py` | 4995 | `E49F2770E11D64F2B8914DD33FC6772CFC8115E5F9D8EAB4007593CF4EE01911` |
| `scripts/platformkit/eval_gate/backtest_runner.py` | 16320 | `3B904B3D75437A8A21D98D380578C9BC395DF94BC6174D8BEFEFA672AF4E4C31` |
| `scripts/platformkit/eval_gate/cpcv_engine.py` | 7030 | `6F622DC107B432DF0BDC1F4700E44D900DE5C5ADAAD9657E15A22C579269C6E6` |
| `scripts/platformkit/combo/fwer_budget.py` | 8726 | `073F81443820CE36741EF815B4F79B90FDAE5C6464FEFDEBF00B165977E6DD9F` |
| `scripts/platformkit/foundry/screen_charge.py` | 983 | `F1F1D6591087BE8B8A5F0B139F584AA8ABF7845F06DCF9841AB14D0A05300623` |
| `tests/platformkit/foundry/test_screen_charge.py` | 3170 | `F253F363769CB9278CF87C910B8196FE2C82722C0E5A5536AC126A5A1136CBDC` |

## Premise reproduction

`python -m pytest tests/platformkit/foundry/test_tiers.py -q` reported
`12 passed in 3.62s`. That file exercises SF-1's disjoint partition, the
`ScreenPartitionLeak` rejection for an off-side verdict row, and the required
`screened_n` rejection on a charged tier.

The complete `_charge_ledger` call-site survey found the production callers in
`hedge_trial_runner.py`, `backtest_runner.py`, the three S58 trial modules,
`stacker.py`, `student_gate.py`, and `foundry/tiers.py`, plus their test
callers. None can supply a screen-derived increment: the shared function's
keyword-only signature does not accept one. Its one global-K write is
`cumulative_k(prior, 1)` at `backtest_runner.py:192`. In particular,
`foundry/tiers.py:144-146` forwards metadata only; `screened_n` terminates at
the required evidence field in `charge_path_followups.py` rather than reaching
the shared counter.

This is the precise coupling: `_charge_ledger` owns the single caller-shared
K counter and does not expose a per-charge increment. Repairing it requires a
gated edit to `backtest_runner.py` plus caller threading, which this lane may
not make.

## Construct result

The fixture JSON is
`docs/evidence/harness/S234_signal_factory_charge_fixtures_2026-09-04.json`.
Every case starts from an empty temporary JSONL path; it never reads the real
ledger. `K_true` is `k_increment(screened_n, 1)`. The scratch column applies
only the proposed defaulted parameter and literal replacement to a temporary
copy of `backtest_runner.py`.

| Fixture | screened_n | K_currently_charged | K_true | K_proposed_scratch |
|---|---:|---:|---:|---:|
| zero screens | 0 | 1 | 1 | 1 |
| one screen | 1 | 1 | 1 | 1 |
| two hundred screens | 200 | 1 | 200 | 200 |

The immutable bar is met: `k_increment(200, 1) == 200`. The non-tautological
zero-screen floor is also asserted: it remains one rather than silently zero.

The shared evaluator ran through
`scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate` on eight
timestamp-distinct synthetic states with `n_groups=4`, `n_test_groups=1`, and
`embargo_days=1`. It returned eight records with train sizes 4 and 5. Its
route applies the imported purge and symmetric nonzero calendar-day embargo;
the rail has no predictive claim and does not affect the deterministic K
arithmetic.

## Proposed shared edit

The review-only snippet is in
`docs/research/organization-sprint/S234_backtest_runner_proposed_diff.md`.
It introduces `k_increment: int = 1` at `_charge_ledger` and replaces the
literal increment. The default preserves legacy calls; the scratch fixture
reproduces the current one-step result for zero screens.

## Test line

```text
python -m pytest tests/platformkit/foundry/test_screen_charge.py -q
1 passed
```

## Verifier self-check

- B1-B10: exhaustive named construct cases, additive-only new files, no
  threshold change, deployment, retirement, or fall-through path.
- Q1: preregistration path and pre-metric seal are above.
- Q2: no charged trial; only isolated temporary JSONL fixtures were used.
- Q3: the stated 200 and zero-screen bars are unchanged.
- Q4: the shared CPCV evaluator ran with purge and symmetric nonzero embargo.
- Q5: no AHEAD claim; this is a construct accounting result.
- Q6: calibration language only.
- Q7: exactly three exhaustive CONSTRUCT fixtures; reproduction replaces an
  eye check.
- Q8: SF-1 and literal-increment premises were remeasured before the change.
- Q9: the fixture JSON archives each paired K value, construct cluster, and
  timestamp; no fitted model state is involved.

No register or ledger line is written by this lane because the dispatch
explicitly forbids either mutation.
