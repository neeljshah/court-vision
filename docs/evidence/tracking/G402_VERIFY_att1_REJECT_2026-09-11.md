VERDICT: REJECT
Candidate: b749346af; verifier: codex-sol; scope: G402 acceptance plus B1-B10 and Q1-Q8.
ACCEPTANCE replay/accounting FAIL: the source-frame cap is detector-dependent at scripts/run_clip.py:191-193; g402_run.py:100-102 therefore overran 15/59 windows, and g402_tables.py:123-124 expands rather than seals the denominator.
ACCEPTANCE mask/coverage FAIL: 2,347/21,434 rows and 317 admitted rows are outside the sealed windows; coverage_per_section.csv:1 has only 59 data rows, while g402_tables.py:247-248 omits the failed planned window instead of retaining UNKNOWN.
ACCEPTANCE eye check FAIL: 3/60 cards are outside the sealed decision set at eye_index.csv:3,54,57; six evenly spaced cards were visually checked and rendered legibly.
ACCEPTANCE traceability FAIL: route_hashes.json:27 records no model weights and launch_receipts.csv:1 has an empty weight_digest for 60/60 launches; this evidence is NOT VALIDATED.
B1 PASS: both traversal and sealed denominators and the one exclusion are named at g402_mixed_provenance_target_mask_2026-09-11.md:21,37, although the claimed coverage fails the acceptance scope above.
B2 PASS: touched Python is additive (all seven diffs have zero deleted lines); no field, status, alias, or existing reader behavior was removed; g402_tables.py:23-36.
B3 PASS: the incomplete launch remains explicit rather than quarantined; launch_receipts.csv:6 and summary.json:10-12.
B4 PASS: all launched section IDs enter the done set, including failure status; g402_run.py:145-151.
B5 PASS: route identity distinguishes read-only deploy and scratch copies; route_hashes.json:2,15-26 and summary.json:106-114.
B6 PASS: no rename or retirement occurred; the only importing test is test_g402_mixed_provenance_mask.py:70-74.
B7 PASS: audit selection is even, not a head slice; g402_audit.py:37-42,88-96. Its decision-set scope separately fails acceptance.
B8 PASS: this is a diagnostic with no fit or residual claim; summary.json:2.
B9 PASS: remeasurement found 30 unique sections per kind and exact sealed even draws from populations 40 and 79; supply.json:2-25.
B10 PASS: no existing harness threshold changed; the new fixed bars remain in prereg.md:12-18.
Q1 PASS: prereg.md:23 seal recomputes from 3,104 LF bytes to the claimed digest; standalone commit 6120fc58f precedes measurement.
Q2 PASS (not applicable): no charged trial or trial counter is used; summary.json:2.
Q3 FAIL: the effective source-frame limit moved because --frames is detector-dependent; exported data exceed the sealed 300/600-frame windows despite prereg.md:12.
Q4 PASS (not applicable): no OOS score or meta-learner is claimed; summary.json:2.
Q5 PASS (not applicable): no comparative status is claimed; g402_mixed_provenance_target_mask_2026-09-11.md:55.
Q6 PASS: q6_scan.txt:400-410 classifies all matches as opaque quoted data or code syntax and reports zero non-opaque hits; memo and proposed ledger text are clean.
Q7 PASS: draw and eye sample counts are 30 per kind; sub-30 route results are explicitly descriptive at g402_mixed_provenance_target_mask_2026-09-11.md:53-54.
Q8 PASS: premise remeasurement is whole-set and falsifies stale supply: 40 eligible 1080p30 and 79 eligible 720p60; supply.json:2-25.
PREMISE REPRODUCED: G380 CLAMP 85,333 and SUBPIXEL 2,749 give 0.968790; transport 30/30; 0 identical among 30 populated identity rows; summary.json:73-84.
CLAIM REPRODUCED: raw receipts give 59/60 complete, receipt/trace 59/59, and the export gives 3,392/21,434 with 0 forbidden admissions; summary.json:13-70.
SEALED RECOMPUTE: 3,075/19,087 rows survive; 2,347 rows are out of scope. Candidate-frame coverage is 1,019/9,000 and 1,014/18,000, not the memo values at lines 30-32.
EVIDENCE PASS: all 22 named destinations exist; SHA256SUMS verifies 445/445 with no stale/unlisted file; repeats.json:72-78 records two successful fresh-process reproductions.
LOC PASS: g402_audit 157, census 177, repeat 121, retain 107, run 166, tables 280, test 172; all <=300.
TEST PASS: `python -m pytest tests/platformkit/test_g402_mixed_provenance_mask.py -q` -> 15 passed in 0.75s; it is the spec test and the only existing test importing a touched module.
NOT VERIFIED PASS: the memo has an explicit limits list at g402_mixed_provenance_target_mask_2026-09-11.md:51-55.
CORRECTION: minimally bound rows/ticks/cards to [start_frame,start_frame+frames), retain failed launches as UNKNOWN coverage rows, regenerate tables/cards, and replace memo/ledger headline with the sealed recomputation.
CORRECTION: identify every exercised model by path, bytes, and SHA-256 in route_hashes.json and populate one aggregate launch digest before any rerun.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G402 | sealed-window scope failed: 2,347/21,434 rows and 3/60 cards outside the preregistered windows; sealed-only mask 3,075/19,087; model identity absent 0/60 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: scripts/run_clip.py:191-193 exposes no source-frame-exact cap for a nonzero start; add a scratch-only bounded-window route before retrying G402.
NEW GAP: g402_run.py:62-63 records only sizes under one directory and misses all exercised model identities in this run.
NEW GAP: the required targeted git command and sanctioned lane_commit.py both failed on the linked-worktree index.lock outside the writable sandbox; this sole report needs the external path-specific committer.
