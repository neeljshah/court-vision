VERDICT: REJECT
Candidate: ebdd44ab3; verification date: 2026-09-07.
FAIL ACCEPT-source/decomposition: specified G273/G280 sources are mandatory, but substitutes/different populations were measured, so the prior gap was not decomposed (G302_spec.md:43,96; g302_amateur_resolution_attribution_2026-09-07.md:10,51).
FAIL ACCEPT-blind-rating: the live in-play sheet was added after unblinding; only the superseded sheet was committed before the map existed (G302_spec.md:62,92-94; g302_amateur_resolution_attribution_2026-09-07.md:67).
PASS ACCEPT-counts/tests/volume: recomputed counts 32/26/2/12, 35/22/6/9, 18/54/0/0; (b)+(c) 28/28/54; detections 9933/9937/17804 over 1152 frames (g302_amateur_resolution_attribution_2026-09-07.md:34-40).
PASS ACCEPT-determinism: retained fix-session CSVs each have 9939 rows, identical bytes, SHA-256 0dfe034e...; cross-session 9933 vs 9939 is disclosed (g302_amateur_resolution_attribution_2026-09-07.md:18-19,56).
PASS ACCEPT-seal/interleave/n/eye: seal 302b69a..., map hash 3f6e3b4c..., 216 unique 512x640 renders, 72 bins/arm, and bins 6/18/30/42/54/66 inspected (g302_amateur_resolution_attribution_2026-09-07.md:15,59; eye_check.csv:2-19).
PASS ACCEPT-must-not-move/evidence: protected routes unchanged, all named evidence exists, and NOT VERIFIED lists required limits (g302_amateur_resolution_attribution_2026-09-07.md:60,65-75).
REPRODUCED PREMISE: artifact joins give G273 PLAYER 43/72 and NOT A PERSON 15/72; G280b 25/72 and 37/72 (g273_detector_precision_blind_sample_artifact/blind_verdicts.csv:1; g280_amateur_footage_trackability_artifact/blind_packet/blind_verdicts.csv:1).
REPRODUCED HEADLINE: PLAYER 0.444444/0.486111/0.250000; terms -0.041667/+0.236111, substitute gap 0.194444, unresolved 0.055556; nominal p 0.616223/0.003309, matching claims (g302_amateur_resolution_attribution_2026-09-07.md:34,47-51).
TEST: `python -B -m pytest scripts/platformkit/tracking/test_g302_amateur_resolution_attribution.py -q -p no:cacheprovider` -> 10 passed.
TEST: `python -B -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed.
PASS LOC/import scan: touched Python files are 300 and 156 lines; sole test importer is the 10-test spec file; unchanged helper is 53 lines (g302_amateur_resolution_attribution.py:300; test_g302_amateur_resolution_attribution.py:156).
PASS B1: all 216 contiguous verdict rows are counted; no outcome exclusion (blind_verdicts_inplay_rerate.csv:2-217; VERIFIER_CONTRACT.md:20).
PASS B2: old `verdict` remains and additions are aliased; default summary reader behavior remains (eye_check.csv:1; g302_amateur_resolution_attribution.py:252,259; VERIFIER_CONTRACT.md:21).
PASS B3: no production gate or absent-evidence fall-through changed (g302_amateur_resolution_attribution.py:252-282; VERIFIER_CONTRACT.md:22).
PASS B4: no claim, retry, ownership, or queue path changed (g302_amateur_resolution_attribution_2026-09-07.md:60; VERIFIER_CONTRACT.md:23).
PASS B5: compute-only pod scratch is declared; deployed tree stayed read-only (g302_amateur_resolution_attribution_2026-09-07.md:63; VERIFIER_CONTRACT.md:24).
PASS B6: no module, import, test, or command was moved or retired (g302_amateur_vs_resolution_attribution_2026-09-07.md:1-24; VERIFIER_CONTRACT.md:25).
PASS B7: 72 equal-width bins/arm and evenly spaced eye rows, not a head slice (g302_amateur_resolution_attribution_2026-09-07.md:59; eye_check.csv:2-19; VERIFIER_CONTRACT.md:26).
PASS B8: direct counts and pooled two-proportion arithmetic use no fitted residual (g302_amateur_resolution_attribution.py:245-249; VERIFIER_CONTRACT.md:27).
PASS B9: 216 unique crop units, 72 per arm, and 1152 source frames/arm are nondegenerate (blind_order_commitment.json:2-22; VERIFIER_CONTRACT.md:28).
PASS B10: no harness threshold, gate value, or no-pass bar moved (g302_amateur_resolution_attribution.py:27-35; VERIFIER_CONTRACT.md:29).
PASS Q1: prereg seal reproduced and predates scoring (g302_amateur_resolution_attribution_2026-09-07.md:15; VERIFIER_CONTRACT.md:34).
PASS Q2: no charged trial or K applies to this attribution row (g302_amateur_resolution_attribution_2026-09-07.md:4; VERIFIER_CONTRACT.md:35).
PASS Q3: the no-pass-bar rule is unchanged (G302_spec.md:100-103; VERIFIER_CONTRACT.md:36).
PASS Q4: no OOS model score or meta-learner is claimed (g302_amateur_resolution_attribution_2026-09-07.md:4; VERIFIER_CONTRACT.md:37).
PASS Q5: no AHEAD status is claimed (g302_amateur_resolution_attribution_2026-09-07.md:4; VERIFIER_CONTRACT.md:38).
PASS Q6: added-line ASCII, restricted-language, and retracted-number scans each returned 0 (VERIFIER_CONTRACT.md:39).
PASS Q7: sampled n=216, 72 per arm (G302_spec.md:105-107; VERIFIER_CONTRACT.md:45).
PASS Q8: premise independently remeasured before judgment (g302_amateur_resolution_attribution_2026-09-07.md:8; VERIFIER_CONTRACT.md:49).
CORRECTION: - substitute clips; + exact G273 and G280 source populations, then rebuild the 216-crop pool.
CORRECTION: - post-unblind live rerate; + category-correct verdict sheet committed alone before any unblinding.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-07 | wnba + amateur basketball | G302 | substitute clips: PLAYER 32/72, 35/72, 18/72; terms -0.041667 and +0.236111; original-source matched-resolution attribution unmeasured | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G302-LEDGER-APPEND - candidate replaces the existing G302 row instead of appending a new line (RESULTS_LEDGER.md:455).
NEW GAP: G302-A1-MASTER - master contains neither G302 harness nor test, so the candidate-only per-file test cannot be rerun there (VERIFIER_CONTRACT.md:10).
