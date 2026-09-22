# S391 redeploy checklist: CONSTRUCT PASS; deployment NOT VERIFIED

Machine: local harness-h50 worktree. No live archive or process table opened.
Binding before-condition, before coding:
`python scripts/platformkit/ops/capture_supervisor.py --help` returned exit 0:
```text
usage: capture_supervisor.py [-h] --name NAME --log-dir LOG_DIR
                             [--min-free-mb MIN_FREE_MB]
                             [--max-backoff-sec MAX_BACKOFF_SEC]
                             [--gap-sec GAP_SEC] [--keep-awake]
                             ...
Opt-in capture supervisor; the child command is opaque.
positional arguments:
  command
options:
  -h, --help            show this help message and exit
  --name NAME
  --log-dir LOG_DIR
  --min-free-mb MIN_FREE_MB
  --max-backoff-sec MAX_BACKOFF_SEC
  --gap-sec GAP_SEC
  --keep-awake
```
`Get-Item scripts/platformkit/ops/capture_deploy_preflight.py` returned exit 1:
```text
Get-Item : Cannot find path 'C:\Users\neelj\nba-harness-h50\scripts\platformkit\ops\capture_deploy_preflight.py'
because it does not exist.
```
The entire S376 runbook below is quoted to preserve EVERY start / stop line
and EVERY OWNER-ONLY item observed before changes:

> # Capture resilience (S376, PREPARE only)
> 
> S376 history is retained below. Its h33 commands are historical preparation;
> use the S391 owner checklist at the end for the main-tree redeploy.
> 
> No capture was started or stopped by this build. No operating-system task or
> power setting was changed. No second independent capture host exists today.
> The supervisor is opt-in and treats each child command as opaque.
> 
> ## Prerequisites
> 
> Use PowerShell on the owner's laptop. These lines target this worktree only.
> The Python 3.10 pythonw executable below exists on the build machine; capture
> dependencies and operating credentials were not exercised. Neither capture
> requires credentials. The books/trades CLI exists in this checkout. The game
> state module is absent here: its prepared command MUST wait for the S358 module
> to land. The guard below refuses to launch that missing module.
> 
> An existing bare capture must be stopped by its owner before starting its
> replacement. Do not run two writers on the same archive. An existing supervisor
> lock always refuses a second launch; it is never stolen, even after a crash.
> Use the same log directory for a name on every launch. Distinct directories
> are distinct lock namespaces.
> 
> ## Prepared start commands (owner runs when ready)
> 
> ```powershell
> Set-Location -LiteralPath C:\Users\neelj\nba-harness-h33
> $capturePythonw = "$env:LOCALAPPDATA\Programs\Python\Python310\pythonw.exe"
> $capturePython = "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
> $captureLogs = 'C:\Users\neelj\nba-harness-h33\data\cache\capture_supervisor'
> ```
> 
> Books + trades:
> 
> ```powershell
> Start-Process -WindowStyle Hidden -FilePath $capturePythonw -WorkingDirectory C:\Users\neelj\nba-harness-h33 -ArgumentList @('-m','scripts.platformkit.ops.capture_supervisor','--name','books','--log-dir',$captureLogs,'--min-free-mb','2000','--max-backoff-sec','300','--gap-sec','90','--keep-awake','--',$capturePython,'-m','scripts.platformkit.ingame.local_capture_runner','--output-root','C:\Users\neelj\nba-harness-h33\data\cache\ingame_books_local')
> ```
> 
> Game state (blocked until its source lands; default archive root):
> 
> ```powershell
> if (-not (Test-Path -LiteralPath scripts\platformkit\ingame\local_state_capture.py)) { throw 'State capture source is absent; wait for S358.' }
> Start-Process -WindowStyle Hidden -FilePath $capturePythonw -WorkingDirectory C:\Users\neelj\nba-harness-h33 -ArgumentList @('-m','scripts.platformkit.ops.capture_supervisor','--name','state','--log-dir',$captureLogs,'--min-free-mb','2000','--max-backoff-sec','300','--gap-sec','90','--keep-awake','--',$capturePython,'-m','scripts.platformkit.ingame.local_state_capture')
> ```
> 
> The parent uses pythonw and the child uses CREATE_NO_WINDOW. Keep-awake lasts
> only for the supervisor process and is cleared on orderly exit. On non-Windows
> hosts, --keep-awake is refused. It does not change a power plan or registry.
> 
> ## Exact stop commands
> 
> These create persistent supervisor stop sentinels with a flushed filesystem
> write. The supervisor terminates only its own child and waits up to 20 seconds,
> then kills that child if necessary. Stop observation normally takes at most
> one five-second loop tick; filesystem and process operations can take longer.
> 
> ```powershell
> & $capturePython -c "import os; f=open(r'C:\Users\neelj\nba-harness-h33\data\cache\capture_supervisor\STOP_books','ab'); f.flush(); os.fsync(f.fileno()); f.close()"
> & $capturePython -c "import os; f=open(r'C:\Users\neelj\nba-harness-h33\data\cache\capture_supervisor\STOP_state','ab'); f.flush(); os.fsync(f.fileno()); f.close()"
> ```
> 
> After confirming both supervisors exited, remove the respective STOP sentinel
> before a deliberate restart. Also check the capture's own STOP / STOP_STATE
> sentinel; the supervisor never removes either. Leaving a child stop sentinel
> in place causes repeated clean exits and bounded retries.
> 
> ## Evidence and recovery
> 
> Each name produces supervisor_NAME.jsonl, supervisor_NAME.heartbeat.json and
> supervisor_NAME.lock in the log directory. The heartbeat contains the parent
> pid, owned child pid, strict integer restarts_total, last_child_start, last_gap
> and exact decimal free_mb as a JSON string. Its atomic replacement mtime marks
> the latest completed tick. A .tmp file can remain after an interrupted write;
> the previous heartbeat remains readable. Restart counts cover this supervisor
> invocation; historical child_start records remain in the journal.
> 
> Every child exit, including status zero, has one child_exit record with UTC
> start/end, exit code and monotonic duration. Retries grow from one second up to
> the configured maximum and reset after a run of at least 600 seconds. Disk
> free space is checked on the log directory's volume before each attempt;
> disk_refusal prevents launch and is checked again each loop. The units are
> 1024 * 1024 bytes per MB. min-free-mb must be positive and at most 2**40;
> gap-sec and max-backoff-sec are strict integers in 1..86400.
> 
> A wall/monotonic disagreement exceeding gap-sec in either direction, or wall
> elapsed between ticks exceeding gap-sec, produces host_gap with both UTC ticks.
> This includes suspend when both clocks advance equally. Collection health still
> requires checking the child's archive and heartbeat; a live child can be stalled.
> 
> After a host crash or reboot, a stale lock deliberately blocks automatic
> restart. The owner must confirm the recorded parent and child are no longer
> running before removing that lock. Never identify a process by a substring or
> signal a PID merely because an old file names it. Preserve the journal and old
> heartbeat; they bound the last completed observation. There is no exact crash
> timestamp or automatic recovery through a stale lock.
> 
> A torn final journal line is saved to supervisor_NAME.partial, then the complete
> prefix is atomically restored before further appends. journal_recovery counts
> discarded bytes; the quarantine holds the most recent torn suffix. Write errors
> propagate and trigger owned-child cleanup. A fully unwritable volume may also
> prevent recording the refusal or exit: retain its prior heartbeat and do not
> treat silence as successful collection.
> 
> ## OWNER-ONLY: future host resilience (not executed by any agent)
> 
> - Task Scheduler: create an "At log on" task for each capture name only after
>   its module is present. Set the program to the pythonw path above, Start in
>   to this worktree, and arguments to the corresponding complete supervisor
>   argument sequence above. Select "Do not start a new instance". Task Scheduler
>   does not bypass stale locks or STOP files. Confirm existing bare captures are
>   stopped before enabling the tasks. No task is registered by this lane.
> - Power settings: the owner may choose an AC sleep timeout appropriate for
>   collection, and must separately decide battery and lid-close behavior.
>   Keep-awake does not protect against power loss, reboot, or explicit sleep.
>   No agent changes these settings or registers tasks.
> - Second independent host: provision another machine with its own storage,
>   dependency environment, capture roots, supervisor journals and power/network
>   path. Both captures need no credentials. Keep the streams distinguishable;
>   compare their observed gaps before any combined analysis. No second host
>   exists today, and no continuity across host loss is established.
> 
## Imported landed API read before coding
Only project import: `scripts/platformkit/execution/venue_time.py`, read in full.
Exact signature: `def parse_venue_time(value: object) -> float | None:`.
Its parser validates zone/calendar but truncates fractions to microseconds.
The new tool validates with it, parses whole seconds through it, then adds
all original fractional digits as integer nanoseconds for strict comparisons.
No capture or supervisor module is imported. Their source was read for paths,
CLI flags, receipt fields and heartbeat schema. No REAL ROW is supplied by S391;
fixtures reproduce the landed schema and spec paths without opening real data.

## Implemented scope and evidence
- New read-only `scripts/platformkit/ops/capture_deploy_preflight.py` (300 lines).
- New `tests/platformkit/ops/test_capture_deploy_preflight.py` (284 lines).
- Edited `docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md` (257 lines), preserving
  the complete S376 history and adding the owner checklist and exact commands.
- Native Windows inspection uses process snapshots, read-only process memory,
  module arguments, working directories and visible console titles; it imports
  no capture daemon and executes no subprocess. Git identity is read from loose
  or packed refs, including worktree common directories. Archive data is read only.
- BEFORE records each writer and launcher CWD, output root, directory commit,
  per-sport write mtime/counters, stop sentinels and discovered supervisor locks.
  Two writers of the same kind/root refuse even outside the queried root.
  Windows path casing cannot split one target into two identities.
- AFTER adds exact writer counts, matching supervisor lock/heartbeat identities,
  restart timestamps, master-ref equality, book profile digest equality, successful
  receipts after restart and title checks for classic and Windows Terminal consoles.
  Idle sport heartbeats need not fabricate receipts; each writer and active sport
  must have new receipts. Missing or malformed required evidence refuses with 3.
- Strict counters preserve integers above binary floating-point exactness.
  Future receipts are counted before schema checks or duplicate grouping.
  Conflicting duplicate records and duplicate PIDs are refused independently of
  input order. Complete timestamp fractions survive strict restart/as-of tests.
  Receipt JSON uses Decimal for decimal tokens; prices/quantities are not evaluated.
- Evidence output is a temporary file plus flush/fsync and atomic replacement.
  Injected sync/replace failures preserve the previous completed output.
- S388 is not present: the current runner has neither --schedule nor the profile
  file. The owner checklist gates on landing both BEFORE stopping captures.
  The supplied contract alias docs/evidence/VERIFIER_CONTRACT.md is absent;
  the landed docs/evidence/tracking/VERIFIER_CONTRACT.md was used.

## Reproduction and checks
All tests are deterministic constructions in temporary directories; no sampled
or scored metric is reported. The first test consumes the complete landed-shape
fixture through the CLI and checks the emitted JSON and exit status.

```text
python -m pytest tests/platformkit/ops/test_capture_deploy_preflight.py -q -p no:cacheprovider
45 passed
python -m scripts.platformkit.ops.capture_deploy_preflight --help
exit 0
python scripts/platformkit/ops/capture_supervisor.py --help
exit 0 (binding before-condition)
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ops/capture_deploy_preflight.py tests/platformkit/ops/test_capture_deploy_preflight.py docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md docs/evidence/harness/S391_redeploy_checklist_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S391_spec.md
PASS vocab
PASS crlf
PASS loc
PASS schema
PASS head_slice
PASS spec_threshold
PASS proposed
PASS removed_artifact
PASS row_duplication
```
Runbook: eight PowerShell blocks parsed with zero syntax errors; none executed.
ASCII: all four owned artifacts. Line counts use len(text.splitlines()).
Review corrections were exercised by the fixture tests: idle sports, launcher
identity, Windows path casing, duplicate conflicts, console class, integer
coercion, future nanoseconds and atomic failure recovery.
The earlier 325-line candidate failed the LOC check; the final module is 300.
No thresholds or pre-existing executable modules were edited. Q1-Q5/Q9 scored
requirements do not apply to this construct-only operational preparation.

## FIX 1b
Binding inputs: `_verdict_s391_1b.md` and S391_spec.md, including the master
copy read with git show; neither spec copy contains an AMENDMENT block.
All reproductions use constructed process tables and fixture archives.
Before editing the module, the expanded per-file test returned:
```text
5 failed, 45 passed in 4.39s
```
1. BLOCKING: launcher and supervisor records were incomplete. Reproduced both
   capture types with hidden_launch, supervisor and runner command lines:
   `assert [20] == [10, 20, 30]` and `assert [21] == [11, 21, 30]`.
   Command-line capture matching now emits complete process records separately
   from invoked-module writer matching. Records retain observed cwd and add
   cwd_argument (MISSING when absent), PID, parent PID, resolved output_root and
   the revision of the effective directory. Existing observer fields remain.
   Regression: test_complete_launcher_supervisor_runner_records, 2 cases,
   checks all fields, both capture types, one writer, and reversed input order.
2. BLOCKING: empty root environment values resolved to cwd. Both regressions
   failed with the same suffix difference (distinct fixture directories):
   ```text
   - nt_us0\main\data\cache\ingame_books_local
   + nt_us0\main
   - nt_us1\main\data\cache\ingame_books_local
   + nt_us1\main
   ```
   The resolver now uses environment_value or the documented default archive
   path. test_empty_root_environment_uses_runner_default covers both variables
   and verifies a second explicit-default writer causes duplicate refusal.
3. CORRECTION: JSON lacked the directory-revision limitation. Reproduced:
   `KeyError: 'commit_scope'`. Reports now include the string
   `commit_scope=directory_at_inspection_not_loaded_process_code`.
   Regression: test_json_labels_commit_scope. The runbook is unchanged in this
   pass, including its fixed-tree requirement and OWNER ONLY minutes 2-6.
After the module fixes the same per-file command returned:
```text
50 passed in 3.54s
```
The five new regression cases pass, alongside all 45 original cases.
Final owned-file sizes: module 300 lines; tests 293 lines; runbook 257 lines.
No process-control call or subprocess path was introduced.
Both documented help commands returned exit 0 (2/2). There is no self-check
option on either CLI. Contract preflight initially rejected a 301-line module;
after consolidating statements it returned all 9 PASS checks and exit 0, using
the same four owned paths, --base master and --spec from Reproduction above.
The verdict file was excluded. NOT VERIFIED remains the final section.

## NOT VERIFIED
- No production archive, process table, heartbeat, STOP, lock or live window was
  opened by this build. No capture or other process was started, stopped or
  signalled by the tool. Build commands ran only help, tests and static checks.
- Native Windows Toolhelp/PEB and window inspection were not executed against
  real processes; only injected process/window tables exercised the evaluator.
  Unsupported hosts, inaccessible processes and failed native queries refuse.
- No owner commands were executed, no deployment completed, and no live
  watchdog, schedule/profile loader, TLS/CA bundle or ESPN request was exercised.
- Current S388 absence prevents the documented AFTER proof on this checkout.
  State captures do not emit S388 profile hashes; that check applies to books.
- A heartbeat replaced after the observation cutoff causes a counted refusal;
  an owner may need a fresh preflight during concurrent writes. No live
  ten-minute duration or large-archive resource bound was established.
- Git-directory identity cannot prove the exact bytes an already-running Python
  interpreter imported before a checkout change. Keep the source tree fixed.
- No power-loss filesystem test, inaccessible-process test, alternate Windows
  architecture or hidden/pseudoconsole topology was exercised on a real host.
- Independent verifier acceptance and lane_commit remain outstanding.
