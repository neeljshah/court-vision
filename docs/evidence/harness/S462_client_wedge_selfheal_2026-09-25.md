# S462: a wedged capture client heals itself or exits

## Build result (FIX 1h, this session)

Owned tests: `test_local_capture_wedge.py` 16 passed, `test_local_capture_wedge_1b.py`
14 passed, `test_local_capture_wedge_1c.py` 7 passed, `test_local_capture_wedge_1d.py`
8 passed, `test_local_capture_wedge_1e.py` 8 passed (one new regression test,
AMENDMENT 7(a) -- up from FIX 1g's 7), `test_local_capture_runner.py`
8 passed (unchanged, must-not-move) -- every other count unchanged from FIX 1g.
Normal `python -m pytest <file> -q -p no:cacheprovider` ran clean for all six
files this session (not only direct synthetic invocation).
`contract_preflight` 9/9 PASS over the same 15 owned paths (vocab, crlf, loc,
schema, head_slice, spec_threshold, proposed, removed_artifact,
row_duplication) -- no new files this round (see A9 below for the exact 15).
Must-not-move diff empty against master for all ten spec files
(`capture_supervisor.py`, `capture_watchdog.py`,
`local_capture_backfill.py`, `local_capture_runner_trades.py`,
`capture_scheduler.py`, `polymarket_live_capture.py`,
`capture_schedule_loader.py`, `schedule_pointer.py`, `local_capture_writer.py`,
`local_capture_runner.py`); `git status --porcelain` shows only this row's
own owned paths. No commit made.

## HEAD / master (one plain sentence)

FIX 1i re-ran `git merge --ff-only master` at the start of this session
(`Already up to date` -- no new commits landed upstream since FIX 1h).

- HEAD: `b45883fdac1b3f2149833d5007a92e6ebae0ab5c`
- master: `b45883fdac1b3f2149833d5007a92e6ebae0ab5c`
- HEAD equals master.

## What changed in earlier sessions (Build through FIX 1g) -- compressed, superseded detail dropped

Full per-round detail is compressed to git-free memory only, not on disk.

**Build -> FIX 1d:** discovery/books/M-second design -> per-source wedge
clock keyed on ESSENTIAL_SOURCES (AMENDMENT 2) -> the clock follows the
validated-success COUNTER rising mid-tick, not the tick-end streak
(AMENDMENT 3); due-work refusals are a per-tick delta; case 14 pinned to a
fixed commit; case 13 made real.

**FIX 1e:** `failing_since[source]` replaces the validated-success-counter
clock (AMENDMENT 4), stamped to `prev_mono`; `_rebuilt_sources` becomes a
per-source SET; case 14 moves to raw-byte comparison.

**FIX 1f (round 6, REJECT/REJECT):** AMENDMENT 5's attempt-relative rework --
`failing_since` stamps to the CURRENT observing tick's `mono` (never
`prev_mono`, which let a lone never-retried failure still exit M later),
RE-STAMPS after an idle gap > M, and reads `attempt_age = last_attempt -
failing_since` (never `mono - failing_since`); a stale-idle-rebuild
assertion inverted; `_row_bytes` moved to raw-byte concatenation;
`last_validated_success_mono` deleted; every boundary test's hardcoded
tick/mono re-derived from the fixed formula (`_1d.py` 150/305 -> 300/600,
`_1e.py` 180/360 -> 240/420).

**FIX 1g (round 6, REJECT/ACCEPT WITH CORRECTIONS):** the three boundary
tests now assert the exact derived exit/rebuild mono, not just occurrence
(case 11 `== 420.0`/`== 240.0`; `_1b.py` `== 310.0`/`== 150.0`); two stale
docstrings/one comment restated for AMENDMENT 5(a); owned-path count
corrected 12 -> 15; a harmless regression side effect disclosed at
`local_capture_wedge.py:210`; books 5s/60s-from-310 cadence (rebuild
490/exit 670 at 60s; exit 615 at 5s) hand-derived, NOT VERIFIED by a
construct.

## What changed in FIX 1h (this session) and why

Two round-7 verifier outputs reviewed FIX 1g's candidate, combined into
`_verdict_s462_1h.md` (worktree root; VERDICT 1 = `cx_s462_verify7_out.md`,
REJECT; VERDICT 2 = `_verdict_S462_opus7.md`, ACCEPT WITH CORRECTIONS);
`docs/evidence/tracking/specs/S462_spec.md` AMENDMENT 7 is the reconciled
binding form. Findings and fixes, file:line in the current tree:

1. **A clock invalidation could cause a false immediate exit** (VERDICT 1
   finding 1, BLOCKING). Repro this session, byte-for-byte: books failing at
   mono 5 (`failing_since` stamps to 5.0); a non-finite (`NaN`) mono reading
   clears every stored clock (`_invalidate_clock`); the next OBSERVED tick,
   valid but with no new attempt, at mono 20 re-stamps `failing_since` to
   20.0 while `last_attempt_mono` stays unset (the guard's own post-clear
   `first_call` makes `validated_rose` True that tick, not a real validated
   success); the FIRST reattempt at mono 401 then read the old `idle_restart`
   as False (it required `prior_last_attempt is not None`), so
   `failing_since` stayed at 20.0 and `401 - 20 = 381 > M` raised
   `SystemExit(1)` with `session_rebuilt=1` and `client_wedged=1` on that
   single reattempt after an idle gap. Fix: `local_capture_wedge.py`'s
   `idle_restart` branch (`:235-237`) now reads
   `attempted_this_tick and (prior_last_attempt is None or mono -
   prior_last_attempt > M)`, so the reattempt re-stamps `failing_since` to
   401.0 and neither the exit nor the rebuild fires. Regression test added:
   `test_local_capture_wedge_1e.py::test_clock_invalidation_then_idle_reattempt_restarts_not_exits`,
   which reproduces the exact sequence above; confirmed this session to
   raise `SystemExit(1)` against the pre-fix code (mutation check) and to
   pass clean against the fix.
2. **The case list still described the retired accumulator formula**
   (VERDICT 1 finding 2, CORRECTION). Case 10 said ">= M accumulated
   seconds" and case 11 said a 429 "never advances ... the clock"; the
   implemented AMENDMENT 5(a) formula is strict attempt-relative
   (`last_attempt - failing_since > M`), and a LIVE 429 request still
   advances `last_attempt` (`client.py:64`) without setting or resetting
   `fail_since_validated`. Fix: both case lines below restated to the
   implemented formula.
3. **The hook-run provenance was mislabeled** (VERDICT 2 finding 1,
   CORRECTION). This memo's "The hook, applied and reverted for real"
   section named the recorded run "FIX 1f"; the run itself (and the
   hook-run record's own section title,
   `docs/evidence/forward/capture_wedge/2026-09-25_hook_run.md:99`) is
   FIX 1e, against the AMENDMENT 4 (pre-5(a)) module -- no run exists
   against the AMENDMENT 5(a)/attempt-relative module. Fix: relabeled below;
   NOT VERIFIED states the gap explicitly. This row does NOT re-run the
   hook, which would require editing `local_capture_runner.py`.
4. **A pre-5(a) narrative survived in the PROPOSED twin** (VERDICT 2
   finding 2, CORRECTION). `S462_PROPOSAL_runner_call_2026-09-25.md`'s
   "429-bounded, not 429-delayed" design note said "wall time still elapses
   toward WEDGE_EXIT_SECONDS" during a 429 hold; under AMENDMENT 5(a) the
   clock is attempt-relative, so wall time alone never advances it -- only
   LIVE attempts do (`client.py:64`). Fix: the bullet restated; the twin's
   fenced diff itself is untouched (confirmed this session: byte-equal to
   the local `.diff` under `docs/research/organization-sprint/`, and
   `git apply --check` clean against the worktree's own unmodified
   `local_capture_runner.py`).
5. **A stale section header and two stale citations** (VERDICT 2 findings
   3-4, NOTE). `test_local_capture_wedge.py:180`'s header said "the
   per-source M-second wall clock" -> now "the per-source attempt-relative
   clock". `wedge.py:46`'s docstring cited `(:228)` for the validated-rise
   re-stamp, which at the time of the verdict actually pointed at the
   `idle_restart` line rather than the stamp; fixing finding 1 above
   shifted the branch by +1 line (227 -> 228) and the stamp by +8 lines
   (230-231 -> 238-239), so the docstring now cites the branch and the
   stamp by their current lines (`:228`, `:238-239`). The regression
   `continue` citation (this memo, FIX 1g bullet above) is `:210` after
   FIX 1h's docstring wrap (`:209` was the round-7/FIX 1g citation, now
   stale); corrected in the compressed bullet above.
6. **VERDICT 1 finding 3 (NOTE, exact fix: none):** the three FIX 1g
   boundary tests still pass through direct synthetic invocation, and
   forcing `WEDGE_EXIT_SECONDS=100` still raises `AssertionError` in all
   three (re-confirmed this session); preflight 9/9 over 15 paths;
   must-not-move empty; the twin applies cleanly; A9 matched 18/18 before
   this session's edits; all candidate files ASCII and <=300 lines. No
   action required.

## Spec-premise context (present in the spec; unchanged, not re-verified this session)

Quoted from `docs/evidence/tracking/specs/S462_spec.md`'s BINDING
BEFORE-CONDITION (f), against the artifacts it cites, still on disk:

- Probe (`docs/evidence/forward/capture_probe/2026-09-25_fresh_process_probe_summary.json`):
  `shard_bytes_observed=471764` at `heartbeat_last_write
  2026-09-25T14:42:14.790422Z`; its own `note`, quoted verbatim: "The fleet
  was later found dead since 14:34Z (session job object), so this probe
  proves network health at 14:4xZ, not an in-process wedge."
- Runbook (`docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md:259`, section
  "2026-09-25 FINDING"): confirms the same 14:34Z boundary -- "Every capture
  death without a `child_exit` event in the supervisor journal (2026-09-23
  19:51Z, 2026-09-25 03:43Z, 2026-09-25 14:34Z) coincided with the Claude
  Code session process exiting."
- pid events (restated from the spec's own prior-session read of
  `supervisor_books.jsonl`, a live/local path not present in this worktree):
  `child_start` pid 8308 at 13:56:26.942441Z, next `child_start` pid 16900 at
  14:49:58.832277Z, NO intervening `child_exit` -- the honest wedge window
  this row can reason about is 13:56:26Z to 14:34Z. Dropped claim, quoted
  verbatim: REWRITE 1's "approximately 14:20Z (last successful discovery)"
  boundary has no artifact behind it and stays DROPPED.

## The 14 acceptance-rule construct cases (spec ACCEPTANCE RULE, restated)

1. discovery outage (focus_games empty) with an in-window `forward_schedule` row -> due=True
2. zero capacity (budget=0) with an in-window row -> due=True
3. empty schedule, zero refusals this tick (quiet night) -> due=False, unresolved NOT counted
4. empty schedule, refusals nonzero this tick -> unresolved counted once per positive delta
5. page-shape failure -> raw `successes` climbs, `validated_successes`/streak untouched
6. drain failures then one valid page -> `validated_successes`+1, streak resets
7. books failures then one raw success -> books' `successes` resets books AND combined streak
8. exactly K failures -> one `session_rebuilt`, streak unaffected by the rebuild
9. session-factory exception at a later K boundary -> `session_rebuild_failed`, no crash
10. continuous essential failure + due, `last_attempt - failing_since > M` (attempt-relative, AMENDMENT 5(a)) -> `SystemExit(1)` + `client_wedged`
11. same span with a 429 burst -> live 429 attempts still advance `last_attempt` (client.py:64) without setting or resetting the failure streak, so the bound is unchanged
12. same span with due=False throughout -> no exit, `wedge_idle_skipped` counted
13. across every case -> `client.aimd`/`trade_groups`/`checkpoints` byte/value-identical
14. zero-failure run -> every existing heartbeat field byte-identical, new counters present-and-zero

## The hook, applied and reverted for real (not rerun this session; see FIX 1e)

Not re-applied this session (this row's own fix changed
`local_capture_wedge.py`'s `idle_restart` branch, not the runner, and
re-running the hook would require editing `local_capture_runner.py`, which
this row must not do). Last real run: **FIX 1e**, against the AMENDMENT 4
(pre-5(a)) module -- `SystemExit(1)` at tick 47, elapsed ~304.9s,
`wedge_combined_streak` 94. Full driver, raw output:
`docs/evidence/forward/capture_wedge/2026-09-25_hook_run.md` (unchanged,
reverted, `git diff --stat master --` empty). No run exists against the
AMENDMENT 5(a)/attempt-relative module (see NOT VERIFIED below).

## A9: file identities (LF-normalised bytes and sha256, regenerated LAST, after every other edit, this session)

Owned files are CRLF on disk (`git config core.autocrlf` normalises on add);
this table normalises CRLF->LF before hashing EVERY row for a consistent
sha256, and reports LF-normalised byte counts (18 rows total). The 15 paths
fed to `contract_preflight --paths` this session are: `local_capture_wedge.py`,
`local_capture_client.py`, `local_capture_metrics.py`, the 5 test files,
`S462_PROPOSAL_runner_call_2026-09-25.md`, THIS memo (not its own A9 row,
being edited as this table is written), `.gitattributes`, the 3 case-14
fixtures, and the hook-run record. The remaining 3 rows are the gitignored
local `.diff` (read-only convenience, not a candidate path), read-only
reference (1), or must-not-move (2).

| path | LF bytes | sha256 (LF-normalised) |
|---|---|---|
| `scripts/platformkit/ingame/local_capture_wedge.py` | 15306 | `b49200546e09c4c8cd6d9cb51f0431f8c60df81952c6528a08890cc577df76e4` |
| `scripts/platformkit/ingame/local_capture_client.py` | 7366 | `349829a07b1781afdee3c3bc0dd31f08cf9a57d93a20a33a1a7ce8336cb6cb7c` |
| `scripts/platformkit/ingame/local_capture_metrics.py` | 2905 | `28313b211a3b6082e9bfac8525c53c32be4db7be085d791adfa9af44b7d50325` |
| `tests/platformkit/ingame/test_local_capture_wedge.py` | 15529 | `f125cb04b7426358b3e9e2d4b607c5d0cbbebaee6adb0252fcc29934d43dcaee` |
| `tests/platformkit/ingame/test_local_capture_wedge_1b.py` | 10344 | `39fae34fc817f29f2bea92bda3a44f80e786bca4b99c035bc641548bb59acf3c` |
| `tests/platformkit/ingame/test_local_capture_wedge_1c.py` | 15056 | `844fea7049bbd8391a873a31ae054082f89461e91debf37b58bd693a54f652be` |
| `tests/platformkit/ingame/test_local_capture_wedge_1d.py` | 11064 | `33461af7b1be6cdf93b1a3e7c936acf143b74e517d1b350adb28d43adec80987` |
| `tests/platformkit/ingame/test_local_capture_wedge_1e.py` | 13630 | `a12d77c7fb5a5041acda112c48b8b5fdc906f9189b2fe0186dffd2931bb2e076` |
| `tests/platformkit/ingame/fixtures/s462_case14_rows.jsonl` | 4514 | `80c9b223ba25079d3448107499c0c2fccf203750b45940136b79fa1508a6476c` |
| `tests/platformkit/ingame/fixtures/s462_case14_heartbeat_master.json` | 3312 | `635af43d90cc13e623cf65d3ae5ba7df5dfaf32322634cf3f36668909f84c8cd` |
| `tests/platformkit/ingame/fixtures/s462_case14_base_sha.txt` | 41 | `e07549eba1fb0cf539211ebf2a437fac05f83a86fabcb487d657c17e22bbdb32` |
| `.gitattributes` | 428 | `592cbedcaa74a3e82e8f2610c3c8b2d1b6141676d34b25bed5d759378a57b917` |
| `docs/evidence/harness/S462_PROPOSAL_runner_call_2026-09-25.md` | 14038 | `60a595cf99ccfc18876b34dbdf99ca44356efac7ba3a511adda67feea9a24f71` |
| `docs/research/organization-sprint/S462_scheduled_tick_wedge_hook.diff` | 3033 | `766ce5bb8cf1f699309963e256a385e697c0f0aa3dec471bcc15bd68f672c099` |
| `docs/evidence/forward/capture_wedge/2026-09-25_hook_run.md` | 7317 | `c6936881fd1ec90627ba655ed79732f38f630e8f1b22c6de17ef16e152dbe5bb` |
| `docs/evidence/forward/capture_probe/2026-09-25_fresh_process_probe_summary.json` (read-only reference) | 700 | `8afc0fd346a5bded03ad60ccb134e2385ca499774d781b4d8ad4c5d2debc5a9b` |
| `scripts/platformkit/ingame/local_capture_runner.py` (must-not-move) | 18177 | `5dedfaaf962131a433b88b18aef04189d7ede880b94463f05c45f7e2f971cff4` |
| `scripts/platformkit/ingame/local_capture_writer.py` (must-not-move) | 9737 | `ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e` |

`local_capture_wedge.py`, `test_local_capture_wedge.py`,
`test_local_capture_wedge_1e.py`, and the twin
`S462_PROPOSAL_runner_call_2026-09-25.md` CHANGED this session (this row's
own edits, within budget: wedge.py 265->273 lines, `test_local_capture_wedge.py`
300->300 lines (header text only, no net change), `test_local_capture_wedge_1e.py`
217->261 lines (one new regression test), the twin 208->211 lines (prose
only, fenced diff untouched)); `_1b.py`/`_1c.py`/`_1d.py`, the fixtures, the
local `.diff`, the hook-run doc, `local_capture_client.py`/
`local_capture_metrics.py`, `.gitattributes` and both must-not-move rows are
UNCHANGED from the FIX 1g table (confirmed by the empty `git diff --stat
master --` above for the must-not-move pair).

## History

- **Build -> FIX 1g (earlier sessions):** discovery/books/M-second design ->
  per-source wedge clock (AMENDMENT 2) -> validated-counter clock
  (AMENDMENT 3) -> `failing_since` clock (AMENDMENT 4) -> attempt-relative
  rework (AMENDMENT 5) -> exact-mono boundary tests (AMENDMENT 6); see the
  compressed section above; tests grew to `+_1b/_1c/_1d/_1e.py` (S463
  AMENDMENT 2(a)).
- **FIX 1h (this session):** the `idle_restart` clock-invalidation
  false-immediate-exit fixed and regression-tested (finding 1); the case
  list restated to the strict attempt-relative formula (finding 2); the
  hook-run provenance relabeled FIX 1e (finding 3); the PROPOSED twin's
  pre-5(a) wall-time narrative restated (finding 4); a stale header and two
  stale citations corrected (finding 5); A9 regenerated as the LAST edit.
- **FIX 1i (memo-only, no code/test/fixture change):** round-8 corrections:
  `idle_restart` citation `:234-236` -> `:235-237`; `continue` citation
  `:209` -> `:210` (two spots) and its backwards sentence fixed; the
  "10 lines" shift restated as +1 branch/+8 stamp; "finding 5 above"
  disambiguated to "FIX 1g bullet above"; two register-only gaps added
  under NEW GAPS (not claimed fixed); A9 regenerated LAST, unchanged.

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NEW GAPS (round 8 Opus verdict, register disclosures -- not fixed this row)

- `test_local_capture_wedge_1d.py:160-197`'s dead-discovery construct
  passes only because re-attempts land exactly M apart; re-attempted
  more than M apart it never exits. Production is unaffected:
  `local_capture_state.py`'s `if failed: return None` branch leaves
  `entry["ts"]` unchanged on a refresh failure (`local_capture_runner.py:37`)
  and a dead discovery retries every tick -- the "real ~300s cadence"
  docstring is still a construct. Fix, later row: say so, or drive the
  test at the real retry-every-tick cadence.
- A non-finite `mono` recurring more often than every M seconds
  (`local_capture_wedge.py:137-143`) can mask a real wedge indefinitely;
  `clock_invalid` is still counted (visible, not silent). Consider a cap
  on consecutive `clock_invalid` reads in a later row.

## NOT VERIFIED

- The hook was NOT re-applied or re-run this session (see "The hook" section
  above) -- FIX 1e's run, against the AMENDMENT 4 (pre-5(a)) module, stands
  as the last real execution; the hook has NEVER been run against the
  AMENDMENT 5(a)/attempt-relative module (nor against this row's own FIX 1h
  `idle_restart` fix), so the tick-47/304.9s figures may shift by a tick
  under either; only against a constructed fixture, never a live capture,
  real corpus, network, pod, or real Kalshi ledger, in any session.
- `test_local_capture_failures.py` and `test_capture_scheduler.py` were not
  re-run this session (both exercised, unmodified, in earlier FIX rounds).
- The `supervisor_books.jsonl` pid 8308/16900 events are restated from the
  spec's own prior-session read, not re-opened this session (the file is not
  present in this worktree).
- The books 5s/60s-from-310 cadence literal (mono 615/490/670, FIX 1g
  bullet above) is hand-derived from the AMENDMENT 5(a) formula and
  cross-checked only against VERDICT 2's own probe text -- not
  independently re-derived by running a construct test.
- Every FIX 1g boundary-test number was hand-derived from the fixed formula
  BEFORE editing the test, then confirmed passing (and confirmed to fail
  against an injected wrong-exit case) -- not independently cross-checked by
  a second method.
- The next owner-visible relaunch, after a human applies the PROPOSED runner
  diff (LOC-cap exception A12 required), is the only route to a real wedge
  cleared by rebuild or ended by `client_wedged` in production.
