VERDICT: REJECT
Candidate 0e432a907; verifier scope: S308 acceptance, B1-B10, Q1-Q8.
PREMISE PASS: raw data/cache/inplay_odds/nba_checkpoints_full.parquet is 2,829,826 bytes, 465,249 rows, 13 columns, first IDs 401704627 x3; landed S294 recomputes ALL coverage 1.0 and half-widths 0.03111479645515689/0.019952037973183918 (spec:7-10).
ACCEPTANCE FAIL metric/report: nested interval-score summaries and signed deltas are absent from memo/JSON; only group rows and the S294 correction are stored (S308_band_functional_validity_attempt2_2026-09-08.md:18; .json:35).
ACCEPTANCE PASS dependency bar: 30/30 rows independently sum to 0 outer-label dependencies (S308_band_functional_validity_attempt2_2026-09-08_train_dependencies.csv:2; s308_band_functional_validity.py:120).
ACCEPTANCE PASS n/bars: 465,249 ticks, 1,593 games; smallest cell OT has 81 games; 400 and 0.004 unchanged; all failures shown (S308_band_functional_validity_attempt2_2026-09-08.md:18).
ACCEPTANCE PASS reproduction: fold 0 is 78,255 test ticks/248 games and 386,994 calibration ticks/1,345 games; all 286 nominal-0.90 group memberships match exactly and score-sum difference is 0 (S308_band_functional_validity_attempt2_2026-09-08_intervals.csv.gz:1).
ACCEPTANCE FAIL immutability: S294 route bytes changed despite the unchanged-replay and must-not-move clauses (S308_spec.md:9; S308_spec.md:23; s276_incumbent_conformal_band_full_attempt2.py:23).
B1 PASS: every tick and every eligible phase/ALL group is scored; no post-score exclusion (s308_band_functional_validity.py:82).
B2 PASS: no field/status removal or rename; all direct test readers were identified and passed (s308_band_functional_validity.py:124; test_s308_band_functional_validity.py:10).
B3 PASS (not applicable): no absent-evidence quarantine gate was added (s308_band_functional_validity.py:148).
B4 PASS (not applicable): no claim lifecycle was added (s308_band_functional_validity.py:148).
B5 FAIL: the memo records a pre-verification write into /workspace/nba-ai-system, outside the scratch-only exception (S308_band_functional_validity_attempt2_2026-09-08.md:9; VERIFIER_CONTRACT.md:140).
B6 PASS: no file was moved or removed; importer census is complete (test_ladder_block_predict.py:7; test_s276_incumbent_conformal_band_full_attempt2.py:7).
B7 PASS: S-row reproduction used the full nominal decision set, not a head slice (S308_band_functional_validity_attempt2_2026-09-08_intervals.csv.gz:1).
B8 PASS: inner OOF calibration excludes the outer block (s308_band_functional_validity.py:108; cpcv_engine.py:140).
B9 PASS: denominators are 465,249 distinct tick positions and 1,593 games, not recycled IDs (s308_band_functional_validity.py:143; .json:131).
B10 PASS: 6 blocks, 1-day embargo, 400-tick rail, and 0.004 bar match master/spec (s308_band_functional_validity.py:35; .json:52).
Q1 PASS: seal recomputed as 92e7463acabc9a58dbad4c7b83dfec37a13e7a63295f009629b634dbc7698f4f; commit d0397d231 at 02:38:39 CDT predates launch 02:39:32 (S308_preregistration_attempt2_2026-09-08.md:181).
Q2 PASS (not applicable): the diagnostic is explicitly uncharged (S308_band_functional_validity_attempt2_2026-09-08.md:3).
Q3 PASS: frozen numeric bars were not changed (S308_spec.md:17; s308_band_functional_validity.py:192).
Q4 PASS: CPCV uses game-disjoint purging, symmetric embargo, strict redaction, and OOF calibration (s308_band_functional_validity.py:67; cpcv_engine.py:140).
Q5 PASS (not applicable): no AHEAD claim; one-window limitation is explicit (S308_band_functional_validity_attempt2_2026-09-08.md:42).
Q6 PASS: automated vocabulary scan of all nine candidate files was clean (S308_band_functional_validity_attempt2_2026-09-08.md:56).
Q7 PASS: full-set reproduction covered 1,593 games and every cell exceeds 30 games (S308_band_functional_validity_attempt2_2026-09-08.json:61).
Q8 PASS: premise was remeasured first and held (S308_spec.md:10; S308_band_functional_validity_attempt2_2026-09-08.md:12).
LOC PASS: touched Python LOC = 84,253,210,45,42; repo rail passed (test_loc_rail_scope.py:1).
TEST: python -m pytest tests/platformkit/test_s308_band_functional_validity.py -q -p no:cacheprovider -> 1 passed in 1.76s.
TEST: python -m pytest tests/platformkit/test_ladder_block_predict.py -q -p no:cacheprovider -> 1 passed in 9.60s.
TEST: python -m pytest tests/platformkit/ingame/test_s276_incumbent_conformal_band_full_attempt2.py -q -p no:cacheprovider -> 1 passed in 5.37s.
TEST: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider -> 1 passed in 0.90s.
REPRODUCED: claimed baseline coverage 1.0/1.0 and half-width 0.03111479645515786/0.019952037973190725; measured 1.0/1.0 and 0.03111479645515689/0.019952037973183918.
REPRODUCED: claimed nested ALL coverage 1.0/1.0 and half-width 0.030624216/0.020048515; measured 1.0/1.0 and 0.030624216396511642/0.020048514753337167.
REPRODUCED: claimed S294 score sums 52.217066476/61.766351358 and 42 changed; measured 52.217066475722/61.766351357624 and 42. Nested score sums at 0.90/0.80 are 33.575997256835/28.104450674369.
CORRECTIONS: revert s276_incumbent_conformal_band_full_attempt2.py to 0e432a907~1; keep batching S308-only; stage required input in job scratch; regenerate evidence with per-cell/ALL score summaries and signed deltas.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | in-game calibration | S308 | 0 outer-label dependencies across 30 folds; nested ALL coverage 1.0 at both nominals, but S294 bytes changed and score summaries are omitted | REJECT (verified: codex-sol, contract A/B/Q)
MEMO PASS: candidate includes an explicit NOT VERIFIED list (S308_band_functional_validity_attempt2_2026-09-08.md:37). NOT VERIFIED: fresh model refit; verifier reproduced archived folds/groups only because the supplied pod wrapper could not execute in this sandbox.
NEW GAP: the report names S308_band_functional_validity_attempt2_2026-09-08_memberships.csv, but that path is absent locally; only its hash and pod residence are stated (.json:5; memo:40).
NEW GAP: JSON reuses S101 symmetric within_tolerance flags while the memo applies the S307 asymmetric band; add an aliased within_s307_band field (.json:159; memo:18).
