VERDICT: REJECT
ACCEPTANCE FAIL: required n>=60 per section; reproduced n=59/58/60/60/58/59 and source mix 5x1080p+1x720p (specs/G338_spec.md:55; g338_detector_input_decision_2026-09-08.md:17).
B1 PASS: all decoded rows enter summaries and the six excluded indices are named (g338_detector_input_decision.py:95; premise.json:14).
B2 FAIL: `_frame` changed decode failure from an exception to `None`, then the reader drops that frame; no compatibility path or importing test exists (g338_detector_input_arms.py:112,167).
B3 PASS: absent decoded evidence is passed onward as a named omission, not quarantined as bad evidence (g338_detector_input_arms.py:167).
B4 PASS (N/A): this row has no claim queue; failure produces a null recommendation and named failure mode (g338_detector_input_arms.py:250).
B5 PASS: compute ran in pod scratch and the deployed tree was not written (g338_detector_input_decision_2026-09-08.md:33).
B6 PASS: candidate adds/modifies only G338 evidence and its runner; no module was moved or retired (g338_detector_input_arms.py:1).
B7 PASS: every source has 60 salted, stride-spaced sealed indices; no head slice was used (snapshot.json:18).
B8 PASS (N/A): the rule compares direct plausibility summaries and fits no model (g338_detector_input_decision.py:132).
B9 FAIL: wholly_in_frame_share is exactly 1.0 in all 16 nonempty arm-section cells, so one of five decision measures is trivially constant (arms.csv:2).
B10 PASS: 0.95 closeness, four-section, and 0.8 throughput thresholds match the seal (g338_detector_input_decision.py:142; g338_prereg_2026-09-08.md:45).
Q1 PASS: seal c1e93fb53c7957f9f74bce9867f55685080d3f568f05f67ddbca6408c9c87e6c verifies and commit 2883f30d1 predates scoring (g338_prereg_2026-09-08.md:63).
Q2 PASS (N/A): no charged-trial comparison is made (g338_prereg_2026-09-08.md:5).
Q3 FAIL: the sealed resolution/n bars were unmeetable, but the memo reports UNDECIDED instead of CLOSED AT LIMIT (g338_detector_input_decision_2026-09-08.md:1,29).
Q4 PASS (N/A): no OOS score or meta-learner is claimed (g338_prereg_2026-09-08.md:5).
Q5 PASS (N/A): no AHEAD status is claimed (g338_detector_input_decision_2026-09-08.md:1).
Q6 PASS: automated scan of every candidate-added line and evidence artifact found 0 prohibited vocabulary/figure hits (g338_detector_input_decision_2026-09-08.md:52).
Q7 PASS: this is sampled, not a construct, and every arm-section cell has n>=58, above the n>=30 rail (arms.csv:2).
Q8 PASS: premise independently remeasured before verdict as 2536/635=3.993700787402 over 59 unique same-frame keys (premise.json:6).
TEST PASS: `set PYTHONDONTWRITEBYTECODE=1&& python -m pytest tests/platformkit/test_g338_detector_input_decision.py -q -p no:cacheprovider` -> 5 passed in 0.98s (test_g338_detector_input_decision.py:20).
IMPORTER CENSUS PASS: repository search found no test importing touched module g338_detector_input_arms; the sole G338 test imports the unchanged scorer (test_g338_detector_input_decision.py:4).
LOC PASS: touched Python file g338_detector_input_arms.py is 279 lines, <=300 (g338_detector_input_arms.py:279).
EVIDENCE PASS: all six named committed artifacts exist; largest loaded file is frames.csv at 72,226 bytes; all six claimed hashes reproduce (g338_detector_input_decision_2026-09-08.md:49).
NOT VERIFIED PASS: the memo lists deployment identity, proxy, timing, corpus, tiling, and claim limits (g338_detector_input_decision_2026-09-08.md:38).
REPRODUCED: claimed ratio 3.99 vs 3.993700787402; claimed 1416 records vs 1416 unique; claimed qualifiers 0/0/0/0 vs 0/0/0/0 (g338_detector_input_decision_2026-09-08.md:7,27).
REPRODUCED: claimed live-box totals 2543/4227/5651/7681 and ms means 56.9/40.4/48.1/52.2 vs 2543/4227/5651/7681 and 56.919975/40.429870/48.065412/52.175554 (arms.csv:2).
CORRECTION: memo:1 `-VERDICT: UNDECIDED` / `+VERDICT: CLOSED AT LIMIT`; RESULTS_LEDGER.md:587 `-UNDECIDED` / `+CLOSED AT LIMIT`; status-only correction does not cure B2/B9.
CORRECTION: runner:112 `-return None` / `+raise RuntimeError(...)`; B9 needs a newly sealed replacement measure and rerun, so no permitted in-place bar diff exists.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G338 | premise 2536/635=3.993701; 1416/1416 unique records; qualifiers 0/0/0/0; section n 59/58/60/60/58/59; changed decode-failure behavior and a constant decision measure fail B2/B9 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: frames.csv rounds timing to 0.001 ms, so all 24 exact ms_per_frame aggregates differ from arms.csv by up to 0.000095 ms.
NEW GAP: committed evidence omits raw boxes and homographies, so height, court, and persistence numerators cannot be recomputed from the bundle alone.
