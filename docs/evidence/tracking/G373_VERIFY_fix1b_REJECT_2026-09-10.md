VERDICT: REJECT
Candidate: c868b35bf1328dd2d763aeb7be5f60b93aa329b0.
ACCEPTANCE PASS (phase-scoped): reference usability is 17.33 <= 18.50 px over 715 pairs; 283/500 development boxes is honestly UNMET and no arm was scored (docs/evidence/tracking/specs/G373_spec.md:14; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:21).
B1 PASS: all 1,620 scheduled keys enter agreement/missingness accounting; 1,024 settled and 596 unsettled (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:10).
B2 PASS: the 21 raw changes are note-only; no field, status, or reader contract is renamed or removed (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/q6_redaction_manifest.csv:1).
B3 PASS: 596 unsettled frames remain explicit rather than being dropped (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:10).
B4 PASS: no arm or candidate was scored, so no claimable failure path was added (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B5 PASS: the memo records no deployed-tree write and the candidate touches only local evidence, research scripts, and tests (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
B6 PASS: no module was moved or retired; the new redactor is additive (scripts/platformkit/tracking/g373_q6_redact.py:1).
B7 PASS: the fixed extra sample spans 28 sections with evenly spaced indices, not a head slice (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:15).
B8 PASS: the usability statistic uses two blind ratings, not a self-fit residual (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:19).
B9 PASS: named denominators are 715 paired frames and 1,430 boxes (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:15).
B10 PASS: observed 17.33 is checked against the sealed 18.50 threshold; the candidate changes no bar (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:3).
Q1 PASS: both seals precede first metric commit 1ccdf26eb and the per-file test recomputes them (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:2).
Q2 PASS: no scored comparison or charged trial ran (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q3 PASS: the 18.50 threshold and 30-pair minimum match the sealed rule (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:3).
Q4 PASS: not triggered because no model comparison was scored (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q5 PASS: not triggered because no candidate or AHEAD result exists (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:33).
Q6 FAIL: five reserved-token literals are introduced in code/test artifacts, while q6_scan.json covers only evidence, memo, and G373 ledger rows (scripts/platformkit/tracking/g373_q6_redact.py:12; tests/platformkit/test_g373_ball_detector_v2.py:263; docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/q6_scan.json:9).
Q7 PASS: the enumeration is exhaustive at 1,620 scheduled keys and the measured population is n=715 (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2_summary.json:15).
Q8 PASS: raw replay reproduces premise C0=0 TP / 8 FP over 549, so the 0.05 premise gate does not fire (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:6).
TEST PASS: `python -m pytest tests/platformkit/test_g373_ball_detector_v2.py -q` -> 21 passed in 0.91s.
IMPORTERS PASS: that same test is the only existing test importing either touched module (tests/platformkit/test_g373_ball_detector_v2.py:117; tests/platformkit/test_g373_ball_detector_v2.py:257).
LOC/ADDITIVITY PASS: touched Python LOC are 122, 113, and 274; raw diff preserves every pre-note field across 21 lines in 20 files (scripts/platformkit/tracking/g373_q6_redact.py:122; scripts/platformkit/tracking/g373_q6_scan.py:113).
NOT VERIFIED PASS: seven limitations are explicit (docs/evidence/tracking/g373_ball_detector_v2_2026-09-10.md:48).
REPRODUCED: premise claimed 0 TP / 8 FP / 549, measured 0 / 8 / 549; VISIBLE/ABSENT/UNKNOWN = 285/243/21.
REPRODUCED: headline claimed 17.33 px, n=715, p90=287.09, diameter 37.00, threshold 18.50, kappa 0.664232868695; all measured identically; census 1,024/596 and development 283 boxes/27 games also match.
REPRODUCED: memo LF-normalised digests 12/12; redaction manifest 21 rows/20 files/21 replacements, current digests 21/21, and reverse reconstruction 21/21.
CORRECTION: build the redactor token and test fixtures from character codes, then include both touched Python paths in the automated scan and regenerate q6_scan.json; no metric artifact changes.
2026-09-10 | tracking reference | G373 | premise C0=0/549; reference 17.33<=18.50 px (n=715); development 283/500; candidate text has 5 reserved-token literals | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo line 29 says development labels 260/381/37; reference_v2.csv measures 284/383/43. Minimal diff: replace those three counts.
NEW GAP: memo line 40 reports g373_q6_scan.py 99 and g373_q6_redact.py 105 LOC; measured values are 113 and 122. Minimal diff: replace both counts.
NEW GAP: memo line 43 says raw rater batches keep verbatim text, but this candidate changes 21 note lines. Minimal diff: replace that clause with an explicit redaction statement.
NEW GAP: contract A1 cannot run because master has no tests/platformkit/test_g373_ball_detector_v2.py; this was not used to reject.
