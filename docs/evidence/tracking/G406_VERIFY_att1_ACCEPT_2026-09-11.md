VERDICT: ACCEPT
Candidate: 7e90616923f7d31ad8128894a8709ccfaba0d873.
ACCEPTANCE sample/mask PASS - independent recount gives 3,075/19,087, 59/60, 60 distinct exact-even ticks, 0 forbidden admissions; masks unchanged (g406_masked_target_pixel_audit_2026-09-11.md:7-13; G406_spec.md:22).
ACCEPTANCE pixel review PASS - 60/60 blind-first; 803 unique adjudication_ids cover 206 producer rows, 592 comparator boxes, and 5 silence ticks (g406_masked_target_pixel_audit_2026-09-11.md:24-46; G406_spec.md:23).
ACCEPTANCE identity/reproduction PASS - prereg and identity precede load; both saved-output regeneration rounds are identical; no teacher claim (g406_comparator.py:70-73; g406_masked_target_pixel_audit_2026-09-11.md:15-22,50,56; G406_spec.md:24).
A2/A4 PASS - claimed candidate support 34/34, extent-correct 1/206 overall, match n=51 and dy median -58.2 px; reproduced 34/34, 1/206, 51, -58.203 px; 60/60 unique ticks and 803/803 unique adjudication_ids (g406_masked_target_pixel_audit_2026-09-11.md:32-46).
A3 PASS - all 60 cards are retained; verifier inspected exact-even indices 00,06,12,18,24,29 in both kinds (g406_masked_target_pixel_audit_2026-09-11.md:28-50).
A5/A7 PASS - all 19 named evidence entries exist, all 102 SHA256SUMS entries match, and the only test reader importing a touched module is the focused file (test_g406_target_pixel_audit.py:96-102).
LOC PASS - aggregate 203, comparator 110, measure 230, render 102, review 205, seal 107, test 151; all <=300.
ADDITIVITY PASS - candidate adds schemas/modules and appends the ledger; no field, status, module, or reader behavior is renamed or removed (g406_measure.py:137-150; g406_review.py:173-175).
MEMO PASS - NOT VERIFIED names teacher independence and training suitability (g406_masked_target_pixel_audit_2026-09-11.md:54-60).
TEST PASS - `python -m pytest tests/platformkit/test_g406_target_pixel_audit.py -q` -> 15 passed in 0.80s; no other existing test imports a touched module.
B1 PASS - every selected row remains in the support/error/UNKNOWN denominators (test_g406_target_pixel_audit.py:133-141).
B2 PASS - additive schemas and reader survey complete (g406_measure.py:137-150; test_g406_target_pixel_audit.py:96-151).
B3 PASS - absent suppression evidence yields declared PARTIAL, not case loss (g406_masked_target_pixel_audit_2026-09-11.md:1,22,58).
B4 PASS - diagnostic export has zero training callers and no accepted-reference promotion (g406_masked_target_pixel_audit_2026-09-11.md:5,57).
B5 PASS - the deployed route was read-only and computation used isolated scratch (g406_masked_target_pixel_audit_2026-09-11.md:17-22).
B6 PASS - no module was moved or retired; all touched Python modules are new (g406_comparator.py:1-6; g406_seal.py:1-14).
B7 PASS - selection is exact-even over the full bounded universes and every card is retained (g406_masked_target_pixel_audit_2026-09-11.md:9,50).
B8 PASS - same-detector comparison is explicitly not independent evidence (g406_masked_target_pixel_audit_2026-09-11.md:56).
B9 PASS - distinct tick, row, instance, and full-window denominators are separately named (g406_masked_target_pixel_audit_2026-09-11.md:28-46).
B10 PASS - frozen 0.50 association and 30-per-kind sampling match the spec (g406_audit.py:29-31; G406_spec.md:22-24).
Q1 PASS - prereg seal 88449bac72ab8bbe972faf01944e3d53c60c5a95342205dc32fddf1099d7aba5 independently hashes exactly and predates measurement (prereg.md:24; g406_masked_target_pixel_audit_2026-09-11.md:13).
Q2 PASS (not applicable) - this diagnostic is not a charged trial and reports no K (g406_masked_target_pixel_audit_2026-09-11.md:52).
Q3 PASS - no bar or threshold moved (g406_audit.py:29-31; G406_spec.md:22-24).
Q4 PASS (not applicable) - no OOS score or meta-model is claimed (g406_masked_target_pixel_audit_2026-09-11.md:5,52).
Q5 PASS (not applicable) - no AHEAD result is claimed (g406_masked_target_pixel_audit_2026-09-11.md:5,52).
Q6 PASS - independent full-pattern field-aware scan of 43 text artifacts found 0 hits (g406_masked_target_pixel_audit_2026-09-11.md:50).
Q7 PASS - sampled n=60 with 30 exact-even ticks per kind (g406_masked_target_pixel_audit_2026-09-11.md:28-40).
Q8 PASS - premise was independently remeasured from the landed G402 rows and full tick receipts (g406_measure.py:50-68; g406_masked_target_pixel_audit_2026-09-11.md:7-9).
CORRECTIONS: none.
RESULTS_LEDGER_SYSTEM: 2026-09-11 | tracking | G406 | premise 3,075/19,087 and 59/60 reproduced; 60 exact-even native ticks, 803 adjudications, candidate support 34/34, matched-pair vertical-center median -58.203 px; diagnostic only, no teacher or training promotion | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: The automated field scanner enumerates only part of the Q6 pattern set, so future artifacts could pass it incorrectly; extend `_terms()` and its positive fixtures to the complete contract set (g406_audit.py:65-67; test_g406_target_pixel_audit.py:68-75).
NEW GAP: The verifier commit is blocked by linked-worktree Git metadata outside the writable root; direct targeted Git, `lane_commit.py`, and alternate-index staging all failed before commit creation.
