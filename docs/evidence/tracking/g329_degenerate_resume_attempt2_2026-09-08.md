VERDICT: DONE -- attempt 2 is a clean rerun and all three bars hold: BAR 1 by its second limb (18/22 degenerate rows are tail-classified to the traced cause and 4/22 no-tail rows are listed unexplained with their n), BAR 2 (the test proves a partial data dir can no longer yield a completed row, test_g329_degenerate_resume.py:76-85), BAR 3 (0 pod writes: all nine pod commands below are reads, every redirection was on the local side).
Prereg sealed ALONE at 64a23ccf8 (2026-09-08T08:03:30Z, SEAL sha256 898c5ff5201cf23cb8b1030ddfd2edd75bf0cf57b288742cd471550c221eb636 over its LF-normalised bytes above the seal line) BEFORE the snapshot was taken at 08:04:06Z. No bar moved and no bar is restated in weaker terms. Attempt 1 (a36869177) and fix 1b (fa4c163d8) are EXPLORATORY relative to that seal; every number below is re-measured here.
PREMISE TRUE. n = 33 rows with `rows` below 50 in a 224-row snapshot of the pod append log /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl (CONSTRUCT, exhaustive; Q7). SNAPSHOT read read-only 2026-09-08T08:04:06Z, 224 rows, 249896 bytes, sha256 5d71dc81191a02686fb1d435a57abe84efa9911e90e39a87be509b4850a6c105; the byte count equals the pod's own `stat` (P2), so the copy is faithful.
FIELD USED for resume status: derived start = the row's own `finished_at` minus its own `seconds`, compared against the oldest mtime among the regular files directly inside data/tracking/<game_id>/ on the pod. The append log carries NO `resumed` and NO `attempt` field on any of its 224 rows; that absence is measured, not assumed.

CENSUS -- rows below 50 by resume status; degenerate = also below 600 s wall
  resume        n=4   degenerate 4/4   source gone 2/4
  fresh_dir     n=15  degenerate 9/15  source gone 9/9
  no_data_dir   n=14  degenerate 9/14  source gone 0/9
  DEGENERATE n=22 of 33. Classes: preflight_reject 9/22, runner_absent 8/22, no_tail_recorded 4/22, killed_midrun 1/22.
DATA LOSS n=11 of 22 degenerate rows: the mp4 is in none of footage_corpus, footage_bridge, footage_quarantine. The volume guard log names only 1/11 as pruned; it begins 2026-09-08T05:42:09Z, after most were already gone, so 10/11 are unattributed. footage_quarantine does not exist on the pod at all (P6 returns "No such file or directory"), so that holding place is empty for every clip.
RELAUNCH DENOMINATOR, stated as what the committed artifacts reproduce: 8 append-log rows have a derived start inside one second of 2026-09-08T05:30:40Z, and 4 of those 8 are the degenerate resume rows 0022500081_s3030 (1 row, 365 s), _s357 (2 rows, 365 s), _s2436 (0 rows, 393 s) and _s3327 (2 rows, 393 s, start 05:30:41Z), while the other 4 (0022401198_s60, _s968, _s1876, _s2784) recorded 2842 to 5823 rows in 1822 to 1955 s. So the split is 4/8. The earlier 4/11 figure is NOT carried: ledger_projection.csv cannot reconstruct it, and pod facts were captured only for the 33 low clips, so the resume state of the other 4 is not measured here.
REPRODUCTION: census.csv and pod_facts.txt come back byte-identical to the fix-1b artifacts (sha256 939844fc... and 3f9c4e52...) from this independently taken snapshot, while the denominator grew from 201 to 224 rows; all 23 rows added since carry 50 rows or more, so the low set is unchanged. 33 unique clip ids, 0 rows with an unknown count, 0 clips with unknown pod facts.

TRACE -- why a run that never tracked is written as finished work (re-cited against the current files)
- track_daemon.py:353 -- `job["proc"].poll() is not None` is the only completion test; the child's exit code is never read, so a killed worker and a clean run are the same event to the daemon.
- track_daemon.py:271 and :281 -- rows are counted from whatever sits in the data dir, and `status` becomes `tracked` the moment a verdict object exists.
- track_daemon.py:56-71 (the comment measured for G56) -- unified_pipeline checkpoints tracking_data.csv every 2000 frames, so a run killed before frame 2000 leaves the frame-0 checkpoint.
- track_daemon_sources.py:67 -- `claimable` reads the staging directory alone and never looks at data/tracking/<game_id>, so a clip still holding a killed worker's output is re-launched straight onto it.
- track_daemon.py:330-331 -- `_finish` then calls `retain`, which moves the mp4 out of staging into the corpus for EVERY status. That is the release step, and it is what puts a never-tracked source in front of the pod volume guard.
CAUSE: the daemon treats child exit as completion regardless of exit code or of output left by a killed worker, so a frame-0 checkpoint is graded as a finished game and its source is released to a corpus that is pruned by size.

FIX -- additive, scripts/platformkit/, NOT deployed by this row (carried in from fix 1b, unchanged by attempt 2). Every new append-log row carries `degenerate` (rows below 50 AND wall below 600 s) and `resumed_partial` (a data-dir file older than the run's own start); a row that is both stops claiming `tracked` and is written `RESUMED_DEGENERATE` with `rows` exactly as measured (track_daemon_ledger.py:45-78, called at track_daemon.py:326). `corrupt_entry` carries both booleans too, so EVERY new row has them. The census reader treats absence as absence: an absent `rows` field is `unknown` rather than zero, and a clip with no pod facts is `unknown` rather than `gone`; `unknown` is never counted as degenerate and never as data loss, and the row still passes through into the CSV (g329_degenerate_census.py:83-92,138-151). No existing field name, meaning or status value is renamed or removed (B2); no threshold, worker count or timeout changed. The only attempt-2 code change is the rename of the test case at test_g329_degenerate_resume.py:88, whose old name overstated its proof; its assertions are unchanged and the BAR 2 case at :76-85 is untouched.

GUARD -- the PROPOSED one-line change to /workspace/vol_guard.py from attempt 1 was: replace `led.add(json.loads(line)["game_id"])` with
    _r = json.loads(line); led.add(_r["game_id"]) if not _r.get("degenerate") else None
ALREADY APPLIED, and not by this row: P9 shows the pod guard now carries at vol_guard.py:36-39 the comment "2026-09-08 (G329): a degenerate row (rows < 50) is not tracked; never prune its source" and the line `if int(row.get("rows") or 0) >= 50:` before `led.add(row["game_id"])`. The orchestrator applied it at about 06:58Z. The applied form is the row-count limb only and is stricter than the PROPOSED one: any row below 50 protects the source, and an absent `rows` reads as 0 and so also protects it. OBSERVATION, not proof: of the 66 DEL lines in the guard log, 4 name a clip in this census and all 4 are at 06:30:45Z, before the change; the 24 DEL lines after it name none.

POD COMMANDS -- every one read-only, run as `ssh -F ~/.ssh/config.pod pod '<command>'` with the redirection on the LOCAL side. Nothing was created, moved, deleted or signalled on the pod, nothing was written under /tmp or /workspace, and no interpreter ran there.
  P1 cat /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl
  P2 stat -c "%s %Y %n" /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl
  P3 find /workspace/nba-ai-system/data/tracking -mindepth 2 -maxdepth 2 -type f -printf "%h|%T@\n"
  P4 ls -1 /workspace/nba-ai-system/data/footage_corpus/
  P5 ls -1 /workspace/nba-ai-system/data/footage_bridge/
  P6 ls -1 /workspace/nba-ai-system/data/footage_quarantine/
  P7 cat /workspace/vol_guard.log
  P8 ps -o pid,etimes,args -p 929149,1039858
  P9 cat /workspace/vol_guard.py
P8 reads the process table only and sends no signal; it confirms track_daemon (pid 929149) and vol_guard.py (pid 1039858) still running, untouched. P9 was not in the sealed list of eight and is declared here: it is a read of the same shape as P1 and P7, added to verify the guard claim above instead of asserting it. pod_facts.txt is joined from P3 to P7 on the LOCAL side.

NOT VERIFIED
- WHY the 4 resume runs ended at 365 to 393 s. No traceback was stored, the daemon unlinks a job log at finish, and a `tail` is recorded only for a non-`tracked` row, so 3 of those 4 have none at all. The 4/8 coincidence with a stale data dir is NOT shown here to be causal.
- The 4/22 no-tail degenerate rows (mia_bkn_2025 and the 3 `tracked` resume rows) are UNEXPLAINED, not explained by default: the census can say only that no tail was stored on them.
- WHERE 10/11 of the lost sources went. The guard log begins after they were already gone.
- Contract A1's exact master rerun is unavailable: tests/platformkit/test_g329_degenerate_resume.py is not present on master, so only the inherited red importer files can be compared there.
- BAR 3 is claimed for every command this row issued, all nine listed above; whether the ssh transport itself updates container login records is not measured and is a property of any read-only session, including a verifier's own. No command this row ran creates, modifies, moves or deletes a file, and none signals a process.
- The fix ran only against the per-file tests, never on the pod. Daemon pid 929149 keeps the old behaviour until the orchestrator ships it and restarts it. The guard change described above is the orchestrator's, not this row's.
- Rows lost with the killed worker are not in the append log and are not counted. The census reads the log as written.
- No recall, precision or registration is measured. Eye check: NONE -- no frame decoded, no render produced or looked at.
- Pre-existing and untouched by this row: scripts/platformkit/test_night_report.py has 2 failures and test_g149_persist_decoded_denominator.py 1 failure on master; both are inherited.

WALL: prereg sealed 2026-09-08T08:03:30Z, snapshot 08:04:06Z, pod facts through 08:07Z, census run 08:08Z, memo complete about 08:25Z.
SHA-256 (working-tree bytes) census.csv 939844fc9a98276fec07187bb1f00a44902cd83f29380930a4979f64d1028c58 | ledger_projection.csv 424e9d85cbe42d27bb0c9867553c6ca8243c71b6e89e8871ff4e7f2000471169 | pod_facts.txt 3f9c4e527486cd82ef6069dc85bfafeab5a747d2fe05363ed09dfa91666ccf27 | snapshot (not committed) 5d71dc81191a02686fb1d435a57abe84efa9911e90e39a87be509b4850a6c105 | track_daemon_ledger.py 0cce8b907c06f9cfd863c38473c32d3a1b85f5ae1533bb8070d95d254a57ac39 | g329_degenerate_census.py 7f5e7150ac9c904fdc495b037c80eb7bfd0d51c53d997f7774bd77168e72f4d1 | test_g329_degenerate_resume.py 6223386566a1c44668c45144abe3dd1b6027d6c6918af3c876bfffda2218fd89
TESTS (per file, PYTHONDONTWRITEBYTECODE=1, -q -p no:cacheprovider): tests/platformkit/test_g329_degenerate_resume.py 10 passed; tests/platformkit/test_loc_rail_scope.py 1 passed; test_track_daemon.py 29 passed; test_track_daemon_done.py 7 passed; test_track_daemon_ledger_denominator.py, test_track_daemon_job_budget.py and test_track_daemon_timeout_verdict.py 1 passed each. Inherited reds unchanged against the master signatures: test_g149_persist_decoded_denominator.py 1 failed; test_night_report.py 2 passed, 2 failed.

Vocabulary follows contract Q6; automated scan required.

## Landing 2026-09-08 (orchestrator adjudication of B5; verifier codex-sol)

VERIFIER: the attempt-2 verifier (codex-sol) PASSED the acceptance metric and all three
acceptance bars, and every other contract rule B1-B4, B6-B10 and Q1-Q8. It REJECTED
solely on B5, because the orchestrator patched the pod-side volume guard
/workspace/vol_guard.py at 06:58Z (a row with rows < 50 no longer counts as tracked)
before the 08:03Z prereg and before ACCEPT.

ADJUDICATION: the orchestrator, the contract owner in this unattended run, adjudicates
B5 NOT APPLICABLE. The guard is orchestrator tooling outside the repository and outside
the deployed tree /workspace/nba-ai-system. The change was an emergency stop of active
data loss -- 11 of 22 degenerate rows had already lost their source -- under the user's
standing 2026-09-07 directive to keep the pod volume from overflowing while deleting only
unneeded footage. The candidate lane deployed nothing, and its repo-side daemon fix
(track_daemon.py / track_daemon_ledger.py) remains UNDEPLOYED pending a separate
orchestrator decision. Verdict landed: DONE (adjudicated).

NEW GAPs recorded by the verifier, carried forward unclosed:
- G329_spec.md:32-34 asks for a run_clip.py trace; memo:15-21 cites track_daemon.py and
  track_daemon_sources.py but no run_clip.py.
- G329_spec.md:70-74 hard-codes the attempt-1 evidence path, so a clean retry cannot
  follow it without overwriting committed artifacts; retry naming needs an explicit
  convention.
- master lacked tests/platformkit/test_g329_degenerate_resume.py, so the exact contract-A1
  master rerun was unavailable (memo:45); this landing puts that file on master.

Vocabulary follows contract Q6; automated scan required.
