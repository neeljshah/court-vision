VERDICT: REJECT
Candidate 98b706a52: full diff inspected; it changes only memo line 36 to name the retained discarded-run artifact.
ACCEPTANCE PASS: PARTIAL is correct because both class Wilson lower bounds and the mirror control miss sealed bars (g378_orientation_cue_2026-09-10.md:20-26; G378_spec.md:36-44).
PREMISE PASS: independently re-read G371 357/2/1/0, orientation UNKNOWN 360/360 and 4/4, 0 accepts; G367 left/right/unknown 12/16/26, 28 resolved, quota false (g378_orientation_cue_2026-09-10.md:7-8).
REPRODUCTION PASS: claimed/measured calls 81/77/82, resolved 158/240 = 0.658333, UNKNOWN 82/240 = 0.341667 (g378_orientation_cue_2026-09-10.md:15).
REPRODUCTION PASS: claimed/measured LEFT 29/49 = 0.591837, Wilson [0.452473,0.717848]; RIGHT 33/51 = 0.647059, Wilson [0.509861,0.763655] (g378_orientation_cue_2026-09-10.md:21-22).
REPRODUCTION PASS: claimed/measured mirror 12/30, masked 30/30, primary agreement 196/240, kappa 0.715486582606, adjudication complete (g378_orientation_cue_2026-09-10.md:17-18,25-26).
SAMPLING PASS: 240 unique keys/caches, 20 sections x 12 interior ticks, 16 games; controls match the sealed even indices; 120 unique renders exactly census 82 cue-UNKNOWN plus 38 wrong (g378_orientation_cue_2026-09-10.md:11,30).
EYE CHECK PASS: independently inspected 30 evenly spaced renders across the 120-item decision set; overlays and reported failure pattern agree (g378_orientation_cue_2026-09-10.md:30).
EVIDENCE PASS: every spec-listed artifact exists; candidate-named discarded run exists; memo has a NOT VERIFIED list (g378_orientation_cue_2026-09-10.md:36,53-58).
TEST PASS: `python -m pytest tests/platformkit/test_g378_orientation_cue.py -q` -> 8 passed in 1.85s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 2.46s.
IMPORT/LOC PASS: only test_g378_orientation_cue.py imports touched modules; LOC controls/cue/sample/score/sheets = 77/171/219/195/149, all <=300 (test_g378_orientation_cue.py:14).
B1 PASS: all decoded rows remain in coverage; class resolution is declared before scoring (g378_score.py:35,48,159).
B2 PASS: row code is additive; no prior field/status/reader changed, and all new imports resolve (test_g378_orientation_cue.py:14).
B3 PASS: absent frame/detection returns UNKNOWN and the row is retained (g378_cue.py:90-97,135-138).
B4 PASS: no claim or retry queue is introduced (g378_orientation_cue_2026-09-10.md:58).
B5 PASS: no deployed tree file changed; route use is read-only (g378_orientation_cue_2026-09-10.md:35,58).
B6 PASS: no module moved or retired; importer census found no orphan (test_g378_orientation_cue.py:14).
B7 PASS: both controls use whole-set even selection; renders are an exact census (g378_controls.py:34,40; g378_sheets.py:74-85).
B8 PASS: no rated label fits the cue; development-only choices were sealed (g378_prereg_2026-09-10.md:58).
B9 PASS: denominator is 240 distinct frame keys and cache names, not recycled units (g378_orientation_cue_2026-09-10.md:11).
B10 PASS: spec/prereg/code bars are 120/20/8, class 30, Wilson 0.90, controls 30 (G378_spec.md:39; g378_prereg_2026-09-10.md:198; g378_score.py:25).
Q1 PASS: seal holds at cb4ecf39b94a41c21f309f6fbebaffbd8b5d2c8f3d5176d36940385fea912a12 and commit a9259d109 predates metrics (g378_prereg_2026-09-10.md:231).
Q2 PASS: no charged trial or K applies; the pre-run ledger snapshot is recorded (g378_orientation_cue_2026-09-10.md:12).
Q3 PASS: sealed acceptance bars are byte-identical to the spec (G378_spec.md:39-40; g378_prereg_2026-09-10.md:198-199).
Q4 PASS: no fitted OOS forecaster or meta-learner is claimed; cue parameters precede ratings (g378_prereg_2026-09-10.md:58).
Q5 PASS: result is PARTIAL, not AHEAD (g378_orientation_cue_2026-09-10.md:1,20-23).
Q6 FAIL: retained prose has one prohibited standalone scanner hit (g378_orientation_cue_2026-09-10/raters/g378_rater_terra_09.txt:5); memo scan omitted rater logs while claiming every artifact (g378_orientation_cue_2026-09-10.md:38-41).
Q7 PASS: sampled metric has 240 unique frames and every scored class has >=30 resolved rows (g378_orientation_cue_2026-09-10.md:11,21-22).
Q8 PASS: premise was remeasured before scoring and independently reproduces (g378_orientation_cue_2026-09-10.md:7-8).
CORRECTION (minimal): g378_rater_terra_09.txt:5 replace only the scanner-hit prose token with `calibration-only` and disclose that redaction.
CORRECTION (minimal): g378_orientation_cue_2026-09-10.md:38-41 scan every text artifact in the evidence tree and report zero non-opaque hits.
2026-09-10 | tracking | G378 | cue PARTIAL: 158/240 resolved; LEFT 29/49 = 0.591837 Wilson lower 0.452473; RIGHT 33/51 = 0.647059 Wilson lower 0.509861; mirror 12/30, masked 30/30; kappa 0.715487 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: The attack-direction quantity named outside the acceptance rule remains unmeasured (g378_orientation_cue_2026-09-10.md:32,53-56).
NEW GAP: The masked control uses the cue evidence band rather than the banner named outside the acceptance rule (g378_orientation_cue_2026-09-10.md:33).
