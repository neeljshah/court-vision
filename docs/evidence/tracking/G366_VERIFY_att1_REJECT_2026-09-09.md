VERDICT: REJECT
CANDIDATE: 26cfd89401c84872a7040d00b64e51bc0d8a908e.
ACCEPTANCE PASS: premise is 3/4 classified gates on 34 sealed sections; held-share has 34 rows and arms has 4,896 rows (g359_held_position_vs_threshold_2026-09-09/decision.csv:2).
ACCEPTANCE PASS: fresh 59 unique sections/14 games, minimum 358 unique frames, no G358 section or game overlap (g366_gate_confirmation_2026-09-09/summary.json:101).
ACCEPTANCE PASS: M1 A0 rejects are 0/59 zero-step, 0/59 distinct-position, 12/59 stationary, and 56/59 median-step v1 (g366_gate_confirmation_2026-09-09/summary.json:2).
ACCEPTANCE PASS: plants are 10/10 in M0 and M1; tick median is 0.153195; v2 A0 is 3/59, A1 0/59, A2 32/59 (g366_gate_confirmation_2026-09-09/summary.json:108,167,173).
ACCEPTANCE PASS: four required gates reach 59/59; ten evenly spaced SVG strips exist, max 14,397 bytes, with distinct M0/M1 rows (g366_gate_confirmation_2026-09-09/reach.csv:1; strips/0SQ709_N0Yg_s1325.svg:1).
TEST FAIL: `python -m pytest tests/platformkit/test_g366_gate_confirmation.py -q -p no:cacheprovider` -> 5 passed, 1 failed (test_g366_gate_confirmation.py:136).
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed (test_loc_rail_scope.py:1).
IMPORT/LOC PASS: only the spec test imports row modules; cumulative row Python LOC are 300, 275, 274, and test 140, all <=300 (g359_held_position.py:300; g366_confirm.py:275; g366_fresh.py:274; test_g366_gate_confirmation.py:140).
B1 PASS: eligibility exclusions are named before gate scoring; PASS/REJECT alone form each denominator (g366_fresh.py:72; g366_confirm.py:185).
B2 PASS: G359 copy matches master; v2 fields/statuses are additive and nonterminal statuses pass through (g366_confirm.py:57,64).
B3 PASS: absent evidence remains non-passing and outside required numerators (g366_confirm.py:155; test_g366_gate_confirmation.py:55).
B4 PASS: no claim lifecycle or retry state is introduced (g366_confirm.py:73).
B5 PASS: memo identifies pod scratch worktree only; candidate changes evidence paths only (g366_gate_confirmation_2026-09-09.md:5).
B6 PASS: no module is moved or retired; G359 is byte-identical to master (g366_gate_confirmation_2026-09-09.md:10).
B7 PASS: selected set is the full eligible set and eye-check members span first through last rank (g366_fresh.py:45,229).
B8 PASS: v2 is scored on sections and games disjoint from the 34-section fitting set (g366_gate_confirmation_2026-09-09.md:14).
B9 PASS: 59 distinct section units and 14 games; every headline gate has 59 distinct units (g366_gate_confirmation_2026-09-09/summary.json:101).
B10 PASS: v1 threshold stays 8.408436 and v2 is a separate max-direction column (g366_confirm.py:33,57; test_g366_gate_confirmation.py:40).
Q1 PASS: Git blob seal matches af4285e560598ba0b8512c3521d78604ef6b01b80949532bf8c4d0de84578e4a and commit a13979ab predates scoring (g366_prereg_2026-09-09.md:300).
Q2 PASS (N/A): this tracking confirmation charges no trial ledger (g366_prereg_2026-09-09.md:12).
Q3 PASS: bars remain 0.05, 0.80, [0.90,1.10], 30 sections, and 10 games (g366_gate_confirmation_2026-09-09/summary.json:52).
Q4 PASS (N/A): no predictive OOS comparison or meta-learner is scored (g366_prereg_2026-09-09.md:12).
Q5 PASS (N/A): no AHEAD status is claimed (g366_gate_confirmation_2026-09-09.md:1).
Q6 FAIL: candidate memo repeats three prohibited prose tokens in scanner commentary (g366_gate_confirmation_2026-09-09.md:48,51).
Q7 PASS: 59 unique scored sections exceed n=30; all eligible units were retained and strips use even ranks (g366_gate_confirmation_2026-09-09/summary.json:101; g366_fresh.py:45).
Q8 PASS: predecessor premise was remeasured as 3/4 classes before the fresh result (g366_gate_confirmation_2026-09-09.md:8).
NOT VERIFIED PASS: explicit list exists and scopes snapshot, stationary, v2, geometry, A5, and generalization limits (g366_gate_confirmation_2026-09-09.md:53).
REPRODUCED VS CLAIMED: all headline counts above match memo lines 17-29 exactly; CSV hashes match summary.json and all named committed artifacts exist (g366_gate_confirmation_2026-09-09.md:17).
CORRECTION (minimal): replace memo lines 47-51 with a compliant zero-hit vocabulary-scan statement, then rerun the scan.
CORRECTION (minimal): at test_g366_gate_confirmation.py:137 normalize CRLF to LF before hashing; the Git blob seal already matches.
PROPOSED RESULTS_LEDGER_SYSTEM:
2026-09-09 | tracking | G366 | premise 3/4; fresh 59 sections/14 games; M1 gate rejects 0/59, 0/59, 12/59, 56/59; tick median 0.153195; plants 10/10 per mode; v2 A0 3/59, A1 0/59, A2 32/59 | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: memo:14 and memo:47 name a pod-only snapshot and scanner absent from this checkout, so raw census replay and scanner replay were unavailable.
NEW GAP: test_g366_gate_confirmation.py:137 hashes checkout bytes without newline normalization, failing on CRLF checkouts although the committed blob seal is valid.
