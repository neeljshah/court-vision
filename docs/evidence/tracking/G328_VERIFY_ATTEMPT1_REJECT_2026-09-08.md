PROVENANCE: recovered 2026-09-08 from C:/Users/neelj/AppData/Local/Temp/cx_verify_g328.log (lines 4391-4428, the complete 38-line diff hunk `@@ -0,0 +1,38 @@`; `+` prefixes stripped, CR stripped). The original file was overwritten in place by the second verify run; this is the full memo, not a tail. The run ended EXIT:0 gap=verify_G328 at 2026-09-08T05:43:51-05:00 with no commit (sandbox denied .git index.lock).

VERDICT: REJECT
Candidate: 969bceb2a; verification date 2026-09-08; contract A/B/Q and G328 acceptance rule applied.
ACCEPTANCE FAIL: the required construct is not passing; tests/platformkit/test_g328_daemon_worker_accounting.py:125 differs on `resumed_partial`, contrary to specs/G328_spec.md:63-64.
PREMISE PASS: independent census is 327/327 unique instance-seq rows; 2026-09-08b has 7/21 above 8 (six instances unverified), matching tick_table.csv:2-328 and memo:5-15.
HEADLINE PASS: recomputed implied wall median/p90/max = 0/9/19 s (n=190), job wall median = 1874 s (n=209), 22.60/21 = 1.076190, and 3600*8/1874 = 15.3682; memo:27-44.
TRACE PASS: thread start/end, slot release, and ledger write are cited; track_daemon.py:245-275,333-360 and memo:17-25.
TIMING PASS: 209 unique rows, 190 timed rows, method and n disclosed; timing.csv:2-210 and memo:27-35.
CAP PASS: optional boolean flag defaults false and calls the original expression; track_daemon.py:333,360,417-431; track_daemon_slots.py:18-31.
ESTIMATE PASS: both flag modes are labelled estimates and deployment is excluded; memo:42-51.
EVIDENCE PASS: all seven named paths exist, all hashes reproduce, memo is 60 lines, and NOT VERIFIED is present at memo:46-52.
B1 PASS: exhaustive named sets precede metrics; memo:5-15,27-35.
B2 PASS: no field/status removal or rename; optional parameter preserves callers and all 11 importer tests were run; track_daemon.py:333,360,417-431.
B3 PASS: absent evidence is not gated by the slot counter; track_daemon_slots.py:18-31.
B4 PASS: adjudication timeout still removes and records the job; track_daemon.py:335-359.
B5 PASS: candidate records no deployment or pod write; memo:3,51.
B6 PASS: no module moved; the added module has a live import; track_daemon.py:23.
B7 PASS: no head slice or eye sample; the tick census is exhaustive; memo:5-15.
B8 PASS: no fitted residual is used; timing is ledger/proc accounting; memo:27-35.
B9 PASS: denominators are unique ticks, rows, completions, seconds, and cores; memo:5-15,27-44.
B10 PASS: no threshold/default moved; the new store_true flag is off by default; track_daemon.py:417-431.
Q1 PASS: prereg commit b504d0d75 predates candidate; body seal independently matches cd96127d5ba8da858ff9c2ab0214e51cc85e40270a589434210e39ab48ee90e5; g328_prereg_2026-09-08.md:113.
Q2 PASS (N/A): this diagnostic row has no charged trial or K; specs/G328_spec.md:57-66.
Q3 PASS: the spec permits either cap form and defaults are unchanged; specs/G328_spec.md:40-43.
Q4 PASS (N/A): no OOS comparison or meta-learner is scored; specs/G328_spec.md:57-60.
Q5 PASS (N/A): no AHEAD result is stated; memo:1-60.
Q6 PASS: automated candidate-added-line scan returned zero prohibited-language or retracted-number hits; memo:1-60.
Q7 PASS: all 327 tick rows and 209 ledger rows are enumerated; both flag states are constructed at test_g328_daemon_worker_accounting.py:109-125.
Q8 PASS: premise was independently remeasured before adjudication from tick_table.csv:2-328.
TEST: `python -m pytest tests/platformkit/test_g328_daemon_worker_accounting.py -q` -> 1 passed, 1 failed; `python -m pytest scripts/platformkit/test_track_daemon.py -q` -> 29 passed.
TEST: `python -m pytest scripts/platformkit/test_track_daemon_done.py -q` -> 7 passed; `python -m pytest scripts/platformkit/test_track_daemon_ledger_denominator.py -q` -> 1 passed.
TEST: `python -m pytest scripts/platformkit/test_track_daemon_job_budget.py -q` -> 1 passed; `python -m pytest scripts/platformkit/test_track_daemon_timeout_verdict.py -q` -> 1 passed.
TEST: `python -m pytest tests/platformkit/test_g329_degenerate_resume.py -q` -> 10 passed; `python -m pytest scripts/platformkit/test_bridge_supervisor.py -q` -> 6 passed.
TEST: `python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q` -> 1 failed; `python -m pytest scripts/platformkit/test_g153_local_decoded_frames_producer.py -q` -> 1 passed.
TEST: `python -m pytest tests/platformkit/test_g151_quota_fails_loud.py -q` -> 3 passed; `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed. Total: 61 passed, 2 failed.
CORRECTION (minimal): tests/platformkit/test_g328_daemon_worker_accounting.py:89, `time.time()` -> `(csv_dir / "tracking_data.csv").stat().st_mtime - 1`; both fixtures then deterministically model fresh output; rerun that file.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G328 | premise 7/21 above 8 on the verified instance; 327 unique ticks; required construct 1 passed, 1 failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: LOC FAIL -- scripts/platformkit/track_daemon.py is 438 lines, above 300, but candidate reduced the allowlisted 440-line file and the rail passes; track_daemon_slots.py is 31 and the new test is 139; specs/G328_spec.md:80-82.
NEW GAP: pre-existing importer failure -- test_g149_persist_decoded_denominator.py:32 lacks the `publish` keyword accepted by track_daemon.py:275; both lines predate 969bceb2a.
