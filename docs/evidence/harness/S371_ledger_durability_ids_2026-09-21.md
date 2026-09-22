# S371: ledger durability and globally scoped replay IDs

Construct and fixture verification only. All work ran locally in
`C:/Users/neelj/nba-harness-h29`. The pod is OFF.

Vocabulary follows contract Q6; automated scan required.

## Authority and reproduced defects

Authority: `docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md`, findings 8 and 3.
The binding S343, S344, S345, S354, S356 and S357 specifications and their
amendments were read, together with verifier contract sections B and Q.

Finding 8 text:
> Import failure disables locking, `required=False` permits unlocked read/append,
> and fsync failure is swallowed while append reports success.

Finding 3 text:
> Repro: day-1 `Q` submit+fill followed by day-2 submit `Q` qty 10 produced
> `terminal=True, open=False, unfilled_qty="0"`. The new order disappears from caps.

Before any module edits, this command reproduced every named failure:

```text
python -m pytest tests/platformkit/execution/test_ledger_durability_ids.py -q -p no:cacheprovider
test_import_failure_raises[read]: Failed: DID NOT RAISE <class 'ImportError'>
test_import_failure_raises[append]: Failed: DID NOT RAISE <class 'ImportError'>
test_unavailable_lock_raises[read]: Failed: DID NOT RAISE <class 'RuntimeError'>
test_unavailable_lock_raises[append]: Failed: DID NOT RAISE <class 'RuntimeError'>
test_fsync_failure_raises: Failed: DID NOT RAISE <class 'OSError'>
test_day_two_reuse_rejected: Failed: DID NOT RAISE <class 'ValueError'>
audit finding 3: {"terminal": true, "open": false, "unfilled_qty": "0"}
6 failed in 1.09s
```

Those same six tests passed after the module fixes:

```text
6 passed in 0.50s
```

## Changes and boundaries

`position_ledger.py` now imports the shared lock acquisition primitive lazily.
Import failure propagates. Missing backends, sidecar-open failures and failed
acquisition cannot enter the critical section. The existing optional shared
wrapper was insufficient even with `required=True`: it ignores missing backends
and sidecar-open failures. The local mandatory wrapper reuses its sidecar naming,
acquisition and release primitives without editing the shared module.
Public reads acquire the same lock even when the ledger is absent. Append uses
an internal reader so its scan, validation, write and synchronization share one
lock without recursive acquisition. Construct failure tests inject fake locks.

Each fresh append encodes one JSONL line and calls `os.write` once on an
`O_APPEND` descriptor in binary mode, then flushes and calls `os.fsync`.
Short writes and fsync failures raise. A complete line left by a failed sync is
synchronized again before a retry can return an idempotent no-op. Appending onto
a malformed or unterminated tail is refused; tolerant public reads retain the
prior final-line rule while counting and warning about the skipped line.

`position_reducers.py` rejects incoming intent/submit reuse with
`ValueError("order_id_reuse")` when an existing order is terminal or has a
different idempotency key. Changed declaration payloads cannot hide behind
deduplication. Identical declarations remain no-ops after termination; integer
and persisted string quantities compare as exact Decimals. Fills still deduplicate
solely by `fill_id`, including repeats labelled with another fill event type.
Every permutation of the audit's conflicting declarations is rejected.
Game ticker lists use sorted ticker traversal for deterministic aggregation.
The ordered event log remains the chronology for average-cost accounting.

`replay_units.py` adds `replay_order_id` and `replay_event`. IDs have the form
`<utc-day>-<run-nonce>-<counter>`. The caller supplies a unique nonce for each run
and a positive counter unique within that run, independent of input list order.
Every generated event records the nonce and matching order/quote IDs. Lifecycle
events retain the original order's day/nonce/counter; a fill after midnight
retains that order ID. Fill conversion recovers the nonce from generated IDs
when the simulator carries only the quote ID, checks explicit nonce agreement,
and carries the nonce into both ledger and mark records. Legacy external IDs
remain accepted; no missing nonce is invented for old events.

Venue-time parsing delegates directly to `execution.venue_time.parse_venue_time`;
refused times raise explicitly. Existing public arguments and reason codes remain;
`new_event` adds only an optional `run_nonce` argument. Snapshots add an order
`idempotency_key` field. No prior field was renamed or removed.

Quantity parsing and accumulation remain Decimal, with floats refused for sizes.
The fee helper receives cumulative Decimal quantity and Decimal probability;
the unchanged `venue_fees` implementation internally coerces them to floats.
Incremental fees remain the cumulative per-order/per-price ceiling less fees
already charged. The 9.47 + 0.53 construct still totals the whole-order fee.
Nonfinite mark inputs are rejected with `math.isfinite` and Decimal checks.

## Original verification output

The original candidate passed per-file constructs: ledger 83 (one expected
warning), reducers 40, fractional chain 26, caps 42, exposure 26, durability/IDs
31 and replay IDs 36. All nine contract preflight checks passed over six paths.
During development, an unowned simulator rejected a four-digit quote timestamp;
the fixture routes that timestamp through the shared parser. No simulator edit.
The FIX sections below supersede those original test and file counts.

## FIX 1b

Binding review: `_verdict_s371_1b.md`. The local S371 spec and the copy read
with `git show master:docs/evidence/tracking/specs/S371_spec.md` have no
AMENDMENT blocks. This pass used constructed fixtures in this worktree only.
The earlier Verification output section records the original candidate run;
the counts below are the final FIX 1b run.

Finding 1 (BLOCKING): declarations were compared by event type and key, so
intent Q/A/G1/yes/1 and submit Q/B/G2/no/10 with key K were accepted together.
Before module edits, the verifier's minimal reproduction printed:

```text
Finding 1: accepted open=True A/G1/yes/10
```

`position_reducers.py` now stores canonical immutable declarations by order_id.
It compares ticker, game, side, price, exact Decimal quantity, idempotency key,
and optional nonce/quote identity before mutation or deduplication. Lifecycle
type is not part of that canonical declaration. Fill metadata is not an
immutable order field; existing full-payload checks for same-event retries
remain. Every mismatch raises the existing order_id_reuse reason. After:

```text
Finding 1: ValueError: position replay line 2: order_id_reuse
```

Finding 2 (BLOCKING): a half-length os.write permanently blocked later appends.
Before module edits, the verifier's minimal reproduction printed:

```text
Finding 2 first: OSError: position_ledger: short append write
Finding 2 retry: ValueError: position_ledger: unterminated final line requires repair; tail unchanged=True
```

`position_ledger.recover_incomplete_tail(path)` is an explicit mandatory-lock
operation. It validates the complete prefix before writing anything, refuses
complete JSON tails (including invalid schema) and interior corruption, and
records the final incomplete bytes as hex, original content hash and truncation
offset in `<ledger>.recovery.jsonl`. That prepared record is flushed and fsynced
before truncation; the repaired ledger is then flushed and fsynced. Both sync
failures raise. The record describes a prepared operation, so interrupted
recovery does not falsely claim completion. Ordinary append still refuses torn
tails until recovery is explicitly invoked. The same half-write reproduction,
followed by explicit recovery and retry, printed:

```text
Finding 2 first: OSError: position_ledger: short append write
Finding 2: recovery=True; retry=True; intact events=1; recovery records=1
```

Finding 3 (NOTE, no fix): the verified locking, restart identity, replay,
accounting and cap behavior was preserved. `replay_units.py` was not changed
during FIX 1b. No other pre-existing module or original assertion was edited.

New regression file: `tests/platformkit/execution/test_s371_fix_1b.py`.
Its 29 constructs cover both reproductions, both declaration orders, individual
immutable field mismatches, no mutation on rejection, append/read rejection,
exact large quantities, valid lifecycle transitions, preserved prefix bytes,
recovery journaling and sync ordering, incomplete UTF-8, corruption refusals,
lock refusal, sync failures and missing/empty/complete no-ops.
The first ledger rerun found `2 failed, 81 passed` because the first canonical
comparison included fill metadata; selecting immutable order fields corrected
that implementation without changing the existing test expectations.

Final per-file runs, each using `python -m pytest <one file> -q -p no:cacheprovider`:

| File under tests/platformkit/execution/ | Pass count |
| --- | --- |
| test_position_ledger.py | 83 (one expected torn-tail warning) |
| test_position_reducers.py | 40 |
| test_fractional_chain.py | 26 |
| test_position_caps.py | 42 |
| test_position_exposure.py | 26 |
| test_ledger_durability_ids.py | 31 |
| test_replay_units_ids.py | 36 |
| test_s371_fix_1b.py | 29 |

Total: 313 passed. Writable temporary fixtures were available in this session.
The three row modules were invoked with `--help`, all exit 0: ledger and
reducers execute their existing `_demo` self-checks and print OK; replay_units
has no CLI or self-check and emits nothing. These are not argparse help pages.

Final contract preflight used the earlier six candidate paths plus
`tests/platformkit/execution/test_s371_fix_1b.py`, with `--base master --spec
docs/evidence/tracking/specs/S371_spec.md`; the verdict file was excluded.
All 9 checks passed: vocabulary, CRLF, LOC, additive schema, head slices,
spec thresholds, proposed changes, removed artifacts and row duplication.
All 7 candidate files passed ASCII decoding. Module line counts are now
300 / 256 / 121, and test line counts are 261 / 113 / 182.
`git diff --check` passed. Files remain on disk for lane_commit.

## FIX 1c

Binding review: `_verdict_s371_1c.md`; local and master S371 specs contain no
AMENDMENT blocks. Only `position_ledger.py` changed in this pass, plus this memo
and the new `tests/platformkit/execution/test_s371_fix_1c.py` regression file.
Verifier-confirmed declaration, accounting, cap and replay behavior was retained.

Finding 1 (BLOCKING), reproduced before module edits with the exact 97/194
journal write and retry. The new regression first failed with:

```text
journal write: 97/194
first recovery: position_ledger: short recovery record write; ledger preserved=True
retry recovery: True
json.decoder.JSONDecodeError: Expecting ',' delimiter: line 1 column 100 (char 99)
1 failed in 1.31s
```

Under the existing mandatory lock, recovery now parses every complete journal
line before mutation, repairs only an incomplete final journal segment, and
counts that repair. Complete JSON tails and corrupt interior lines raise.
A detected short journal write rolls back to the validated offset, flushes and
fsyncs before raising. Successful journal writes flush and fsync before the
ledger truncation and fsync. If rollback is interrupted with an incomplete
segment, the next recovery repairs it. Prior complete journal records survive.
The exact reproduction then passed: `1 passed in 0.55s`.

The all-durable-files review additionally reproduced a ledger write missing
only its newline, before changing that path:

```text
ValueError: position_ledger: complete JSON tail requires manual repair
1 failed, 15 passed in 0.98s
```

That detected boundary write now rolls back to the pre-write offset under the
append lock and flushes/fsyncs before raising. Ordinary half-write refusal and
explicit recovery are unchanged. Complete JSON tails found during later recovery
remain refused; the rollback only uses the known result of the active write.
The boundary regression then passed with the other constructs:
`16 passed in 0.76s`; adding its rollback-sync-failure case produced 17 passes.

The 17 new constructs cover exact retry, zero/one/half/all-but-newline journal
writes, preserved prefixes, interrupted rollback, incomplete UTF-8, journal
corruption refusals, sync ordering/failures and both ledger short-write shapes.
Recovery/retry tests parse every line in both durable JSONL files afterwards.
No marker is introduced. The existing lock sidecar carries no payload.

Finding 2 (CORRECTION): the scratch-directory check prints `scratch_present=True`.
Per the explicit orchestrator override, scratch remains uncommitted and excluded
from landing. The candidate is exactly these eight owned paths:

```text
scripts/platformkit/execution/position_ledger.py
scripts/platformkit/execution/position_reducers.py
scripts/platformkit/execution/replay_units.py
tests/platformkit/execution/test_ledger_durability_ids.py
tests/platformkit/execution/test_replay_units_ids.py
tests/platformkit/execution/test_s371_fix_1b.py
tests/platformkit/execution/test_s371_fix_1c.py
docs/evidence/harness/S371_ledger_durability_ids_2026-09-21.md
```

Findings 3, 4 and 5 (NOTEs): no requested correction; existing regression
assertions remain unchanged. No other pre-existing module was edited.
Final commands used `python -m pytest <one file> -q -p no:cacheprovider`, one
file at a time, with temporary fixtures confined to this worktree:

| File under tests/platformkit/execution/ | Pass count |
| --- | --- |
| test_position_ledger.py | 83 (one expected torn-tail warning) |
| test_position_reducers.py | 40 |
| test_fractional_chain.py | 26 |
| test_position_caps.py | 42 |
| test_position_exposure.py | 26 |
| test_ledger_durability_ids.py | 31 |
| test_replay_units_ids.py | 36 |
| test_s371_fix_1b.py | 29 |
| test_s371_fix_1c.py | 17 |

Total: 330 passed. All three row module `--help` invocations exited 0; ledger
and reducers printed `_demo OK`; replay_units has no CLI and emitted nothing.
These remain self-check invocations, not argparse help pages.

Contract preflight used exactly the eight paths above with `--base master
--spec docs/evidence/tracking/specs/S371_spec.md`; all nine checks passed.
The verdict file and scratch were excluded. The explicit path check printed
`candidate_owned_only=True; scratch_excluded=True`. All eight files decoded as
ASCII and stayed within 300 lines; `git diff --check` passed.

## NOT VERIFIED

- Real archive completeness, real execution, real queues and venue ordering.
- Physical power-loss behavior or filesystem durability beyond the exercised
  write/flush/fsync contract; an fsync exception leaves durability unknown.
- Cross-process contention under load; lock failures and critical-section
  ordering were exercised with constructs on this local Python 3.10 environment.
- Global nonce uniqueness outside the caller's contract; deployments must supply
  a fresh nonce for each new run and preserve the original identity on retries.
- The unowned simulator timestamp defect, external fee-parser changes, deployment
  and verifier execution on master. No network, pod or measured result was used.
- No commit was created; files remain on disk for lane_commit.
