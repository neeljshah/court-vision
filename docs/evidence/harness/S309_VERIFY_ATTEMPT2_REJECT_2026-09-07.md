VERDICT: REJECT
PREMISE PASS: measured 465249 ticks/1593 games, 244183 terminal-like ticks, S280 tick-minus-game -0.000130557034, and RG0 171546/200000 cross-side rows (docs/evidence/tracking/specs/S309_spec.md:12).
B1 PASS: all ticks and named clock/status cuts are retained without outcome exclusions (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:55).
B2 FAIL: replacement paired/fold archives drop p_baseline/p_candidate and prior fold fields instead of retaining aliases (scripts/platformkit/s309_canonical_loss_audit.py:222).
B3 PASS: absent receipt/final evidence yields UNKNOWN, not quarantine (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:58). B4 PASS: SCREEN ONLY has no claim path (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:3).
B5 PASS: recorded compute is scratch-only with no deployed-tree write (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:224). B6 PASS: modules are additive, not moved/retired (scripts/platformkit/s309_design_evaluators.py:1).
B7 PASS: metrics use the full decision set (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:55). B8 PASS: callbacks fit train labels only (scripts/platformkit/s309_design_evaluators.py:143).
B9 PASS: 215072 tick predictions differ across arms (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:117). B10 PASS: bar remains 0.004 (scripts/platformkit/s309_canonical_loss_audit.py:27).
Q1 PASS: seal cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad recomputes; prereg commit precedes scoring (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md:132).
Q2 PASS: comparison is uncharged (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:7). Q3 PASS: frozen bars remain byte-identical (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md:95).
Q4 PASS: shared walk_forward and symmetric-embargo CPCV callbacks produce distinct OOF series with agreement <=1e-9 (scripts/platformkit/s309_design_evaluators.py:207).
Q5 PASS: candidate is BEHIND and no AHEAD claim is made (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:68).
Q6 PASS: policy scan found 0 prohibited claims/numbers in all text artifacts (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:90).
Q7 PASS: scored n is the exhaustive 465249 ticks/1593 games (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:55). Q8 PASS: premise was remeasured above (docs/evidence/tracking/specs/S309_spec.md:12).
ACCEPTANCE PASS: all-tick sums/counts, both bootstrap arms, design comparison, MDEs, loss replay, canonical accounting, and one callback fold reproduce (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b.json:1).
ACCEPTANCE FAIL: S272 replay is computed/asserted after _score, contrary to the required replay-FIRST stop gate (scripts/platformkit/s309_canonical_loss_audit.py:181,212,215).
ACCEPTANCE FAIL: folds archive has no train/test membership and omits fitted isotonic thresholds/values, so candidate fits are not archived (scripts/platformkit/s309_design_evaluators.py:154).
ACCEPTANCE FAIL: retained S272 tail ECE change is absent from attempt-2 summary and memo (docs/evidence/tracking/specs/S309_spec.md:49; docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:39).
MEMO PASS: explicit NOT VERIFIED list is present and last (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:254).
REPRODUCED: forward claimed/measured Brier 0.073906391099/0.073984841253; delta -0.000078450154; CI [-0.000136780928,-0.000028628302]; MDE 0.000053709961.
REPRODUCED: CPCV delta -0.000031583337; design delta 0.000529854625, CI [-0.000034107543,0.001139144397]; 215072 differing ticks.
REPRODUCED: accounting claimed/measured 8092183 rows, 0 unaccounted, 4917502 unique keys, 1593 joined games, replay error 0, overlap 40.
REPRODUCED FOLD: forward game 401704641, 259 ticks; state keys exact; probability max error 2.22e-16 and loss max error 1.11e-16.
ARTIFACT PASS: all six manifest SHA-256 values match and all candidate evidence paths exist (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_hashes.json:1).
TEST: python -m pytest tests/platformkit/test_s309_canonical_loss_audit.py -q -p no:cacheprovider -> 3 passed in 3.06s (local).
TEST: python -m pytest tests/platformkit/test_s309_design_evaluators.py -q -p no:cacheprovider -> 2 passed in 1.81s (local).
TEST: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider -> 1 passed in 2.89s (local).
LOC PASS: candidate touches no .py; row modules are 245/248 LOC and importing tests are 69/82 LOC (scripts/platformkit/s309_canonical_loss_audit.py:245; scripts/platformkit/s309_design_evaluators.py:248).
CORRECTION: move _historical plus replay asserts before _score; retain paired/fold aliases; archive exact train/test IDs and isotonic X/y thresholds; publish the retained tail ECE replay; regenerate new dated artifacts.
2026-09-07 | calibration harness | S309 | forward Brier delta -0.000078450154 reproduced; replay-order, archive, and additive-schema checks failed | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: S309_spec.md:27 names 2026-09-04 evidence while this attempt uses 2026-09-07b filenames; align the next spec version.
NEW GAP: attempt2 memo:179 records only three relative-path inputs; add absolute path/bytes/hash/rows/columns/first IDs for the S272/S280 inputs.
NEW GAP: master has neither S309 test file, so the contract A1 baseline command cannot run; add the focused test on landing.
