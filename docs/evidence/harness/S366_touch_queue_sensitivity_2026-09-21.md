# S366 touch queue sensitivity - PREPARE only

Construct verification passed; runtime use remains NOT VALIDATED.
Vocabulary follows contract Q6; automated scan required.

Binding before-condition, rerun before construction:

```text
ls scripts/platformkit/execution/touch_queue_sensitivity.py
Exit code: 1
ls : Cannot find path 'C:\Users\neelj\nba-harness-h24\scripts\platformkit\execution\touch_queue_sensitivity.py'
because it does not exist.
```

Scope: exactly the three new files named in
`docs/evidence/tracking/specs/S366_spec.md`. No pre-existing module was edited.
Design: `docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md`, section 1
at-limit paragraph and section 6 row 7. Contract: sections B and Q of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

`scripts/platformkit/execution/touch_queue_sensitivity.py` imports the landed
`tape_fill_sim.simulate_fills` for both independent runs. It does not implement
another fill engine. `build_book_snapshots` accepts S341 snapshot and
snapshot_bulk dictionaries, using response_end_ts or, only when absent,
capture_ts. Venue times pass through `execution.venue_time.parse_venue_time`.
Raw nested fixed-point, legacy cent and explicit probability ladders map to
resting-side cent levels. Without a ladder payload, raw YES bid size maps to the
YES bid; raw YES ask size maps to the complementary NO bid. An explicit ladder
is authoritative, including missing levels. No neighboring size is borrowed.

Sizes enter as strings or Decimal, never binary floats. Missing or malformed
size produces an unknown queue, not zero. Invalid sides have named counters;
invalid timestamps refuse the call instead of silently reusing an older row.
Nonfinite numbers are refused. Duplicate normalized levels sum with protected
Decimal precision before the scenario multiplier is applied.
Same-time snapshots use the landed conservative maximum/unknown rule.
Conflicting duplicate print IDs refuse in either order; identical duplicates
retain the simulator's counted deduplication. No input is mutated.

The declared multipliers are 2 (default), 4 and 8. The mapped displayed queue
is multiplied with sufficient Decimal precision. Unknown queues exceed the
entire supplied tape volume using exact arithmetic, so no finite tape can
exhaust them in the sensitivity run. Primary retains the landed call's original
inputs, parameters and queue policy with no displayed books. The sensitivity is a separate result, with
`scenario = touch_queue_x<multiplier>` on the result and every fill, including
strictly-through fills within that scenario. These are alternative runs and
must not be concatenated. No sensitivity field is added to primary results.

The landed simulator supplies subsequent matching-aggressor depletion, no
cancellation credit, replacement resets, latency handling, cumulative fees
and shared print conservation. NormalizedPrint inputs use its resting-side
convention. Whole positive order quantities remain the landed API restriction;
displayed size, print quantity and partial fills can be fractional.
`assert_primary_isolated` compares canonical JSON bytes before, during and
after the sensitivity call. The fixture also compares to a direct landed-core
baseline and checks input immutability and independent result storage.

Displayed size does not establish intervening arrivals or actual priority.
This named assumption is not a lower bound and is not primary G3 evidence.
No archive was run; no data directory was accessed; no network or pod was used.
The pod remains OFF. No measured calibration, fill or markout result is given.

Reproduction (local, self-contained CONSTRUCT; no gitignored fixture dependency):

```text
python -m pytest tests/platformkit/execution/test_touch_queue_sensitivity.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.touch_queue_sensitivity --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/touch_queue_sensitivity.py tests/platformkit/execution/test_touch_queue_sensitivity.py docs/evidence/harness/S366_touch_queue_sensitivity_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S366_spec.md
```

The current per-file construct run passed 68 tests. Cases enumerate both sides, raw
ladder schemas, exact-level refusal, unknown and invalid sizes, explicit zero,
all three multipliers, fractional shared queues under reduced Decimal
precision, later matching prints, replacement resets, cancellation timing,
same-time ambiguity, permutations, duplicate IDs, equal Decimal representation
ties, primary isolation, four- and
five-digit timestamp fractions, invalid parameters, refusals and empty tape.
No sampling or scored comparison was performed. B1-B10 and Q1-Q9 self-review:
no metric selection, schema removal, production activation, threshold changes,
scored comparison, trial charge or corpus claim. Q6 is checked by the required
automated preflight; Q7 uses the enumerated CONSTRUCT cases; Q8 is the rerun
before-condition. No ledger or register edits are part of this new-files row.
The module's --help command passed. Contract preflight passed all nine checks,
including the automated vocabulary scan over all three new files.

## FIX 1b

Both BLOCKING findings were reproduced locally before editing the row module.
The worktree spec and `git show master:docs/evidence/tracking/specs/S366_spec.md`
were read; neither contained an AMENDMENT block.

1. Primary-path isolation: the verifier's quote (price 50, quantity "2",
   submit time 10) and through print (price 49, count "1", time 12) produced:

```text
DIRECT queue_ahead_at_submit='1000000' fill_ts=12
MODULE queue_ahead_at_submit='2' fill_ts=12.0
BYTE_EQUAL False
```

`primary_fills` now calls the landed simulator with the caller's original
inputs and parameters. Only sensitivity uses `_inputs` normalization and the
unexhaustible unknown queue. The isolation helper compares canonical bytes
against direct landed calls before and after sensitivity. A supplied
`primary_result` is copied unchanged for callers whose sensitivity timestamps
need normalization unsupported by the landed primary API.
Regression: `test_primary_canonical_bytes_match_original_landed_call` checks
the non-coincidental case, default and explicit latency parameters, integer
timestamp serialization, unchanged inputs and both primary entry points.
The existing fractional-time fixtures exercise supplied primary preservation;
the equivalent-print permutation fixture checks sensitivity determinism and
preserves each original landed primary result, including its representation.
After the fix, the same minimal reproduction produced:

```text
DIRECT queue_ahead_at_submit='1000000' fill_ts=12
MODULE queue_ahead_at_submit='1000000' fill_ts=12
BYTE_EQUAL True
PRIMARY_SELF_CHECK PASS
```

2. Duplicate normalized prices: the two exact-level amounts "1" and "2" at
   probability "0.50", multiplier 2, print size "5" and order size "2"
   produced the failing output:

```text
MAPPED_QUEUE [[50, '4']]
FILLED_QTY 1
```

Repeated normalized prices now raise a counted invalid-side error. The mapped
side becomes unknown, so at-limit depletion cannot yield a fill.
Regression: `test_duplicate_normalized_prices_block_at_limit_fill` asserts
the invalid-side counter, unknown mapping and no fill in both input orders.
After the fix, the same minimal reproduction produced:

```text
MAPPED_QUEUE []
FILLED_QTY 0
```

Validation: 47 per-file tests passed with the exact pytest command above;
no fixture isolation workaround was needed. The module's --help passed and
`assert_primary_isolated` passed on the minimal reproduction. The CLI exposes
no separate self-check option. The contract preflight command above checks
only this row's three owned files, excluding the verifier verdict.

## FIX 1c

Both BLOCKING findings in `_verdict_s366_1c.md` were reproduced before editing.
The local spec and `git show master:docs/evidence/tracking/specs/S366_spec.md`
contain no AMENDMENT blocks. Only this row's module, tests and memo changed.
All commands ran locally in `C:/Users/neelj/nba-harness-h24` on constructs.

1. Partial explicit ladder (BLOCKING): YES ladder `[[50,"9"]]`, raw YES ask
   `60` with size `"1"`, NO quote `40` with quantity `"2"` at time 10,
   matching print size `"3"` at time 12, snapshot time 9 and multiplier 2:

```text
PARTIAL MAPPED [[40, '2']] DIAGNOSTICS {} FILLED_QTY 1
PARTIAL CHECK FAIL
```

An explicit ladder now prevents raw touch fallback for a missing side or price.
Only an absent or null book permits touch fallback. Empty ladders remain
authoritative. Missing sides increment `missing_ladder_side`.
`test_partial_ladder_never_borrows_raw_touch` covers both sides, three ladder
wrappers and absent side, absent price and empty ladder cases (18 constructs).
The same minimal reproduction after the fix:

```text
PARTIAL MAPPED [] DIAGNOSTICS {'missing_ladder_side': 1} FILLED_QTY 0
PARTIAL CHECK PASS
```

2. Duplicate normalized levels (BLOCKING): YES levels `[["0.50","1"],
   ["0.50","2"]]`, quote quantity `"2"`, matching print `"5"`, multiplier 2:

```text
DUPLICATE MAPPED [] DIAGNOSTICS {'invalid_yes': 1} FILLED_QTY 0
DUPLICATE CHECK FAIL
```

Sizes at each normalized price now sum exactly before multiplication. The
local Decimal context accounts for exponent span and carry digits. This
supersedes the FIX 1b duplicate refusal and its regression expectation.
`test_duplicate_normalized_prices_aggregate_before_depletion` checks both
permutations with print sizes 5, 6 and 6.125: no fill below or at queue
depletion, then a 0.125 partial fill. The additional precision regression uses
equivalent normalized prices and widely separated size exponents under ambient
precision 4 in both input orders. The same minimal reproduction after the fix:

```text
DUPLICATE MAPPED [[50, '6']] DIAGNOSTICS {'missing_ladder_side': 1} FILLED_QTY 0
DUPLICATE CHECK PASS
```

3. Primary isolation (NOTE): preserved without edits. The original through-print
   self-check still reports `PRIMARY_SELF_CHECK PASS`; its regression passed.
4. Verifier temporary-directory limitation (NOTE): reran the exact per-file
   pytest command above in this writable worktree: `68 passed in 0.79s`.
   No fixture workaround or additional pytest option was needed.

Validation: both minimal reproduction checks passed, the primary isolation
self-check passed, CLI --help passed, and all nine contract preflight checks
passed over the three owned files. The verdict file was excluded. No separate
CLI self-check option exists; `assert_primary_isolated` is the API self-check.

NOT VERIFIED:
- Real archive compatibility or measured coverage.
- Actual queue priority, unseen arrivals, cancellations or realized fills.
- Calibration, fill or markout performance on any corpus.
- Current fee certification or fractional order submission support.
- Production integration, deployment, pod execution or G3 qualification.
- Independent verifier reproduction on master and lane_commit creation.
- Landed primary timestamp support or queue-policy changes; primary is preserved.
