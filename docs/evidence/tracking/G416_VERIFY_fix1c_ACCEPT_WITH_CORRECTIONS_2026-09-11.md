VERDICT: ACCEPT WITH CORRECTIONS
Candidate: e522846d1; verified in track-a10.
PASS ACCEPTANCE Projection/receipt mechanics: measured 32/32 controls, 30/30 distinct prescribed-UNKNOWN snapshots, zero foreign-run numerical outputs, and static detection-to-slot-to-row transport (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/construct_cases.csv:1; docs/research/organization-sprint/PROPOSED_g416_court_point.diff:68).
PASS ACCEPTANCE Binding census/compatibility: measured 279/279 distinct checks; original fields/statuses/readers are restored and new writer aliases are additive (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/field_restoration.csv:2; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/reader_manifest.csv:30).
PASS ACCEPTANCE Empirical CLAMP boundary: measured 0/7 independently bound pairs over 5 sections and retained NOT VALIDATED (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:5).
PASS B1: whole denominators are named before outcomes; no post-filter denominator (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:2).
PASS B2: 32 original fields remain UNCHANGED, seven fields are ADDITIVE, two statuses and 28 reader rows are restored, and the proposal is +39/-0 (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/compatibility.csv:9; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/field_restoration.csv:37).
PASS B3: absent or non-box evidence yields UNKNOWN while original coordinates remain unchanged (scripts/platformkit/tracking/g416_contract.py:83).
PASS B4: no claim or retry path is introduced (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:1).
PASS B5: PC-only, EMPTY model set, with production changes retained as an unapplied proposal (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:3).
PASS B6: no module moved; the sole importing test resolves both touched modules (tests/platformkit/test_g416_court_point_proposal.py:18).
PASS B7: independently recomputed 30 unique exact-even sections/ticks and inspected all 30 cards (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/draw.csv:1; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/eye_index.csv:1).
PASS B8: the corner oracle is a separate implementation with no proposal-helper import (scripts/platformkit/tracking/g416_oracle.py:8).
PASS B9: measured 279 unique check identities/37 sections and 32 unique construct tuples (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/binding_deficits.csv:1).
PASS B10: guard constants remain 250 and 350; the proposal changes neither (scripts/platformkit/tracking/g416_contract.py:10).
PASS Q1: seal ad581968ad764fcb4b8b19e18d71ec4b533fdef14b8ebec6b0455416745d68fa recomputes and prereg commit 1a196a410 predates measurement (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:24).
PASS Q2: the mechanical construct is uncharged and makes no K-based trial claim (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:3).
PASS Q3: the fixed NOT VALIDATED boundary and guard bars are unchanged (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:21).
PASS Q4: no OOS score or meta-learner claim is made (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:3).
PASS Q5: no AHEAD claim is made (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:1).
PASS Q6: independent scan of all 23 candidate-touched paths measured indices 0/1/2 = 0; all 26 index-3 matches precede G416 (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/q6_scan.json:617).
PASS Q7: measured all 32 unique 2x2x2x2x2 construct cases; no sampling rail applies (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/construct_cases.csv:1).
PASS Q8: premise remeasured as 279 checks/37 sections and 7 guard rows/5 sections before verdict (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/summary.json:25).
PASS NOT VERIFIED list: CLAMP quality, physical homography, original model identity, and live behavior are named (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:22).
PASS EVIDENCE: both proposal copies are byte-identical at 5,939 bytes; git apply --check returned 0; all memo-named paths exist (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/runtime_receipts/git_apply_check.txt:1).
PASS LOC: g416_finish.py 279; g416_fix1c.py 143; test_g416_court_point_proposal.py 155; all touched Python files are <=300 (scripts/platformkit/tracking/g416_finish.py:279).
TEST: python -m pytest tests/platformkit/test_g416_court_point_proposal.py -q -> 12 passed in 0.74s.
TEST IMPORTERS: git grep found only tests/platformkit/test_g416_court_point_proposal.py; covered by the command above (tests/platformkit/test_g416_court_point_proposal.py:18).
REPRODUCED PREMISE claimed 279/37 and 7/5 = measured 279 unique/37 and 7/5; also measured 58 matrix rows/keys, 479 original rows/478 keys, and 39 emitted files/486 rows/473 keys/13 duplicate keys.
REPRODUCED HEADLINES claimed 32/32, 30/30, 0/7, 118/97 = measured 32/32, 30/30, 0/7 over 5 sections, 118 original rows/97 moving boxes; fixture measured one BOX row and four UNKNOWN route rows.
REPRODUCED RECEIPTS: two runs have identical 19-table digests; file_manifest 66/66 and SHA256SUMS 67/67 validate.
CORRECTION DIFF 1: docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:20 -056ee9d37d72a18ee138f6139c53ef7caed3c21c6f2e2f43d633128346960998 +221cab0763103863ebfabb15b272bc9f62982d4ac2cdb3151abcb8beb7473f5f.
CORRECTION DIFF 2: docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:6 -fixture proves emitted values +fixture models emitted values; proposal transport is statically checked and live behavior remains NOT VERIFIED.
2026-09-11 | tracking geometry | G416 | premise 279/37 and 7/5; controls 32/32; draw 30/30 UNKNOWN; proposal transport static; memo digest corrected | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: q6_scan.json omits candidate-touched findings.md and task_plan.md from its claimed complete path set; the independent 23-path scan is clean except inherited index-3 matches (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/q6_scan.json:2).
NEW GAP: serializer_fixture recreates field mapping independently and its test only searches proposal text; it does not execute extracted proposed writer behavior (scripts/platformkit/tracking/g416_fix1c.py:133; tests/platformkit/test_g416_court_point_proposal.py:133).
NEW GAP: linked-worktree Git metadata is outside this verifier's writable sandbox; targeted git add and the sanctioned lane_commit helper both failed at index.lock, so no verifier commit object was created.
