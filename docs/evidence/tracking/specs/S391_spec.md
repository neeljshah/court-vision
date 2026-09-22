GAP S391 | sport all captured | worktree harness-h50 (master-based) | log cx_s391_redeploy_checklist
# OWNER ten-minute capture redeploy checklist + preflight (design: ASTRA_ROUND14 row 2; the binding constraint this week)

SINGLE PROBLEM: five landed capture rows (S341 fixes, S358, S374, S375, S376) are not live: the production book and state
captures still run older code from other directories, and the permission layer refuses to let an agent write the STOP files. The
owner needs one page they can execute in ten minutes, plus a preflight that proves the state BEFORE and AFTER.

BINDING BEFORE-CONDITION: read docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md (row S376) and quote every start / stop line and every
OWNER-ONLY item; read scripts/platformkit/ops/capture_supervisor.py --help; `ls scripts/platformkit/ops/capture_deploy_preflight.py`
fails. FACTS (2026-09-22): the book capture runs from C:/Users/neelj/nba-harness-h10 (an unlanded fix-1d candidate) with
--output-root C:/Users/neelj/nba-ai-system/data/cache/ingame_books_local; the state capture runs from the main tree's old S352
copies; both are pythonw + C:/Users/neelj/bin/hidden_launch.py children; the STOP files are data/cache/ingame_books_local/STOP and
STOP_STATE; Norton intercepts TLS (the runner bakes in the CA bundle); ESPN refuses a custom User-Agent; no console windows.

CHANGE (owned files: docs/operations/CAPTURE_RESILIENCE_RUNBOOK.md (edit; keep history), NEW scripts/platformkit/ops/
capture_deploy_preflight.py, NEW tests/platformkit/ops/test_capture_deploy_preflight.py, memo):
1. capture_deploy_preflight.py (<= 300 LOC, stdlib, READ-ONLY, Windows-aware): `--phase before|after --root <archive root> --out
   <json>`. BEFORE: list every python / pythonw process whose command line names local_capture_runner or local_state_capture
   (pid, parent pid, cwd argument, --output-root, the git commit of that directory), the newest write time per sport archive, the
   heartbeat counters, the presence of STOP / STOP_STATE and any supervisor lock; refuse to run if two writers target one archive.
   AFTER: the same, plus: exactly one writer per archive, both under a supervisor, the running directory's commit == master's
   HEAD, the profile SHA-256 in the heartbeat, first receipts after restart, no console window (window title scan). Every
   finding is a strict-int count or a string; exit 0 only when every AFTER check holds; never signals, stops or starts anything.
2. Runbook section "TEN-MINUTE REDEPLOY (OWNER)": minute 0-2 run the BEFORE preflight and commit its JSON under docs/evidence/
   capture/redeploy/<date>_before.json; 2-4 create STOP and STOP_STATE, wait for both exits (the exact PowerShell wait loop);
   4-6 delete the sentinels and start both captures from the MAIN tree under capture_supervisor.py with pythonw +
   hidden_launch.py (exact lines, incl. --schedule once S388 lands and the profile file); 6-10 run the AFTER preflight, commit
   its JSON, and check the watchdog (row S363) reports OK for every live sport. State plainly that the agent cannot perform
   minutes 2-6.
3. Tests: fake process tables and archives; two writers on one archive refused; commit mismatch reported; console-window
   detection injected; AFTER exit code 3 on any failed check; nothing is ever signalled (assert no os.kill / Stop-Process path
   exists in the module).
4. Memo docs/evidence/harness/S391_redeploy_checklist_2026-09-22.md.

CONTROLS: read-only tooling, construct tests, no process is started or stopped by the builder or the tool. ACCEPTANCE: per-file test
passes; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list.
