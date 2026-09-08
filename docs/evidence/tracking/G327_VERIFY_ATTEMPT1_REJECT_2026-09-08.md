VERDICT: REJECT
Candidate: 668b9929b; full 8-file diff reviewed; evidence memo is 56 lines.
ACCEPTANCE FAIL: the immutable G324 games/lists/anchors in G327_spec.md:192-197 were replaced by a runtime selection rule (g327_prereg_2026-09-08c.md:47-80) and different realised clips (g327_detector_batch_stability_2026-09-08.md:15-20).
ACCEPTANCE FAIL: the memo lacks the required per-game/per-arm agreement and bit-identity table and the verbatim process/disk output required by G327_spec.md:206-211; memo:23-30 is aggregate only and memo:41 is a summary.
ACCEPTANCE FAIL: frame 2204 is absent from every raw CSV arm; its zero-box identity is restored only from summary frame_indices (g327_summary.json:137; g327_detector_batch_stability.py:217), contrary to CSV-only reconstruction in G327_spec.md:199-203.
ACCEPTANCE FAIL: no nmsord-labelled raw rows exist although raw CSVs for EVERY arm are required at G327_spec.md:175 and :211; nmsord is derived from batch8 in g327_detector_batch_stability.py:222-224.
B1 PASS: sealed verdict uses all 120 frames; the post-hoc 119-frame cut is separate (g327_score.json:1847-1883).
B2 PASS: candidate is additive evidence plus one ledger append; no field, status, or reader behaviour is renamed or removed (RESULTS_LEDGER.md:513).
B3 PASS: no production gate or absent-evidence quarantine is introduced (memo:3,41).
B4 PASS: no claim/retry path is introduced (memo:3).
B5 PASS: pod activity is reported scratch-only with deployed hashes unchanged (memo:41).
B6 PASS: no module is moved or retired; the only importer found is test_g327_batch_stability.py:10-13.
B7 PASS: each realised clip uses 40 indices spanning 0..anchor (memo:19).
B8 PASS: no fit or residual metric is used (memo:3,37).
B9 PASS: the scored denominator is 120 and includes the one empty frame (memo:21; g327_score.json:1847-1883).
B10 PASS: 110/120 and 120/120 remain unchanged (memo:5; G327_spec.md:181-183).
Q1 PASS: scored prereg seal recomputed as 6548ebe7d340cb94c021ab363d574438f976628ab5d52ba7c7ebceac6f130534 (g327_prereg_2026-09-08c.md:186-188), committed before scoring.
Q2 PASS: not applicable; this screening row has no charged trial or K (G327_spec.md:181-186).
Q3 PASS: verdict bars and IoU 0.5 are unchanged (memo:5,21; G327_spec.md:181-183).
Q4 PASS: not applicable; no OOS predictive metric is scored (memo:3).
Q5 PASS: not applicable; no AHEAD claim is made (memo:3).
Q6 PASS: automated vocabulary scan of candidate prose and ledger addition is clean (memo:1-56; RESULTS_LEDGER.md:513).
Q7 PASS: the realised construct exhaustively enumerates 3 x 40 = 120 frames (g327_summary.json:119-243,408-532,697-821).
Q8 PASS: premise independently confirmed: 6dc55b929 is not on master; G324 carries Y true/310.5, true/861.0, false/null and R true/0.0 x3, while measure discards batch rows (g324_arms.py:63-72).
TEST PASS: python -m pytest tests/platformkit/test_g327_batch_stability.py -q --confcutdir=tests/platformkit -> 10 passed in 0.80s.
TEST PASS: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed in 1.13s.
LOC PASS: g327_arms.py 181, g327_detector_batch_stability.py 282, g327_sources.py 139; each <= 300. Memo claim 181/139/267 at memo:43 is stale.
REPRODUCED: NOT PINNED; repeat 120/120, batch8 3/120, pad 3/120, fp32 1/120, nmsord 3/120; claimed values match.
REPRODUCED: batch8 1243 greedy matches, coordinate-exact 983/1243 = 79.08 pct, p99 1.500 px, max 78.750 px; full sealed records exact 628/1243 = 50.52 pct.
CORRECTION: memo:37 and RESULTS_LEDGER.md:513 minimal diff: "bit-exact" -> "coordinate-exact"; full bit-identity includes score/class (g327_prereg_2026-09-08c.md:133-136).
CORRECTION: memo:43 minimal diff: "181 / 139 / 267" -> "181 / 139 / 282".
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G327 | inherited premise 310.5/861.0/null confirmed but unrecomputable; alternate-source recount NOT PINNED (3/120,1/120,3/120) and DETERMINISTIC 120/120; spec construct and memo/raw durability fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the claimed 119-to-85 live-queue change and two attempt-2 deletions lack a committed raw census/log artifact (memo:17).
NEW GAP: memo names G324_VERIFY_2026-09-08.md at :8, but that path is absent from this candidate tree; it is only addressable through the cited unmerged commit.
