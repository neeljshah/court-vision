VERDICT: REJECT
Candidate: deb020e90712af9343a89857391e854467d0b550; verified in track-a10.
FAIL ACCEPTANCE Projection/receipt mechanics: intermediate normalization/int changes producer semantics; proposal (100,200) vs producer (109,209) (scripts/platformkit/tracking/g416_contract.py:77; src/tracking/advanced_tracker.py:1411).
FAIL ACCEPTANCE Projection receipt: the delivered six-line comment file is not a valid patch and contains no exercised expression (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/PROPOSED_g416_court_point.diff:1).
FAIL ACCEPTANCE eye check: old court-map coordinates are drawn directly as native image pixels, leaving multiple points off-frame (scripts/platformkit/tracking/g416_finish.py:60; scripts/platformkit/tracking/g416_finish.py:85).
FAIL ACCEPTANCE Binding census: memo claims 279 deficits, but binding_deficits.csv has only the 30 sampled rows (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:7; scripts/platformkit/tracking/g416_finish.py:94).
PASS ACCEPTANCE Empirical CLAMP: 0/7 bound guard rows over 5 sections remains descriptive and NOT VALIDATED (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:7).
PASS B1: UNKNOWN and denominator populations are named; no post-filter metric (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:2).
PASS B2: 118 retained rows and 32 parent fields reproduce exactly; proposal remains unapplied (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/compatibility.csv:2).
PASS B3: absent receipts yield UNKNOWN while original fields survive additive_row (scripts/platformkit/tracking/g416_contract.py:103; scripts/platformkit/tracking/g416_contract.py:124).
PASS B4: no claimable queue or retry path is introduced (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:30).
PASS B5: PC-only, empty model set, and no gated source change (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/summary.json:10).
PASS B6: no module moved or retired; both new imports resolve (scripts/platformkit/tracking/g416_finish.py:7).
PASS B7: independently reproduced exact-even 30-of-37 draw (scripts/platformkit/tracking/g416_finish.py:37).
FAIL B8: independent_corner_oracle reuses native_then_cropped_foot and project_m_then_m1 from the proposal (scripts/platformkit/tracking/g416_contract.py:90; scripts/platformkit/tracking/g416_contract.py:94).
PASS B9: 32 unique constructs, 30 unique sections, 279 checks/37 sections (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/denominator_table.csv:2).
PASS B10: guard constants remain 250/350 and match the sealed bar (scripts/platformkit/tracking/g416_contract.py:10; docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:17).
PASS Q1: seal ad581968ad764fcb4b8b19e18d71ec4b533fdef14b8ebec6b0455416745d68fa validates and predates measurement (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:24).
PASS Q2: this is an uncharged mechanical construct; no K-based trial is claimed (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:21).
PASS Q3: 32 constructs, 30 draw sections, and fixed NOT VALIDATED boundary match the seal (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/prereg.md:19).
PASS Q4: no OOS score or meta-learner claim is made (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:29).
PASS Q5: no AHEAD claim is made; empirical comparison is NOT VALIDATED (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:1).
PASS Q6: candidate memo and added ledger row use calibration-only language (docs/evidence/tracking/RESULTS_LEDGER.md:791).
FAIL Q7: the clipped construct uses stored x1=-5, then adds PAD=15 to +10, so it is not clipped; the claimed enumeration is not exhaustive (scripts/platformkit/tracking/g416_finish.py:71; scripts/platformkit/tracking/g416_contract.py:43).
PASS Q8: independently remeasured 279 checks/37 sections and 7 guard rows/5 sections (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:3).
PASS NOT VERIFIED list: CLAMP quality, physical homography, original model identity, live behavior (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:29).
TEST: python -m pytest tests/platformkit/test_g416_court_point_proposal.py -q -> 10 passed in 1.10s.
TEST IMPORTERS: no existing test imports scripts.platformkit.tracking.g416_finish; no additional per-file command.
PASS LOC: scripts/platformkit/tracking/g416_finish.py 111; tests/platformkit/test_g416_court_point_proposal.py 113; both <=300.
REPRODUCED: claimed premise 279/37 and 7/5 = measured 279/37 and 7/5; claimed retention 118/97 = measured 118/97.
REPRODUCED: claimed tables 32/32 and 30/30 = row counts 32/32 and 30/30; claimed 279 deficits = measured artifact 30/279.
CORRECTION DIFF 1: - normalize/int after M; + compute M1 @ (M @ kpt), normalize once, int32 once.
CORRECTION DIFF 2: - shared oracle helpers and x1=-5 clip fixture; + separate oracle and a stored coordinate below -15.
CORRECTION DIFF 3: - 30 sampled deficit rows and native-image court points; + 279 per-check deficits and court-map renders.
CORRECTION DIFF 4: - six-line comment receipt; + valid unapplied patch hunk invoking the tested expression, committed at both named paths.
2026-09-11 | tracking geometry | G416 | premise 279/37 and 7/5 reproduced; 32/32 and 30/30 tables counted, producer counterexample (100,200) vs (109,209), deficits 30/279 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Contract A1 cannot run pre-landing in master c8bcd5d47 because the G416 test path is absent; candidate-worktree test passed.
NEW GAP: repeats.json is inherited G410 content rather than the G416 two-run receipt; run1.json and run2.json exist separately (docs/evidence/tracking/g416_court_point_proposal_2026-09-12/repeats.json:1).
NEW GAP: the named docs/research proposal exists locally but is ignored and absent from candidate deb020e90 (docs/evidence/tracking/g416_court_point_proposal_2026-09-12.md:30).
NEW GAP: targeted git add and the sanctioned lane_commit helper both failed on the external index.lock ACL; no verifier commit object was created.
