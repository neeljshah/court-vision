GAP S376 | sport all captured | worktree harness-h33 (master-based) | log cx_s376_capture_supervisor
# Capture supervisor: one laptop must not be able to silently end a forward series (design: docs/evidence/harness/ASTRA_ROUND13_2026-09-21.md section 1 row 3)

SINGLE PROBLEM: both forward captures (books + trades, game state) are bare processes on one laptop. A crash, a sleep / resume, a
reboot or a full disk ends the series and nothing records WHEN collection stopped, so a gap cannot even be declared honestly.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ops/capture_supervisor.py` fails.

CHANGE (NEW files only; import nothing from the capture modules -- the child is an opaque command line):
1. scripts/platformkit/ops/capture_supervisor.py (<= 300 LOC, stdlib only): `--name <id> --log-dir <dir> [--min-free-mb 2000]
   [--max-backoff-sec 300] [--gap-sec 90] [--keep-awake] -- <child command ...>`. Behaviour: single-instance lock file per --name
   (second start exits nonzero, never steals); start the child with no console window (CREATE_NO_WINDOW on Windows); when the child
   exits for ANY reason write one `child_exit` record (exit code, UTC start / end, run seconds) and restart it after a bounded
   exponential backoff that resets after 600 s of healthy run; before every start check free space on the --log-dir volume with
   shutil.disk_usage and, below --min-free-mb, write `disk_refusal` and do NOT start (re-check each loop); a wall-clock jump larger
   than --gap-sec between two supervisor loop ticks (loop period 5 s, time.time vs time.monotonic disagreement) writes a `host_gap`
   record with the last tick before and the first tick after -- this is how sleep / resume becomes a declared gap; a STOP_<name> file
   in --log-dir stops the child it started (terminate, then kill after 20 s) and exits 0; the supervisor NEVER signals any process it
   did not start. --keep-awake calls SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) for the life of the process only
   and clears it on exit (no power-plan or registry change); on a non-Windows host the flag is refused with a clear message.
   Every record is one JSON line appended to <log-dir>/supervisor_<name>.jsonl (open, append, flush, os.fsync) plus an atomically
   replaced heartbeat JSON (pid, child pid, restarts_total, last_child_start, last_gap, free_mb). All counts are strict ints.
   Every except clause counts or re-raises.
2. tests/platformkit/ops/test_capture_supervisor.py: a fake child (sys.executable -c ...) that exits at once -> restart with growing
   backoff (inject the sleep and both clocks; no real waiting); healthy-run reset; disk refusal (inject disk_usage); host_gap on an
   injected clock jump and none without one; STOP file; second instance refused; a child that ignores terminate is killed; the
   supervisor's own records parse as JSON and carry timezone-aware UTC times.
3. docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md: exact start / stop lines for both captures under the supervisor via pythonw (no
   console window), and an OWNER-ONLY section (NOT executed by any agent): registering a Task Scheduler "at log on" entry, power-plan
   sleep settings, and a second independent capture host (no credentials are needed for either capture); state plainly that no
   second host exists today.
4. Memo docs/evidence/harness/S376_capture_supervisor_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only, construct tests, no network, no real capture started or stopped by the builder, nothing
registered with the operating system. ACCEPTANCE: the per-file test passes; --help works; diff = NEW files only; <= 300 LOC per
file; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list. The pod is OFF.
