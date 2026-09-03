# S150 runner leases

Date: 2026-09-03. Scope: construct-only queue lifecycle repair.

## Premise reproduction

The pre-change `claim(50, tier="T0")` path was loaded from `HEAD` into an
isolated temporary SQLite database. Fifty unique hypotheses were queued, claimed,
then left without renewal or a result. The measured default lease was 45,000
seconds (`900 * 50`); `reap_expired` at plus one hour released 0 rows.

The pre-change source search found zero production `renew()` callers and no
`atexit`, `SIGTERM`, `SIGINT`, or release path in `foundry_runner.py`.

## Change summary

- The default lease is now `LEASE_SECONDS * min(claimed, 5)`. An explicit
  `lease_seconds` remains an exact value.
- Claimer identifiers are `host:pid`. `reap_expired` also releases an unfinished
  claim when its local host process no longer exists. Remote-host identifiers are
  left alone until their time lease expires.
- `release` retains its hash-list form unchanged and adds a claimer form that
  releases only rows without a result at their queued tier.
- The queue runner registers normal-exit, SIGTERM, and SIGINT cleanup, and renews
  every in-flight hash set after every screened hypothesis.

## Acceptance construct

| Behavior | Before | After | Proof |
|---|---:|---:|---|
| Exit release | absent | pass | normal-exit and SIGTERM subprocesses release temporary claims |
| Dead local claimer reap | absent | pass | real finished subprocess PID is released by another local owner |
| Per-hypothesis renewal | absent | pass | a two-hypothesis runner pass makes two renew calls |

Metric: 3 required behaviors out of 3. Before: 0/3. Bar: 3/3. After: 3/3.
`n = 3 (CONSTRUCT)`: each required behavior is enumerated, with no excluded
behavior. Eye check: n/a; reproduction is the three test cases below.

The capped default is independently asserted as 4,500 seconds for a claimed
50-row batch. The existing explicit-lease checks remain green.

## Tests

```
python -m pytest tests/platformkit/foundry/test_foundry_runner_s150.py -q
5 passed
python -m pytest tests/platformkit/foundry/test_results_db.py -q
21 passed
python -m pytest tests/platformkit/foundry/test_foundry_runner_s16.py -q
7 passed
```

## Contract self-check

Section B: no scored metric or exclusions; no removed schema field or status;
no absent-evidence gate; release and reap return unfinished claims to the queue;
no pod action; no moved module; no render or fitted-model claim; denominator is
the three enumerated requirements; and no threshold changed.

Section Q: no scoring occurred, no ledger was opened, and no corpus claim is
made. The fixed 3/3 bar is unchanged. This is a full construct enumeration, so
the sampling rail does not apply. The premise was remeasured before the change.
The text uses calibration-only language.

## NOT VERIFIED

- The verifier must repeat these focused tests and the dead-process reproduction
  after landing in master.
- No pod was contacted and no production database was opened.
