VERDICT: REJECT
Candidate: 13be14ae6b2321ce91008215bde867306f39e41a; G316 acceptance rule plus contract B1-B10/Q1-Q8 applied.
ACCEPTANCE FAIL: required n is 200 frames per broadcast on 2 broadcasts, but candidate scored 100 per clip on 4 clips (docs/evidence/tracking/specs/G316_spec.md:80; g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:26-34).
BAR REPRODUCED: 246/372 = 0.661290 versus 0.900; skin rates 67/93, 70/95, 78/95, 31/89; Wilson pooled [0.611765,0.707518] (g316_attempt2/g316_liveness_summary.json:5-61).
PREMISE PASS: streaming raw pod columns reproduced clock fills 0/5,603, 0/2,642, 0/6,623, 0/3,606; periods filled on every row with values 1-4 (g316_attempt2/g316_premise.json:1-78).
EYE CHECK PASS: 20 evenly spaced source renders were regenerated; 19/20 hashes matched, the remaining visual class was unchanged, 9/20 agree within 1 s, and no legible clock was rule-rejected (g316_attempt2/g316_handcheck_index.json:1-322).
PERIOD PASS: the frame-percentile fallback explains values 1-4; operative assignment is at src/pipeline/unified_pipeline.py:4334-4335 (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:17-18).
B1 PASS: presence rule was sealed before scoring and all 28 exclusions are retained/named; 20-set review found no legible rejected clock (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:23-24,38-39).
B2 PASS: candidate only adds new evidence and appends a status row; no field/status rename or reader change, and no artifact reader exists (docs/evidence/tracking/RESULTS_LEDGER.md:496; g316_attempt2/g316_frame_records.jsonl:1).
B3 PASS: no gate or absent-evidence handling is changed (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:46-47).
B4 PASS: no claim lifecycle is added or changed (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:46-47).
B5 PASS: read-only pod scan found no G316 file in the deployed tree (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:46-47).
B6 PASS: candidate has 924 additions, no deletion/move, and no orphaned reference (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:52-53).
B7 PASS: 400 unique hashes use whole-clip midpoint spacing, not a head slice (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:20-26).
B8 PASS: design and score manifests contain 160/400 hashes, zero clip/hash overlap (g316_attempt2/g316_design_manifest.json:1; g316_attempt2/g316_score_manifest.json:1).
B9 PASS: denominator is 372 unique accepted frames across four varying skin counts (g316_attempt2/g316_liveness_summary.json:2-55).
B10 PASS: 0.90 bar and 0.30 confidence threshold match spec/module; candidate changes neither (docs/evidence/tracking/specs/G316_spec.md:76; scripts/platformkit/tracking/g316_scoreboard_clock_liveness.py:34-36).
Q1 PASS: prereg/amendment seals independently reproduce and commits 558771cb4/637f7d79a precede scoring commit (g316_preregistration_attempt2_2026-09-07.md:156; g316_preregistration_attempt2_amendment_device_2026-09-08.md:51).
Q2 PASS: no charged comparative trial or K claim is made (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:1-3).
Q3 PASS: artifact retains the 0.90 bar and reports it unlowered (g316_attempt2/g316_liveness_summary.json:61; g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:36).
Q4 PASS: this is a liveness measurement, not an OOS model comparison (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:3).
Q5 PASS: no AHEAD claim is made (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:3).
Q6 PASS: candidate-added prose is calibration-only; the sole restricted-token match is an exempt exact identifier (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:23-24).
Q7 PASS: sampled metric has n=400 and 400 unique records (g316_attempt2/g316_liveness_summary.json:2-3).
Q8 PASS: raw premise was re-measured before adjudication and matches the artifact (g316_attempt2/g316_premise.json:1-78).
LOC PASS: candidate touches no .py; row module is 299 lines (scripts/platformkit/tracking/g316_scoreboard_clock_liveness.py:1).
MEMO PASS: 60 lines and includes a NOT VERIFIED list (g316_scoreboard_clock_liveness_attempt2_2026-09-07.md:55-60).
TEST PASS: `python -m pytest tests/platformkit/test_g316_scoreboard_clock_liveness.py -q -p no:cacheprovider` -> 6 passed.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed; the spec test is the sole row-module importer.
CORRECTION (minimal rerun): preregister 2 broadcasts without using outcomes, add midpoint-offset frames to reach 200 each, rebuild the 20-render review, then replace memo:3,26-39 and ledger:496 from that result.
2026-09-08 | tracking | G316 | premise 0/18,474; 400 unique but 100x4 differs from required 200x2; parsed-clock 246/372 = 0.6613; hand agreement 9/20 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the original render sheet named at memo:53 is absent locally and from the named pod scratch; regeneration matched 19/20 hashes and preserved the unmatched frame's visual class.
NEW GAP: the record omits spec-requested `frame_index` and `crop_box`, using `j` and `region_set`; this is outside the acceptance rule and did not rename an existing artifact field (G316_spec.md:62-65; g316_frame_records.jsonl:1).
NEW GAP: A1 master-tree rerun is unavailable because the row module/test are not present on master; exact candidate-worktree commands are reported above.
NEW GAP: eye-check scope conflicts internally: acceptance says accepted frames, while NON-TAUTOLOGY says the full 400; the candidate follows the latter (G316_spec.md:81-82,96-98).
