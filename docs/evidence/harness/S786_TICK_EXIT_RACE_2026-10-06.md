# S786 -- paper-desk tick exit race (child_exited_during_observation)

Status: BUILT on branch `cxp/S786-2026-10-06` (NOT LANDED). PAPER ONLY. Lands after one
read-only tier (10-07 08:45Z-11:45Z).

## Before

`_owners()` in `scripts/platformkit/ops/paper_desk_process.py` resolved each pid from
`job.pids()` with `psutil.Process`. A child that exited in the gap between the listing and the
lookup raised `NoSuchProcess`, which was counted as the refusal
`child_exited_during_observation`. The step row still read `decision: ran, exit_code: 0`, but
any non-empty `refusals` makes `paper_desk_tick.py` (:259, :265) end the tick as
`refused / step_refusals` with exit 3.

Evidence (local journal `data/cache/paper_desk/journal/`, gitignored):
- 2026-10-06T15:56:31Z `heartbeat:state_root` (capture_watchdog): `decision ran`,
  `duration_s 0.25`, `exit_code 0`, all seven state roots OK,
  `refusals {child_exited_during_observation: 1}`.
- Count of rows carrying this refusal per journal day: 09-30 3, 10-01 1, 10-02 1, 10-03 1,
  10-06 1 (7 total). Short children (sub-second) hit the race.

## Fix

`paper_desk_process.py:117`: `refused(row, "child_exited_during_observation")` becomes
`continue`. A vanished pid is simply not an owner; the next poll decides. Zero-net-line edit
(275 lines before and after).

Why this is safe for every caller of `_owners`:
- Initial observation (:190): empty owners falls to the existing check -- completes only if
  `child.poll()` has a code and containment has no survivors; otherwise raises
  `child_identity_unobservable` and the row is refused `producer_exception` as before.
- Monitor loop (:207): empty owners keeps the previous marker owners; completion still needs
  `child.poll()` not None AND an empty `job.pids()`. A child that is still running keeps hitting
  the RAM / RSS / deadline refusals, so a real vanish without an exit is still a counted refusal
  (`child_timeout` at worst).
- `_cleanup` (:136): runs after `terminate()`, where pids vanishing is the expected outcome;
  survivors and reap timeouts still refuse `cleanup_survivors` / `child_reap_timeout`. The one
  shared-function edit covers it; no separate change.
- `AccessDenied` (`owner_identity_unobservable`) is unchanged.

Pins: `paper_desk_process.py` appears only in `tests/platformkit/ingame/fixtures/s544/must_not_move.json`,
read by `test_case18_must_not_move_at_landing`, which is skipped unless `S544_LANDING=1`; that
pin was already stale before S786 (master LF sha 769f9016... vs pinned d154e15d...). No repin.

## Tests

New `tests/platformkit/ops/test_s786_exit_race.py` (2 cases, both FAIL on master, PASS here):
1. pid listed by `job.pids()`, then `NoSuchProcess`, child exited 0 -> returns 0, `refusals == {}`.
2. pid `NoSuchProcess` but the child never exits -> returns None, refused `child_timeout`, no
   `child_exited_during_observation`.

Per-file runs on the branch (RAM-gated): test_paper_desk_tick 14, test_paper_desk_start 34,
test_paper_desk_process 24, orphan_grace 12, process_s658_review 2, r2_runtime 12, r3_process 2,
r4_process 5, runtime 14, s522_light_ram 35, threaded_zombie_s658 1, s717_capture_retry 36,
s717_process_cause 17 passed; job_posix 13 and start_posix 5 skipped (POSIX only).

## First live check (after landing)

Across the next 48 tick slots: zero journal rows with `child_exited_during_observation`, and no
tick ending `step_refusals` whose only refusal would have been that key. Not verified yet.
