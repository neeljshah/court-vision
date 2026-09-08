Recovered from the verifier log at landing 2026-09-08; candidate 195d1c456.
VERDICT: REJECT
Candidate: `195d1c45660924367d46d7eabb16fa9f7d8b5bea`.
ACCEPTANCE PREMISE PASS - independently parsed call-site observation is P=640 < 1920; source chain is `player_detection.py:82`, `unified_pipeline.py:917,1021`, artifact `g310_postprereg_proxies.json:33-38`.
ACCEPTANCE SOURCES/ARMS PASS - 3 named 1920x1080 inputs and 15/22 rejects reproduce (`g310_pilot_pre_prereg/pilot_summary.json:185,221,285,365-374`); one-difference settings are stated (`g310_native_input_arm_2026-09-07.md:15`).
ACCEPTANCE RESULT FAIL - required 3/3 games and 7 runs became 1/3 and 2/7; no post-prereg repeat, and rows-per-frame is not tabulated while its evaluated-frame field is null (`G310_spec.md:74-90`; `g310_native_input_arm_2026-09-07.md:17-25,35-39`).
ACCEPTANCE DISCLOSURE PASS - SCREENING, sign convention, no-ground-truth sentence, NONE eye check, source limit, and NOT VERIFIED list are explicit (`g310_native_input_arm_2026-09-07.md:27-43`).
HEADLINE REPRODUCTION PASS - claimed P/N values reproduce: rows 1433/2940; row-bearing frames 458/469; ratios 3.128821/6.268657; ids 10/10; medians 158.0/267.5; ball 414/500 and 173/500; p95 0.331528/0.901019; wall 1668.4/2193.4 (`g310_postprereg_proxies.json:3-12,32,43-52,72`).
EVIDENCE PASS - every repository evidence path named by the memo exists; embedded prereg seal and all seven artifact hashes independently match (`g310_native_input_arm_2026-09-07.md:4,38,47`).
TEST PASS - `python -m pytest scripts/platformkit/tracking/test_g310_native_input_arm.py -q -p no:cacheprovider` -> 5 passed in 1.74s.
IMPORTERS PASS - the only Python importer is `test_g310_native_input_arm.py:6`; it was run above.
LOC PASS - new Python files are 299 and 64 lines (`g310_native_input_arm.py:1-299`; `test_g310_native_input_arm.py:1-64`).
B1 PASS - no pass-conditioned exclusion; missing evaluated denominator stays null (`g310_native_input_arm.py:43-71,82-92`).
B2 PASS - diff has zero deletions; ledger is append-only and the new schema has its sole reader checked (`RESULTS_LEDGER.md:455`; `test_g310_native_input_arm.py:6`).
B3 PASS - this is a measurement runner, not an item quarantine; missing sources are disclosed (`g310_native_input_arm_2026-09-07.md:31`).
B4 PASS - no claim queue or retry state exists (`g310_native_input_arm.py:232-276`).
B5 PASS - scratch-only pod execution is permitted and deployed paths stayed unchanged (`VERIFIER_CONTRACT.md:140`; `g310_native_input_arm_2026-09-07.md:33`).
B6 PASS - no move or retirement; the self `-m` reference and test import resolve (`g310_native_input_arm.py:212`; `test_g310_native_input_arm.py:6`).
B7 PASS - the full sorted candidate glob is probed; no render or head slice is used (`g310_native_input_arm.py:232-241`; `g310_native_input_arm_2026-09-07.md:29`).
B8 PASS - no fitting or residual claim exists (`g310_native_input_arm_2026-09-07.md:29`).
B9 FAIL - `player_id` is a reusable tracker slot 1-10 (`unified_pipeline.py:4352-4357`), yet it keys distinct ids, track lengths, and steps (`g310_native_input_arm.py:45-68`); `g310_native_input_arm_2026-09-07.md:27` confirms 10 is the roster-slot count.
B10 PASS - 1920, 8192 MiB, and 3600 s match the spec; no production setting moved (`g310_native_input_arm.py:24-26`; `G310_spec.md:15-17,47-50`).
Q1 FAIL - `g310_prereg_2026-09-07.md:3` says no arm or proxy preceded sealing, but `g310_native_input_arm_2026-09-07.md:38-39` records and uses a seven-run pre-prereg pilot for the required repeat assessment.
Q2 PASS - no charged-trial multiplicity mechanism applies to this screening comparison (`g310_prereg_2026-09-07.md:5`).
Q3 PASS - the 3/3, both-arm, 3600 s bar is byte-equivalent and reported unmet (`g310_prereg_2026-09-07.md:19`; `g310_native_input_arm_2026-09-07.md:1,36`).
Q4 PASS - no OOS score or meta-learner is present (`g310_native_input_arm_2026-09-07.md:29`).
Q5 PASS - no AHEAD result is claimed (`g310_native_input_arm_2026-09-07.md:27-29`).
Q6 PASS - scan of all 525 added lines found zero prohibited prose tokens and zero listed figures (`g310_native_input_arm_2026-09-07.md:29,43`).
Q7 PASS - the synthetic construct enumerates every row and hand-pins all requested proxy outputs (`test_g310_native_input_arm.py:1-48`).
Q8 PASS - premise was measured at the call site and reproduced as 640 (`g310_postprereg_proxies.json:33-38`; `g310_native_input_arm_2026-09-07.md:6`).
CORRECTIONS AS MINIMAL DIFFS:
- `g310_prereg_2026-09-07.md:3`: seal before any arm or proxy computation.
+ Seal a fresh source set before its first run; keep the existing pilot exploratory only.
- `g310_native_input_arm.py:47`: group the three track proxies by reusable `player_id`.
+ Require a non-recycled track-instance key, then regenerate distinct-id, length, and step proxies.
+ `g310_native_input_arm_2026-09-07.md:20-21`: add rows/frame P 3.128821 (1433/458), N 6.268657 (2940/469), with the exact denominator definition.
2026-09-08 | tracking | G310 | premise 640 reproduced; post-prereg 1/3 games and 2/7 runs; Q1 prereg timing and B9 track-unit checks failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: G310 archives aggregate proxy outputs but not the row-level inputs needed to independently recompute medians and p95; archive the minimal per-run columns in a future row.
