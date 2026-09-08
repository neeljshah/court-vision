[RECOVERED 2026-09-08 from the local verifier run log C:/Users/neelj/AppData/Local/Temp/cx_verify_g327.log (fix-2b run, EXIT:0 gap=verify_G327 at 2026-09-08T05:05:53-05:00); the run reported blob 3f6cda2ffd4c40964f27e492f593a4a580dbb3a1 and the reconstructed body below hashes to exactly that; the working file was overwritten by the later fix-2c verify run.]
VERDICT: REJECT
Candidate: 7a3feeae42afbc0c15cb2aa9a2857ecc9dcf4db9; full 5-file diff reviewed; evidence memo is 58 lines.
ACCEPTANCE FAIL: the amendment forbids paths absent from the candidate tree, but the memo cites an external local verifier transcript while claiming no absent path is cited (G327_spec.md:250-255; g327_detector_batch_stability_attempt2_2026-09-08.md:49).
ACCEPTANCE PASS: premise, per-game/per-arm CSV arithmetic, tensor metadata, emission order, screening statement, sources, probes, route hashes, and all seven raw arm CSVs are present (g327a2_table.md:7-45; g327a2_arms.csv:1-22; memo:1-33,47-57).
ACCEPTANCE PASS: the 58-line memo has a NOT VERIFIED list (g327_detector_batch_stability_attempt2_2026-09-08.md:35-45).
B1 PASS: all 120 unique frames are scored in every arm; no scored row is excluded (g327a2_report.json:5,377-414).
B2 PASS: nine legacy fields, reader/writer aliases, both rows_for call forms, and valid legacy behavior remain additive; all readers were checked (g327_arms.py:27-34,198-293; test_g327_batch_stability.py:139-194).
B3 PASS: no production gate or absent-evidence quarantine is introduced (g327_detector_batch_stability_attempt2_2026-09-08.md:1-3,57).
B4 PASS: no claim or retry path is introduced (g327_detector_batch_stability_attempt2_2026-09-08.md:1-3,57).
B5 PASS: compute is scratch-only and gated before/after hashes match (g327a2_summary.json:22-37,810-815).
B6 PASS: no module is moved or retired; the only test importer is the G327 spec test (g327_report.py:24,144; test_g327_batch_stability.py:12-15).
B7 PASS: each 40-frame list spans zero through its anchor; no head slice is used (g327_detector_batch_stability_attempt2_2026-09-08.md:11).
B8 PASS: no fit or residual metric is used (g327_report.py:52-82).
B9 PASS: denominator is 120 unique frames per arm, including explicit zero-box rows; realised zero count is zero (g327a2_table.md:39-45).
B10 PASS: IoU 0.5, batch sizes 2/8, route 0.22, and bars 110/120 and 120/120 are unchanged (g327_prereg_2026-09-08d.md:228-265).
Q1 PASS: seal recomputed fb668830470aff9abdff6b580771db97fe58c7ce4ab04f3cb61fc551fed2cb13; commit 541f2f331 predates scoring (g327_prereg_2026-09-08d.md:300-305; memo:53).
Q2 PASS: not applicable; no charged trial or K exists (G327_spec.md:183-189).
Q3 PASS: sealed verdict bars are unchanged (g327_prereg_2026-09-08d.md:257-265).
Q4 PASS: not applicable; no OOS predictive metric is scored (g327_detector_batch_stability_attempt2_2026-09-08.md:1-3).
Q5 PASS: not applicable; no AHEAD claim is made (g327_detector_batch_stability_attempt2_2026-09-08.md:1-3).
Q6 PASS: automated scan of candidate additions is clean (g327_detector_batch_stability_attempt2_2026-09-08.md:58).
Q7 PASS: exhaustive construct is 3 games x 40 frames x 7 arms = 840 arm-frames (g327a2_summary.json:50-70; g327a2_arms.csv:2-22).
Q8 PASS: premise remeasured as Y true/310.5, true/861.0, false/null and R true/0.0 x3; batch rows remain unavailable (g324_summary.json:125-148,234-257,343-366; g324_arms.py:84-97).
TEST PASS: `python -m pytest tests/platformkit/test_g327_batch_stability.py -q --confcutdir=tests/platformkit` -> 16 passed in 0.58s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.79s.
LOC PASS: touched g327_arms.py 293 and test_g327_batch_stability.py 194; both <= 300.
REPRODUCED PREMISE: Y true/310.5, true/861.0, false/null; R true/0.0 x3; Y rows 343/320/326 and R rows 741/541/729; claimed values match.
REPRODUCED HEADLINE: NOT PINNED and DETERMINISTIC 120/120; batch2 46/120, batch8 48/120, pad 48/120 not applied, fp32 0/120, nmsord 48/120; claimed values match.
REPRODUCED PAIRS: batch8 587 matches, 465 coordinate-exact, 311 full-exact, max delta 3750 thousandths; in-memory report and table are byte-identical to committed artifacts.
INTEGRITY PASS: prereg seal and 17 cited artifact hashes checked; no mismatch (memo:13,33,55).
CORRECTION: memo:49 minimal diff: remove the external path/size/hash clause and replace it with "The prior reject is cited by its quoted verdict only; its full transcript is not in the candidate tree and is NOT VERIFIED here."
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G327 | premise confirmed; CSV-only reconstruction gives NOT PINNED and DETERMINISTIC 120/120 (batch2 46/120; batch8/pad/nmsord 48/120; fp32 0/120), but the memo cites evidence outside the candidate tree | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: the disk-size probe was captured 36 minutes after scoring, so it does not establish the pre-run disk state (g327_detector_batch_stability_attempt2_2026-09-08.md:13).
NEW GAP: read_arm_csv checks only intra-file arm consistency; a wholly mislabeled arm file passes because no expected arm is supplied (g327_arms.py:210,224-227).
NEW GAP: persisted frame arrays remain outside the candidate tree and may be pruned, so committed hashes cannot re-hash source bytes alone (g327_detector_batch_stability_attempt2_2026-09-08.md:42).
