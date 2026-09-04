# S239 CLV Countdown Metric Preregistration, Attempt 2

Scope: add an opt-in reader-only countdown metric for the existing CLV capture
stores. No capture-store fields, locations, thresholds, register rows, ledger
rows, or execution routes are changed.

Predeclared inputs, opened one at a time:

- `data/frontend/clv_ledger.jsonl`, using each JSON line's settlement class and
  any dated settled-history fields present in that file.
- `data/frontend/analytics/execution_status.json`, using `n_settled` and
  `row_classes.settled`.

Predeclared arms (exhaustive, n = 2 CONSTRUCT):

1. The current named capture stores. The expected result is `n_settled_today =
   0`, `settlement_rate_per_day = null`, and `days_to_first_reading =
   "UNDEFINED"`, with the current named open blocker rows printed.
2. A test-local construct ledger with a nonzero dated settled history and a
   matching execution-status object. The expected result is a finite integer
   equal to `ceil((200 - n_settled) / settlement_rate_per_day)`.

Predeclared method: `countdown(ledger_path, execution_status_path)` reads only
the two supplied stores. It counts settled rows from the ledger, derives a
per-day settlement rate only from dated settled ledger history, returns
`UNDEFINED` when no positive rate can be derived, and names the current open
blocker chain from the supplied/current status context.

Frozen bar: 200 settled observations across at least two sports and seven
days. This metric does not alter it.

Verdict rule: ACCEPT only when both exhaustive arms reproduce their stated
outputs and the frozen 200 / 2 sports / 7 days bar is unchanged; otherwise
report NOT VERIFIED with the mismatching quantity named. `UNDEFINED` at zero
settled rate is a valid result, never a fabricated day count.

Fold scheme, purge, and embargo: not applicable. These two enumerated
reader-only reproduction arms have no train/test split, learned model, or
out-of-sample score; applying `walk_forward` or `cpcv_evaluate` would create a
non-semantic quantity. The existing shared evaluator's 48-hour purge and
symmetric nonzero embargo are therefore not invoked.

Predeclared acceptance bar: the real-store arm reproduces zero settled rows,
null rate, `UNDEFINED`, and at least one named blocker. The construct arm
returns the finite hand-computed integer. The implementation remains additive
under `scripts/platformkit/live_edge/clv/`, is at most 300 LOC, and is covered
by one focused test file.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Q1 applies: this preregistration is sealed before either result is measured.
Q2/Q4/Q5/Q9 are not applicable because neither arm is a charged trial,
out-of-sample comparison, ahead claim, or paired-loss comparison. Q3 applies:
the existing 200 / 2 sports / 7 days bar is unchanged. Q6 applies: reporting
uses calibration language only.

SEAL RULE: seal = SHA-256 of every byte of this file above the seal line, as committed (LF line endings, computed with: git show HEAD:<path> | head -n <N> | sha256sum after the commit, and verified equal to the working-tree computation before committing)
Seal SHA-256 of lines 1-56: `4cdd7a5304229b35b0c65dc2bb0ddf04db26d27a4d58cd86861957d062d69e75`.
