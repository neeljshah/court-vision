VERDICT: CLOSED AT LIMIT
Candidate: ae36e57e7eaf7c70ba8278b590789733346d68db; full 22-file diff audited. Spec recovered from `4a272c503:docs/evidence/tracking/specs/G368_spec.md` because the named worktree path is absent.
ACCEPTANCE PREMISE PASS: reproduced old-set state 53/59 ABSENT and 6/6 surviving DIFFER; replacement median motion share 0.279919 is below 0.90 (memo:8,14; motion.csv:1-138).
ACCEPTANCE HEADLINES PASS: reproduced FRESH_REPL p10/p50/p90 0.032064/0.279919/0.832640; held p50/p90/max 8/146/361; class coverage 1.000000; no-coast median 0.164718 (memo:14,17,21,24).
ACCEPTANCE N/CONTROLS PASS: census exhausts 44 eligible unique sections over 10 unique game_ids; G358 has 34; controls reproduce 10/10 exact (fresh_sections_replacement.csv:1-45; controls.csv:1-11).
ACCEPTANCE ATTRIBUTION FAIL: 114064 held steps reproduce, but 66723 (0.584961) remain pooled as CLAMP_OR_SUBPIXEL, so required per-branch shares are absent; the memo admits P1/P5/P6 and stationary cases cannot be split (G368_spec.md@4a272c503:43-47; memo:20-21).
ACCEPTANCE EYE FAIL: 10 samples are at the sealed even indices and contain two polylines plus held shading, but committed `strips/` is 364333 bytes against the sealed 204800-byte TOTAL limit (G368_spec.md@4a272c503:49; g368_prereg_2026-09-09.md:339-352; memo:28).
ACCEPTANCE SCOPE PASS: ae36e57e changes no src/data/code/flag/threshold file; the proposal is unapplied evidence text (memo:20,29; PROPOSED_position_source.md:1-6).
EVIDENCE PASS: all 14 hashes claimed at memo:32 reproduce from candidate blobs; memo is 38 lines and has NOT VERIFIED at memo:37-38.
LOC PASS: ae36e57e touches 0 .py; referenced modules/test are 300/235/196 lines (memo:33; test_loc_rail_scope.py:174-203).
ADDITIVITY PASS: diff has only additions plus memo/ledger edits; no code field, status, or reader behavior is renamed or removed (fresh_sections_replacement.csv:1; memo:29).
TEST IMPORT PASS: the only existing tests importing either G368 module are in test_g368_evaluated_tick_motion.py:12-13; no .py is touched by ae36e57e.
TEST ENV: `conda run -n basketball_ai python -m pytest tests/platformkit/test_g368_evaluated_tick_motion.py -q -p no:cacheprovider` and the same command with `--basetemp=.pytest_tmp_g368_verify` -> 17 setup errors each; sandbox temp access failed before test bodies ran.
TEST PASS: `python -m pytest tests/platformkit/test_g368_evaluated_tick_motion.py -q -p no:cacheprovider --basetemp=.pytest_tmp_g368_verify2` -> 17 passed in 0.88s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider --basetemp=.pytest_tmp_g368_verify3` -> 1 passed in 0.99s.
B1 PASS: all 44 eligible replacement rows are scored; all absences and zero unparsed-frame counts are retained (motion.csv:1-138; memo:8,11).
B2 PASS: candidate changes no executable schema or reader and removes no field/status value (fresh_census_replacement.csv:1; memo:29).
B3 PASS: absent old-set sections remain explicit ABSENT rows and do not enter the measured share (motion.csv:79-137; test_g368_evaluated_tick_motion.py:164-181).
B4 PASS: no claim/reclaim lifecycle is introduced or changed (memo:29; candidate diff).
B5 PASS: compute is identified as pod-worktree scratch; no deployed-tree path is changed (memo:5,11; candidate diff).
B6 PASS: no module is moved or retired; both G368 imports resolve in the passing focused test (test_g368_evaluated_tick_motion.py:12-13).
B7 PASS: manifest rows equal floor(i*44/10), i=0..9, over the sorted set (g368_prereg_2026-09-09.md:341-346; strips/manifest.csv:2-11).
B8 PASS: this is a direct table census with no fitted residual used as independent evidence (g368_prereg_2026-09-09.md:13-20).
B9 PASS: denominators are 114064 distinct held steps over 139777 player rows, with three nonzero classes (memo:11,21; attribution.csv:1-390).
B10 PASS: candidate changes no harness code; tested constants remain 0.90/0.95/0.20 and total limit 200*1024 (test_g368_evaluated_tick_motion.py:183-189).
Q1 PASS: prereg seal reproduces; seal commit e203ae3a at 15:32:49Z precedes candidate ae36e57e at 16:38:51Z (g368_prereg_2026-09-09.md:444; memo:5).
Q2 PASS (N/A): this static producer census has no charged trial or launch K (g368_prereg_2026-09-09.md:13-20).
Q3 FAIL: memo:28 changes the sealed TOTAL interpretation to per-file after observing 364333 bytes; prereg:441-442 requires CLOSED AT LIMIT when this bar is unmet.
Q4 PASS (N/A): no OOS forecast or meta-learner is scored (g368_prereg_2026-09-09.md:15-20).
Q5 PASS (N/A): no advancement status is claimed; the 34-section G358 snapshot is separately reported (g368_prereg_2026-09-09.md:289-292; memo:14).
Q6 PASS: independent candidate-addition scan found 0 prohibited prose or figure hits (memo:34).
Q7 PASS: the replacement construct exhaustively selects all 44 eligible census rows; no sampled metric below 30 is barred (fresh_census_replacement.csv:1-877; memo:11).
Q8 PASS: premise loss and replacement motion were remeasured, not inherited; reproduced median is 0.279919 (memo:7-14; motion.csv:1-138).
CORRECTION (minimal): memo:1 `DONE` -> `CLOSED AT LIMIT`; memo:28 replace the per-file reinterpretation with `TOTAL 364333 > 204800; sealed bar not met`; memo:21 must label 0.584961 branch-unresolved unless new branch evidence is produced.
CORRECTION (minimal): RESULTS_LEDGER.md:700 `DONE` -> `CLOSED AT LIMIT`, remove the per-file-cap statement, and retain the reproduced measurements.
RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G368 | replacement premise median 0.279919 on 44 sections/10 game_ids; class coverage 1.000000; controls 10/10; strips 364333 bytes exceeds sealed 204800-byte total | CLOSED AT LIMIT (verified: codex-sol, contract A/B/Q)
NEW GAP: the named spec path is absent from both candidate and master and survives only in commit 4a272c503; restore a tracked authoritative spec copy (memo:5).
NEW GAP: the required `docs/research/organization-sprint/PROPOSED_position_source.md` is absent although memo:29 says it was copied; only the evidence-directory copy exists.
NEW GAP: memo:35 says finisher wall time ended 16:47Z, nine minutes after candidate commit ae36e57e was recorded at 16:38:51Z; reconcile the timestamp.
NEW GAP: targeted git add cannot create the linked-worktree index.lock because shared Git metadata is outside the writable root; an outer path-specific committer must land only this verifier file.
