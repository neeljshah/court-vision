VERDICT: REJECT
CANDIDATE: fa4c163d8a88bfd02ce73bb7e3fda049e6aa7fbb; verified in track-a6.
PREMISE PASS: independent projection recount is nonzero: 33/201 rows are below 50; the four resume rows are 1/2/0/2 rows in 365/365/393/393 s (ledger_projection.csv:1-202; census.csv:2-34).
HEADLINES PASS: claimed 33/201 low, 22/33 degenerate, resume 4/4, fresh 9/15, no-data 9/14, data loss 11/22, guard-named 1/11; reproduced exactly, with 33 unique census ids and 0 missing/extra low rows (memo:3-12).
ACCEPTANCE BAR 1 PASS: 18/22 carry named tail classes and 4/22 no-tail rows are explicitly unexplained (memo:1,10,30,35-37).
ACCEPTANCE BAR 2 PASS: partial output produces RESUMED_DEGENERATE with measured rows, never tracked (test_g329_degenerate_resume.py:76-85).
ACCEPTANCE BAR 3 FAIL: zero pod writes is binding, but one remote scratch listing was written and is not waived (G329_spec.md:61-63; memo:42).
B1 PASS: the all-row projection yields the same 33-row low set as the census, with no unknown row counts (ledger_projection.csv:1-202; census.csv:1-34).
B2 PASS: both row builders add the booleans without removing old fields; the only new status is spec-required, and status readers were checked (track_daemon_ledger.py:25,74-77; memo:22).
B3 PASS: absent resume evidence passes as false, and absent census evidence stays unknown rather than becoming a failure (track_daemon_ledger.py:53-63; g329_degenerate_census.py:83-92,139-151).
B4 PASS: every finished item still leaves staging through retain, so the new status creates no reclaim loop (track_daemon.py:326-331).
B5 PASS: no deployed-tree copy is claimed; the admitted scratch listing fails the acceptance bar, not deployment (memo:22,39,42).
B6 PASS: the cumulative row adds modules and moves or removes none (g329_degenerate_census.py:1; test_g329_degenerate_resume.py:1).
B7 PASS: exhaustive rows are used; eye check is NONE and no render exists (memo:3,41).
B8 PASS: this is a census and construct, with no fitted residual (memo:3-12,41).
B9 PASS: all 33 census units are unique clip ids; repeated all-ledger ids do not enter the low set twice (census.csv:2-34).
B10 PASS: 50/600 match the sealed definitions and boundary tests (track_daemon_ledger.py:40-48; test_g329_degenerate_resume.py:125-133).
Q1 PASS: prereg commit 08edacaeb is an ancestor and its recorded SHA-256 reproduces (g329_prereg_2026-09-08.md:1-4; memo:2).
Q2 PASS: no charged trial or launch K exists in this construct (g329_prereg_2026-09-08.md:5-9).
Q3 PASS: all three bars and both thresholds remain byte-identical to the spec and prereg (G329_spec.md:61-63; g329_prereg_2026-09-08.md:31-37).
Q4 PASS: no OOS score or meta-learner is claimed (memo:41).
Q5 PASS: no AHEAD verdict or corpus comparison is claimed (memo:1-12).
Q6 PASS: independent restricted-vocabulary scan over prereg, memo, evidence, code, and test returned 0 hits (memo:49).
Q7 PASS: 201 projected rows independently yield exactly the 33 census rows and 22 degenerate rows, with 0 missing and 0 extra (ledger_projection.csv:1-202; census.csv:1-34).
Q8 PASS: the binding nonzero premise was independently remeasured before verdict (memo:3; ledger_projection.csv:1-202).
A2/A4/A5/A7 PASS: metrics and uniqueness were recomputed, readers were searched, and every committed local evidence path exists (memo:22,46).
NOT VERIFIED LIST PASS: memo:35-43 is explicit. LOC PASS for fa4c163d8-touched Python: ledger 78, census 264, test 233 lines.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g329_degenerate_resume.py -q -p no:cacheprovider` = 10 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_track_daemon.py -q -p no:cacheprovider` = 29 passed.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_track_daemon_done.py -q -p no:cacheprovider` = 7 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_track_daemon_ledger_denominator.py -q -p no:cacheprovider` = 1 passed.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q -p no:cacheprovider` = 1 failed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_g153_local_decoded_frames_producer.py -q -p no:cacheprovider` = 1 passed.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_track_daemon_job_budget.py -q -p no:cacheprovider` = 1 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_track_daemon_timeout_verdict.py -q -p no:cacheprovider` = 1 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_bridge_supervisor.py -q -p no:cacheprovider` = 6 passed.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g151_quota_fails_loud.py -q -p no:cacheprovider` = 3 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_night_report.py -q -p no:cacheprovider` = 2 passed, 2 failed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g309_multigame_census.py -q -p no:cacheprovider` = 1 passed.
TEST: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g322_oversized_boxes.py -q -p no:cacheprovider` = 5 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g325_offframe_boxes.py -q -p no:cacheprovider` = 10 passed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` = 1 passed.
TEST MASTER (cwd C:/Users/neelj/nba-ai-system): `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q -p no:cacheprovider` = 1 failed; `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest scripts/platformkit/test_night_report.py -q -p no:cacheprovider` = 2 passed, 2 failed; signatures match, so both are inherited.
CORRECTION: no local diff can repair the historical write admitted at memo:42; retain PARTIAL and rerun only as a new clean row.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G329 | 33/201 rows below 50; 22/33 also below 600 s; resume 4/4; 11/22 sources absent; one remote scratch write admitted | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: test_g329_degenerate_resume.py:87-95 prewrites output and uses an already-exited fake process, so its name overstates proof that the tracker actually ran; acceptance BAR 2 is still proven by :76-85.
NEW GAP: the fixed 4/11 historical before-denominator is not reconstructible from ledger_projection.csv:1-202 because non-low rows lack data-dir mtimes; the committed artifacts reproduce 4/8 for the named relaunch only (memo:12).
NEW GAP: contract A1's exact master rerun is unavailable because the G329 spec test is not present on current master; candidate execution passed 10, while inherited red importer files were independently reproduced on master.
