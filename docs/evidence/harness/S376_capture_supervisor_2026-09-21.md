# S376 capture supervisor - 2026-09-21

Status: PREPARE; NOT VALIDATED for operational collection. The candidate module,
construct tests and runbook are on disk. Independent FIX 1b verification and
lane_commit remain outstanding. No capture was started or stopped by this lane.

## Binding premise (executed before coding)

Machine: local Windows laptop; worktree C:/Users/neelj/nba-harness-h33.
Command: `ls scripts/platformkit/ops/capture_supervisor.py`
Exit code: 1. Exact output:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h33\scripts\platformkit\ops\capture_supervisor.py' because it does
not exist.
At line:2 char:1
+ ls scripts/platformkit/ops/capture_supervisor.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\...e_supervisor.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```

The before-condition holds. The binding source is
docs/evidence/tracking/specs/S376_spec.md. The contract is
docs/evidence/tracking/VERIFIER_CONTRACT.md; the shorter path named in the task
does not exist in this checkout. Sections B and Q were read before coding.

## Imports, source scope and fixture

Landed module imports: NONE. The new supervisor uses only the standard library
and never imports either capture. Consequently there is no landed Python API
signature on which this implementation relies. The test imports the new module
through `from scripts.platformkit.ops import capture_supervisor as cs`.

S376 provides no REAL ROW. The first test consumes the explicit fixture
`[sys.executable, "-c", "raise SystemExit(7)"]` through actual Popen, child exits,
injected backoff, JSONL journal, heartbeat and STOP. Only disposable toy children
are executed. All clocks, disk conditions and waits used for failure scenarios
are constructed. No archive, video, network or pod input was opened.

The runbook's books command was checked against
scripts/platformkit/ingame/local_capture_runner.py, including its parse_args
options and run_local_capture STOP handling. These are documentation references,
not imports. The state module is absent; S358 and S380 specs document the pending
state route. Its prepared no-argument launch is protected by a source-file guard.
The local Python310 pythonw executable exists; its capture environment was not
validated. No second independent capture host exists today (binding premise).

## CHANGE coverage

1. scripts/platformkit/ops/capture_supervisor.py: exclusive O_EXCL name lock,
   opaque child launch with Windows CREATE_NO_WINDOW, child_exit with aware UTC
   start/end and monotonic duration, bounded exponential retry and 600-second
   reset, Decimal disk guard, wall-elapsed and signed clock gap detection, persistent
   STOP handling and owned-child terminate/kill, scoped keep-awake, durable
   JSONL and atomically replaced heartbeat. Counts are integers; invalid count
   types are refused. Each caught exception records a refusal/timeout or exits
   through a raised exception. Disk and clock errors cannot silently proceed.
2. tests/platformkit/ops/test_capture_supervisor.py: n = 45 (CONSTRUCT), all 45
   collected cases passed. Coverage groups: real toy child and increasing/capped
   retries; healthy reset; disk refusal then recovery; unchanged/boundary/forward/
   backward clocks; terminate and kill; preexisting STOP and stale lock; live
   second-instance refusal; spawn refusals; torn startup journal; atomic-write
   failure; storage failure while a child runs; strict count and Decimal inputs;
   invalid free-byte counts; keep-awake normal/failure cleanup and non-Windows
   refusal; execution-state flags/API failure; non-finite clocks; append fsync;
   partial append during cleanup followed by another invocation.
3. docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md: exact prepared pythonw start
   lines and durable STOP commands for books and state; missing-state guard;
   documented stale-lock recovery, full-disk limitations and heartbeat fields;
   OWNER-ONLY Task Scheduler, sleep settings and independent-host preparation.
4. This memo records the premise, implementation, tests and limits.

The read-only review found a cleanup append after a torn journal write could
make the final line malformed yet newline-terminated. Recovery now runs before
every append. The new lifecycle regression reproduces that injected fault and
checks valid journal records after cleanup and a subsequent invocation. The
follow-up read-only review reported no remaining concrete spec blocker; it does
not substitute for the independent verifier specified by the owner.

## Reproduction and mechanical checks

```text
python -m pytest tests/platformkit/ops/test_capture_supervisor.py -q -p no:cacheprovider
python -m scripts.platformkit.ops.capture_supervisor --help
python -m scripts.platformkit.tracking.contract_preflight --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ops/capture_supervisor.py tests/platformkit/ops/test_capture_supervisor.py docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md docs/evidence/harness/S376_capture_supervisor_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S376_spec.md
```

Observed FIX 1b test outcome: 45 passed, zero failed, zero skipped. An earlier run had
33 passed and one failure in a test's OS mock; that mock was corrected before
the final run. Both CLI help commands exited 0. Only the named test file ran.
Preflight result: 9 PASS, 0 FAIL, exit 0 (vocab, crlf, loc, schema, head_slice,
spec_threshold, proposed, removed_artifact, row_duplication).
Source checks: all four files ASCII and <=300 lines using len(text.splitlines()).
Lines: module 245; tests 300; runbook 118; memo below 300. git diff --name-only was
empty; git status listed exactly these four new files and no existing edits.
No git mutation or commit was attempted; handoff remains files on disk.

Contract self-check: no existing schema, caller, file, threshold, production
configuration or registry was changed. No scored comparison or sampled corpus
claim is made; this is construct coverage. Q6 wording and all mechanical checks
are subject to the preflight command above. The pod was not accessed.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1b

Binding review: `_verdict_s376_1b.md`, read before any other file. The local spec
and `git show master:docs/evidence/tracking/specs/S376_spec.md` have no AMENDMENT
blocks. All reproduction inputs below are CONSTRUCT, on this local worktree.

1. BLOCKING, suspend detection: the previous condition considered only clock
   disagreement. Exact minimal reproduction before the module change:

   ```text
   wall_delta=3605, mono_delta=3605, gap=90; disagreement=0, host_gap=False
   suspend regression: FAIL
   ```

   The condition now also declares host_gap when wall elapsed exceeds gap_sec.
   test_clock_gap_boundary covers eight cases, including equal clock advances
   at 90, 91 and 3605 seconds, normal ticks and signed disagreement. The runbook's
   affected gap paragraph now describes the wall-elapsed condition. After:

   ```text
   wall_delta=3605, mono_delta=3605, gap=90; disagreement=0, host_gap=True
   suspend regression: PASS
   ```

2. BLOCKING, STOP chronology: the timestamp preceded the terminate wait.
   Exact minimal reproduction before the module change:

   ```text
   stop_at=1800000000, terminate_wait=20; terminate_timeout=1800000020, child_exit=1800000020, supervisor_stop=1800000000
   journal chronology: FAIL
   ```

   The STOP branch now calls _clock() after _finish() and records that wall time.
   test_stop_terminates_only_owned_child asserts nondecreasing journal timestamps
   for both terminate and kill paths, with STOP observed at 1800000000. After:

   ```text
   stop_at=1800000000, terminate_wait=20; terminate_timeout=1800000020, child_exit=1800000020, supervisor_stop=1800000020
   journal chronology: PASS
   ```

3. NOTE, confirmed controls: no fix requested. Locking, owned-child signaling,
   retry bounds, disk refusal, persistence, keep-awake and OWNER-ONLY instructions
   are unchanged. No pre-existing module outside S376 ownership was edited.

The minimal probes used the test Clock/Child helpers and Supervisor._loop(),
with in-memory journal/heartbeat/STOP seams. Both probes were run before and
after the module fixes: 2/2 PASS after. The persisted-journal regressions were
added first; the per-file run then reported `4 failed, 41 passed`, including
`assert 0 == 1` for the equal-clock suspend and a timestamp-order assertion for
the kill path. The same per-file command after the fixes reported `45 passed`.
Both documented help commands exited 0 (2/2); there is no separate self-check
option. Contract preflight covers all four owned files, excludes the verdict,
and reports 9 PASS, 0 FAIL. No operational capture command was executed.

## NOT VERIFIED

- Real books/trades or state collection, external services, archive completeness,
  stalled-child detection, and missing state-module integration.
- Real Windows suspend/resume, reboot, host power loss, physical disk exhaustion,
  forced supervisor death or independent-host continuity.
- Actual keep-awake operating-system behavior; tests replace the Windows call.
- Failed terminate/kill/wait system calls, interrupted journal recovery replace,
  and storage that stays unwritable throughout cleanup.
- Automatic restart through a stale lock: deliberately refused. Owner recovery
  is required. An exact crash timestamp cannot be reconstructed from silence.
- Any existing bare capture's state, installed capture dependencies, Task
  Scheduler registration, power-plan changes or a second capture host.
- Independent verifier acceptance, deployment, git commit and publication.
