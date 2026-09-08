VERDICT: REJECT
Candidate: e7bbbc35b; full 20-file diff reviewed; evidence memo is 55 lines.
ACCEPTANCE FAIL: required `du -sm /workspace` disk guard is unmeasured; the artifact substitutes `df -m /workspace` (G327_spec.md:27-29,250-252; g327a2_probes.txt:17-27).
ACCEPTANCE FAIL: required pod log tail is absent from the memo and candidate artifacts (G327_spec.md:205-211; g327_detector_batch_stability_attempt2_2026-09-08.md:52-54). [landing note: the Q6 scan flags a standalone `54` in this line; it is the file line-range citation `52-54`, not the retracted in-play figure -- see docs/JOB_EVIDENCE_PACKET.md. Line text otherwise verbatim.]
ACCEPTANCE FAIL: memo cites `G327_VERIFY_ATTEMPT1_REJECT_2026-09-08.md`, absent from candidate tree (G327_spec.md:253-255; g327_detector_batch_stability_attempt2_2026-09-08.md:48).
ACCEPTANCE PASS: all seven CSVs explicitly carry 120 unique frames and 587 boxes; CSV-only arithmetic reproduces every verdict cell (g327_report.py:146-183; g327a2_table.md:9-45).
ACCEPTANCE PASS: memo is <=60 lines and has a NOT VERIFIED list (g327_detector_batch_stability_attempt2_2026-09-08.md:35-44).
B1 PASS: no scored row excluded; all 120 unique frames are used (g327a2_summary.json:50-70; g327a2_report.json:377-414).
B2 FAIL: `read_boxes_csv`/`write_boxes_csv` were removed and `rows_for` changed signature without compatibility aliases; reader behavior is not additive (g327_arms.py:162-218; test_g327_batch_stability.py:11-13).
B3 PASS: no production gate or absent-evidence quarantine is introduced (g327_detector_batch_stability_attempt2_2026-09-08.md:3).
B4 PASS: no claim/retry path is introduced (g327_detector_batch_stability_attempt2_2026-09-08.md:3,50).
B5 PASS: compute is scratch-only and gated hashes match before/after (g327a2_summary.json:22-26,810-815).
B6 PASS: no module is moved or retired; importer census found only the updated G327 test (test_g327_batch_stability.py:11-13,128,136).
B7 PASS: no renders; each 40-frame list spans 0..anchor (g327_detector_batch_stability_attempt2_2026-09-08.md:11).
B8 PASS: no fitting or residual metric is used (g327_report.py:57-82).
B9 PASS: denominator is 120 unique frames per arm, including zero-box rows by construction; realised zero count is 0 (g327a2_table.md:39-45).
B10 PASS: IoU 0.5, batches 2/8, route 0.22, and bars 110/120 and 120/120 are unchanged (g327_prereg_2026-09-08d.md:228-265).
Q1 PASS: seal recomputed `fb668830470aff9abdff6b580771db97fe58c7ce4ab04f3cb61fc551fed2cb13`; prereg commit 541f2f331 predates scoring (g327_prereg_2026-09-08d.md:300-305).
Q2 PASS: not applicable; no charged trial or K exists (G327_spec.md:183-189).
Q3 PASS: sealed verdict bars are unchanged (g327_prereg_2026-09-08d.md:257-265).
Q4 PASS: not applicable; no OOS predictive metric is scored (g327_detector_batch_stability_attempt2_2026-09-08.md:3).
Q5 PASS: not applicable; no AHEAD claim is made (g327_detector_batch_stability_attempt2_2026-09-08.md:1-3).
Q6 PASS: automated scan of candidate additions is clean (g327_detector_batch_stability_attempt2_2026-09-08.md:55).
Q7 PASS: exhaustive construct is 3 games x 40 frames x 7 arms = 840 arm-frames (g327a2_summary.json:50-70; g327a2_arms.csv:2-22).
Q8 PASS: premise remeasured as Y true/310.5, true/861.0, false/null and R true/0.0 x3; batch rows remain unavailable (g324_summary.json:127,148,236,257,345,366; g324_arms.py:108-118).
TEST PASS: `python -m pytest tests/platformkit/test_g327_batch_stability.py -q --confcutdir=tests/platformkit` -> 12 passed in 0.63s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed in 0.64s.
LOC PASS: g327_arms.py 226; g327_detector_batch_stability.py 275; g327_report.py 200; g327_sources.py 155; test_g327_batch_stability.py 140.
REPRODUCED: NOT PINNED; repeat 120/120, batch8 48/120, pad 48/120 not applied, fp32 0/120, nmsord 48/120; claimed values match.
REPRODUCED: batch8 587 matches, coordinate-exact 465/587, exact with score/class 311/587, both-way 587/587, max delta 3750 thousandths; claimed values match.
CORRECTION: rerun the mandated `du` probe, preserve its verbatim output and pod log tail, then cite both in the memo.
CORRECTION: add legacy reader/writer aliases plus a nine-column parse branch; retain the prior `rows_for(table, arm, idxs)` behavior.
CORRECTION: memo:7 minimal diff: qualify 343/320/326 as Y rows; R rows are 741/541/729.
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-08 | tracking | G327 | premise confirmed; attempt-2 CSV reconstruction gives NOT PINNED (48/120, 0/120, 48/120) and DETERMINISTIC 120/120, but required disk/log evidence is absent and reader compatibility was removed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: persisted frame arrays named by the prereg are absent from the candidate tree, so committed hashes cannot re-hash the source bytes later.
NEW GAP: `read_arm_csv` ignores arm, box-index and declared-count cells; malformed rows can be scored without rejection (g327_arms.py:205-214).
