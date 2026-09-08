# S310 preregistration supplement, corrected rationale

Supersedes `docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg_supplement.md`
(seal `4f9898cf09f46f91253286ba2ccd8047813b46fbd920bf6ad81b4740dc10a904`, committed at
`15a0db133`). That file is not rewritten; it stands in the record with its seal intact.

## What this file does and does not change

It changes **no clause of the protocol**. The three amendments sealed in the superseded
supplement stand exactly as sealed, unchanged in wording and effect:

1. Evaluator grain: one state per `(game_id, period, floor(game_clock_s / 30))`, keeping
   the lowest source row index in each cell.
2. One `cpcv_evaluate` pass instead of two.
3. A scored-state counter on stderr.

Those were sealed at `15a0db133` before the amended harness had been run and before any
amended number existed. What this file corrects is the **stated reason** for amendment 1,
which was wrong, and it records a **defect fix** found afterwards. Both corrections were
made after a first local run had been seen, and that is stated here rather than concealed.

## Correction 1: the reason given for amendment 1 was wrong

The superseded supplement attributed the cost to an inherent quadratic term in the shared
evaluator's `_blocked_indices`. That was a misreading of a real timing produced by a
defective harness.

## Correction 2: the timestamp defect (a defect fix, not an amendment)

`ts` in the corpus is an int64 column of **epoch seconds**. `_states` built its evaluator
timestamp with `pd.Timestamp(row.ts)`, and `pd.Timestamp` reads a bare integer as
**nanoseconds**. Every state therefore carried a `state_ts` on 1970-01-01, all within
about 50 ms of each other, so:

- `_blocked_indices` blocked every index on every path
  (`n_states=117964 n_test=48349 n_blocked=117964`);
- the train set was empty on both folds (`n_train_ticks: 0`, `beta: [0,0,0]`);
- with no train rows the baseline was never fit and the candidate took its zero-beta
  identity path, so both arms returned the raw market probability;
- every reported improvement was exactly `+0.000000000` with a zero-width interval.

That is a tautological null, not a result. Fixing it is a defect fix rather than an
amendment: the preregistration declares a "symmetric one-day nonzero embargo", and the
embargo was silently blocking the whole corpus instead. The fix restores the
preregistered behaviour and is stated explicitly as
`pd.Timestamp(int(row.ts), unit="s", tz="UTC")`.

The reading is corroborated independently inside the same codebase: the sibling harness
`s265._rows` converts the same column with
`pd.to_datetime(raw["ts"], unit="s", utc=True)`.

## Correction 3: the real reason amendment 1 is needed, measured after the fix

With the defect fixed, `_blocked_indices` is no longer pathological, but the full tick
grain is still not affordable under the pod share this lane actually gets. Measured
single-core locally, with the fix in place and one evaluator pass:

| design | single-core CPU | wall at the measured 0.125-core pod share |
|---|---:|---:|
| full tick grain, 465249 states | more than 1465 s, stopped unfinished | more than 3.3 h |
| 30 s grain, 117964 states | 201.1 s, RSS 646 MB | about 27 m |

Budget 3 h. The pod container's 27.2-core quota is saturated by the tracking fleet (load
average 40 to 70), and a single-threaded harness was measured twice at 0.125 of one core.
The full-tick arm breaches the budget; the amended grain fits with margin. Amendment 1 is
therefore retained, for this reason rather than the one originally given.

All timing figures in the superseded supplement were measured before the defect fix and
are withdrawn.

## Unchanged

Estimand, primary and guard metrics, epsilon 1e-15, the frozen tail bins, the ridge, the
nested inner OOF construction, the acceptance bar, the seed 905, the 10000 bootstraps, the
sign convention, the shared route, the shared purge, the symmetric one-day embargo, the
Holm rule, the frozen 0.004 global bar, the S272 references, and the ban on deploy, flag,
registry, ledger and source-store writes. The remeasured band counts in the superseded
supplement (low 4420 states / 570 clusters / 26 positive; high 6515 states / 742 clusters)
are properties of the grain rule and are unaffected by the defect fix.

Seal-SHA256-LF: aaecd6956b75c305118a24b0156510e79cd483c1875e42ebd1afff704c5f0e00
