# S464: pointer and supervisor atomic writes survive a replace race

BUILD: 10 + 16 new tests pass, 45 pre-existing unchanged, preflight 9/9, 13 of 13 case rows PASS (before 2 of 9).

Worktree `C:/Users/neelj/nba-harness-h118` (bash `/c/Users/neelj/nba-harness-h118`). Candidate HEAD: `git rev-parse HEAD` = `ce759dbe41c62115247de4df7aaa34bbbf87f052`. Verification-base master: `git rev-parse master` = `ce759dbe41c62115247de4df7aaa34bbbf87f052`. EQUAL -- this worktree's HEAD and the shared master ref are the same commit as of this pass (unrelated lanes may move master again after this row lands).

## Binding before-condition, re-verified this session at that commit

- `scripts/platformkit/execution/schedule_pointer_writer.py:44` (pre-edit): bare
  `os.replace(temporary, pointer)` inside `write_pointer()`, its only write. Any
  OSError from open/write/fsync/replace propagates through the `:45-47` finally
  (removes the leftover temp file) to `main()`'s handler at `:62-64`, which prints
  `{"status":"REFUSED",...}` and returns 2. **Not silent** -- already a durable,
  visible raise today; the defect fixed here is the absence of retry before that
  raise, not the absence of a raise.
- `scripts/platformkit/ops/capture_supervisor.py:23-29` (pre-edit): module-level
  `_atomic(path, payload)`, no `self` -- cannot mutate a `Supervisor` instance's own
  counters. `os.replace` is its final line, reached from two sites: `:83` inside
  `_beat()` (heartbeat, every tick and after every `_record`), and `:109`/`:110`
  inside `_recover()` (rewriting a torn journal's `.partial` sidecar, then the
  truncated journal; `_recover` runs at process start and before every `_record`).
- Neither site is reached through S461's scope. S461 is **NOT landed** as of this
  dispatch: `scripts/platformkit/ingame/local_capture_writer.py:164` in this
  worktree is still the bare `os.replace(temporary, path)` (185 lines, no
  `REPLACE_RETRY_ATTEMPTS`), unlike the S461 AMENDMENT-1 candidate at
  `C:/Users/neelj/nba-harness-h116/scripts/platformkit/ingame/local_capture_writer.py`
  (read-only reference for this row, never imported).
- `capture_supervisor.py` had zero project imports before this row (argparse,
  ctypes, datetime, decimal, json, math, os, pathlib, re, shutil, subprocess, time,
  typing only).

## Deviation from the original CHANGE text, authorized by the dispatching orchestrator

`S464_spec.md` (as revised) says each file gains its **own** local
`REPLACE_RETRY_ATTEMPTS`/`REPLACE_RETRY_DELAY_SEC` constants and a **private** retry
loop, duplicated by value. This lane's dispatch prompt carries an "ORCHESTRATOR
AUTHORIZATION (overrides the generic clause)" that instead permits a **new sibling**
`scripts/platformkit/ops/atomic_replace.py`, shared by both sites. This build follows
that override: one retry helper (`replace_with_retry`), imported by both
`schedule_pointer_writer.py` and `capture_supervisor.py`. `capture_supervisor.py`'s
isolation is broken only for this one new, dependency-free sibling (itself: `os`,
`time`, `pathlib` only). If S461 lands first, `ArchiveWriter.atomic()`'s own inline
loop is a candidate to later point at this same helper; out of scope here.

## Path-form launch regression (FIX 1b, Tier 2 finding 1 -- memo note only)

`capture_supervisor.py:18`'s new project import breaks the path-form invocation
`docs/evidence/harness/S391_redeploy_checklist_2026-09-22.md:5` and `:204` document:
`python scripts/platformkit/ops/capture_supervisor.py --help` now raises
`ModuleNotFoundError: No module named 'scripts.platformkit'` (reproduced this
session), because a relative package import needs the package to be importable,
which only `-m` guarantees. `python -m scripts.platformkit.ops.capture_supervisor
--help` still works and prints usage (reproduced this session) -- this is the form
`CAPTURE_RESILIENCE_RUNBOOK.md:37,44` already uses, so the production runbook is
unaffected. The S391 checklist's path-form example is now stale and needs a
refresh to `-m`; that edit is outside this row's file ownership (S391's own doc),
so it is recorded here as a FIX note rather than applied.

## The sites, quoted verbatim post-edit (line numbers re-verified against the on-disk file this pass)

`schedule_pointer_writer.py:44-51`: `os.fsync` (44) -> `replace_with_retry(temporary, pointer)`
(45) -> `finally:` (46) -> the outer temp-file cleanup, wrapped `try/except OSError: pass`
(47-51, FIX 1b Tier 2 finding 3 -- a cleanup failure here never replaces the propagating
replace error; proven by `test_case8b_pointer_cleanup_failure_does_not_mask_replace_error`).

**AMENDMENT 2(b), Opus finding 2 -- declared uncounted by design** (the amendment's
either/or; no code change at the pointer site): neither the `finally` unlink above nor
`replace_with_retry`'s own exhaustion cleanup (the pointer's call at :45 passes no
`on_cleanup_error`) increments any counter, matching `_recover`'s two call sites below.
Counting stays scoped to `_beat` (all three `atomic_replace_*_total` counters) because
only `_beat` has a live `Supervisor` instance to carry a counter through its heartbeat --
`write_pointer`'s `main()` is a single-shot REFUSED/exit-2, not a running counter surface.

`atomic_replace.py:33-35,59-68` (FIX 1c re-cite, current on-disk lines; the round-2
suggestion `:33-34,57-61` was itself stale by the time this pass's own edit landed --
recomputed from disk, not carried forward blind): `replace_with_retry`'s signature now
takes `on_retry` alongside `on_cleanup_error` (33-35); AMENDMENT 2(a): `on_retry()` fires
once per retry, before the sleep, never on the final exhausted attempt or a same-attempt
success (59-61); the pre-existing cleanup-error callback is unchanged (64-68).

`capture_supervisor.py:102-118` (`_beat`): a local `_count_cleanup_error` closure (FIX 1b)
and a second local `_count_retry` closure (FIX 1c) each increment their own counter; both
are forwarded into `_atomic`, and both fields (`atomic_replace_cleanup_errors_total`,
`atomic_replace_retry_total`) are added to the heartbeat payload dict alongside the
pre-existing `atomic_replace_refused_total`.

`_recover()`'s two `_atomic` call sites (`.partial` sidecar, then the truncated journal)
are untouched -- both keep `durable=True` default, no `on_cleanup_error`, no `on_retry`
(counting stays scoped to `_beat`, the only site with a persistent counter surface), no
behavior change beyond the retry itself.

## The 9 CONSTRUCT cases, before values (corrected), and results

`before = 2 of 9` (`S464_spec.md`): cases 3 and 9 held on master already --
non-PermissionError raises unretried by construction, and (case 9, corrected
wording, Tier 2 finding 9) an open/write/fsync failure raises *before* the
retry-wrapped replace line is ever reached, regardless of durability
classification. Cases 1, 2, 5, 6, 8 failed (no retry seam existed). Cases 4 and 7
held functionally but had no retry seam or return-value contract to verify
against, so they count as "before FAIL" per the spec's acceptance rule.

| # | Case | Before | Test(s) | Result |
|---|------|--------|---------|--------|
| 1 | pointer: 3 failures then success | FAIL | `test_case1_pointer_retries_then_succeeds` | PASS |
| 1b | pointer: 4 failures then success (5th attempt) | FAIL | `test_case1b_pointer_succeeds_on_fifth_attempt` | PASS |
| 2 | pointer: fails all 5, destination unchanged, later publish succeeds | FAIL | `test_case2_pointer_exhausts_unchanged_destination_then_later_publish` | PASS |
| 3 | pointer: non-PermissionError raises unretried | PASS | `test_case3_pointer_nonpermission_raises_unretried` | PASS |
| 4 | pointer: first-try success, byte-identical to master | FAIL (no seam) | `test_case4_pointer_first_try_success_byte_identical_to_master` | PASS |
| 5 | supervisor `_beat` (durable=False) exhausts, counter +1, next beat carries it | FAIL | `test_case5_beat_durable_false_counts_then_next_beat_carries_it` | PASS |
| 5b | supervisor `_beat` transient recovery (4 failures then success) leaves counter at 0 | FAIL | `test_case5b_beat_transient_recovery_leaves_counter_at_zero` | PASS |
| 6 | supervisor `_recover` (durable=True) exhausts, raises unhandled | FAIL (raises after 1 attempt, no bound) | `test_case6_recover_durable_true_raises_unhandled` | PASS |
| 7 | supervisor, real caller sites (`_beat`, torn-tail `_recover`), first-try success, byte-identical | FAIL (no seam) | `test_case7a_beat_...`, `test_case7b_recover_...` | PASS |
| 8 | cleanup failure does not mask the primary outcome (both durable values) | FAIL | `test_case8_cleanup_failure_does_not_mask_primary_outcome[False/True]` | PASS |
| 8a | `_beat`-path cleanup failure counted by name, outcome unchanged | FAIL | `test_case8a_beat_cleanup_failure_counted_and_does_not_mask_outcome` | PASS |
| 8b | pointer-site cleanup failure does not replace the replace error | FAIL | `test_case8b_pointer_cleanup_failure_does_not_mask_replace_error` | PASS |
| 9 | retry scoped to `os.replace` only -- open/write/fsync raise unretried, both sites | PASS | `test_case9_pointer_open_write_fsync_raise_unretried`, `test_case9_retry_scoped_to_replace_only` | PASS |

Two new test files (AMENDMENT 1(a)): `tests/platformkit/execution/test_schedule_pointer_writer_retry.py`
(10 tests: cases 1, 1b, 2, 3, 4, 9-pointer x3, 8b, constants) and
`tests/platformkit/ops/test_capture_supervisor_atomic_retry.py` (FIX 1c: 16
tests, +1 -- cases 5, 5b, 6, 7a, 7b, 8a, 8 x2, 9 x6, constants, plus
`test_helper_on_retry_fires_once_per_retry_before_success`, AMENDMENT 2(a)).
`tests/platformkit/ops/test_atomic_replace_sites.py` removed.

Byte comparisons (AMENDMENT 1(b)): case 4 and case 7a/7b assert against a
checked-in literal (`EXPECTED_POINTER_BYTES` / `_expected_first_beat_bytes()` /
literal journal and `.partial` bytes), each captured once from an unmocked run
this session, never a same-test reference call. Case 5 asserts each of the 9
heartbeat fields (FIX 1c: was 8, `atomic_replace_retry_total` added) against
literal values (`pid` via a live `os.getpid()` call, the same OS fact the code
itself reads) and `set(heartbeat)` against the exact 9 keys.

Timing (AMENDMENT 1(c)): every sleep/attempt count in both files is a literal
(`5`, `[0.1, 0.1, 0.1, 0.1]`, etc.); `test_retry_constants_are_five_and_tenth_second`
in each file checks `REPLACE_RETRY_ATTEMPTS == 5` and `REPLACE_RETRY_DELAY_SEC ==
0.1` separately.

Test isolation note: `os.replace`/`os.remove`/`time.sleep`/`Path.open`/`os.fsync`
are monkeypatched on the shared module objects both call sites read from
dynamically at call time, matching this repo's existing convention
(`tests/platformkit/ingame/test_local_capture_failures.py:150`). No real
`time.sleep` runs in any of the 26 test invocations across both files.

## Readers checked (A5)

`git grep -l schedule_pointer_writer` over `tests/` and `scripts/` names 4 readers:
`tests/platformkit/ingame/test_capture_schedule_pointer.py`,
`test_capture_schedule_pointer_1c.py`, `test_capture_schedule_pointer_1d.py` (53
tests total) and `scripts/platformkit/execution/schedule_d1.py` (imports
`write_pointer`). All 53 reader tests still pass unchanged after this edit (below);
`schedule_d1.py` is untouched. `capture_deploy_preflight.py:148-153` reads the
supervisor heartbeat generically by key suffix -- the new
`atomic_replace_refused_total`, `atomic_replace_cleanup_errors_total` and (FIX
1c) `atomic_replace_retry_total` keys are additive and picked up automatically.

## Pre-existing test counts (STEP 0 premise check, before and after FIX 1c)

| File | Tests | Result |
|---|---|---|
| `tests/platformkit/ops/test_capture_supervisor.py` | 45 | 45 passed, unchanged |
| `tests/platformkit/ingame/test_capture_schedule_pointer.py` + `_1c` + `_1d` | 53 | 53 passed, unchanged |
| `tests/platformkit/execution/test_schedule_pointer_writer_retry.py` (split) | 10 | 10 passed, unchanged by FIX 1c |
| `tests/platformkit/ops/test_capture_supervisor_atomic_retry.py` (split) | 16 | 16 passed (+1 this pass) |

No pre-existing test file exists for `schedule_pointer_writer.py` alone and none of
the four pre-existing files above were edited.

## S461 consolidation note (updated, FIX 1d)

S461 LANDED at 0378a2352, inline inside `ArchiveWriter.atomic()`. This row's local helper (`atomic_replace.replace_with_retry`) is kept per the spec's unlanded-at-build-time clause; unifying needs a refusal callback on the durable path and a non-Permission error hook, neither of which it has today.

SAME (vs `local_capture_writer.py:163-208`, post-landing): 5 attempts, 4 sleeps of 0.1s before each retry, PermissionError-only retry, a counted retry before each sleep, a best-effort remove on exhaustion with the cleanup error counted and never masking. DIVERGENT: S461 counts `atomic_replace_refused` for every source including durable ones that then re-raise, while this row counts a refusal only for the heartbeat (`_beat`, `durable=False`; the pointer and `_recover` sites are durable and uncounted by design, AMENDMENT 2(b)); S461 counts `<source>_write_errors` on open/write/fsync and non-Permission replace failures, which this helper has no hook for (those failures still raise unretried per case 9, just uncounted); and the soft/durable selector differs (S461: literal `source == "heartbeat"` string; this row: an explicit `durable: bool` keyword).

Two notes carried forward (Tier 2 findings 10, 12; no code change): the retry sleep bypasses `Supervisor`'s injected `sleep` seam (at most 0.4s per exhausted beat, harmless); an open/write/fsync failure on the `.tmp` file, before the retry-wrapped replace is reached, still hard-raises out of `_beat`/`_loop` -- the heartbeat is "soft" only at the replace step.

## S466 ordering

`S466_spec.md` also edits `capture_supervisor.py` and must land AFTER this row,
preserving: the `_atomic(path, payload, *, durable=True, on_cleanup_error=None,
on_retry=None) -> bool` signature and its return-value contract, and the three
`atomic_replace_*_total` heartbeat fields (`refused`, `cleanup_errors`, and FIX
1c's `retry`). This row's diff to `capture_supervisor.py` is scoped to
`_atomic`, `__init__`, and `_beat` only.

## FIX 1b -- round-1 findings (both tiers), all fixed or noted; see git history
for the pre-FIX-1b diff. Tier 1 BLOCKING (2/2): wrong test-file paths -- split
into the two spec-named files; case 4/7 never byte-compared and case 7 bypassed
the real caller sites -- both now literal/checked-in comparisons through
`_beat`/`_recover`. Tier 2 CORRECTIONS (9/9) and NOTES (3/3): by-path launch
regression documented (S391 outside this row); `on_cleanup_error` added and
wired to `atomic_replace_cleanup_errors_total`; pointer `finally` unlink no
longer masks the replace error; timing asserted as literals, constants checked
separately; missing cases (1b, 2-extended, 5b) added; case 9 parametrized over
`{open, write, fsync}` at both sites; cases 4/7/5 de-self-referenced; citation
`:44-45` -> `:45-46`; case table before-column and case-9 reason fixed; the two
policy/timing notes recorded in the consolidation note above.

## FIX 1c -- every round-2 finding and what changed

Tier 1 (codex sol), BLOCKING, both fixed:
1. `atomic_replace.py:33` -- retries were invisible (only `on_cleanup_error`
   existed; reproduced this session: `on_retry` absent from the signature) --
   added an `on_retry` callback, threaded through `_atomic`, wired in `_beat`
   to a new `atomic_replace_retry_total` counter emitted in the heartbeat.
   `test_helper_on_retry_fires_once_per_retry_before_success` asserts the
   reproduction's own numbers (3 denials then success -> 3); cases 5/5b assert
   4 (4 denials then success/exhaustion).
2. Memo `:80` tripped the vocab scanner's bare-integer check on a banned
   two-digit token embedded in the stale line-range citation (reproduced this
   session via `contract_preflight`) -- citation recomputed from the post-edit
   file on disk rather than carried forward (the round-2 suggestion was itself
   stale by the time this pass's own `on_retry` edit landed); now
   `:33-35,59-68`; preflight re-run below to confirm PASS.

Tier 2 (Opus), CORRECTIONS: 1 is the same fix as sol 1. 2, pointer-site cleanup
failures uncounted -- declared uncounted by design per the amendment's
either/or (reasoned in the sites-quoted section above); no code change at the
pointer site or in `_recover`. 3, case-6 Before cell said PASS, contradicting
the memo's own prose and master's real 1-attempt behavior -- corrected to FAIL.
4, bytes column claimed "LF-normalized" while holding on-disk CRLF sizes --
relabeled "bytes (on-disk)" below; sha256 stays genuinely LF-normalized
(`tr -d '\r' | sha256sum`, regenerated this pass). NOTES: cases 7a/7b now
assert `sleeps == []`; case 6 now asserts the journal unchanged and no
leftover `.tmp`; the self-contradictory "lags" sentence is removed (identities
below).

## FIX 1d -- every round-3 finding and what changed

Tier 1 (sol), all fixed: 1, S461 is now an ancestor of HEAD -- the A9 row for `local_capture_writer.py` was the pre-S461 blob, regenerated from disk below; landing status/consolidation wording updated above. 2, memo reported 25 test invocations against its own 10 + 16 -- corrected to 26. 3, test-file comment said "two new counters" against three declared keys -- corrected to "three".

Tier 2 (Opus), all fixed: 1 same as sol 1. 2, the false "different sha" sentence removed at both places; HEAD/master now printed as two separate full shas with an explicit EQUAL statement. 3, memo now opens with a one-line BUILD result. 4, S461 section rewritten (landed at 0378a2352, "without a metrics gap" overclaim dropped, same/divergent recorded above). NOTES: 5, a docstring line added stating `on_retry`/`on_cleanup_error` must not raise (no behavior change). 6-8 (supervisor/pointer temp leaks, counter reset on process restart) unchanged from FIX 1c -- already register items or already conforming, no code change this pass.

## A9 artifact identities (regenerated this pass, `tr -d '\r' | sha256sum`)

Owned files (post-FIX-1d, this worktree; bytes are raw on-disk sizes, CRLF where the file has it -- sha256 is LF-normalized):

| File | bytes (on-disk) | lines | sha256 (LF-normalized) |
|---|---|---|---|
| `scripts/platformkit/ops/atomic_replace.py` | 3678 | 76 | `3713e3b05a1cb9152aba16147d4bd46f71903455eb820dda224b4a06e21c5cd7` |
| `scripts/platformkit/execution/schedule_pointer_writer.py` | 3261 | 74 | `60083a06dc144c604e138569e6d7926d813504035dbaffe1c0253931b5a54ad1` |
| `scripts/platformkit/ops/capture_supervisor.py` | 12965 | 277 | `73159b52be3e7c696cbbc9e99c9097afd408a4493eb7c6a7d9a9f8db2968af51` |
| `tests/platformkit/execution/test_schedule_pointer_writer_retry.py` | 9077 | 221 | `2f7bc70cb0ad780d300730895d0da48509387e181e05b5d244f179966111a965` |
| `tests/platformkit/ops/test_capture_supervisor_atomic_retry.py` | 11239 | 251 | `d3f65d3eab930c0271966aaa72d8fa25e95fdcbb04b435fb16ff2850b16b9849` |

Must-not-move files, re-confirmed byte-identical to master this pass (`git diff --stat master -- <paths>` empty):

| File | bytes (on-disk) | lines | sha256 (LF-normalized) |
|---|---|---|---|
| `scripts/platformkit/ingame/local_capture_writer.py` | 9963 | 226 | `ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e` |
| `scripts/platformkit/ingame/schedule_pointer.py` | 9549 | 196 | `8f9dbae90ff2597a96d17b83f6c5f8b7b98e731ddaf76b86aba02b8abb8aebf0` |
| `scripts/platformkit/ingame/capture_schedule_loader.py` | 3350 | 50 | `6e5bbdd3aa0a9fce855be37ed9d6311a010bf05b0878bd124dbdcb90854d5820` |
| `scripts/platformkit/ingame/local_capture_runner.py` | 18383 | 300 | `482fb91ec07e9e65de0249f8748bbe75e71b863742951641961458e36b193068` |
| `scripts/platformkit/ingame/polymarket_live_capture.py` | 15122 | 276 | `28f5f5ecf54d2eee2b25e7388eb88087f6c213b9dd8c2e75463e2ffae3eb2073` |

Candidate HEAD: `git rev-parse HEAD` = `ce759dbe41c62115247de4df7aaa34bbbf87f052`. Verification-base master: `git rev-parse master` = `ce759dbe41c62115247de4df7aaa34bbbf87f052`. EQUAL -- same commit as of this pass (unrelated lanes may move master again after this row lands).

## NOT VERIFIED

- No real transient Windows `PermissionError` (WinError 5 sharing violation) was
  observed or replayed for either site this session -- every case is a
  CONSTRUCT test with an injected `os.replace`/`os.remove`/`os.fsync`/
  `Path.open`/`tempfile.NamedTemporaryFile` failure, never a real filesystem
  race. Adoption proof is only available from the next owner-visible relaunch.
- No running capture child or supervisor process was touched, started, or
  stopped; `run()`/`_loop()` were not exercised end-to-end -- `_beat`,
  `_record`, and `_recover` were called directly, narrower but sufficient for
  the retry/return/counter contract.
- `python scripts/platformkit/ops/capture_supervisor.py --help` still fails
  with `ModuleNotFoundError` (documented, not fixed -- the orchestrator-
  authorized shared-module design requires `-m`; the S391 checklist refresh is
  a follow-on, not this row's file).
- Pointer-site and `_recover` cleanup failures remain genuinely uncounted (by
  design, AMENDMENT 2(b)); if a future row needs that visibility, it is new
  scope, not a defect here.
- No pod, no network. `git commit` was not attempted (sandbox may deny it);
  files are left on disk for `lane_commit`.
