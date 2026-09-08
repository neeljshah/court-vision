VERDICT: REJECT
ACCEPTANCE FAIL: G333_spec.md:69-74 requires all existing touched-module tests green; 9 of 32 files were non-green (34 failed, 1 collection error), and g333_apply_producer_diffs_2026-09-08.md:1,30 instead reports 26 failures in 7 files.
A1 PASS: candidate test ran against an isolated master-code archive: 16 failed, 2 passed, 1 informational skip; all four old behaviors reproduced (VERIFIER_CONTRACT.md:11; G333_spec.md:71-72).
A2 PASS: premise, source growth, test totals, live panorama census, sidecars, and smoke CSV were independently recomputed; claimed-versus-measured values are below (VERIFIER_CONTRACT.md:12).
A3 PASS: eye check NONE is required and stated (G333_spec.md:66; memo:3). A4 PASS: n=4 names four distinct diffs; smoke rows have distinct arms and each records 26 distinct frames (smoke_census.csv:2-3).
A5 PASS: repository grep covered all ball_inferred/evaluated_frames readers and cache/row-builder importers; 9 focused reader files passed 46 tests (VERIFIER_CONTRACT.md:15).
A6 PASS: no candidate landing was performed; this report is committed by explicit path only, per the user override to VERIFIER_CONTRACT.md:16.
A7 PASS: prereg, memo, four committed artifacts, four proposal sources, and fallback image exist; the disposable clip is absent exactly as G333_spec.md:12-14 requires (VERIFIER_CONTRACT.md:17).
B1 PASS: four premises and all smoke rows are retained; powerless smoke effects are named (memo:17-21,38-45).
B2 PASS: no field/status was renamed or removed; sidecar keys remain, unavailable count retains reason, and reader tests pass (run_clip.py:226-243; test_g333_producer_diffs.py:245-285).
B3 PASS: unavailable evaluated_frames remains null with its reason (run_clip.py:236-238; test_g333_producer_diffs.py:275-285).
B4 PASS: no claim lifecycle is introduced (memo:23-28).
B5 PASS: no deployment occurred and the pod producer remains pre-edit (memo:32,44).
B6 PASS: no module moved or retired; the spec test and all 32 pre-existing files naming the touched modules were exercised (candidate diff; memo:30).
B7 PASS: smoke starts at source frame 1200, not at the head; no render decision set exists (memo:32).
B8 PASS: construct evaluation and direct counts use no fit residual (test_g333_producer_diffs.py:88-285).
B9 PASS: n=4 is four distinct producer changes and evaluated_frames counts detector-gated frames, not recycled identifiers (unified_pipeline.py:3055).
B10 PASS: candidate diff changes no harness threshold or gate value (97adf3ec2 full diff; memo:1).
Q1 PASS: prereg seal recomputes to 4b3764fe5ac7d833336561f85437014bff65d7789069615da60af88a8329dcc4; parent 19592438a predates candidate 97adf3ec2 (prereg:186).
Q2 PASS: no charged trial or K applies to this producer construct (G333_spec.md:68-74).
Q3 FAIL: spec fixes peak RSS below 1.5 GB and prereg says an over-limit arm is NOT RUN, but memo:34-35,42 reports 2689/2678 MiB and uses both arms; an unmeetable fixed bar cannot be ignored (G333_spec.md:13-14; prereg:155-158; VERIFIER_CONTRACT.md:36).
Q4 PASS: no OOS score or meta-learner is used (memo:3,32). Q5 PASS: no AHEAD claim is made (memo:1).
Q6 PASS: restricted-language scan of candidate-added lines returned 0 matches (VERIFIER_CONTRACT.md:39).
Q7 PASS: n=4 CONSTRUCT exhaustively enumerates G330/G325/G320/G331; 19 cases exercise all four (G333_spec.md:16-40; test_g333_producer_diffs.py:1-285).
Q8 PASS: all four premises are preregistered before the candidate and independently reproduce on master code (prereg:27-57; candidate parent 19592438a).
TEST COMMAND FORM: each path below ran separately through C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe, with a Path.mkdir ACL shim, then pytest.main([PATH,"-q","-p","no:cacheprovider","--basetemp=C:/Users/neelj/nba-track-a1/.verify_tmp/reliable"]); p/f/e/s are passed/failed/error/skipped.
TEST: tests/conformance/nba/test_nba_config_values.py=53p; tests/ingest/test_preflight_checks.py=8p,2s; tests/platformkit/test_g313_ten_id_cap.py=3p; tests/platformkit/test_g333_producer_diffs.py=19p; tests/test_ball_track_resume.py=5p; tests/test_broken_games_unstick.py=4p; tests/test_coord_normalization.py=13p,1f,2s.
TEST: tests/test_court_zone.py=8p; tests/test_data_collection_gaps.py=21p; tests/test_dengw.py=1e; tests/test_hardening.py=69p,1f; tests/test_homography_thresholds.py=4p; tests/test_issue009_game_id_wiring.py=3p; tests/test_phase2.py=69p,13f,2s.
TEST: tests/test_phase5.py=18p; tests/test_pipeline_e2e.py=13p,2s; tests/test_pipeline_live.py=6p,1s; tests/test_pipeline_smoke.py=5p,1s; tests/test_possession_boundary.py=7p,3f; tests/test_possession_segmentation.py=5p; tests/test_possession_tracking_gaps.py=24p,10f.
TEST: tests/test_run_phase_g.py=15p,2f; tests/test_shot_clock_est.py=5p; tests/test_shot_directional_gate.py=6p; tests/test_shot_gate.py=6p,1f; tests/test_shot_log_features.py=16p; tests/test_shot_log_team_abbrev.py=1p,3f; tests/test_shot_log_units.py=10p.
TEST: tests/test_threshold_validation.py=10p; tests/platformkit/test_g233_basketball_seeded_court_coordinates.py=1p; tests/test_broadcast_detection.py=14p; tests/test_court_detector.py=7p; tests/test_run_clip_output_contract.py=2p; tests/platformkit/test_loc_rail_scope.py=1p. Total 451p,34f,1e,10s over 34 files.
TEST READERS: scripts/platformkit/test_evaluated_frame_count_direct_path.py; scripts/platformkit/tracking/test_g310_native_input_arm.py; tests/platformkit/test_g309_multigame_census.py; tests/platformkit/test_g310_instance_key.py; tests/platformkit/test_g312_coverage_denominator.py; tests/platformkit/test_g314_ball_inferred_coords.py; tests/platformkit/test_g320_ball_inferred_no_coord.py; tests/platformkit/test_g331_evaluated_frames_sidecar.py; scripts/platformkit/test_track_daemon_done.py -> 46 passed.
TEST MASTER [isolated archive]: same command form, basetemp master_base2, tests/platformkit/test_g333_producer_diffs.py -> 16 failed, 2 passed, 1 skipped; current -> 19 passed; all 32 existing-file and LOC-rail outcomes are identical on master/candidate, so measured regressions=0.
REPRO: claimed premise 4/4, current 19/19, old 16 red/3 pass, existing 26 failures/7 files; measured 4/4, 19/19, old 16 red/2 pass/1 skip, existing 34 failures+1 error/9 files; unified_pipeline.py net +11 (15 add/4 delete) <=12, run_clip.py +20.
REPRO SMOKE: claimed and CSV-measured before/after player rows 34/35, wholly-off-frame 0/0, ball rows 50/50, flagged-without-coordinate 0/0, panorama files 4/3, evaluated_frames null/50; live cache census is 3/3 byte-identical to fallback. Memo has NOT VERIFIED at lines 38-45.
CORRECTIONS (minimal diff): memo:1 DONE -> PARTIAL; memo:1,30 "26 failures in 7 files" -> "34 failures and 1 collection error in 9 files"; memo:36 must label the smoke descriptive only unless rerun below the fixed memory bar.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G333 | premise 4/4; candidate construct tests 19/19; master construct test 16 failed, 2 passed, 1 skipped; 32 existing files 431 passed, 34 failed, 1 error, 10 skipped with identical master/candidate outcomes; smoke exceeded fixed memory bar | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: LOC FAIL: scripts/run_clip.py is 821 lines and src/pipeline/unified_pipeline.py is 4791; tests/platformkit/test_g333_producer_diffs.py is 285, while test_loc_rail_scope.py does not cover the first two.
NEW GAP: pytest temp directories created with restrictive ACLs are unreadable to verifier cleanup; git clean removed all readable test artifacts but .verify_tmp/current remains inaccessible and untracked.
NEW GAP: linked-worktree index.lock is outside the writable sandbox; both explicit git add and lane_commit.py were denied, so the requested commit requires the external lane-commit runner.
