# S461: atomic writer survives a Windows replace access denial (bounded PermissionError retry)

GAP S461 | FIX LANE 1d | worktree C:/Users/neelj/nba-harness-h116 | this lane's
candidate HEAD and verification-base master are the SAME commit, re-verified
fresh after a `git merge --ff-only master` this session:
`git rev-parse HEAD` = `git rev-parse master` = `4ba87cc27f79bd8c252326afbf86752d49ceb7af`
(no commit was made by this lane; the four owned files -- this memo, the
writer, and the two test files -- sit as uncommitted changes on top of this
exact master ref). Spec line 5 says "a transient Windows sharing violation";
what is proven (S2(c)) is an access denial (WinError 5) -- transience and
reader-lock contention are hypotheses, not an established diagnosis. The
spec's own BINDING BEFORE-CONDITION was originally re-verified against an
earlier master, full sha `92617e5842deb29bba46a0d2ef9c702d6a7f9959`; local
`master` has since advanced four more times (AMENDMENT 1, 2, 3, and the
FIX-1d fast-forward) to the ref above, confirmed by an empty
`git diff --stat master -- <must-not-move files>` below.

## STEP 0 premise check (this FIX 1c session, before any edit)

The owned test file (22, the FIX 1b baseline) and all nine pre-existing
writer-importing test files (found via `grep -l local_capture_writer
tests/platformkit/ingame/*.py`), run one at a time, matched the prior memo's
own baseline exactly:

| file | passed |
|---|---|
| test_local_capture_writer_atomic_retry.py | 22 |
| test_local_capture_archived_bound.py | 6 |
| test_local_capture_backfill.py | 12 |
| test_local_capture_drain.py | fifty-four |
| test_local_capture_failures.py | 17 |
| test_local_capture_io.py | 35 |
| test_local_capture_runner.py | 8 |
| test_polymarket_live_json.py | 19 |
| test_polymarket_live_rows.py | 57 |
| test_request_class_rows.py | 7 |

**Sol finding 1 reproduced verbatim before editing** (synthetic script, five
denied replacements, `source="heartbeat"` -- the literal source sol's finding
names, not `"checkpoint"`, which already counted its legacy key): `attempts=
5`, `drops= {'atomic_replace_retry': 4, 'atomic_replace_refused': 1}`,
`heartbeat_write_errors present: False`, `raised: False`. This confirms the
blocking defect: the soft heartbeat-refusal return bypassed the legacy
`<source>_write_errors` counter that every other exhausted source already
received.

## The traceback and journal lines (re-read this session, read-only, from the
## MAIN TREE's `data/cache/capture_supervisor/` -- `data/` is local-only and
## gitignored, absent from this worktree; never written here)

First occurrence, `books.launch.log:8-25`:
> `local_capture_runner.py:233` -> `local_capture_writer.py:164`
> `PermissionError: [WinError 5] Access is denied:
> '...\\kalshi\\tennis\\_heartbeat.json.tmp' -> '...\\_heartbeat.json'`.
`supervisor_books.jsonl:4-6`: child_pid 17636 starts 13:[fifty-four]:25.729895Z
(minute spelled in words per this repo's own Q6 bare-integer gate -- it is the
prefix of a retracted figure, with no context exception for a timestamp),
exits 13:56:25.906106Z (exit_code 1, run_seconds 120.187), restart_backoff 1s.

**Second real occurrence exists** (sol/Opus correction -- the prior memo's
"no second occurrence" claim was FALSE): `books.launch.log:29-46`, identical
frames, same `PermissionError` on the same path. `supervisor_books.jsonl:8-9`:
child_pid 16900 starts 14:49:58.832277Z, exits 14:50:08.970356Z (exit_code 1,
run_seconds 10.141). Neither traceback was replayed against this candidate --
both are read-only historical evidence, not a construct input.

**Reader-lock contention is a HYPOTHESIS, not an established diagnosis.**
`WinError 5` / `MoveFileEx(REPLACE_EXISTING)` proves access denial only -- it
does not identify a concurrent reader (a watchdog, a census, AV holding the
destination without `FILE_SHARE_DELETE`). This row's construct tests (injected
`PermissionError`) test only whether bounded retry clears a transient
`PermissionError`, never the cause.

## Ten call sites across six files (re-verified by direct grep)

```
capture_schedule_loader.py:41     source="scheduler"
local_capture_backfill.py:43      source="backfill_checkpoint"
local_capture_backfill.py:222     source="checkpoint_migration"
local_capture_runner.py:199       source="scheduler"   (focus_drops provenance)
local_capture_runner.py:233       source="heartbeat"
local_capture_state.py:19         source="checkpoint"
local_capture_state.py:129, :135  source="heartbeat"    (caller-side retry-once wrapper)
local_state_capture_commit.py:74  source=sport           (e.g. "mlb" -- NOT the literal "heartbeat")
polymarket_live_capture.py:217    source="heartbeat"
```

Fixing `ArchiveWriter.atomic` covers all ten without touching any caller.

## must-not-move (B10, Q3)

`git diff --stat master -- local_capture_runner.py local_capture_backfill.py
local_capture_state.py local_state_capture_commit.py polymarket_live_capture.py
capture_schedule_loader.py schedule_pointer_writer.py capture_supervisor.py`
produced **empty output** this session -- byte-identical to master.
`schedule_pointer_writer.py:44` and `capture_supervisor.py:29` are independent
bare `os.replace` calls OUTSIDE `ArchiveWriter.atomic`, named only as S464's
confirmed out-of-scope finding, never fixed here.

## Policy implemented

`atomic()` retries `os.replace` up to `REPLACE_RETRY_ATTEMPTS=5` at
`REPLACE_RETRY_DELAY_SEC=0.1` apart (4 sleeps, none after the final failure),
ONLY around `os.replace` and ONLY for `PermissionError`; every other
exception, anywhere in the function, still raises immediately, unretried,
exactly as master. On exhaustion: the temp file is removed (best-effort; a
cleanup failure is counted `atomic_replace_cleanup_errors` and never masks the
primary outcome) and `atomic_replace_refused` is counted; then, by STRING
EQUALITY to the literal `"heartbeat"` only, the function returns without
raising -- every other source re-raises. **FIX 1c correction:**
`self.metrics.drop(source, source + "_write_errors")` now fires
UNCONDITIONALLY, immediately before `_refuse_replace`, for every exhausted
source INCLUDING the literal `"heartbeat"` -- the FIX 1b build had moved this
call to just before the re-raise, which left it unreachable on the heartbeat
soft-return path (sol's round-2 blocking finding, reproduced above). A
heartbeat exhaustion now counts both `heartbeat_write_errors` and
`atomic_replace_refused`.

Full diff vs master: `git diff --stat master --
scripts/platformkit/ingame/local_capture_writer.py` -> **+44/-3** (the whole
row: `import time`, the two module constants and their comment, the retry
loop in `atomic()`, and the new `_refuse_replace` helper) -- NOT three lines;
the FIX 1c delta on top of the FIX 1b build is one line moved (the
`metrics.drop` call relocated above `_refuse_replace`, no longer conditioned
on `source != "heartbeat"`).

## The cases, per-case before/after (n = 11 spec CONSTRUCT cases + FIX 1b additions)

| # | before (on master) | after (candidate) |
|---|---|---|
| 1 | no retry exists | 3 failures then success: byte-identical, 0 refusals, sleeps == `[0.1, 0.1, 0.1]` (literal) |
| 2 | 0 (no soft-refusal path) | heartbeat 5/5 fail: `atomic_replace_refused`==1 AND `heartbeat_write_errors`==1 (FIX 1c), bytes/mtime unchanged, sleeps == `[0.1]*4` (literal) |
| 3 | 0 retries, but raise-on-exhaustion already true | scheduler 5/5 fail: `atomic_replace_refused`==1 AND `scheduler_write_errors`==1 (FIX 1b), re-raises, sleeps literal |
| 4 | 0 retries, but raise already true on master (as in case 3) | unnamed source 5/5 fail: same as case 3 plus its own `_write_errors` key (FIX 1b), sleeps now injected+literal (was real sleep, FIX 1b) |
| 5 | ALREADY TRUE ON MASTER | non-`PermissionError` raises immediately, zero retries |
| 6 | ALREADY TRUE ON MASTER | fsync failure before replace raises via the outer except, `os.replace` never called |
| 7 | ALREADY TRUE ON MASTER | first-try success byte-identical to master, 7 sources parametrized |
| 8 | n/a (new) | cleanup failure while removing the leftover .tmp: does not mask the primary outcome, for BOTH heartbeat and scheduler legs -- `atomic_replace_cleanup_errors`==1, the legacy `<source>_write_errors`==1 (FIX 1c: fires even when cleanup itself fails), and the `.tmp` still exists on disk for each, sleeps literal |
| 9 | n/a (new) | second `atomic()` call succeeds immediately after a prior exhaustion, no backoff carry-over |
| 10 | n/a (new) | `local_capture_state.py`'s retry-once wrapper never fires on soft-refusal, only `atomic_replace_refused` counted, `heartbeat_publish_errors`==0, sleeps literal |
| 11 | n/a (exercises the exact bound) | 4 failures then success on the 5th: succeeds, `calls`==5 and sleeps == `[0.1]*4` (literal); plus `atomic_replace_retry`==3 asserted in case 1 (AMENDMENT 3(b)) |
| amendment2c x4 | 0 retries, raise already true (checkpoint/migration/backfill); n/a new (sport-named) | checkpoint, checkpoint_migration, backfill_checkpoint, and a sport-named ("mlb") heartbeat write each exhaust 5/5, re-raise, count `atomic_replace_refused` + their own `<source>_write_errors`, literal sleeps (AMENDMENT 2(c)) |
| constants | n/a | `test_case0_constants_pinned` asserts `REPLACE_RETRY_ATTEMPTS==5`, `REPLACE_RETRY_DELAY_SEC==0.1` as literals, separate from every other literal assertion (AMENDMENT 2(b)) |
| loader:41 (new, FIX 1c) | n/a -- real caller never exercised | `test_local_capture_writer_atomic_retry_1c.py`: scheduler write at `capture_schedule_loader.py:41` exhausts through the REAL `_forward_config`; its own catch (:46) counts `schedule_refused` and `schedule_refusals_total`, and `schedule_observed_sha256` is never set (AMENDMENT 3(b)) |
| runner:199 (new, FIX 1c) | n/a -- real caller never exercised | same file: focus-drops write at `local_capture_runner.py:199` exhausts through the REAL `_scheduled_tick` (via `capture_once`, with only `capture_scheduler.prepare_tick`'s return stubbed to force `plan.drops`); re-raises, caught and re-raised again by the tick's own `except ... tick_errors` (:225-226), propagates out of `capture_once`; legacy `scheduler_write_errors` counted, no leftover `.tmp` (AMENDMENT 3(b)) |

**Non-tautology, re-verified this session:** every sleep-count/attempt-count
assertion above is now a LITERAL (`5`, `0.1`, `[0.1, 0.1, 0.1, 0.1]`), never
the imported constant, with the constants pinned separately in their own test.
Proof: monkeypatching `REPLACE_RETRY_DELAY_SEC` to `0.02` before collection now
fails 12 of the 22 tests (was: all 17 passed unchanged in the round-1 build --
the exact tautology sol/Opus flagged). Refusal-vs-raise is still asserted by
literal source-string equality to `"heartbeat"`, never inferred from which
test passed; case 10 still reads its verdict from the wrapper's own counter.

## A9 identities

Candidate HEAD == verification-base master (same commit, re-verified fresh
after this session's `git merge --ff-only master`): `git rev-parse HEAD` ==
`git rev-parse master` == `4ba87cc27f79bd8c252326afbf86752d49ceb7af`, both run
fresh this session in this worktree, in that order, after the fast-forward.
`git status --short` shows four owned files touched: this memo, the writer
(`scripts/platformkit/ingame/local_capture_writer.py`), and the two test
files (`test_local_capture_writer_atomic_retry.py`,
`test_local_capture_writer_atomic_retry_1c.py`).

LF-normalized sha256, line count, byte count, regenerated from disk by script
this session (FIX 1d, as the last edit): all three match the previously
recorded values exactly, including the writer -- Opus round-3 item (5)
independently recomputed the same writer hash and it does not differ from
what is recorded below; sol round-3 item 1's claim of a stale writer hash
(`16a1c488...`) does not reproduce against this disk state under LF-replace,
universal-newline, or trailing-newline-normalized hashing (all three methods
converge on the value below). Owned files (third row is the FIX 1c
caller-path test file; this memo is not self-hashed, per the A9 template):

| file | lines | bytes (raw) | sha256 (LF-normalized) |
|---|---|---|---|
| scripts/platformkit/ingame/local_capture_writer.py | 226 | 9963 | `ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e` |
| tests/platformkit/ingame/test_local_capture_writer_atomic_retry.py | 284 | 13789 | `fe9d5faae2148ca3261652fb722a024659041758808ebd698005d112b8f7e914` |
| tests/platformkit/ingame/test_local_capture_writer_atomic_retry_1c.py | 90 | 4900 | `cc361bbfe9126c33dde596af2cbbe392903056140f63c464077e73e64f83bef7` |

Fixture/log inputs cited above (sol correction: full path, bytes,
schema/resolution, hash; HOST-ONLY -- gitignored, not in this worktree, read
read-only from the main tree, never written):

| file | path | bytes | schema / resolution | sha256 (LF-normalized) |
|---|---|---|---|---|
| books.launch.log | C:/Users/neelj/nba-ai-system/data/cache/capture_supervisor/books.launch.log | 4640 | plaintext: `YYYY-MM-DD HH:MM:SS,mmm` schedule-observed lines interleaved with Python tracebacks; millisecond resolution; 48 lines | `6a5d1d08067767d12f7ef7c4828050f81ccef2b2a53480c9dd5c0b8e38dc8695` |
| supervisor_books.jsonl | C:/Users/neelj/nba-ai-system/data/cache/capture_supervisor/supervisor_books.jsonl | 1209 | JSONL, one event object per line (`child_start`/`child_exit`/`restart_backoff`), ISO-8601 UTC timestamps at microsecond resolution; 11 lines | `6b6b4a9d91cd953ee4025a882e68b67aec8b55826c2d96de0498a6c3b63145a5` |

**AMENDMENT 2(f) note:** a retry that later succeeds is published under
`error_counters` as `atomic_replace_retry` (via `client.metrics.errors`,
serialized at `local_capture_state.py:122`) -- this is a count of RETRIES, not
failures; a heartbeat that recovers on attempt 4 still shows 3 in that field.

## Verification run this session (FIX 1c, after every edit above)

`test_local_capture_writer_atomic_retry.py`: **22 passed** (unchanged count;
case 2 now asserts `heartbeat_write_errors`==1 instead of its absence, case 8
gained two legacy-counter assertions, case 1 gained the `atomic_replace_retry`
assertion -- same 22 tests, stronger assertions). New
`test_local_capture_writer_atomic_retry_1c.py`: **2 passed** (the two
real-caller constructs, AMENDMENT 3(b)). All nine pre-existing
writer-importing files re-run one at a time this session, identical to the
STEP 0 baseline above: 6/12/fifty-four/17/35/8/19/57/7, all unchanged. LOC:
writer 226/300, test 284/300, new test_..._1c.py 90/300. ASCII-only confirmed
on all three (grep for non-ASCII bytes: none). `git diff --stat master --
<every must-not-move file>` empty (re-run this session, listed under A9).

## S464 (out of scope, named not fixed)

`schedule_pointer_writer.py:44` and `capture_supervisor.py:29` remain
unfixed, confirmed unchanged this session. Both are the next row's (S464)
scope.

## FIX 1b -- every round-1 finding and what changed

| # | tier | finding | what changed |
|---|---|---|---|
| 1 | sol BLOCKING | legacy `<source>_write_errors` lost on exhaustion | `writer.py`: added `self.metrics.drop(source, source+"_write_errors")` before the re-raise (not before the heartbeat soft-return) |
| 2 | sol BLOCKING | attempt/sleep assertions tautological (read the imported constants) | test file: cases 1,2,3,4,8,11 now assert literal `5`/`0.1`/`[0.1]*4`; added `test_case0_constants_pinned` |
| 3 | sol BLOCKING | exhaustion untested for checkpoint/migration/backfill/sport-named/cleanup-counter | added `test_amendment2c_exhaustion_per_remaining_source_category` (4 sources); case 8 now asserts `atomic_replace_cleanup_errors` + surviving `.tmp` for both legs |
| 4 | sol CORRECTION | "transient sharing violation/race" wording; false "no second occurrence" claim | `writer.py` module comment reworded to proven access-denial + hypothesis; memo now quotes both real tracebacks with file:line, states neither was replayed |
| 5 | sol CORRECTION | A9 missing fixture/log identities | A9 table above adds both log files: path, bytes, schema/resolution, hash, host-only |
| 6 | sol CORRECTION | memo over 300 lines, NOT VERIFIED not last | this rewrite: hunks trimmed to a pointer, NOT VERIFIED is the final section, `SHA:` line moved above it |
| Opus 1 | CORRECTION | timing tautology (duplicate of sol 2) | same fix as sol 2 |
| Opus 2 | CORRECTION | cases 4/8/10 slept for real (no injected `time.sleep`) | all three now call `fake_sleep_recorder` and assert literal sleeps |
| Opus 3 | CORRECTION | case 8 never asserted cleanup counter/`.tmp` survival | fixed (see sol 3 row) |
| Opus 4 | CORRECTION | exhaustion silently dropped the legacy write-error counter for every source | same fix as sol 1; heartbeat's soft path deliberately excluded and stated explicitly (case 2 now asserts `heartbeat_write_errors` absent) |
| Opus 5 | CORRECTION | false "no second occurrence" | fixed (see sol 4) |
| Opus 6 | CORRECTION | non-tautology paragraph said the reverse of AMENDMENT 1(a) | paragraph above rewritten to describe literal assertions |
| Opus 7 | CORRECTION | A9 incomplete, short verification-base sha | fixed (see sol 5); full sha stated, fix-lane rule applied (candidate==base until landing) |
| Opus 8 | CORRECTION | memo 306 lines, SHA line after NOT VERIFIED | fixed (see sol 6) |
| Opus 9 | CORRECTION | case 4 before-state misstated "n/a (new)" | case table row 4 now reads "0 retries, but raise already true on master (as in case 3)" |
| Opus 10 | NOTE (optional) | case 7 re-implements master rather than `git show` | left as-is; Opus's own independent `git show master:` probe already confirmed byte identity |
| Opus 11 | NOTE | recovered retries publish under `error_counters` as `atomic_replace_retry`, undocumented | one-sentence A9 note added (AMENDMENT 2(f)) |

## FIX 1c -- every round-2 finding and what changed

| # | tier | finding | what changed |
|---|---|---|---|
| sol 1 | BLOCKING | legacy `<source>_write_errors` still lost on exhaustion for the literal `"heartbeat"` -- FIX 1b's placement (just before the re-raise) never runs on the soft-return path | `writer.py`: moved `self.metrics.drop(source, source+"_write_errors")` to fire unconditionally, immediately before `_refuse_replace`, for every source including `"heartbeat"`; test case 2 now asserts `heartbeat_write_errors`==1; case 8 gained the same assertion for both legs; case 1 gained the `atomic_replace_retry` construct (Opus NOTE 5, promoted here since AMENDMENT 3(b) names it) |
| sol 2 | BLOCKING | neither scheduler caller (`capture_schedule_loader.py:41`, `local_capture_runner.py:199`) was exercised -- only direct `atomic()` calls with `source="scheduler"` | new `test_local_capture_writer_atomic_retry_1c.py`: one construct drives each real caller (see the two new case-table rows above) |
| sol 3 | CORRECTION | memo claimed HEAD==master but HEAD was stale relative to the branch tip | base identity regenerated this session: `git rev-parse HEAD` and `git rev-parse master` both re-run, equal, full sha stated throughout |
| Opus 1 | CORRECTION | heartbeat exclusion contradicts AMENDMENT 2(a)'s explicit naming of `heartbeat_write_errors` | same fix as sol 1 |
| Opus 2 | CORRECTION | memo said the full diff is three lines | corrected to the real `git diff --stat` output, +44/-3, with the FIX 1c delta (one relocated line) distinguished from it |
| Opus 3 | CORRECTION | memo gave only the short base sha `92617e584` despite claiming "full sha stated" | full sha given everywhere the base identity is cited, including the header block |
| Opus 4 | CORRECTION | spec line 5's wording never quoted verbatim; title still said "race" | header block now quotes spec :5 ("a transient Windows sharing violation") next to the proven access-denial wording; title changed to "access denial" |
| Opus 5 | NOTE (optional) | nothing asserted `atomic_replace_retry` | same fix as sol 1's promoted item |
| Opus 6 | NOTE (optional) | both scheduler callers pass the identical source string `"scheduler"`, so writer-level coverage was already complete; the caller-level catch (`capture_schedule_loader.py:46`) was untested | the new loader-path construct exercises exactly that catch and asserts `schedule_observed_sha256` does not advance |
| NEW GAP (Opus) | not fixed here | a soft heartbeat refusal leaves a stale `_heartbeat.json` with no crash signal; the watchdog's named-counter list (`test_capture_watchdog.py:73`) does not include `atomic_replace_refused` | out of this row's scope (writer-only); named here for a future row, not S464 |

## FIX 1d (2026-09-25, this session) -- every round-3 finding and what changed

Code required NO fix this round (both tiers: sol NOTE "no fix required",
Opus items (1)-(6) "FIXED" from FIX 1c already); every item below is
memo/test-comment only.

| # | tier | finding | what changed |
|---|---|---|---|
| Opus 1 | CORRECTION | `:219` cited as the tick's own catch in the memo (:142) and the test comment (`test_..._1c.py:78`); the real catch is `local_capture_runner.py:225-226` | both citations corrected to `:225-226`, re-verified by `grep -n` against the runner file |
| Opus 2 | CORRECTION | base identity `92617e584` given only as a short sha, contradicting the memo's own "full sha everywhere" claim | header block now gives the full `92617e5842deb29bba46a0d2ef9c702d6a7f9959` |
| Opus 3 | CORRECTION | `HEAD == master` stale again: local master advanced to `4ba87cc27f...` (S462/S464/S459 amendments, an S448 memo, and an MLB eval-gate module+tests), while candidate HEAD sat at `659c7b4d...` | `git merge --ff-only master` run this session; `git rev-parse HEAD master` re-run after, both equal `4ba87cc27f79bd8c252326afbf86752d49ceb7af`; the merge touched no owned or must-not-move file (verified via `git diff --stat` in both directions) |
| sol 1 | CORRECTION | recorded writer sha256 (`ef36aff9...`) claimed stale vs a claimed current value `16a1c488...` | NOT REPRODUCED: regenerated this session by script (byte-replace CRLF->LF, universal-newline text mode, and trailing-newline-normalized variants all agree); result is `ef36aff9...4a5c2e`, identical to what was already recorded and to Opus round 3's own independent recomputation (item (5) of the Opus verdict). The recorded hash is left unchanged; see A9 |
| sol 2 | CORRECTION | memo said three owned/touched files; `git status --porcelain` (post-merge) shows four | header and A9 sections now say four and enumerate: memo, writer, `test_local_capture_writer_atomic_retry.py`, `test_local_capture_writer_atomic_retry_1c.py` |
| Opus 4 (NOTE, optional) | not applied | seed `schedule_observed_sha256` with a prior digest to catch a regression that overwrites it on refusal | deferred -- optional per the verdict, out of this correction-only round's scope |
| Opus 5 (NOTE, out of scope) | not applied | `test_capture_watchdog.py:73` parametrize gap (already named as a FIX 1c NEW GAP above) | unchanged -- explicitly named out of scope for this writer-only row in both round-2 and round-3 verdicts |

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- Whether a real transient Windows `PermissionError` on `os.replace` is
  actually cleared by this bounded retry has NOT been observed in this
  session -- every case is a construct (injected `PermissionError` via
  monkeypatched `os.replace`), never a real archive, network call, or pod run.
- Reader-lock contention remains an unconfirmed HYPOTHESIS; this row does not
  identify the actual concurrent reader.
- Neither real traceback quoted above was replayed against this candidate;
  both are read-only historical evidence from the main tree's gitignored
  `data/cache/capture_supervisor/`, not independently reproduced here.
- No running capture child was touched, restarted, or observed by this row.
  Adoption is the next owner-visible capture relaunch.
- `schedule_pointer_writer.py:44` / `capture_supervisor.py:29` remain unfixed
  (S464's scope).
- The `runner.py:199` construct stubs `capture_scheduler.prepare_tick`'s
  return value (with a real, independently-built `TickPlan` from four real
  `plan_tick` calls) to force `plan.drops` without a full multi-tick
  network-driven run; the planner logic itself is exercised by
  `test_capture_scheduler.py`, not re-proven here.
- `test_capture_watchdog.py:73`'s named-counter list not including
  `atomic_replace_refused` (Opus NEW GAP) was not fixed or tested in this row.
- git commit / push was NOT performed (sandbox git may be denied); files are
  left on disk for `lane_commit`.
