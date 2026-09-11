VERDICT: REJECT
Candidate: 9fb6642ae47a52efee82e8b6dd6e33e0111d3c79; 1,620 added JPEGs only.
ACCEPTANCE PASS (phase-scoped): premise and reference were measured; 283/500 development boxes is honestly unmet and no arm was scored or claimed DONE (docs/evidence/tracking/specs/G373_spec.md:14; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:1).
B1 PASS: all 1,620 scheduled keys enter agreement/missingness accounting; 1,024 settled plus 596 queued (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:11).
B2 PASS: candidate only adds sheets; no field, status, reader, or behavior is renamed or removed (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv:1).
B3 PASS: 596 unsettled frames remain explicit rather than being dropped (scripts/platformkit/tracking/g373_reference_v2.py:118).
B4 PASS: no claim path is added; no candidate arm ran (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B5 PASS: candidate is evidence-only and the measured run records no deployed-tree write (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B6 PASS: no module is moved or retired by the candidate (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv:1).
B7 PASS: 739 extra frames span 28 sections with observed minimum index gap 144; sheets cover all 1,620 keys (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:15).
B8 PASS: the agreement statistic uses two blind ratings and is not a detector residual (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:19).
B9 PASS: named denominators are 715 paired frames and 1,430 boxes (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:16).
B10 PASS: candidate changes no bar; observed 17.33 is checked against sealed 18.50 (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:3).
Q1 PASS: both seals recompute exactly and commits 24336b55b/450935189 precede first metric commit 0e9f7281d (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:2).
Q2 PASS: no arm metric or charged trial ran (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q3 PASS: reference bar is byte-consistent with the sealed rule and spec (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:7).
Q4 PASS: not triggered; this phase contains an identity replay and no new model comparison (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q5 PASS: not triggered; no candidate was selected and no AHEAD result exists (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:47).
Q6 FAIL: independent recursive rescan finds 42 non-exempt findings across 21 files, not 21 across 20; raw prose is outside the opaque-identifier exception (docs/evidence/tracking/VERIFIER_CONTRACT.md:39; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/q6_scan.json:162).
Q7 PASS: the scheduled set is exhaustive and the scored agreement population is n=715 (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:18).
Q8 PASS: raw replay gives A0 TP=0, FP=8, C0=0/549, matching the claimed premise (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:6).
NOT VERIFIED PASS: seven explicit limitations are listed (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:45).
DIFF/LOC PASS: 1,620 unique added .jpg paths, no removals/renames and zero touched .py files; touched-Python LOC rail is vacuous.
TEST PASS: `python -m pytest tests/platformkit/test_g373_ball_detector_v2.py -q` -> 20 passed in 0.84s; no touched module, so no additional importer test exists.
REPRODUCED: sheets 1,620/1,620 unique, 304,866,022 bytes, all JPEG 1920x1080, 7 over cap, max 230,512; 0 hash/size/dimension mismatches versus manifest (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv:1).
REPRODUCED: agreement 17.33 vs 18.50 px, n=715, p90=287.09, kappa=0.6642328687; census 1,024/596 (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:5).
REPRODUCED: 283 unique boxes, 27 games, sources 92 sealed/191 extra; claimed headline matches (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/dev_boxes_summary.json:41).
CORRECTION: change only the 21 raw free-text reason findings to neutral spatial wording, regenerate q6_scan.json after removing its old self-report, and amend memo line 43 to report zero.
2026-09-10 | tracking reference | G373 | C0=0/549; reference 17.33<=18.50 px (n=715); development 283/500; Q6 rescan 42 findings | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo line 29 says development labels 260/381/37; reference_v2.csv recomputes 284/383/43. Minimal diff: replace those three counts.
NEW GAP: memo line 39 says g373_rate.py 256 and g373_adjudicate.py 93 LOC; current files are 279 and 91. Minimal diff: replace both counts; all remain <=300.
NEW GAP: contract A1 master rerun is unavailable because master lacks tests/platformkit/test_g373_ball_detector_v2.py; the requested worktree test passed and this was not used to reject.
