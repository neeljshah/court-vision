VERDICT: ACCEPT WITH CORRECTIONS
Candidate 388efcdd7: full stat/diff inspected; four documentation/evidence files changed and no Python module changed.
ACCEPTANCE PASS: measured PARTIAL is correct: class-left lower 0.452473, class-right lower 0.509861, and mirror 12/30 miss sealed bars; masked 30/30 passes (G378_spec.md:37-44; summary.json:24-30,56-66,82).
PREMISE PASS: full-artifact recount gives G371 status 357/1/2, 0 ACCEPT, orientation UNKNOWN 360/360 and 4/4; G367 left/right/unknown 12/16/26, 28 resolved, quota false (g371_symmetry_margin_2026-09-09/summary.json:107-112,372; g367_init_symmetry_2026-09-09/agreement.json:33-43).
REPRODUCTION PASS: claimed/measured calls 81/77/82; resolved 158/240 = 0.658333 and UNKNOWN 82/240 = 0.341667 (g378_orientation_cue_2026-09-10/summary.json:12-19).
REPRODUCTION PASS: claimed/measured LEFT 29/49 = 0.591837, Wilson [0.452473,0.717848]; RIGHT 33/51 = 0.647059, Wilson [0.509861,0.763655] (g378_orientation_cue_2026-09-10.md:21-22).
REPRODUCTION PASS: claimed/measured agreement 196/240, kappa 0.715486582606, 44/44 adjudicated; mirror 12/30 and masked 30/30 (g378_orientation_cue_2026-09-10.md:17-18,25-26).
SAMPLING PASS: 240 unique keys/caches, 20 sections x 12 interior even ticks, 16 games; 120 renders exactly equal 82 cue-UNKNOWN union 38 wrong (g378_orientation_cue_2026-09-10.md:11,30).
EYE/EVIDENCE PASS: inspected 30 evenly spaced renders over indices 0..119; overlays agree, all required paths exist, memo is 60 lines and has NOT VERIFIED (g378_orientation_cue_2026-09-10.md:30,53-58).
TEST PASS: `python -m pytest tests/platformkit/test_g378_orientation_cue.py -q` -> 8 passed in 0.97s.
IMPORT/LOC PASS: candidate touched no module or .py file, so importing-test and <=300 LOC checks are vacuous; sole G378 module-import test is the spec test above (test_g378_orientation_cue.py:14).
B1 PASS: every decoded row remains in coverage and resolved-class scoring is declared (g378_score.py:48,159-172).
B2 PASS: no field, status, reader behavior, or schema changed; the sole replacement is retained-log prose (g378_rater_terra_09.txt:5; g378_orientation_cue_2026-09-10.md:60).
B3 PASS: absent frame/detection emits UNKNOWN and remains a row (g378_cue.py:93-97,135-138).
B4 PASS: no claim or retry surface is introduced by the documentation-only candidate (g378_orientation_cue_2026-09-10.md:58,60).
B5 PASS: no deployed-tree path changed and nothing is wired (g378_orientation_cue_2026-09-10.md:58,60).
B6 PASS: no module moved or retired; no orphan can result from the four-file documentation/evidence diff (G378_VERIFY_att1_REJECT_2026-09-10.md:2).
B7 PASS: controls use whole-set even selection; renders are the exact decision-set census (g378_controls.py:34,40; g378_orientation_cue_2026-09-10.md:30).
B8 PASS: cue outputs preceded blind labels and no label fitted the cue (g378_orientation_cue_2026-09-10.md:17,34).
B9 PASS: denominator is 240 distinct frame keys and caches, not recycled units (g378_orientation_cue_2026-09-10.md:11,15).
B10 PASS: candidate changes no bar; spec/code remain 120/20/8, class 30, Wilson 0.90, controls 30 (G378_spec.md:39-40; g378_score.py:25; g378_controls.py:19).
Q1 PASS: seal independently holds at cb4ecf39b94a41c21f309f6fbebaffbd8b5d2c8f3d5176d36940385fea912a12; prereg commit a9259d109 predates metric commit 93711937b (g378_prereg_2026-09-10.md:231).
Q2 PASS: no charged trial/K applies; the pre-run ledger snapshot is recorded (g378_orientation_cue_2026-09-10.md:12).
Q3 PASS: sealed bars are unchanged and byte-consistent with the spec (G378_spec.md:39-40; g378_score.py:25).
Q4 PASS: no fitted OOS forecaster/meta-learner is claimed; cue output was fixed before ratings (g378_orientation_cue_2026-09-10.md:13-17,34).
Q5 PASS: result is PARTIAL, not AHEAD (g378_orientation_cue_2026-09-10.md:1,20-23).
Q6 PASS: independent 50-file plus G378-ledger scan found 124 bare-token hits, all in opaque digests/cache names or timestamp metadata; zero governed prose/claim/label/ledger hits (g378_orientation_cue_2026-09-10.md:38-41,60; g378_rater_terra_09.txt:5).
Q7 PASS: sampled metric has 240 unique frames and each scored class has >=30 resolved predictions (g378_orientation_cue_2026-09-10.md:11,21-22).
Q8 PASS: premise was measured first and independently reproduces from complete artifacts (g378_orientation_cue_2026-09-10.md:7-8).
2026-09-10 | tracking | G378 | cue PARTIAL: 158/240 resolved; LEFT 29/49, Wilson lower 0.452473; RIGHT 33/51, Wilson lower 0.509861; mirror 12/30, masked 30/30; kappa 0.715487 | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: memo:60 minimal diff: replace before sha256 f3c9d41a9527ffad4c720354ce544058e2f172c6f661f29c7fec6717c0c750a3 with independently measured 02fd3d66960ebafb126595843319c5c43b5cd72433c82383e139dcdba3d4aea8.
NEW GAP: memo:60 minimal diff: replace `digests or cache basenames` with `digests, cache basenames, or two timestamp metadata fields` so the scan disclosure matches the artifacts.
NEW GAP: RESULTS_LEDGER.md:718 minimal diff: delete the extra final blank line reported by `git diff --check`.
NEW GAP: attack-direction quantity remains unmeasured outside the acceptance rule (g378_orientation_cue_2026-09-10.md:32,54).
NEW GAP: masked control uses the cue evidence band rather than the banner wording outside the acceptance rule (g378_orientation_cue_2026-09-10.md:33).
