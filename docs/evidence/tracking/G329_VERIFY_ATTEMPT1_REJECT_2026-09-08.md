[provenance: recovered 2026-09-08 from C:/Users/neelj/AppData/Local/Temp/cx_verify_g329.log lines 5207-5246, the attempt-1 verify block preceding the EXIT:0 gap=verify_G329 marker at 2026-09-08T02:18:38-05:00; the a6 working copy was overwritten by the later fix-1b verify. Body below is verbatim and reproduces blob e4af8750db6d3d110a09f104caa344d71d755ea9.]
VERDICT: REJECT
CANDIDATE: a36869177b71bcac49cfa73bb2f7089a139a5cd1; verified in track-a6.
ACCEPTANCE FAIL: G329_spec.md:39 requires both booleans on every new ledger row, but track_daemon_ledger.py:12-20 emits corruption rows without either field.
ACCEPTANCE FAIL: memo:1 says 21/21 explained while memo:10 records 4/21 no_tail_recorded and memo:29 says the four resumed endings are not causally shown; at minimum 4/21 are unexplained.
ACCEPTANCE PASS: the partial-directory construct writes RESUMED_DEGENERATE, not tracked (test_g329_degenerate_resume.py:76-85); 8/8 spec tests pass.
ACCEPTANCE FAIL: prereg BAR 3 requires zero pod writes (g329_prereg_2026-09-08.md:36); memo:34 admits one remote scratch write and correctly does not waive it.
PREMISE PASS: committed census has 31 unique rows below 50, so the binding nonzero condition at memo:3 holds; live SSH was sandbox-blocked.
HEADLINES: claimed 31/184, 21/31, 11/21, resume 4/4; reproduced from census.csv:2 as 31 unique, 21, 11, 4/4. The 184 denominator and fresh-run 0/4 are not reproducible without the absent source snapshot.
TRACE PASS: exit-code-blind completion is at track_daemon.py:353; stale row read/status at :271/:281; unconditional retain at :330-331.
B1 PASS: all 31 committed census rows remain in the grouped denominator (g329_degenerate_census.py:133-170).
B2 FAIL: schema is not uniformly additive because corrupt_entry omits the new fields (track_daemon_ledger.py:12-20), contradicting memo:22 and G329_spec.md:39.
B3 PASS: absent/unreadable resume evidence returns false and does not downgrade a row (track_daemon_ledger.py:47-58).
B4 PASS: a finished item leaves staging through retain, so the new status does not create a reclaim loop (track_daemon.py:326-333).
B5 PASS: no deployed-tree copy is claimed; memo:31 says the fix is local-only. The remote tmp write is an acceptance BAR 3 failure, not deployment.
B6 PASS: the patch adds modules and removes or moves none (g329_degenerate_census.py:1).
B7 PASS: no render/head slice is used; memo:33 states eye check NONE and census.csv:2 enumerates rows.
B8 PASS: this is a census and construct, with no fitted residual (memo:3-10).
B9 PASS: 31 census rows have 31 unique clip_id values (census.csv:2).
B10 PASS: 50/600 match the sealed definitions (track_daemon_ledger.py:34-35; g329_prereg_2026-09-08.md:12-13).
Q1 PASS: this is not a scored comparison; the prereg hash at memo:2 matches and commit 08edacae is the candidate parent.
Q2 PASS: no charged trial or K is used (g329_prereg_2026-09-08.md:1-13).
Q3 PASS: bars and 50/600 definitions match prereg:33-36 and G329_spec.md:79-88.
Q4 PASS: no OOS claim or meta-learner exists (memo:33).
Q5 PASS: no AHEAD verdict or corpus comparison exists (memo:1-12).
Q6 PASS: verifier scan over prereg, patch artifacts, code, tests, and added results row found 0 restricted-vocabulary hits (memo:41).
Q7 FAIL: memo:3 calls 31/184 exhaustive, but no 184-row snapshot or all-row projection is committed; only the already-filtered 31-row census and 31 facts exist.
Q8 PASS: the binding premise was remeasured as nonzero from the committed artifact (memo:3; census.csv:2).
NOT VERIFIED LIST PASS: memo:28-35 explicitly lists route causality, missing-source attribution, deployment, unlogged rows, unmeasured quality, BAR 3, and known test failures.
CORRECTION 1: track_daemon_ledger.py:20 add `"degenerate": True, "resumed_partial": False`; extend test_g329_degenerate_resume.py:108 to assert both on corrupt_entry().
CORRECTION 2: memo:1 replace `21/21 ... explained` with `17/21 tail-classified; 4/21 no-tail rows explicitly unexplained`; keep PARTIAL.
CORRECTION 3: commit a minimal 184-row projection containing game_id, rows, seconds, and finished_at, then regenerate census.csv and re-run Q7.
TEST: `python -m pytest tests/platformkit/test_g329_degenerate_resume.py -q` = 8 passed; `python -m pytest scripts/platformkit/test_bridge_supervisor.py -q` = 6 passed; `python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q` = 1 failed.
TEST: `python -m pytest scripts/platformkit/test_g153_local_decoded_frames_producer.py -q` = 1 passed; `python -m pytest tests/platformkit/test_g151_quota_fails_loud.py -q` = 3 passed; `python -m pytest scripts/platformkit/test_track_daemon.py -q` = 29 passed.
TEST: `python -m pytest scripts/platformkit/test_track_daemon_done.py -q` = 7 passed; `python -m pytest scripts/platformkit/test_track_daemon_job_budget.py -q` = 1 passed; `python -m pytest scripts/platformkit/test_track_daemon_ledger_denominator.py -q` = 1 passed.
TEST: `python -m pytest scripts/platformkit/test_track_daemon_timeout_verdict.py -q` = 1 passed; `python -m pytest scripts/platformkit/test_night_report.py -q` = 2 passed, 2 failed; `python -m pytest tests/platformkit/test_g309_multigame_census.py -q` = 1 passed.
TEST: `python -m pytest tests/platformkit/test_g322_oversized_boxes.py -q` = 5 passed; `python -m pytest tests/platformkit/test_g325_offframe_boxes.py -q` = 10 passed; `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` = 1 passed.
TEST MASTER: `python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q -p no:cacheprovider` = 1 failed; `python -m pytest scripts/platformkit/test_night_report.py -q -p no:cacheprovider` = 2 passed, 2 failed.
RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G329 | committed artifacts reproduce 31 unique low rows, 21 degenerate, 11 sources absent, and 4/4 resumed degenerate; 184-row exhaustiveness and every-row schema are not verified | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: LOC check is 440 track_daemon.py, 72 track_daemon_ledger.py, 213 g329_degenerate_census.py, 187 test_g329_degenerate_resume.py; only the pre-existing unchanged 440-line file exceeds 300.
NEW GAP: g329_degenerate_census.py:82 maps an absent rows field to zero and :118-123 maps absent pod facts to gone; add unknown/pass-through behavior. Also, test_g329_degenerate_resume.py:87-95 does not prove tracker invocation, and the two failing importer files reproduce on master.
