VERDICT: REJECT
Candidate: fd1871999d2d8b78fb19052211f988a0b1696fce; verifier: codex-sol; scope: G402 acceptance plus B1-B10 and Q1-Q8.
ACCEPTANCE replay/accounting FAIL: committed g402_tables.py:119-124 keeps overrun ticks and :247-248 drops the failed window; the candidate-only test fails at test_g402_mixed_provenance_mask.py:150.
ACCEPTANCE mask/coverage PASS: independent scan finds 3,075/19,087 admitted sealed rows, 0 forbidden admissions, 0 out-of-window rows, and 60 coverage rows with one UNKNOWN; target_mask.csv:1-19088; coverage_per_section.csv:1-61.
ACCEPTANCE eye check FAIL: the exact sealed even draw disagrees on 26/30 cards in each kind; all 207 audit boxes are (0,0,0,0), so emitted boxes and matched detections are not shown; g402_audit.py:87-90,111-120,150-156; target_mask.csv:1.
ACCEPTANCE traceability/reproduction FAIL: repeats.json:73 claims a mode absent from committed g402_repeat.py:49-55,108-110; committed code cannot regenerate the delivered tables/cards, despite 448/448 valid evidence digests.
B1 PASS: the excluded set is named as 2,347 rows, including 317 formerly admitted rows; g402_mixed_provenance_target_mask_2026-09-11.md:5,14.
B2 PASS: changed CSV schemas only add fields; no field or status was renamed/removed, and owned readers name the additions; g402_audit.py:25-33; test_g402_mixed_provenance_mask.py:175-195.
B3 FAIL: the committed producer skips every non-COMPLETE launch instead of carrying missing evidence through; g402_tables.py:244-258. The delivered UNKNOWN row was produced by absent code.
B4 PASS: the sole failure remains INCOMPLETE and is not retried or replaced; launch_receipts.csv:6; g402_mixed_provenance_target_mask_2026-09-11.md:14.
B5 PASS: the memo records an unchanged deploy tree and no deployment; g402_mixed_provenance_target_mask_2026-09-11.md:8,41.
B6 PASS: no module was moved or retired; touched Python remains at g402_audit.py:1-188 and test_g402_mixed_provenance_mask.py:1-195.
B7 PASS: this is not a head slice; the code constructs a full sealed pool before selection at g402_audit.py:98-108. Exact-even failure is reported under acceptance.
B8 PASS: this is a diagnostic with no fitted residual or quality comparison; summary.json:2.
B9 PASS: the draw has 60 unique sections, 30 per kind, from populations 40 and 79; draw.csv:1-61; supply.json:2-25.
B10 PASS: preregistered bars remain 30/kind, 60 planned, exact agreement, and zero forbidden admissions; prereg.md:12-18.
Q1 PASS: LF-byte seal recomputes to 0bfd1363cc6df3796e11894c7973062c2078ee9aa2c0951961b114d238cd4955 and commit 6120fc58f is an ancestor; prereg.md:1-23.
Q2 PASS (not applicable): no charged trial or trial counter is used; summary.json:2.
Q3 PASS: the source-frame and mask bars match the spec; prereg.md:12-18.
Q4 PASS (not applicable): no OOS score or meta-learner is claimed; summary.json:2.
Q5 PASS (not applicable): no comparative status is claimed; g402_mixed_provenance_target_mask_2026-09-11.md:39-41.
Q6 PASS: the committed scan reports 0 non-opaque hits; q6_scan.txt:394.
Q7 PASS: both sampled sets contain 30 unique cards; eye_index.csv:1-61. Their spacing separately fails acceptance.
Q8 PASS: whole-set remeasurement gives 40 eligible 1080p30 sections/14 games and 79 eligible 720p60 sections/16 games, falsifying the stale supply premise; census.csv:1-156.
PREMISE REPRODUCED: G380 receipts sum to CLAMP 85,333 and SUBPIXEL 2,749, fraction 0.9687904453; transport 30/30; identity 0/30; g380 receipts.csv:1-36, receipts_trace_a3.csv:1-31, identity.csv:1-36.
HEADLINE REPRODUCED: 1080p30 1,565/9,146 rows and 1,019/9,000 candidate frames; 720p60 1,510/9,941 and 1,014/18,000; receipt equality 29/29 and 30/30; summary_tables.json:2-65.
EVIDENCE PASS: all 21 named destinations exist; source receipts are 60/60 byte/hash equal; SHA256SUMS verifies 448/448 with no stale or unlisted file; source_receipts.csv:1-61; SHA256SUMS:1-451.
LOC PASS: g402_audit.py 188; test_g402_mixed_provenance_mask.py 195; both <=300.
IMPORT TEST SURVEY PASS: no existing test imports the only touched module, g402_audit.py; the spec test remains mandatory; test_g402_mixed_provenance_mask.py:1-195.
TEST FAIL (fd1871999 snapshot): `python -m pytest tests/platformkit/test_g402_mixed_provenance_mask.py -q` -> 15 passed, 1 failed in 1.01s.
TEST PASS (dirty worktree only): `python -m pytest tests/platformkit/test_g402_mixed_provenance_mask.py -q` -> 16 passed in 0.98s; uncommitted g402_tables.py/g402_repeat.py changes mask the candidate failure.
NOT VERIFIED FAIL: the memo has `## Limits`, not an explicit NOT VERIFIED list; g402_mixed_provenance_target_mask_2026-09-11.md:37-41.
CORRECTION: commit the current sealed-window and UNKNOWN-retention changes in g402_tables.py plus the matching --sealed-fix reproduction path in g402_repeat.py, then regenerate evidence from that commit.
CORRECTION: in g402_audit.py:111-119 reuse a card only when its (section_id,frame) equals the newly selected pair; add bbox fields to the mask join and rerender all 60 exact-even cards.
CORRECTION: rename the memo heading at line 37 to `## NOT VERIFIED / limits` and make the candidate test green without relying on worktree-only files.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G402 | artifacts reproduce 3,075/19,087 sealed rows with 0 forbidden admissions, but candidate test is 15/16, exact-even cards are 8/60, and 207/207 audit boxes are degenerate | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the spec test does not assert exact eye-sample identities or nondegenerate audit boxes, allowing both acceptance regressions to pass artifact-only checks.
NEW GAP: the linked-worktree index is outside the writable sandbox; targeted git add failed at index.lock, and the available lane_commit helper would sweep unrelated dirty files, so no compliant verifier commit can be created here.
