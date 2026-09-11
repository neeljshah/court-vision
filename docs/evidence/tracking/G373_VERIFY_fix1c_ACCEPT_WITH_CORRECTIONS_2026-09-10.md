VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 3a3487e0a536b020743b04f1892f4ed44bb614c8.
ACCEPTANCE PASS (phase-scoped): premise holds, the reference bar passes, all 881 original keys plus 739 fixed development keys are retained, and the unmet 283/500 box quota correctly prevents arm scoring (docs/evidence/tracking/specs/G373_spec.md:14; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:29).
B1 PASS: all 1,620 scheduled keys enter the census; 1,024 are settled and 596 remain explicit (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:12).
B2 PASS: the code change preserves the token and manifest fields; the sole reader test passes (scripts/platformkit/tracking/g373_q6_redact.py:12; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/q6_redaction_manifest.csv:1).
B3 PASS: missing or unsettled ratings are counted, and no arm is scored through them (scripts/platformkit/tracking/g373_reference_v2.py:178; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B4 PASS: no arm, candidate, evaluator, or new claim path ran (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B5 PASS: the memo records no deployed-tree write or flag change (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B6 PASS: no module was moved or retired; the changed module remains additive (scripts/platformkit/tracking/g373_q6_redact.py:1).
B7 PASS: 739 distinct frames span 28 sections; raw recomputation found a minimum within-section span of 3,650 frames (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:15).
B8 PASS: reference usability compares two blind primary ratings, not fitted residuals (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:21).
B9 PASS: raw denominators are 715 paired frames and 1,430 boxes, both nonconstant populations (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:18; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:35).
B10 PASS: 18.50 px and the 30-pair minimum match the sealed acceptance rule; this commit changes no threshold (docs/evidence/tracking/specs/G373_spec.md:16; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:4).
Q1 PASS: both seal tests pass; commits 24336b55b and 450935189 precede first metric commit 1ccdf26eb (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/g373_execution_prereg_2026-09-10.md:36; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/g373_execution_prereg_amendment_phase1_2026-09-10.md:56).
Q2 PASS: no scored comparison or charged trial ran (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q3 PASS: the fixed reference bar is 17.33 <= 18.50 px over 715 pairs (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:5).
Q4 PASS: no model comparison or meta-learner was scored (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q5 PASS: no candidate result or ahead classification exists (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:50).
Q6 PASS: independent full-scope automated scan reports 0 findings; changed fixtures construct the reserved token from character codes (scripts/platformkit/tracking/g373_q6_redact.py:12; tests/platformkit/test_g373_ball_detector_v2.py:55).
Q7 PASS: 1,620 scheduled keys are exhaustive and the scored reference population is n=715 (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:18; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:31).
Q8 PASS: fresh raw replay measures A0 at 0 TP / 8 FP over 549 before the successor gate (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/binding_replay.json:8; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/binding_replay.json:42).
TEST PASS: `python -m pytest tests/platformkit/test_g373_ball_detector_v2.py -q` -> 21 passed in 0.75s.
IMPORTERS/LOC PASS: importer census finds only the spec test; touched Python files are 123 and 275 lines, both <= 300 (scripts/platformkit/tracking/g373_q6_redact.py:123; tests/platformkit/test_g373_ball_detector_v2.py:275).
MEMO PASS: 57 <= 60 lines and a seven-item NOT VERIFIED list is present (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:48).
REPRODUCED: claimed A0 0/8/549 and A7 2/178/549; raw frame scoring measures the same, with 549 unique rows per arm (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/binding_replay.json:8; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/binding_replay.json:23).
REPRODUCED: claimed 17.33 px, n=715, p90=287.09, diameter=37.0, bar=18.50, kappa=0.6642328686951492, census=1,024/596, and development=283 boxes/27 games; raw CSV recomputation matches (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:16; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/dev_boxes_summary.json:2).
REPRODUCED: 12/12 memo digests and 20/20 current redaction-file digests match; manifest totals are 21 rows, 20 files, 21 replacements (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/q6_redaction_manifest.csv:1).
2026-09-10 | tracking reference | G373 | premise A0=0 TP/8 FP/549; reference 17.33<=18.50 px (n=715); development 283/500 boxes across 27 games | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: committed q6_scan.json:10 lists only evidence and memo roots although memo:57 claims source/test coverage. Minimal diff: regenerate it with both changed Python paths in scanned_roots.
NEW GAP: memo:29 reports development labels 260/381/37; dev_boxes_summary.json:7 measures 284/383/43. Minimal diff: replace those three counts.
NEW GAP: memo:40 reports scanner/redactor LOC 99/105; measured values are 113/123. Minimal diff: replace both counts.
NEW GAP: memo:43 says raw rater batches remain verbatim, conflicting with memo:46 and the 21-row manifest. Minimal diff: replace that clause with the explicit note-field normalization statement.
NEW GAP: memo:8 names models/weights/yolov8n_ball.pt, but that evidence path is absent locally at verification time; record it as NOT VERIFIED or restore the named path.
NEW GAP: contract A1 cannot run because master lacks tests/platformkit/test_g373_ball_detector_v2.py; this does not reject the candidate.
NEW GAP: git diff --check flags CRLF-wide memo churn and an extra ledger EOF blank. Minimal diff: restore LF and remove only the added blank line.
