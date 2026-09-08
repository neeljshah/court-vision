VERDICT: PARTIAL -- bar 1 holds by its second limb (18/22 degenerate rows are tail-classified to the traced cause; 4/22 no-tail rows are explicitly unexplained and carry their n) and bar 2 holds (the test proves a partial data dir can no longer yield a completed row); bar 3 "zero pod writes" is UNMET by one scratch write, listed below and not waived.
Prereg sealed ALONE at 08edacaebeacf8f522df88ba66406440e04529c1 before any measurement (sha256 89c6e920566652f6cd06a96ae2b5ae41f2ba9017080784c3e0258ae0b954559f). No bar moved and no bar is restated in weaker terms.
PREMISE TRUE. n = 33 rows with `rows` below 50 in a 201-row snapshot of the pod append log /workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl (CONSTRUCT, exhaustive; Q7). SNAPSHOT: read read-only 2026-09-08T07:24:21Z, 201 rows, sha256 0e67f38fa71867efcac932358235015b6581b0fff9a0f43afb8bf24b554e6df9. Every number below comes from that snapshot: the earlier 184-row read was NOT retained locally, so fix 1b re-measured instead of reconstructing it.
FIELD USED for resume status: derived start = `finished_at` minus `seconds`, both read from the row itself, compared against the oldest file mtime in data/tracking/<game_id>/ on the pod. The append log carries NO `resumed` and NO `attempt` field on any of its 201 rows; that absence is itself measured, not assumed.

CENSUS -- rows below 50 by resume status; degenerate = also below 600 s wall
  resume        n=4   degenerate 4/4   source gone 2/4
  fresh_dir     n=15  degenerate 9/15  source gone 9/9
  no_data_dir   n=14  degenerate 9/14  source gone 0/9
  DEGENERATE n=22 of 33. Families: runner_absent 8/22, preflight_reject 9/22, no_tail_recorded 4/22, killed_midrun 1/22.
DATA LOSS n=11 of 22 degenerate rows: the mp4 is in none of footage_corpus, footage_bridge, footage_quarantine. The volume guard log names only 1/11 as pruned; it begins 2026-09-08T05:42:09Z, after most were already gone, so 10/11 are unattributed.
The 4 resume rows are 0022500081_s3030 (1 row, 365 s), _s357 (2 rows, 365 s), _s2436 (0 rows, 393 s), _s3327 (2 rows, 393 s); all started 05:30:40Z at the relaunch after the 05:26Z volume event, and 2/4 lost their source. The 4 clips the same relaunch took with no prior data dir (0022401198_s60, _s968, _s1876, _s2784) wrote 2842 to 5823 rows in 1822 to 1955 s, so the split is 4/8, not a slow night.

TRACE -- why a run that never tracked is written as finished work
- track_daemon.py:353 -- `job["proc"].poll() is not None` is the only completion test; the child's exit code is never read, so a killed worker and a clean run are the same event to the daemon.
- track_daemon.py:271 and :281 -- rows are counted from whatever sits in the data dir, and `status` becomes `tracked` the moment a verdict object exists.
- track_daemon.py:56-71 (the comment measured for G56) -- unified_pipeline checkpoints tracking_data.csv every 2000 frames, so a run killed before frame 2000 leaves the frame-0 checkpoint. Confirmed on the pod: all three surviving degenerate CSVs hold frame 0 only, and _s2436's stored tail ends at "Frame 582..." with no traceback.
- track_daemon_sources.py:67-92 -- `claimable` reads the staging directory alone and never looks at data/tracking/<game_id>, so a clip still holding a killed worker's output is re-launched straight onto it.
- track_daemon.py:330-331 -- `_finish` then calls `retain`, which moves the mp4 out of staging into the corpus for EVERY status. That is the release step, and it is what puts a never-tracked source in front of the pod volume guard.
CAUSE: the daemon treats child exit as completion regardless of exit code or of output left by a killed worker, so a frame-0 checkpoint is graded as a finished game and its source is released to a corpus that is pruned by size.

FIX -- additive, scripts/platformkit/, NOT deployed by this row. Every new append-log row carries `degenerate` (rows below 50 AND wall below 600 s) and `resumed_partial` (a data-dir file older than the run's own start); a row that is both stops claiming `tracked` and is written `RESUMED_DEGENERATE` with `rows` exactly as measured. The corruption row built by corrupt_entry carries both booleans too, so EVERY new row has them. The logic is in track_daemon_ledger.py; track_daemon.py takes three same-length edits and stays at 440 lines. No existing field name, meaning or status value is renamed or removed (B2); no threshold, worker count or timeout changed. Readers that select `status == "tracked"` (night_report.py:132, tracking/g322_oversized_boxes.py:55, tracking/g325_offframe_boxes.py:62) now skip exactly the rows that were never completions, and no historical row changes.

PROPOSED one-line change to the pod's /workspace/vol_guard.py (NOT applied, NOT deployed). Replace line 35, `led.add(json.loads(line)["game_id"])`, with:
    _r = json.loads(line); led.add(_r["game_id"]) if not _r.get("degenerate") else None
A clip then enters the prunable set only through a row that is not degenerate. The 201 existing rows carry no such field, so `.get` is falsy and their behaviour stays byte-identical to today.

Corrections (fix 1b, 2026-09-08)
- corrupt_entry in track_daemon_ledger.py now emits `degenerate` true (0 rows in 0 s is degenerate by D2) and `resumed_partial` false (no tracker ran on a data dir), so the schema is uniformly additive across every new row; the per-file test asserts both on that builder and asserts its `status` and `rows` are untouched.
- Line 1 no longer says every degenerate row is explained. 18/22 are tail-classified and 4/22 have no stored tail at all and stay unexplained with their n. The verdict stays PARTIAL, bar 3 stays UNMET, and no bar text moved.
- Q7: `ledger_projection.csv` commits the all-row projection (game_id, rows, seconds, finished_at; integer cells zero-padded to six digits) of the same snapshot the census read, so the denominator is recountable without the snapshot: 33 LOW ROWS of 201 and 22 degenerate come straight back out of it. Both artifacts are written by one run of the census module (`--out` and `--projection`).
- REPRODUCTION of the first census inside the new snapshot: all 31 census lines of the 184-row read come back byte-identical (same rows, seconds, resume status, source state, class) and the pod facts for those 31 clips are byte-identical too; the 201-row snapshot adds exactly 2 clips the daemon finished since (0022500081_s8673, degenerate; 0022500621_s7200, 630 s so not degenerate). That is why 31 becomes 33, 21 becomes 22, and 4/14/13 becomes 4/15/14.
- The census reader no longer reads absence as a measurement: an absent `rows` field is `unknown` (it was mapped to zero, which invents a LOW ROW) and a clip with no pod facts is `unknown` (it was mapped to `gone`, which invents data loss). `unknown` is never counted as degenerate and never as data loss, and the row still passes through into the CSV. One test case each. This snapshot has no such row: all 201 carry `rows`, and all 33 low clips were probed.

NOT VERIFIED
- WHY the 4 resume runs ended at 365 to 393 s. No traceback was stored, dmesg is unreadable in this container, the daemon unlinks a job log at finish, and a `tail` is recorded only for a non-`tracked` row, so 3 of those 4 have none at all. The 4/8 coincidence with a stale data dir is NOT shown here to be causal.
- The 4/22 no-tail degenerate rows (mia_bkn_2025 and the 3 `tracked` resume rows) are UNEXPLAINED, not explained by default: the census can say only that no tail was stored on them.
- WHERE 10/11 of the lost sources went. The guard log begins after they were already gone.
- The fix ran only against the per-file test, never on the pod. Daemon pid 929149 keeps the old behaviour until the orchestrator ships it and restarts.
- Rows lost with the killed worker are not in the append log and are not counted.
- No recall, precision or registration is measured. Eye check: NONE -- no frame decoded, no render produced or looked at.
- BAR 3 UNMET: one pod write was made in the first pass, `ls .../footage_corpus/ > /tmp/g329_corpus.txt`, a scratch listing in the container tmp, outside /workspace. Nothing under /workspace was written, moved or deleted and no process was signalled. It was left in place rather than compounded by a delete. Fix 1b added NO second write: its re-measurement is one `ssh cat` of the append log plus one `ssh bash -s` probe whose script is fed on stdin and only runs find, grep and test.
- Pre-existing and untouched by this row: scripts/platformkit/test_night_report.py has 2 failures and test_g149_persist_decoded_denominator.py 1 failure on master (the g149 one is a stub lambda that rejects a `publish` keyword); both reproduce unchanged with this row's change in place.

WALL: prereg sealed 2026-09-08T06:43:31Z, first memo 06:58Z, fix 1b snapshot re-read 07:24:21Z and pod facts 07:25:28Z, fix 1b complete about 07:40Z.
SHA-256 (working-tree bytes) census.csv 939844fc9a98276fec07187bb1f00a44902cd83f29380930a4979f64d1028c58 | ledger_projection.csv 4208399722964d0a19d8544875e58fa2b515730f0eb135255f2045354f6f913c | pod_facts.txt 3f9c4e527486cd82ef6069dc85bfafeab5a747d2fe05363ed09dfa91666ccf27 | track_daemon_ledger.py 0cce8b907c06f9cfd863c38473c32d3a1b85f5ae1533bb8070d95d254a57ac39 | g329_degenerate_census.py 7f5e7150ac9c904fdc495b037c80eb7bfd0d51c53d997f7774bd77168e72f4d1 | test_g329_degenerate_resume.py 248d8d46ab6bf952c75d70bb341b057a4fc18be31f68bad3324b67613651f534
TESTS: tests/platformkit/test_g329_degenerate_resume.py 10 passed; test_track_daemon.py 29 passed; test_track_daemon_done.py 7 passed; test_track_daemon_ledger_denominator.py, test_track_daemon_job_budget.py, test_track_daemon_timeout_verdict.py 1 passed each; tests/platformkit/test_loc_rail_scope.py 1 passed.

Vocabulary follows contract Q6; automated scan required.
