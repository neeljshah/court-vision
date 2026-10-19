# S458 -- additive request_class on scheduled Kalshi capture rows

WHERE: local, worktree `harness-h112` (master-based). Construct/fixture tests only -- no
network, no live capture, no pod. The running Kalshi books runner (pids 31768 / 21752 /
34088), their lock files, STOP files and output roots were never touched.

CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` A9, B1-B11, Q1-Q9, S1, S2, S4.
SPEC: `docs/evidence/tracking/specs/S458_spec.md`, built to AMENDMENT 1 (binding, applied
before any code existed): request_class is the accounting class of the HTTP attempt that
produced the row; scope is the scheduled Kalshi capture only; the class context is
dispatch-scoped (set only after successful admission, cleared at the end of every
dispatch including the exception path), never a tick-wide attribute.

ROUND 2 (this revision): applies the round-1 ACCEPT WITH CORRECTIONS -- no `.py` change,
memo only. Corrections made: (1) both SHA roles recorded in full, with the actual observed
relationship rather than an assumed equality; (2) the SHA/status paragraph moved to
immediately precede "## NOT VERIFIED"; (3) full 64-hex sha256 digests for all five
must-not-move files; (4) the seven constructs' actual MASTER-BEFORE results, individually;
(5) an empirical master-vs-candidate byte comparison (rows with request_class stripped,
checkpoints, heartbeat, and a schedule artifact) under frozen clocks and a frozen
`uuid4`; (6) the A9 table regenerated last, as the final edit to this file.

## Pre-edit pass counts (measured before any `.py` edit, re-verified after the round-2
fast-forward by `git stash`, running each file, then `git stash pop`)

| file | function count (spec) | PASS COUNT |
|---|---|---|
| `tests/platformkit/ingame/test_capture_scheduler.py` | 38 | **151 passed** |
| `tests/platformkit/ingame/test_local_capture_runner.py` | 8 | **8 passed** |
| `tests/platformkit/ingame/test_inplay_capture_runner.py` | 5 | **5 passed** |

(Per AMENDMENT 1(e): 38/8/5 are function counts, not pass counts -- parametrization
expands `test_capture_scheduler.py` to 151 collected/passed cases.) These three counts are
unchanged across every base this row has sat on so far (`86e586dc3`, then `ef0a00458` after
the round-2 fast-forward) -- no intervening commit touched `local_capture_runner.py`,
`local_capture_writer.py`, or the three named test files.

## CHANGE (exactly the two hunks in the spec, folded onto existing lines, zero new
functions, zero must-not-move edits -- unchanged from round 1)

`scripts/platformkit/ingame/local_capture_writer.py` (183 -> 185 lines), `ArchiveWriter.append`,
inserted before the `suffix = ...` line (after the `response_end_ts` validation):
```python
label = getattr(self, "request_class", None)
if label is not None and row.get("request_class") is None: row["request_class"] = label
```
Additive stamp: the attribute defaults absent (no `__init__` change), so any writer/caller that
never sets it (legacy `_tick`, Polymarket) is byte-identical; an existing label is never
overwritten.

`scripts/platformkit/ingame/local_capture_runner.py` (299 -> 300 lines), `_scheduled_tick`:
1. In `guarded()`, folded onto the existing `requests_by_class` line (same expression, no
   second literal):
   ```python
   label = "reserve" if retry else kind; state["requests_by_class"][label] += 1; writer.request_class = label
   ```
2. One `finally` added to the per-dispatch `try/except _Deadline` (dispatch-scoped, fires on
   both the success and the exception path):
   ```python
   finally: writer.request_class = None
   ```
No edit to `_book`, `_bulk`, `_trade`, `_tick`, `_discover_page`, or `main` -- verified by the
existing byte-identity AST test `test_fix1b_runner_unrelated_source_unchanged`, which still
passes.

## Constructs and their MASTER-BEFORE results

`tests/platformkit/ingame/test_request_class_rows.py` (new file, 193 lines), 7 test
functions. Each was run TWICE against master's unmodified two modules (`git stash` / run /
`git stash pop`) -- once at base `86e586dc3` (round 1) and once re-confirmed at `ef0a00458`
(round 2, identical results both times) -- then run against the candidate:

1. `test_focus_books_labeled_and_migration_row_stays_unlabeled` -- **MASTER-BEFORE: FAILED**,
   `KeyError: 'request_class'` on `all(r["request_class"] == "focus_books" for r in books)`
   (books carry no such field at all). **Candidate: PASSED.**
2. `test_bulk_row_labeled_without_cross_market_leak` -- **MASTER-BEFORE: FAILED**,
   `KeyError: 'request_class'`, same cause. **Candidate: PASSED.**
3. `test_discovery_only_tick_writes_zero_rows` -- **MASTER-BEFORE: PASSED** (this invariant
   already holds on master -- AMENDMENT 1(e): "discovery writes no rows" -- not something
   this row changes). **Candidate: PASSED** (unaffected, confirms no regression).
4. `test_429_then_200_retry_labeled_reserve` -- **MASTER-BEFORE: FAILED**,
   `KeyError: 'request_class'`. **Candidate: PASSED.**
5. `test_carry_across_ticks_restores_original_class` -- **MASTER-BEFORE: FAILED**,
   `KeyError: 'request_class'` on the resumed row. **Candidate: PASSED.**
6. `test_exception_cleanup_clears_class_before_propagating` -- **MASTER-BEFORE: PASSED, but
   VACUOUSLY** -- `getattr(writer, "request_class", None)` is `None` on master only because
   the attribute is never created at all, not because any clearing logic ran. **Candidate:
   PASSED, non-vacuously** -- confirmed by a targeted mutation check: deleting the
   `finally: writer.request_class = None` line makes this test FAIL
   (`assert 'focus_books' is None`), proving the passing candidate result is load-bearing.
7. `test_legacy_tick_rows_have_no_request_class_key` -- **MASTER-BEFORE: PASSED, but
   VACUOUSLY** -- no code on master ever sets the field, so its absence on a legacy row is
   trivial. **Candidate: PASSED, non-vacuously** -- the same mutation check (deleting the
   `finally` line) makes this FAIL too (a leaked `"focus_books"`/`"trades"` label appears on
   the reused writer's legacy row), proving dispatch-scoped clearing, not the field's mere
   absence, is what the candidate result demonstrates.

Aggregate master-before run: `4 failed, 3 passed in 1.23s`. Aggregate candidate run: `7
passed`. NON-TAUTOLOGY: every assertion reads the written row's own `request_class` key; the
discovery-zero-rows case is asserted by row count, never assumed.

## Byte comparison: master vs. candidate, request_class stripped, under frozen clocks

Method: `scripts/platformkit/ingame/local_capture_backfill.uuid4` was frozen to a constant
(`00000000000000000000000000000000`) and the fixture used `test_capture_scheduler.Timer`
(a deterministic fake clock, `elapsed` starts at 0) so the only two runs being compared
differ in nothing except the two edited modules. Two separate `python` process
invocations were used (module state cannot be hot-swapped mid-process): one against the
candidate worktree, one against master (`git stash` then `git stash pop`).

Construct A -- one pair (`EA`/`EB`), a non-empty fixed `/trades` response, no schedule:
- 8 written rows: for each, the candidate row had `"request_class"` popped before
  serializing through the (unmodified) `encode_json`; **all 8 stripped-candidate rows were
  byte-identical to the corresponding master row** (`records_stripped` lists equal).
  (Before freezing `uuid4`, 4 of 8 rows differed -- purely in a `backfill_id` /
  `drain_boundary_ids`-adjacent hex string derived from `uuid4().hex`, a pre-existing
  per-process-run randomness in `local_capture_backfill.py` unrelated to this change; after
  freezing `uuid4`, the mismatch disappeared, confirming it was never a request_class
  artifact.)
- Heartbeat (`kalshi/mlb/_heartbeat.json`): byte-identical (base64-compared).
- Both trade-state checkpoints (`_trade_state/<hash>.json` and `<hash>.drain.json` for both
  `EA` and `EB`): byte-identical (base64-compared, 4 files).

Construct B -- `test_capture_scheduler.test_schedule_runner_end_to_end`'s exact fixture
(two events, a prospective schedule, rate=1): the `_schedule_<sha256>.json` artifact has the
IDENTICAL filename (content-addressed) and byte-identical contents under master and
candidate; its heartbeat is byte-identical too.

No `_focus_drops_*.json` was produced by either construct (no drop triggered), so that
artifact type has no empirical byte-comparison in this round; it is unaffected by
construction (`writer.atomic`, never touched by this diff) and remains covered by the
still-passing `test_capture_scheduler.py` (151/151, includes drop-artifact assertions).

## Preflight

`python -m scripts.platformkit.tracking.contract_preflight --paths
scripts/platformkit/ingame/local_capture_runner.py
scripts/platformkit/ingame/local_capture_writer.py
tests/platformkit/ingame/test_request_class_rows.py --base master --spec
docs/evidence/tracking/specs/S458_spec.md` -> 9/9 PASS (vocab, crlf, loc, schema, head_slice,
spec_threshold, proposed, removed_artifact, row_duplication).

## Post-edit pass counts

`test_capture_scheduler.py` 151 passed, `test_local_capture_runner.py` 8 passed,
`test_inplay_capture_runner.py` 5 passed (unaffected -- imports neither edited module),
`test_request_class_rows.py` 7 passed. All three pre-existing counts unchanged from the
pre-edit baseline above.

## SHA / status

Worktree HEAD (`git rev-parse HEAD` in `C:/Users/neelj/nba-harness-h112`):
`ef0a004584b7f6fd849c7e9409505d3494ff9949`.

Main-repo master (`git -C C:/Users/neelj/nba-ai-system rev-parse master`), checked at the
time this correction was written: `ef0a004584b7f6fd849c7e9409505d3494ff9949`.

These two are EQUAL: the orchestrator fast-forwarded this worktree onto the current master
immediately before landing (master is a shared ref that moves as unrelated rows land; every
must-not-move digest and the seven master-before results in this memo were re-checked against
that sha with the same outcome, so no measurement depends on which commit was current).

`git status --short`:
```
 M scripts/platformkit/ingame/local_capture_runner.py
 M scripts/platformkit/ingame/local_capture_writer.py
?? docs/evidence/harness/S458_request_class_rows_2026-09-25.md
?? tests/platformkit/ingame/test_request_class_rows.py
```

SHA: NOT CREATED -- no commit made (rails: no git commit or push from this lane). Files are
on disk in `harness-h112`, ready for `lane_commit`.

## NOT VERIFIED

- Historical rows already on disk (captured before this row) remain unresolved --
  `request_class_unresolved` in `observation_support_census.py` still fires on every row
  captured to date; this row does not backfill them.
- `discovery` still writes zero archive rows (no `writer.append` call in `_discover_page`);
  the field cannot be, and was not, exercised for a discovery-labeled row.
- Row counts still cannot reconstruct total HTTP request counts
  (`observation_support_census.py:195`'s existing caveat is retained, unchanged).
- Adoption is the owner-visible relaunch of the scheduled Kalshi capture; no STOP
  authorization and no production relaunch happened from this lane. Nothing here was run
  against a live archive, a pod, or the network.

## A9 -- exact source, byte size, resolution (LF-normalized sha256; regenerated last)

Must-not-move (byte-identical, main-repo master `ef0a004584b7f6fd849c7e9409505d3494ff9949`
vs. worktree; the one intervening commit past this worktree's `ef0a00458` base does not
touch any of these five files, so the master-side digest is the same read from either sha):

| path | bytes (master) | sha256 (master) | sha256 (worktree) | match |
|---|---|---|---|---|
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\local_capture_runner_trades.py` | 5666 | `077294e24cd4d813dfe05b6bfefe480636bd6abca8beb2dc47285c0a9b6ea72c` | `077294e24cd4d813dfe05b6bfefe480636bd6abca8beb2dc47285c0a9b6ea72c` | MATCH |
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\local_capture_backfill.py` | 14321 | `4d685892c000623281f737d26e9fee909e1a067275e43dd4ea251cb28408949e` | `4d685892c000623281f737d26e9fee909e1a067275e43dd4ea251cb28408949e` | MATCH |
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\observation_support_census.py` | 17586 | `fed126cb92e4684d5e80feb3d1acf885e73d833c88ff29cddb24b374283babda` | `fed126cb92e4684d5e80feb3d1acf885e73d833c88ff29cddb24b374283babda` | MATCH |
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\observation_support_phases.py` | 5498 | `eca82038e9cd863894733dbfeaa9546702c04f9e5e853ab2125b7d08189c5b2c` | `eca82038e9cd863894733dbfeaa9546702c04f9e5e853ab2125b7d08189c5b2c` | MATCH |
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\capture_scheduler.py` | 21843 | `1517de7383facfc8607be6ecbf3f376c331eeea208f3a001b3814bc133c2e5c4` | `1517de7383facfc8607be6ecbf3f376c331eeea208f3a001b3814bc133c2e5c4` | MATCH |

Every digest above is a 64-character hex sha256, verified programmatically
(`len(hexdigest) == 64`) before being transcribed into this table. No Polymarket file
(`polymarket_*`) or `schedule_pointer.py` touched (`git status --short` above shows none).

Edited (owned) candidates, resolution "not applicable" (source text, not a decode/frame),
diffed against `ef0a00458` (this worktree's base; unaffected by the one commit main-repo
master has since gained):

| path | bytes master -> worktree | wc -l master -> worktree | sha256 master | sha256 worktree |
|---|---|---|---|---|
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\local_capture_runner.py` | 17989 -> 18383 | 299 -> 300 | `b67b59ac799f259c61b5b9a4cab99340276717463a605b3b6b6ec11f5d8e834d` | `482fb91ec07e9e65de0249f8748bbe75e71b863742951641961458e36b193068` |
| `C:\Users\neelj\nba-harness-h112\scripts\platformkit\ingame\local_capture_writer.py` | 7690 -> 8024 | 183 -> 185 | `7ba00c2200ecf53cba81ab3f3ecbb3ad80ea7233f0607d5094c8bdda72f8cee0` | `1827be16ab5365101ead156c95f60fc6855d830b22340f2f4d56d15fb61b6c94` |

New file: `C:\Users\neelj\nba-harness-h112\tests\platformkit\ingame\test_request_class_rows.py`,
193 lines (not a must-not-move file; new, so no master comparison applies).
