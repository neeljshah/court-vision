# S658 cloud result -- 2026-09-30 (desk-improve one-off, cloud/S658-2026-09-30)

Row: the recorder run path refuses to start off Windows in three unpinned files (portability
audit section 1). Spec: `docs/evidence/harness/S658_spec_2026-09-30.md` (+ AMENDMENT 1).
Base a60dcb09a; three commits (1 job object, 2 relaunch + config + systemd, 3 lock takeover).
Everything is behind the adoption switch `CV_DESK_POSIX=1` (default OFF). PAPER ONLY; no
calibration or scoring claim is made or touched by this row.

## Verdicts

- Pre-build critique (independent Opus sub-agent): REVISE, 16 items -> AMENDMENT 1 (11 adopted,
  item 2 answered by the leader-ticks check instead of a redesign, the rest stated as LIMITs).
- CONTRACT tier (independent Opus sub-agent): ACCEPT WITH CORRECTIONS. Its one correction was that
  this memo did not exist yet; it exists now. Notes: `default_query` dispatches to /proc on POSIX
  even with the switch off, but no production caller reaches it with the switch off
  (reconcile / child_identity / lock_payload return first); and the "refusal while the owner
  lives" case is shown on a real process only for the child; the owner case is shown with
  injected seams (twin).
- ADVERSARIAL tier (independent Opus sub-agent): ACCEPT WITH CORRECTIONS. All 12 mutants killed
  (guardian killpg removed, terminate no-op, popen kwargs dropped / isinstance inverted, naive
  stat split, zombie-as-alive, legacy refusal removed, _versioned nt-only, os.rename on POSIX,
  no kill(pid,0) check, setsid without new session, --keep-awake kept). One CORRECTION, FIXED
  in commit 1: the guardian and PosixJob._ours caught only FileNotFoundError around the
  /proc/<leader>/stat read. A leader reaped between open and read raises ProcessLookupError,
  and the guardian then skipped the killpg. Regression: test_leader_reaped_mid_read_is_still_ours.
  The fix was not re-verified by a sub-agent (one fix round, per the prompt).
- Overall: ACCEPT WITH CORRECTIONS (corrections applied). PORTABLE: yes (code and tests run on
  Ubuntu); adoption is WINDOWS-or-owner (a Linux recorder box decision).

## What is done and verified here (Ubuntu cloud container, Python 3.11.15)

1. JOB (done, verified): PosixJob = new process group (start_new_session) + membership by pgid
   (zombies excluded, bound 1024) + killpg on terminate/close + a guardian that kills the group
   on tick death; RSS limit = run_producer's existing poll (same decisions/reasons/refusal keys).
   Producer identity under the switch = /proc boot_id + start ticks; an exited single-thread
   zombie is dead.
2. RELAUNCH (done, verified): setsid_create (reason setsid_created, benign) replaces WMI under
   the switch; an exited zombie row no longer defers inspect_capture. The derived POSIX config
   comes from paper_desk_config_posix.py; the committed Windows config is byte-identical.
   The systemd unit and timer are text examples (syntax only: `systemd-analyze verify` rc 0).
3. LOCK TAKEOVER (done, verified): /proc start ticks + kernel boot_id seams; versioned lock,
   pre-spawn "unresolved" marker, no-clobber rollback (link + unlink) under the switch; a legacy
   {"pid"} lock is refused (lock_owner_unresolved). Real supervisor: SIGKILL -> restart refused
   child_still_running while its child lives -> child gone -> restart takes over and runs.
4. START smoke: `CV_DESK_POSIX=1 paper_desk_tick --dry-run` with the derived config in a scratch
   worktree: rc 0, every step decided (lock_acquired, 3 x capture would_run, heartbeats,
   schedule, nights, census), nothing launched.

## Tests (one file per process: `python3 -m pytest tests/platformkit/ops/<file> -q -p no:cacheprovider`)

New, switch set inside the tests: test_paper_desk_job_posix.py 13 passed;
test_paper_desk_start_posix.py 5 passed; test_capture_supervisor_lock_posix.py 8 passed;
test_capture_supervisor_lock_posix_twin.py 53 passed (59 lock_recovery cases - 7 named
deselections + 1 meta check). Deselected: base case12, 1b run_case12, 1b
lock_payload_non_windows (switch-OFF by design); base case6, case7, 1b run_case6 (legacy lock,
refused under the switch); 1d reconcile_sidecar_write_failure (injects os.rename; POSIX uses link).

Pre-existing, `env -u CV_DESK_POSIX`, identical on base and HEAD (contract tier ran both):
paper_desk_job 4F (Windows-only, excluded from "green"); paper_desk_process 24P; r3_process 2P;
r4_process 5P; orphan_grace 12P; paper_desk_start 34P; paper_desk_tick 14P; capture_supervisor
45P; lock_recovery 17F/2P, _1b 11F/3P, _1c 10F/4P, _1d 7F/5P (Windows-only; the twin re-runs
them); r5_attention 1F/1P (red on base too, not S658); r6_attention 39P; r4_attention 29P;
atomic_retry 16P; paper_desk_runtime 14P; also r2/r3/r4_runtime 12/9/7P, s522_light_ram 35P,
r7/r8/r9_attention 42/9/10P. No pre-existing test file was edited.
Switch-ON note: test_paper_desk_start.py and test_paper_desk_process.py are switch-OFF files
(their process fakes carry no .pid / use the Windows config); do not run them with the switch set.
A single unexplained first-run failure of the start_posix e2e case was seen once by the
adversarial tier and not reproduced in about 80 reruns; treat it as a possible timing flake.

## NOT VERIFIED (needs a real Linux recorder box, a Windows host or data/)

- Windows behaviour byte-identical: argued from the diff (every new branch is behind
  os.name != "nt" first); not run on Windows. Laptop regression run of the Windows-only files
  (test_paper_desk_job.py, the four lock_recovery files) is the landing check.
- Real captures under the POSIX path (venue and sports hosts blocked here); a real non-dry tick.
- systemd runtime (timer firing, KillMode=process keeping setsid supervisors, linger, reboot).
- hidepid-mounted /proc; a shared or network log dir; a pid namespace boundary.
- A wall-clock step on a live box (start ticks are btime-free by construction; not stepped here).
- Launcher identity (paper_desk_start / reconcile) still uses psutil create_time (LIMIT).
- A descendant calling setsid() escapes the group (no POSIX equivalent of no-breakaway; LIMIT).
- A child exiting before child_identity reads it is recorded "unresolved"; a later SIGKILL of
  the supervisor then needs a manual lock clear (rare; LIMIT).
