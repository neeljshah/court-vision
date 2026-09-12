VERDICT: REJECT
Candidate: 3f0ed7afe13fbe8eeca1ea40cbba801510d25275; verified in track-a10.
FAIL ACCEPTANCE Projection/receipt mechanics: 32/32 controls and 30/30 UNKNOWN snapshots reproduce, but the patch writes constant PROPOSED receipts only into an ephemeral detection dict; `_activate_slot` propagates only bbox/homo, so no additive emitted row or safe UNKNOWN route exists (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/PROPOSED_g416_court_point.diff:8; src/tracking/advanced_tracker.py:626).
FAIL ACCEPTANCE Binding census/compatibility: 279/279 checks are accounted, but the fix removes prior fields, status values, and reader rows instead of preserving them additively (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/parent_schema.json:2; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/reader_manifest.csv:2).
PASS ACCEPTANCE Empirical CLAMP boundary: measured 0/7 independently bound pairs and kept NOT VALIDATED (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:6).
PASS B1: whole populations and UNKNOWN outcomes are named; no post-filter denominator (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:2).
FAIL B2: `g410_per_row`, `draw_kind`, `route`, `window`, summary/repeat keys, two status values, and 28 reader rows were removed without aliases (scripts/platformkit/tracking/g416_finish.py:223; scripts/platformkit/tracking/g416_finish.py:225).
PASS B3: absent receipts return UNKNOWN and `additive_row` retains originals (scripts/platformkit/tracking/g416_contract.py:82; scripts/platformkit/tracking/g416_contract.py:107).
PASS B4: no claim, queue, or retry path was introduced (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:11).
PASS B5: PC-only EMPTY model set; production source remains unchanged and proposal is unapplied (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:3).
PASS B6: no module moved; the sole importer test resolves all three touched modules (tests/platformkit/test_g416_court_point_proposal.py:14).
PASS B7: independently recomputed 30 unique exact-even indices/ticks; all 30 cards inspected (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/draw.csv:1; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/eye_index.csv:1).
PASS B8: oracle is a separate explicit implementation with no proposal-module import (scripts/platformkit/tracking/g416_oracle.py:8).
PASS B9: 279 unique check keys/37 sections and 32 unique constructs/30 unique draw sections (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/binding_deficits.csv:1).
PASS B10: guard constants remain 250/350 (scripts/platformkit/tracking/g416_contract.py:10).
PASS Q1: seal ad581968ad764fcb4b8b19e18d71ec4b533fdef14b8ebec6b0455416745d68fa recomputes and commit 1a196a410 predates measurement (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:24).
PASS Q2: exhaustive mechanical controls are uncharged; no K-based trial is claimed (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:3).
PASS Q3: fixed NOT VALIDATED boundary and guard bars are unchanged (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:21).
PASS Q4: no OOS score or meta-learner claim (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:21).
PASS Q5: no AHEAD claim (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:1).
PASS Q6: the new G416 memo and added results row use calibration-only language (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:1; docs/evidence/tracking/RESULTS_LEDGER.md:793).
PASS Q7: independently enumerated all 32 unique 2x2x2x2x2 controls, including two genuinely clipped numerical cases (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/construct_cases.csv:1).
PASS Q8: premise independently remeasured before verdict as 279 checks/37 sections and 7 guard rows/5 sections (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/summary.json:16).
PASS NOT VERIFIED list: four required exclusions are present (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:26).
TEST: python -m pytest tests/platformkit/test_g416_court_point_proposal.py -q -> 10 passed in 0.78s.
TEST IMPORTERS: only tests/platformkit/test_g416_court_point_proposal.py imports any touched module; covered by the command above.
PASS LOC: g416_contract.py 116; g416_finish.py 280; g416_oracle.py 37; test_g416_court_point_proposal.py 125; all <=300.
REPRODUCED: claimed premise 279/37 and 7/5 = measured 279/37 and 7/5; deficits 279 distinct keys, all missing call identity.
REPRODUCED: claimed controls/draw/pairs 32/32, 30/30, 0/7 = measured 32/32, 30/30, 0/7; bound stored-point comparison claimed 0/0 = measured 0/0.
REPRODUCED: original retention measured 118 rows/97 moving boxes; two-run digests identical; manifest 56/56 and SHA list 57/57 valid.
CORRECTION DIFF 1: - append shadow fields only to detections with constant receipts; + carry the tested result through slot/output serialization with concrete identities and UNKNOWN for unavailable/invalid routes.
CORRECTION DIFF 2: - remove prior artifact fields/statuses/readers; + restore every prior field, status value, and reader row, then append new fields with aliases.
2026-09-11 | tracking geometry | G416 | premise 279/37 and 7/5; controls 32/32; draw 30/30 UNKNOWN; compatibility removed prior schema/status/reader entries | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json omits touched code/tests and reports 26 unclassified pattern-3 hits for RESULTS_LEDGER.md (scripts/platformkit/tracking/g416_finish.py:244; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/q6_scan.json:13).
NEW GAP: candidate rewrites RESULTS_LEDGER.md with CRLF throughout, producing 1,582 diff-check findings; restore LF without changing prior rows (docs/evidence/tracking/RESULTS_LEDGER.md:1).
NEW GAP: the memo-named docs/research proposal exists locally but is ignored and absent from candidate 3f0ed7afe (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:11).
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; targeted git add and the sanctioned path-filtered lane_commit.py both failed at index.lock, so no verifier commit object was created.
