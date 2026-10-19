# S466: supervisor lock recovery after abrupt owner death

Build result: construct pass (pending verification).

BUILD: lock-recovery tests pass, split 19 + 14 + 14 + 12 across the four owned test files (see
Pass counts), 45 + 16 pre-existing unchanged, preflight 9/9, 13 of 13 acceptance cases PASS
(before 1 of 13, case 13 only).

Worktree `C:/Users/neelj/nba-harness-h121` (bash `/c/Users/neelj/nba-harness-h121`).

## Binding before-condition, re-verified against CURRENT master (277 lines, unchanged by this row)

| Ref | Master line | Claim |
|---|---|---|
| (a) | `:233` (master) / `:249` (candidate) | `os.open(..., O_EXCL)` in `run()` raises `FileExistsError` for ANY pre-existing lock; no except in `run()` itself -> `main()` exit 1. Still the only acquisition path. |
| (b) | `:253` (master) / `:276` (candidate) | lock `unlink()` only in `run()`'s own `finally`, `if self.child is None:` -- an abruptly-killed process never reaches it. |
| (c) | n/a | `data/cache/capture_supervisor/` absent from this gitignored worktree; the spec's four real lock filenames not independently re-read here (NOT VERIFIED). |
| (d) | `:57-62` | `_awake` is the file's only prior ctypes use (`os.name != "nt"` gated); the sibling's `OpenProcess`/`GetProcessTimes`/`GetTickCount64` matches that convention, no new dependency. |
| (e) | `:214`->`:219` (popen), `:225`->`:230` (child_start) | `popen(self.command, ...)` and `_record("child_start", ..., child_pid=...)` -- argv is opaque, never scanned; child identity is captured directly by ctypes query of the spawned pid. |

STEP 0 premise-checks, each pass before touching an owned file: pre-FIX-1b, the two
spec-stated counts (45/16) passed clean; pre-FIX-1c, all four files reproduced clean
(19/12/45/16) and the two round-2 verdicts' seven repro scenarios were each reproduced live
against the FIX 1b candidate first, then fixed and re-verified passing. FIX 1h's own premise
check is the finding-1 repro in the FIX 1h section below, reproduced against the FIX 1g
candidate before any owned file was touched.

## The 13 CONSTRUCT cases, before values, and results

`before = 1 of 13` (case 13 only, byte-identical by construction).

| # | Case | Before | Test(s) | Result |
|---|------|--------|---------|--------|
| 1 | live owner, versioned, refuses | FAIL | `test_case1_live_owner_versioned_refuses`, `test_run_case1_live_owner_exits_named_refusal` (run()-level, named exit-1) | PASS |
| 2 | dead owner, no child, takes over | FAIL | `test_case2_dead_owner_no_child_takes_over`, `test_run_case2_takeover_populates_fresh_lock_schema` (run()-level, fresh-lock schema, FIX 1c: query-injected off the real ctypes path) | PASS |
| 3 | dead owner, live child, refuses `child_still_running` | FAIL | `test_case3_dead_owner_live_child_refuses` | PASS |
| 4 | pid reuse (start_time mismatch), takes over | FAIL | `test_case4_pid_reuse_start_time_mismatch_takes_over` | PASS |
| 5 | malformed (unparseable / wrong-typed / partial), refuses | FAIL | `test_case5*` (3 variants) | PASS |
| 6 | legacy, alive, refuses | FAIL | `test_case6_legacy_alive_refuses`, `test_run_case6_legacy_alive_exits_named_refusal` (run()-level, named exit-1) | PASS |
| 7 | legacy, absent, takes over (legacy-schema journal) | FAIL | `test_case7_legacy_absent_takes_over` | PASS |
| 8 | concurrent recoverers, loser refuses `takeover_lost_race` | FAIL | `test_case8_concurrent_recoverer_loses_race` | PASS |
| 9 | fresh owner appears mid-classification, aborts | FAIL | `test_case9_fresh_owner_appears_aborts` | PASS |
| 10 | inaccessible owner / child query, refuses by name | FAIL | `test_case10a/b_*_unresolved_refuses` | PASS |
| 11 | rename / journal-write failure, refuses, untouched | FAIL | `test_case11a/b_*` | PASS |
| 12 | non-Windows, `unsupported_platform`, lock untouched | FAIL | `test_case12_non_windows_returns_unsupported`, `test_run_case12_non_windows_exits_named_refusal` (run()-level, named exit-1, lock byte-untouched schema check) | PASS |
| 13 | no pre-existing lock, `reconcile()` never called | PASS (regression guard) | `test_case13_no_lock_never_calls_reconcile` | PASS |

"13 of 13" restated per amendment 1h: all 13 still pass; case 4's boot-id-alone variant was never
one of the 13 (an additional boundary test) and is corrected below, not a slot change.

FIX 1b-1d (2026-09-25, spec AMENDMENTS 1, 2-3, 4): three rounds of codex sol REJECT
(7 + 4 + 5 blockers) and Opus tier 2 REJECT (4 + 4 + 3 blockers, several corrections each),
reconciled in sequence -- boot-id liveness went to exact truncated-second matching with no
epsilon; the spawn wrapper guards every pre-arm and post-spawn failure so a child is never
orphaned or left untracked; the takeover race closes on a post-rename re-read with a retried,
named rollback; the sidecar and its journal check run on every acquisition path, including a
vacant one; rollback moved into the new `capture_supervisor_lock_io.py` sibling using
no-clobber `os.rename`; tests are query-injected off the real ctypes path via a new
`tests/platformkit/ops/conftest.py` autouse fixture; and a lost post-takeover race journals
through a dedicated `_recover`/`_beat`-free append-only function. `capture_supervisor.py` and
`capture_supervisor_lock.py` reached the 300-line cap by FIX 1d (no net growth left): new
logic in `run()`/`__init__`/`_exit` was offset by merging single-statement `if: raise` pairs
and compressing docstrings. Full item lists and file:line citations live in the spec's
AMENDMENTs 1, 2-3 and 4.

## FIX 1e: verifier findings applied (spec AMENDMENT 5, round 4 both tiers reconciled)

Round 4: codex sol REJECT (three blockers, one correction) + Opus tier 2 REJECT (two
blockers, four corrections, one note), reconciled by AMENDMENT 5 items (a)-(f), each
reproduced by re-tracing the FIX 1d candidate line by line before any owned file was
touched -- findings and fixes in the table below.

| Item | Finding (before) | Fix (file:line) | Proving test(s) |
|---|---|---|---|
| 5a | a pre-arm write failing with `Unresolved` was counted and returned `False` without blocking -- `_spawn()` ignored the result and ran `real_popen` regardless, so the disk could say `child: null` while a spawned process actually ran | `capture_supervisor_lock_io.py:164-173` (FIX 1f: shifted by new 6a/6b/6c functions added earlier in the file) `_write`: ONE merged `except (unresolved, OSError, ValueError)` guard -- every pre-arm failure, `Unresolved` included, raises `OSError("lock refused: child_marker_unwritten")` when `blocking=True` on Windows | `test_pre_arm_unresolved_blocks_spawn_bytes_unchanged` (1d, new: zero popen calls, lock bytes byte-unchanged, counter asserted) |
| 5b | after a rollback AND its own sidecar write both failed, the journal received `lock_marker_write_failed`, but the next launch's `self.lock.exists()` gate (vacant path) skipped `reconcile()` and its `rollback_pending()` check entirely, and silently acquired | `capture_supervisor_lock_io.py:35-50` (FIX 1f note: this last-line-only check is ITSELF superseded by amendment 6a below) `rollback_write_failed_pending`: True when the journal's LAST event was `lock_marker_write_failed`; `capture_supervisor.py:239-240` `run()`: checked immediately after `rollback_pending`, before the `exists()` branch, refusing `lock_marker_write_failed` even on a vacant path | `test_reconcile_sidecar_write_failure_is_journaled_distinctly` (1d, extended, then rewritten again under FIX 1f -- see below) |
| 5c | `child_identity`'s own `default_query()` call sat outside its inner try; a boot-id `Unresolved` was swallowed there (returned `None`, no exception), so the wrapper's guard never saw it and the counter stayed 0; a `ValueError` from `child_identity` escaped the wrapper's `(OSError, unresolved)` guard entirely, propagating past `_loop` (which only catches `OSError`) into `run()`'s `finally`, unlinking the lock while the child still ran | `capture_supervisor_lock.py:279-293` `child_identity`: no inner try left -- `default_query`, `start_time` and `boot_id` all propagate; `capture_supervisor_lock_io.py:175-189` (FIX 1f: shifted) `_spawn`'s own call-site guard widened to `(unresolved, OSError, ValueError)`, the SOLE place that now counts `lock_child_refresh_failed_total`, exactly once per failure, and always reaches `return spawned` | `test_wrapper_survives_start_time_oserror_after_spawn`, `test_wrapper_survives_boot_id_unresolved_on_second_call`, `test_wrapper_survives_default_query_oserror_with_query_none` (all three: exact `== 1` counter, tightened from the old `>=`/absent assertions), `test_wrapper_survives_value_error_after_spawn_exact_counter` (1d, new) |
| 5d | `run()` passed `recover=self._recover` into `reconcile()`; that call runs after the takeover rename vacates the path and before O_EXCL, so a peer acquiring in that exact window has its heartbeat rewritten and a `journal_recovery` row appended to its journal by a process that does not own the lock | `capture_supervisor.py:243-244` `run()`: `recover=None`; `_loop()`'s own `self._recover(previous_wall)` (frozen, untouched, fires right after acquisition) already covers post-acquisition recovery, so nothing runs in the rename-to-O_EXCL window at all | `test_lost_race_never_rewrites_fresh_owners_heartbeat_or_journal_prefix` (1d, rewritten: the sentinel journal now ends in a PARTIAL line -- a fully newline-terminated one is a no-op for `_recover()` either way, so it could never have caught `recover=self._recover` firing) |
| 5e | `test_wrapper_survives_default_query_oserror_with_query_none`'s first call fell through to the REAL `default_query` (its own docstring: "a construct test never calls this"); the pre-arm-`Unresolved` case (5a) had no construct asserting the on-disk bytes at every step, only whether the lock existed | `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1d.py:81-97`: the flaky stub returns a fully synthetic `ProcessQuery` on every call, never the real one | same test (now `== 1`, no real ctypes at all), plus `test_pre_arm_unresolved_blocks_spawn_bytes_unchanged` (1d, new) which pre-writes a real lock payload and asserts those exact bytes survive unchanged |
| 5f | memo line-cite drift; the Q6-flagged verb still present at two lines | this section and the before-condition table re-derive every cite against the FIX 1e candidate; SHA rechecked below; A9 regenerated from disk as the last edit | `test_owned_files_pass_the_real_q6_vocabulary_scan` |

Sanity-checked live (not just by inspection): each of 5a, 5c(ValueError path) and 5d was
verified to actually fail its own proving test when the fix was reverted line-for-line and
the test re-run, then restored and re-verified green -- so none of these three constructs
are vacuously passing against unfixed code.

## FIX 1f: verifier findings applied (spec AMENDMENT 6, round 5 both tiers reconciled)

Round 5: codex sol REJECT (three blockers, one note) + Opus tier 2 REJECT (one blocker, two
corrections, one note), reconciled by AMENDMENT 6 (a)-(f), each reproduced by re-tracing the
FIX 1e candidate before any owned file was touched -- findings and fixes in the table below.

| Item | Finding (before) | Fix (file:line) | Proving test(s) |
|---|---|---|---|
| 6a | `rollback_pending` (io.py, old :25-27) missed the `.tmp` sidecar that survives when the temp write succeeds but the final `os.replace` fails; `rollback_write_failed_pending` (io.py, old :30-48) parsed only the journal's last line, missing a marker glued onto a partial trailing line, a later row, or an unreadable journal | `capture_supervisor_lock_io.py:25-32` `rollback_pending`: also True when `<lock>.rollback_failed.tmp` exists; `capture_supervisor_lock_io.py:35-50` `rollback_write_failed_pending`: rewritten as a raw `b'"lock_marker_write_failed"'` byte search across the WHOLE journal, True on any `OSError` reading it | `test_rollback_pending_catches_unwritten_marker_tmp_file`, `test_rollback_write_failed_pending_partial_last_line`, `test_rollback_write_failed_pending_later_row_still_refuses`, `test_rollback_write_failed_pending_unreadable_journal_refuses` (all 1d, new); `test_reconcile_sidecar_write_failure_is_journaled_distinctly` (1d, rewritten: the same double failure now refuses via the more precise `lock_rollback_pending`, discovered through the surviving `.tmp`, with no separate journal write needed) |
| 6b | `capture_supervisor.py` (old :256) appended `takeover_lost_race` onto `self.journal` -- an owner-held file -- and the old `_1d` construct's `startswith` check could not see the corruption an append onto a partial line produces | `capture_supervisor_lock_io.py:77-83` new `loser_journal_path`: a sibling file keyed by the loser's own pid; `capture_supervisor.py:255` `run()`: journals the lost-race refusal through it instead of `self.journal` | `test_lost_race_never_rewrites_fresh_owners_heartbeat_or_journal_prefix` (1d, rewritten: asserts the owner's journal holds ONLY its own legitimate `reconcile()` row, contains no `takeover_lost_race` event, and the loser's own row lands in the sibling file); `test_run_post_takeover_race_named_counted_journaled` (1c, updated to read the sibling file) |
| 6c | `_append` (`capture_supervisor_lock.py`, old :169-175) wrote straight onto the file's existing tail with no partial-line check of its own | `capture_supervisor_lock_io.py:53-74` new `append_tolerating_partial_line`: writes a leading `\n` first when the file is non-empty and does not already end in one; `capture_supervisor_lock.py:172-175` `_append` now delegates to it | `test_lost_race_never_rewrites_fresh_owners_heartbeat_or_journal_prefix` (1d: the sentinel's partial trailing line is followed by a clean, correctly newline-separated `stale_lock_takeover` row from `reconcile()`) |
| 6d | `_exit` (`capture_supervisor.py`, old :162) caught only `(OSError, Unresolved)` around the lock-refresh write -- a `ValueError` (e.g. a malformed identity) escaped, leaving `child_exit` unrecorded and the counter at 0 | `capture_supervisor.py:162` `_exit`: guard widened to `(OSError, ValueError, Unresolved)` | `test_exit_guards_value_error_and_still_records_child_exit` (1b, new: exact counter, `child_exit` still journaled) |
| 6e | `test_own_identity_resolves_the_real_self_process` and `test_lock_payload_non_windows_matches_master_bytes` (`_1b.py`, old :197-212) both called the REAL `default_query` for the test's own pid | both rewritten to pass a synthetic `ProcessQuery` (`fake_query`); `tests/platformkit/ops/conftest.py` now has a second autouse fixture, `_no_real_default_query`, making the real `default_query` raise for every test in the row -- a row-wide guard, not just these two | same two tests (no real ctypes at all); `test_pre_arm_write_failure_blocks_spawn_disk_asserted` (1b, now asserts the pre-existing lock's exact bytes survive the failed pre-arm write, not just its absence) |
| 6f | memo line-cite drift (the flagged-verb wording at two spots, the 5e row's stale `_1d` citation, the `_recover`/`_loop`/`_beat`/`_record` ranges each including a trailing blank line) | every citation in this memo re-derived against the FIX 1f candidate; the loser's refusal now lives in `loser_journal_path(...)` (stated in row 6b above); SHA rechecked below; A9 regenerated from disk as the last edit | `test_owned_files_pass_the_real_q6_vocabulary_scan` |

Sanity-checked live (not just by inspection): each of 6a (both the `.tmp` check and the
byte-search rewrite), 6b, 6c, 6d and 6e was verified to actually fail its own proving test
when reverted line-for-line and the test re-run, then restored and re-verified green -- none
of these five constructs are vacuously passing against unfixed code.

## FIX 1g: verifier findings applied (spec AMENDMENT 7, round 6 both tiers reconciled)

Round 6: codex sol REJECT (three blockers, one note) + Opus tier 2 REJECT (one blocker,
three corrections, two notes), reconciled by AMENDMENT 7 (a)-(d). Every finding was
reproduced by re-tracing the FIX 1f candidate before any owned file was touched: (a)
`reconcile()` appended `stale_lock_takeover` onto `self.journal` AFTER the takeover rename
but BEFORE `run()`'s own O_EXCL, so a peer that acquired inside that window already owned
the journal when the row landed (probe P1: the peer's own row ends up with the loser's row glued
after it), and the `_1d` construct checked only `startswith`; (b) the loser's sibling file
(`supervisor_<name>.lost_race_<pid>.jsonl`) matched `forward_qualification_daily.py`'s own
`supervisor_*.jsonl` reader glob, so every loser file would be folded into the S390 inputs,
and a reused pid after a reboot could append to an older loser's file; (c) the raw substring
search for `lock_marker_write_failed` also matched the string appearing as a PAYLOAD VALUE
in an unrelated row, and the memo named no action that clears a sticky
`lock_marker_write_failed` refusal; (d) the memo's own prose describing the flagged-verb fix
still used two forms of the flagged verb itself. All four fixed below.

| Item | Finding (before) | Fix (file:line) | Proving test(s) |
|---|---|---|---|
| 7a | `reconcile()` (old `capture_supervisor_lock.py:254-260`) journaled `stale_lock_takeover` onto `self.journal` between the rename and `run()`'s own O_EXCL -- a peer acquiring in that window already owned the journal when the row landed | `capture_supervisor_lock.py:193-263` `reconcile()`: takes a NEW `row_out` parameter and, on a takeover, only `row_out.update(...)`s the row's fields (:257-262) -- no I/O, nothing ever written to `journal_path` here; `capture_supervisor.py:237-262` `run()`: `row = {}` passed as `row_out`, and `capture_supervisor_lock_io.finish_takeover()` (`:165-183`) journals the row to `self.journal` only after O_EXCL succeeds (:260-262) or to the loser's own file on a lost race (:249-252); an append failure at either site falls back to the same rollback-or-`lock_marker_write_failed` path a pre-O_EXCL failure already used | `test_case2_dead_owner_no_child_takes_over`, `test_case7_legacy_absent_takes_over` (recovery.py, rewritten: assert `row_out`, assert `not journal.exists()`); `test_lost_race_never_rewrites_fresh_owners_heartbeat_or_journal_prefix` (1d, rewritten: `after_journal == sentinel_journal` exact byte equality, not `startswith`); `test_peer_interleaves_between_rename_and_o_excl_owns_the_journal` (1c, new: a peer's own lock AND journal row land inside the exact rename-to-O_EXCL window, and `self.journal` ends up holding only the peer's row); `test_case11b_deferred_append_failure_falls_back_to_rollback` (recovery.py) and `test_double_failure_append_and_rollback_both_fail` (1b), both moved from exercising `reconcile()`'s old in-line append to exercising `finish_takeover()` directly |
| 7b | `loser_journal_path()` (old `capture_supervisor_lock_io.py:77-83`) produced `supervisor_<name>.lost_race_<pid>.jsonl`, which matches `forward_qualification_daily.py:198`'s own `supervisor_*.jsonl` glob, and was keyed by pid alone (a reused pid after a reboot could append to an older loser's file) | `capture_supervisor_lock_io.py:90-101` `loser_journal_path()`: renamed to `lost_race_supervisor_<name>_<pid>_<wallstamp>.jsonl` (a `lost_race_` prefix, outside the glob) with a UTC wall-clock stamp beside the pid; nothing prunes these files today, disclosed in NOT VERIFIED below with the operator's clear step named | `test_run_post_takeover_race_named_counted_journaled` (1c, extended: asserts the produced name does not start with `supervisor_`); every rewritten lost-race test now passes the fixed test wall (`1800000000.0`) as the 4th argument |
| 7c | `rollback_write_failed_pending()` (old `capture_supervisor_lock_io.py:35-50`) used a raw substring search for `"lock_marker_write_failed"`, which also matched that string appearing as an unrelated row's PAYLOAD VALUE (e.g. `{"event": "host_gap", "note": "lock_marker_write_failed"}`); the memo named no operator action that actually clears a sticky refusal | `capture_supervisor_lock_io.py:42,63` new `_MARKER_EVENT` bytes regex matches only the JSON EVENT field (`"event"\s*:\s*"lock_marker_write_failed"`), never a payload value; the "## NOT VERIFIED" operator-clear note below now names moving (rotating) the journal aside, not only deleting the sidecar file(s) | `test_rollback_write_failed_pending_ignores_payload_only_match` (1c, new: a payload-only match returns `False`); `test_rollback_write_failed_pending_matches_the_event_field` (1c, new: the real event field still returns `True`) |
| 7d | the memo's own row 6f description of the flagged-verb fix used the flagged verb itself, twice (this memo, old lines 134-135, 206) | every occurrence rewritten to avoid the word family entirely (this section and the 6e/6f rows above) | `test_memo_never_uses_the_flagged_verb` (1c, new: a whole-word, case-insensitive regex over the memo text) |

Sanity-checked live (not just by inspection): 7a, 7b and 7c were each verified to actually
fail their own proving test when reverted line-for-line and the test re-run, then restored
and re-verified green -- none of these three constructs are vacuously passing against
unfixed code. 7d is a pure text fix, verified only by the new scanner test.

## FIX 1h: round-7 corrections applied (both tiers ACCEPT WITH CORRECTIONS; no amendment)

Round 7 on FIX 1g: both tiers ACCEPT WITH CORRECTIONS, not a REJECT (codex's own lane was
down, so tier 1 is an independent Opus critic reading the codex prompt; `_verdict_s466_1h.md`
carries both verdicts). A CORRECTIONS lane: one small code change plus memo/docstring
wording, no spec amendment.

| Item | Finding (before) | Fix (file:line) | Proving test(s) |
|---|---|---|---|
| 1h-1 | `finish_takeover()`'s WIN branch (append fails after O_EXCL already landed) fell into the SAME rollback-or-lock_marker_write_failed fallback as a loss: on Windows the rename-back always loses to our own fresh lock (`FileExistsError`), so `_mark_pending` plants a `.rollback_failed` sidecar for a rollback that was never attempted against a live conflict, `run()` returns 0 with every counter at 0 and no takeover row, and the NEXT launch is refused `lock_rollback_pending` for the wrong reason | `capture_supervisor_lock_io.py:165-191` `finish_takeover()`: a WIN-branch append failure now returns `False` -- no rollback attempted, no sidecar planted, the winner keeps its legitimately-held lock exactly as any clean run does; `capture_supervisor.py:99,261-264` `run()` counts a NEW strict-int `lock_takeover_journal_failed_total` on that `False`; the rollback-or-`lock_marker_write_failed` fallback now runs on the LOSS branch only | `test_win_branch_journal_failure_keeps_lock_no_rollback` (1c, new: `run()` -> 0, counter == 1, no sidecar in any form, a clean exit still unlinks the lock, the NEXT launch acquires); `test_case11b_deferred_append_failure_falls_back_to_rollback` (recovery.py) and `test_double_failure_append_and_rollback_both_fail` (1b), both moved to `won=False` -- a peer's independently-acquired fresh lock is what they always meant to exercise |
| 1h-2 | this memo (FIX 1f/1g Design notes) overclaimed a loser "never appends to any owner-held file at all" and that `reconcile()` "never journals ANYTHING"; `capture_supervisor_lock_io.py`'s `append_tolerating_partial_line` docstring overclaimed a loser "never reaches" it -- `finish_takeover`'s loss branch and `reconcile()`'s own `_rollback_or_journal_failure` both still append `lock_marker_write_failed` onto `journal_path` (an owner- or peer-held file), by the amendment 5(b) design, once the sidecar write has also failed | Design notes above and `capture_supervisor_lock_io.py:66-77`'s docstring now state the one exception by name: every row but `lock_marker_write_failed` after a failed sidecar write lands only in a file its own writer owns | inspection; `test_rollback_write_failed_pending_matches_the_event_field` (1c) already exercises the row this exception describes |
| 1h-3 | the `_1c` peer-interleave construct asserted only the peer's journal byte-unchanged, not its heartbeat | `test_peer_interleaves_between_rename_and_o_excl_owns_the_journal` (1c): a peer heartbeat is written inside `sneaky_open` and asserted byte-identical afterward | same test |
| 1h-4 | `test_memo_never_uses_the_flagged_verb` (1c) resolved the memo path against the CWD, passing only from the repo root | resolved via `Path(__file__).resolve().parents[3]` instead | same test |

Sanity-checked live: 1h-1's pre-fix repro reproduces the verifier's own probe exactly
(`run()` -> 0, every counter 0, a `.rollback_failed` sidecar planted, the next launch
refused `lock_rollback_pending`); restored and re-verified green after the fix.

## Design notes (condensed)

`_loop`/`_record`/`_recover`/`_beat` stay byte-identical (S464's must-not-move list): the spawn
refresh lives in a NEW sibling, `capture_supervisor_lock_io.py` (`make_spawn_wrapper`, called from
`__init__`), not inside `_loop`; the child-clear lives in `_exit` (not frozen). Legacy locks
(`{"pid"}` only, matching all four real on-disk locks per spec premise (c)) are their own
classification, not a separate migration step: alive refuses byte-identically to today, absent
takes over. FIX 1c keeps this shape and adds one more sibling rather than growing either
frozen-adjacent file past budget: `capture_supervisor_lock_io.py` holds
`rollback`/`rollback_pending`/`make_spawn_wrapper`, importing neither `capture_supervisor.py`
nor `capture_supervisor_lock.py` (both pass their own callables in), so there is no import cycle.
`capture_deploy_preflight.py:202-203` is the only other reader of the lock JSON (reads `pid` only,
unchanged in name/type/meaning by this additive schema) -- confirmed via
`grep -rl "capture_supervisor\b" scripts/ tests/` (readers checked, A5). FIX 1f adds one more
convention to the same sibling: a takeover-race LOSER never appends to any owner-held file at
all, EXCEPT (FIX 1h correction) the lock_marker_write_failed refusal row after a failed sidecar
write, by design (amendment 5b), so the next launch refuses -- every other row lands only in
`loser_journal_path()`'s own sibling path, keyed by the loser's own pid. FIX 1g goes one step
further: `reconcile()` itself never journals a takeover row on its own successful or lost-race
path (it only populates the optional `row_out` dict); its `_rollback_or_journal_failure` helper
is the identical one exception, appending that same refusal row pre-O_EXCL for the identical
reason. So `capture_supervisor_lock_io.finish_takeover()` is the SOLE place that journals the
takeover row itself, and only once `run()`'s own O_EXCL outcome is known -- to `self.journal` on
a win (FIX 1h: an append failure there is only counted, never rolled back, since a winning
O_EXCL already legitimately owns the lock), to the loser's own file (named
`lost_race_supervisor_...`, outside `forward_qualification_daily.py`'s `supervisor_*.jsonl`
reader glob, with a wall stamp so a reused pid after a reboot never collides with an older
loser's file) on a loss.

## Pass counts (FIX 1h, this pass)

| File | Tests | Result |
|---|---|---|
| `tests/platformkit/ops/test_capture_supervisor.py` (must-not-move count) | 45 | 45 passed, unchanged |
| `tests/platformkit/ops/test_capture_supervisor_atomic_retry.py` (must-not-move count) | 16 | 16 passed, unchanged |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery.py` (case 11b moved to `won=False`, FIX 1h) | 19 | 19 passed |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1b.py` (double-failure test moved to `won=False`, FIX 1h) | 14 | 14 passed |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1c.py` (one new win-branch construct, peer-heartbeat assertion added, memo-path fix, FIX 1h) | 14 | 14 passed |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1d.py` (unchanged this pass) | 12 | 12 passed |

FIX 1e/1f/1g test-rewrite details are not restated here -- the "Proving test(s)" columns in
the tables above name every one; this pass's own changes are in the FIX 1h table above.

`python -m scripts.platformkit.ops.capture_supervisor --help` works (re-confirmed this pass).
Preflight (`contract_preflight --paths` the 9 owned paths, code + tests + this memo,
`--base master --spec S466_spec.md`) -> 9/9 PASS, re-run FIX 1h. `git diff --stat master --
atomic_replace.py schedule_pointer_writer.py` -> empty (must-not-move, byte-identical,
re-confirmed FIX 1h). `git diff master -- capture_supervisor.py` touches only imports,
`__init__`, `_exit`, `run()` -- zero lines inside `_beat` (104-121) / `_record` (122-129) /
`_recover` (130-146) / `_loop` (179-231), confirmed against every hunk's line range this pass
(ranges shifted by the `__init__` counter this pass added; the bodies are byte-identical).
`_atomic`'s signature and S464's three heartbeat counters
(`atomic_replace_refused_total`, `_cleanup_errors_total`, `_retry_total`) are untouched; this
row's own counters (`lock_child_refresh_failed_total`, `lock_takeover_lost_race_total`,
`lock_marker_write_failed_total`, and now `lock_takeover_journal_failed_total`) are appended
strictly after them via chained assignment.
`capture_supervisor.py` and `capture_supervisor_lock.py` stayed at the 300-line cap through
FIX 1h with no headroom to spare: `capture_supervisor.py` paid for the new counter and the
win-branch failure check by merging two more single-statement `if: raise`/`if: return` pairs
onto one line each (matching the file's own existing style), landing at 299;
`capture_supervisor_lock.py` is untouched this pass, still 298; `capture_supervisor_lock_io.py`
(244 lines) absorbed the win-branch behavior change and both corrected docstrings with room to
spare.

## A9 artifact identities (regenerated from disk as the last edit)

Owned files (bytes are raw on-disk size; sha256 is LF-normalized, `tr -d '\r' | sha256sum`):

| File | bytes | lines | sha256 (LF-normalized) |
|---|---|---|---|
| `scripts/platformkit/ops/capture_supervisor.py` (FIX 1h: new `lock_takeover_journal_failed_total` counter, win-branch `finish_takeover` call counts instead of rolling back, two more `if:` pairs merged) | 15549 | 299 | `c139b08d385079e7fd2b43552795c2ca50d6838db869fb93d61c6d769755c2c3` |
| `scripts/platformkit/ops/capture_supervisor_lock.py` (unchanged this pass) | 14278 | 298 | `f1b914f521d7a4f0771a0bde6cd3f1568bbca7cff41b86f2733c5354ea5f54ba` |
| `scripts/platformkit/ops/capture_supervisor_lock_io.py` (FIX 1h: `finish_takeover` win-branch returns bool and never rolls back; `append_tolerating_partial_line` docstring corrected) | 12289 | 244 | `feb96f529a470ba19f7e05d027a9402149a186c42ef73b0660cbecb13d0ea2d4` |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery.py` (FIX 1h: case 11b moved to `won=False`) | 13550 | 290 | `047b7704fa6c9a0d53ba6071735a54a4c8effd661e7b1b2d2602843747128d55` |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1b.py` (FIX 1h: double-failure test moved to `won=False`) | 14314 | 263 | `532398e9148b390b914908d4ae0ed9a4717ea82d19e541dd61c7295c85f51fc6` |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1c.py` (FIX 1h: one new win-branch construct, peer-heartbeat assertion, memo-path fix) | 15817 | 291 | `26eef838e19348e18d1fba9bb638814f0748932439001a87e7b975691e78903b` |
| `tests/platformkit/ops/test_capture_supervisor_lock_recovery_1d.py` (unchanged this pass) | 15501 | 285 | `86df9caff3eb08f1ddd8c439456dbeef680e4f485f64493e8f0ba516d6bf5056` |
| `tests/platformkit/ops/conftest.py` (unchanged this pass) | 2284 | 50 | `dccc5dd3d2844ceb1f47cef679edd1851f2e748e52f51fc979b335b7a0367bcb` |

Must-not-move files, re-confirmed byte-identical to master this pass (`git diff --stat` empty):
`scripts/platformkit/ops/atomic_replace.py`, `scripts/platformkit/execution/schedule_pointer_writer.py`.

## SHA

The worktree was re-fast-forwarded to master at the start of FIX 1h (`git merge --ff-only
master` -> fast-forward over one spec-only commit, S468_spec.md); HEAD ==
`affaaacf05431161b696ae85bd0c854904201de1` == master ==
`affaaacf05431161b696ae85bd0c854904201de1`, EQUAL. Drift after this point is not a finding. No
commits were made in this worktree (sandbox denies `git commit`).

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- No real abrupt supervisor death was observed or replayed -- every construct test uses an
  injected `ProcessQuery`/`Path.rename`/`os` seam. FIX 1c's injectable `query` hook (amendment 2e)
  and FIX 1d's `conftest.py` autouse fixture (amendment 4d) already kept every `run()`-level,
  `reconcile()`-level and unqueried-Supervisor construct off the real ctypes path. FIX 1f (6e)
  closes the LAST gap: the two `_1b` tests that legitimately queried this process's own pid
  through the real `default_query` now inject a synthetic `ProcessQuery` instead, and a second,
  row-wide autouse fixture (`_no_real_default_query`) makes the real `default_query` raise for
  the duration of every test in the row, confirmed live by reverting each fix and watching its
  own test fail. No test in this row reaches real ctypes at all any more (`OpenProcess` +
  `GetProcessTimes`, `PROCESS_QUERY_LIMITED_INFORMATION`, never a signal/kill/wait, were only
  ever read-only). Adoption proof is only available from the next owner-visible relaunch after a
  real abrupt kill.
- `data/cache/capture_supervisor/`'s four real active locks (spec premise (c)) remain unread --
  absent from this gitignored worktree.
- The true Windows handle-held rename (amendment 1d's ideal fix) was not implemented -- the
  post-rename path-based re-read is a documented ponytail fallback; the residual window between the
  rename syscall and the re-read is unmeasured. Upgrade path: a real `SetFileInformationByHandle`
  rename if that gap is ever measured as live.
- `child_identity()`'s "unresolvable pid" branch on a genuinely absent real pid (rather than an
  injected-query double) is not independently exercised.
- FIX 1c's `os.rename` no-clobber rollback is exercised only via construct: `FileExistsError`,
  `PermissionError` and generic `OSError` are all mocked, never a real Windows AV file lock racing
  a real second owner. The sidecar `.rollback_failed` marker's (and, since FIX 1f, its `.tmp`
  sibling's) operator-clear step (spec 2d: "the memo names the operator action that clears it")
  is not yet a runbook -- clearing it today means deleting the sidecar file(s) by hand once the
  stale lock's disposition is confirmed manually; a proper runbook line belongs in
  `docs/operations/runpod-runbook.md` or equivalent, out of this row.
- OPERATOR NOTE (amendment 7c): a `lock_marker_write_failed` row anywhere in the journal refuses
  EVERY later launch on that lock name (probe P2: it holds even after a later, unrelated
  `host_gap` row lands on top of it). Deleting the sidecar file(s) alone is NOT enough -- the
  clear action is moving (rotating) the journal aside once the `.stale_*` disposition is
  confirmed manually, alongside the sidecar-deletion step above.
- Loser files (`lost_race_supervisor_<name>_<pid>_<wallstamp>.jsonl`, 7b) are never pruned by
  anything in this row (a register gap); an operator clears one by deleting it once its
  `takeover_lost_race` row has been read. Journal rotation/truncation can still mask the
  `lock_marker_write_failed` marker itself (amendment 7's own NEW GAPS), and a triple failure
  (the sidecar `.tmp` write, the deferred append, and the rollback all failing together) still
  lets the next launch acquire silently -- both out of this row, for the register.
- round-7 NOTE (register gap, not fixed this row): `rollback_write_failed_pending`'s
  `_MARKER_EVENT` regex also matches a NESTED event key one level down, e.g. a hypothetical
  `{"host_gap": {"event": "lock_marker_write_failed"}}` row -- fails closed (a false refusal),
  never a false acquire; no writer in this row produces that shape, so it is unreached today.
- round-7 NOTE (register gap, not fixed this row): on the LOSS branch, `run()` calls
  `self._clock()` (raises on a non-finite wall or monotonic reading) AFTER
  `lock_takeover_lost_race_total` is already incremented and BEFORE the loser's own
  `takeover_lost_race` row is written, so that one clock failure moves the counter with no
  row to show it.
- No running capture child or supervisor process was touched, started, stopped, killed or signaled.
  No pod, no network. `git commit` was not attempted (sandbox denies it); files are left on disk
  for `lane_commit`.
