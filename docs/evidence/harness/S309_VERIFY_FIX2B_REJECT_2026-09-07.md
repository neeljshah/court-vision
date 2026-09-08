VERDICT: REJECT
PREMISE PASS: measured 465249 ticks/1593 games, 244183 period-4-plus clock-zero ticks, and S280 tick-minus-game -0.000130557033850 (docs/evidence/tracking/specs/S309_spec.md:12).
ACCEPTANCE FAIL: candidate rewrites prior dated evidence memo (231 insertions/117 deletions), violating the frozen-prior-evidence clause (docs/evidence/tracking/specs/S309_spec.md:25; docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:1).
ACCEPTANCE PASS: full-set paired Brier/log-loss replay errors are 0; ratio-bootstrap headlines, MDEs, signs, and four tables reproduce (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:315).
ACCEPTANCE PASS: replay-first stop gate, exhaustive accounting/provenance, retained S272 values, fold membership/parameters, and one callback fold reproduce (scripts/platformkit/s309_canonical_loss_audit.py:195).
B1 PASS: 465249 rows and all named time cuts are retained without outcome exclusions (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:75).
B2 PASS: prior paired/fold fields remain aliases; measured schemas are strict supersets (scripts/platformkit/s309_canonical_loss_audit.py:245).
B3 PASS: absent receipt/final evidence remains UNKNOWN (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:80).
B4 PASS: SCREEN ONLY has no continuing claim path (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:1).
B5 PASS: recorded compute used per-worktree pod scratch only (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:324).
B6 PASS: candidate moves/retires no module; both S309 imports remain covered (tests/platformkit/test_s309_canonical_loss_audit.py:7).
B7 PASS: metrics use the complete scored set, not a head slice (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:326).
B8 PASS: actual refit used archived train IDs disjoint from test IDs (scripts/platformkit/s309_design_evaluators.py:147).
B9 PASS: 253 cluster sizes and 215072 differing design ticks are non-degenerate (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:122).
B10 PASS: frozen 0.004 bar is unchanged (docs/evidence/tracking/specs/S309_spec.md:25; docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:2).
Q1 PASS: both seals recompute and commits bf7a14de8/24eb96561 precede scoring evidence (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md:132; docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c_supplement.md:45).
Q2 PASS: comparison is explicitly uncharged (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:1).
Q3 PASS: summary and spec both retain the frozen 0.004 bar (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:2).
Q4 PASS: shared strict-past walk-forward and symmetric-embargo CPCV produce OOF series with 2.22e-16 record agreement (scripts/platformkit/s309_design_evaluators.py:239).
Q5 PASS: both candidate comparisons are BEHIND; no AHEAD claim is made (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:1).
Q6 PASS: policy scan found 0 prohibited claims or figures across the evidence text and added ledger line (docs/evidence/RESULTS_LEDGER_SYSTEM.md:544).
Q7 PASS: scored n exhausts 465249 ticks/1593 game clusters (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c.json:326).
Q8 PASS: the premise was independently remeasured before adjudication (docs/evidence/tracking/specs/S309_spec.md:12).
ADDITIVITY PASS: summary, accounting, keys, paired and fold schemas remove no prior field/status; aliases match exactly (scripts/platformkit/s309_canonical_loss_audit.py:251).
MEMO PASS: explicit NOT VERIFIED list starts at line 360 and is last (docs/evidence/harness/S309_canonical_loss_audit_attempt2_2026-09-07.md:360).
REPRODUCED: forward claimed/measured Brier 0.073906391099376/0.073984841253499, delta -0.000078450154123, CI [-0.000136780928,-0.000028628302].
REPRODUCED: CPCV delta -0.000031583336663, CI [-0.000059550789,-0.000005652876]; design delta 0.000529854625223, CI [-0.000034107543,0.001139144397].
REPRODUCED: S272 delta -0.000036668338033 and tail ECE change -0.000248825092559; callback fold probability/loss max errors 2.50e-16/3.33e-16.
ARTIFACT PASS: all seven manifest SHA-256 values, five input identities, and three route hashes match (docs/evidence/harness/S309_canonical_loss_audit_2026-09-07c_hashes.json:1).
LOC PASS: candidate touches no .py; row modules are 275/281 LOC and the repository rail passes (scripts/platformkit/s309_canonical_loss_audit.py:275; scripts/platformkit/s309_design_evaluators.py:281).
TEST: python -m pytest tests/platformkit/test_s309_canonical_loss_audit.py -q -p no:cacheprovider -> 5 passed in 3.56s (local).
TEST: python -m pytest tests/platformkit/test_s309_design_evaluators.py -q -p no:cacheprovider -> 3 passed in 1.87s (local).
TEST: python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider -> 1 passed in 0.73s (local).
CORRECTION: restore the prior memo blob c87bb1da8f39488ee5864e96f51e65955aa8462f and add the corrected text as S309_canonical_loss_audit_2026-09-07c.md; no metric regeneration is needed.
2026-09-07 | nba in-game calibration | S309 | forward Brier delta -0.000078450154 reproduced; prior dated memo rewritten | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: S309_spec.md:27 names 2026-09-04 evidence while the corrected artifacts use 2026-09-07c; align the next spec version.
NEW GAP: candidate adds docs/evidence/RESULTS_LEDGER_SYSTEM.md:544 despite the spec's shared-ledger write ban at S309_spec.md:31.
NEW GAP: master has neither focused S309 test file, so contract A1 cannot run there; add both tests on landing.
NEW GAP: S309_spec.md:17 says one evaluator state per tick, while s309_design_evaluators.py:10 uses one state per game cluster; align the requirement or route.
NEW GAP: linked-worktree git metadata is outside the writable sandbox, so direct git add and lane_commit.py both fail on index.lock; an external path-specific commit is required.
