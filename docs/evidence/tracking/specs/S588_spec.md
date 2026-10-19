GAP S588 | all (paper desk fault matrix, C5 extension) | worktree nba-harness-h257 | Opus builds (codex down)
# Three more scripted faults for the unattended desk (FIVE_HOUR_PLAN_2026-09-30_C.md C5): a live writer during the watchdog read, the OS-sleep signature (all three supervisors dead with journals ending on child_start), and an S561-style cherry-pick onto a master with a conflicting shared file
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q (S-row). Operations language only. Extends S581 (landed f4169ddfe; fix-forward be8ba5da9). Written by the system-test lead 2026-09-30 ~04:0xZ on master e8111a439+.
WHERE THIS ROW RUNS: scratch roots only, through the S581 runner and its live-state guard; no live process, no network, no Windows task, no capture launch, never a git command in the live checkout (every git case runs in a scratch repository it creates).

SINGLE PROBLEM: the plan's C5 faults are the three that took the desk down or nearly did in the last week (a heartbeat read that called a live writer silent; the 09-25 and 09-29 OS-sleep outages that left all three supervisors dead with their journals ending on child_start; the 08:37Z S561 adoption cherry-pick onto a moving master). None is scripted. Case (b) of C5 is dropped (ruling 1: --min-free-mb is free DISK).

CHANGE (owned NEW: scripts/platformkit/ops/system_fault_cases_c5.py (<= 300 lines; a _b companion allowed). MODIFIED: scripts/platformkit/ops/system_fault_matrix.py -- the group tuple gains "c5" (one line); tests/platformkit/ops/test_system_fault_matrix.py -- CASE_IDS gains 37, 38, 39 and DEFECT_ROWS any new DEFECT with its exact failed checks; docs/evidence/harness/SYSTEM_FAULT_MATRIX_2026-09-29.md -- a C5 section generated from the runner JSON):
1. CASE 37 watchdog_live_writer: a scratch state root (state/mlb/<day>.jsonl built from the committed S581 state_mlb fixture rows re-stamped around T, plus a faithful _heartbeat.json with n_games_live 1, last_write_ts, rows_written_total, last_adapter_error null). (i) capture_watchdog.monitor(root, clock=...) with a clock that returns T before the read and T+12 s after it, where the shard's newest rows and last_write_ts are stamped T+5 s (written during the read): expected OK with no invalid_tail_timestamps (S601: now is taken after the last read, capture_watchdog.py:253-261). (ii) a real thread appending rows stamped with time.time() while monitor runs with the real clock: expected OK. (iii) control: heartbeat and rows 20 min old: expected SILENT or STALE (the alarm still fires). Named checks: frozen_clock_ok, live_thread_ok, stale_control_fires. Evidence also records what assess() says with a single start-of-read clock (the pre-S601 semantics) for the (i) inputs.
2. CASE 38 os_sleep_all_dead: a scratch paper-desk root whose scratch config has the three captures (fake argv) and whose three supervisor journals end on child_start (no exit, no stop), with stale supervisor_<name>.lock files naming dead pids, heartbeats 10 h old, and each capture's launch state file confirmed 10 h earlier. One Desk tick at "logon" with processes=[] (all dead), RAM high, an injected create seam counting launches: expected three launches in that one tick (capture_started x3), no capture_backoff, no owner-intervention; a second tick 30 min later with the three launched supervisors now present in the process list: capture_present x3, zero launches. Variant: RAM below the tick's capture floor at logon -> all three deferred, then the next tick with RAM -> three launches. The S510/S583 scanner at the logon instant reports each outage (capture_outage or supervisor_absent) and no capture_crash_loop. Named checks per assertion. Cite paper_desk_start.py start_capture and inspect_capture, paper_desk_tick.py capture(), paper_desk_issue_capture.py.
3. CASE 39 adoption_cherry_pick_conflict: in a scratch git repository created under the case directory (git init; never the live checkout): a base commit with a shared file (a .gitattributes-like list plus a module file); a worktree branch commit (the adoption row) that appends to the shared file and edits the module; a later master commit that also appends to the shared file. (i) git cherry-pick of the row onto master conflicts; git cherry-pick --abort restores HEAD, the index and the module byte-for-byte, and leaves no CHERRY_PICK_HEAD; (ii) without the abort the module/shared file hold conflict markers (evidence of the hazard); (iii) after a clean cherry-pick (a master commit that does not touch the shared file), `git merge-base --is-ancestor <worktree sha> HEAD` is nonzero while `<landed HEAD sha>` is zero -- the S561 relaunch preflight (docs/operations/relaunch_books_s561_2026-09-30.ps1 in the S561 worktree) therefore needs the LANDED sha. Named checks: conflict_detected, abort_restores, landed_sha_required. This case documents git mechanics; the adoption procedure itself is a session cron prompt (not code) -- disclosed.
4. The low-RAM night rehearsal of C5 is S581 case 8 (exit 4 then the tick): since S520(b) landed it reads night_deferred_ram and retries without the 3 h backoff; the memo states this, no new case.

CASES: the three cases above, each with named checks; the pinned test covers them in the landed layout.
EVIDENCE: per-file run of tests/platformkit/ops/test_system_fault_matrix.py (all green); a full runner pass; the memo section generated from the runner JSON; peak RSS of each new case (psutil, must stay < 200 MB).
MANDATORY DISCLOSURES: case 39 tests git mechanics, not the cron prompt; case 37's frozen-clock variant cannot run the pre-S601 code (it records the single-clock assess() result instead); the S561 findings already posted in .planning/NOW.md (the 08:37Z cherry-pick of 5d89469c0 conflicts on .gitattributes on current master; the preflight refuses the worktree sha).
NOT IN SCOPE: changing capture_watchdog.py, paper_desk_start.py, the tick, the scanner or any relaunch script; running any PowerShell script; touching the live checkout's git state.
AMENDMENT 1 (PRE-BUILD; appended verbatim by the system-test lead from s588_critic_r1.md):
AMENDMENT 1 (PRE-BUILD) -- binding; this block wins over the body where they differ.
```
AMENDMENT 1 (PRE-BUILD, critic r1 2026-09-30). THIS BLOCK WINS.
A1 OWNED-LIST WORDING. CASE_IDS is derived (test_system_fault_matrix.py:24); the edit is the literal at
   tests/platformkit/ops/test_system_fault_matrix.py:39, which becomes
   assert CASE_IDS == [*range(1, 30), 32, 33, 34, 35, 36, 37, 38, 39]. system_fault_matrix.py:40 group tuple gains
   "c5" (module scripts/platformkit/ops/system_fault_cases_c5.py; a _b companion imports from it, is NOT in the tuple).
   Expected: all three cases PASS, DEFECT_ROWS unchanged. Any DEFECT found at build = stop and hand back with the
   failed checks (no new register row invented by the builder).

A2 CASE 37 -- exact fixture (capture_watchdog.py:82-110 read_sources, :147-245 assess, :248-270 monitor).
   a. Root = <work>/state_root containing ONLY state/mlb/ (NO kalshi/ dir: capture_watchdog.py:88, S607 -- with
      kalshi/ present state/ is never read and the case would silently test nothing). Expected source keys ==
      ["state/mlb"] exactly (checked; any other key or "root" = check fails).
   b. T = 1790712000.0 (2026-09-29T20:00:00Z, fixed; never time.time() for (i)/(iii)). Shard =
      state/mlb/2026-09-29.jsonl (the day of the FIRST clock call, :256). Rows = the 50 rows of
      tests/platformkit/ops/fixtures/fault_matrix/state_mlb_2026-09-29.jsonl.gz, row i re-stamped in BOTH
      response_end_ts and capture_ts (response_end_ts is the key row_time reads first, :75-80) as ISO
      "%Y-%m-%dT%H:%M:%S.%fZ": i=0..48 -> T-240+5*i (row 48 = T); row 49 -> T+5.
   c. _heartbeat.json EXACTLY: {"sport":"mlb","n_games_live":1,"last_write_ts":<iso T+5>,"rows_written_total":50,
      "n_errors_total":0,"n_adapter_errors_total":0,"last_adapter_error":null}. No heartbeat_ts/ts/updated_at key,
      as in the real writer (local_state_capture_commit.py:62-71), so heartbeat time = file mtime (:155-157):
      the case MUST os.utime(heartbeat, (T+5, T+5)). Without it the real wall-clock mtime is > T+12 and the
      result is DEGRADED heartbeat_time_missing_or_invalid -- not a watchdog finding.
   d. (i) clock = iterator over [T, T+12]; monitor(root, max_age_s=300, watch_s=0, clock=clock, sleep=<raises>).
      Checks: clock called exactly 2 times (a 3rd call raises -> check fails); status "OK"; reasons []; errors {}
      (so no invalid_tail_timestamps). Named check frozen_clock_ok.
      Evidence (not a check): assess(read_sources(root, T)["state/mlb"], None, T, 300) (the pre-S601 single clock).
      Expected recorded value: status "SILENT", reasons include "last_write_missing_or_invalid_while_live",
      "read_error:invalid_tail_timestamps" and "heartbeat_time_missing_or_invalid"; errors
      {"invalid_tail_timestamps": 1}. Record whatever it returns verbatim.
   e. (ii) fresh root; T0 = time.time(); if T0 is within 60 s of a UTC midnight, sleep past it first. Heartbeat as (c)
      with last_write_ts = iso(T0), real mtime. A thread appends rows (fixture rows re-stamped time.time()) every 5 ms
      to the shard of day(T0), each row ONE unbuffered write of the complete line incl. "\n" (open "ab",
      buffering=0), until a stop event; the main thread runs monitor(root) with the real clock 20 times.
      Check live_thread_ok = all 20 statuses "OK" and the thread appended >= 20 rows. If any run is DEGRADED with
      read_error:json_decode_errors (a torn tail line: tail_rows :51-72 has no partial-last-line skip) it is a DEFECT
      with that failed check -- report it, never retry until green.
   f. (iii) fresh root, rows 0..49 stamped T-1200-245+5*i, last_write_ts iso(T-1200), os.utime heartbeat to T-1200,
      clock [T, T]. Check stale_control_fires = status "SILENT" and reasons contain
      "last_write_older_than_max_age_while_live", "today_shard_missing_or_stale_while_live" and
      "heartbeat_older_than_max_age".

A3 CASE 38 -- launch seam, no RAM floor, scanner timing.
   a. There is no create seam on Desk (paper_desk_tick.py:28-31: run, processes, ram, alive, identity). Count launches
      through run=: for argv[2] == "scripts.platformkit.ops.paper_desk_start" the seam parses --config/--name/--state/
      --now and calls paper_desk_start.start_capture(name, read(config), Path(state), now,
      process_rows=<the SAME list the tick's processes() returned>, create=<counter returning
      dict(pid=40001+k, create_time=1790700000.0+k)>) and returns SimpleNamespace(returncode=0,
      stdout=json.dumps(result, sort_keys=True)); every other module returns (0, ""). NEVER let start_capture take
      process_rows=None (paper_desk_start.py:150 would call process_snapshot() and see the REAL live supervisors).
   b. Root from system_fault_cases_tick.make_root, then DELETE the three STOP_<name> files (make_root writes them,
      :57-59; with them present inspect_capture returns stop_present and there are zero launches). stop_paths stay
      in the config (capture_config requires a non-empty list, paper_desk_start.py:80-81).
   c. Seed BOTH state files, confirmed 10 h before L = "2026-09-30T13:30:00Z":
      data/cache/paper_desk/capture_request_<name>.json = {"ts":"2026-09-30T03:30:00Z","status":"confirmed",
      "identities":[{"pid":1111,"create_time":"1.0"}]} (the tick reads old["ts"], paper_desk_tick.py:167-173) and
      launch_<name>.json = {"attempted_at":"2026-09-30T03:30:00Z","status":"confirmed","identities":[same]}
      (start_capture reads attempted_at, paper_desk_start.py:166-173). Supervisor journals
      data/cache/capture_supervisor/supervisor_<name>.jsonl = exactly ONE row {"time":"2026-09-30T03:30:00Z",
      "event":"child_start"} (a SECOND child_start would itself qualify as an outage, paper_desk_issue_capture.py:147).
      Stale supervisor_<name>.lock (dead pid 999999) and supervisor heartbeats 10 h old are written but are inert
      (no tick or scanner reader) -- say so in the memo.
   d. Tick 1 at L, processes=[] , ram=64 GiB. Checks: logon_three_launches = the capture:books, capture:state2,
      capture:polymarket rows all decision "capture_started" reason "wmi_created"; create counter == 3; seam calls
      to paper_desk_start == 3 (no per-tick launch cap exists); no row decision in {"capture_backoff",
      "capture_owner_intervention_required","capture_deferred"}; each capture_request_<name>.json status "pending"
      with launcher_identity pid 40001..40003.
   e. Tick 2 at L+30 min ("2026-09-30T14:00:00Z"), processes = three dicts {pid:40001+k, name:"python.exe",
      create_time:1790700000.0+k, cmdline:["python.exe","-m","scripts.platformkit.ops.capture_supervisor","--name",
      <name>,"--","python.exe","-m",CHILDREN[name]]}. Check second_tick_present = three rows "capture_present",
      zero paper_desk_start seam calls, each capture_request_<name>.json status "confirmed". Evidence only:
      launch_<name>.json stays "pending" (tick 2 never runs start_capture).
   f. LOW-RAM VARIANT -- the premise is false: the capture steps are NOT memory-gated (paper_desk_tick.py:211 calls
      step without memory=True; the 1200 MiB floor at :67-69 applies only to schedule/nights/night/census_scan), and
      the injected run seam bypasses run_producer's reserve (paper_desk_process.py:140-198, which in any case only
      kills a RUNNING child). Pin the landed behaviour: fresh root, tick at L with ram=lambda: 500*1024**2 ->
      check capture_not_ram_gated = three "capture_started" AND the "schedule", "nights" and "census_scan" rows
      decision "deferred_low_ram" reason "available_ram_below_minimum". Memo: owner note that three supervisor
      launches are not held back at low RAM (no spec requires it; not a DEFECT).
   g. SCANNER (paper_desk_issue_capture.py:101-159, :237-270; paper_desk_issue_supervisor.py:82-107). Use
      paper_desk_issues.scan(root, stamp(now), dict(procs=..., mtimes={}, alive_pids=[])) with stdout redirected, as
      system_fault_cases_tick.py:225-232. At L with procs=[]: check logon_absent_named = supervisor_absent FAIL for
      books, state2 and polymarket, severity "P2" (L hour 13 is outside 16-06 and no served game is live, :240-242);
      check logon_no_outage_yet = ZERO capture_outage and ZERO capture_crash_loop observations (an outage is emitted
      only when a LATER child_start follows, :141-149 -- a journal ending on child_start is invisible to outages()).
      Then append {"time":"2026-09-30T13:31:00Z","event":"child_start"} to each journal (the relaunched supervisor)
      and scan at L+30 min with the tick-2 procs as (pid, cmdline) pairs: check outage_after_relaunch =
      capture_outage FAIL for subjects books@2026-09-30T13:31:00Z, state2@..., polymarket@... (exactly 3), severity
      "P1" (start bound is None with no shards, or clamped to 03:30Z -> >= 3600 s, :166-170), supervisor_absent PASS
      x3, zero capture_crash_loop. Record the full (kind, subject, verdict, severity) list.

A4 CASE 39 -- git isolation (the S581 guard checks only git's argv/cwd, and the live .git is NOT a protected dir).
   a. Every git call: argv starts ["git","-C",str(repo)], cwd=repo, and env = os.environ minus EVERY key starting
      "GIT_" (GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE are set when tests run under a git hook and would redirect the
      writes to the live repo), plus GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
      GIT_CEILING_DIRECTORIES=str(repo.parent), GIT_TERMINAL_PROMPT="0", GIT_AUTHOR/COMMITTER_NAME="fault",
      _EMAIL="fault@example.invalid", _DATE fixed "2026-09-30T00:00:00Z" (+1 s per commit). Reason: this box has
      global core.autocrlf=true (verified) which rewrites LF to CRLF on checkout and breaks byte-for-byte checks, and
      GIT_EDITOR=true is in the environment. Use `git init -b master` (git 2.55 here).
   b. Right after init: `git rev-parse --show-toplevel` must equal repo (os.path.normcase compare) else the case
      returns ERROR-by-exception before any other git command. The repo path must not be under LIVE_ROOT.
   c. Shared file name "shared_list.txt" (NOT .gitattributes: git would interpret its lines as attributes, and a
      merge=union entry would remove the conflict). Module "module.py". All content LF, written with write_bytes.
   d. (i) conflict_detected = `git cherry-pick <row>` exit code 1 and `git status --porcelain` shows "UU
      shared_list.txt". abort_restores = after `git cherry-pick --abort`: HEAD sha == master sha before, `git diff
      --cached --quiet` exit 0, `git status --porcelain` empty, .git/CHERRY_PICK_HEAD absent, module.py and
      shared_list.txt bytes == the bytes master's commit wrote.
      (ii) evidence (fresh branch): without abort, shared_list.txt contains "<<<<<<< ", "=======", ">>>>>>> "; module.py
      bytes == the ROW's module.py (clean apply, NO markers -- the body's "module/shared file hold conflict markers"
      is wrong); CHERRY_PICK_HEAD exists. Then abort (clean up).
      (iii) landed_sha_required = after a clean cherry-pick onto a master commit that touches only another file:
      `git merge-base --is-ancestor <row sha> HEAD` exit code == 1 exactly (128 = error = check fails) and
      `git merge-base --is-ancestor <HEAD sha> HEAD` exit code == 0.
   e. cite only paths on master. docs/operations/relaunch_books_s561_2026-09-30.ps1 is NOT on master (docs/operations
      has no s561 file); name it in text as "the S561 worktree preflight" and cite docs/evidence/tracking/specs/
      S561_spec.md instead. .planning/NOW.md is local-only: disclose, do not cite.

A5 MEMORY/TIME. Peak RSS per case via psutil < 200 MB (record). Case 37(ii) thread and all git calls bounded
   (git timeout=60 s each; thread join 10 s); no process left alive after the case (check psutil children == []).
```
