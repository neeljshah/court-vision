GAP S233 | sport all | worktree aXX | log cx_s233_walkforward_embargo_prereg
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S208 was REJECTed on Q1 AND Q4 (docs/evidence/harness/S208_VERIFY_2026-09-03.md, a16 worktree): its own
walk_forward "only asserts train date < test date; it implements neither a purge cutoff nor symmetric embargo",
and "names no prereg artifact or embedded pre-metric SHA-256 seal". Measured 2026-09-04:
`grep -rln "def walk_forward\b" scripts/platformkit/` returns 17 files (incl. the one shared
scripts/platformkit/eval_gate/walkforward.py, which purges same-team games within 48h and embargoes same-matchup
within 3 days -- PREGAME-shaped, not tick-grain); 5 modules duplicate
`seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()` verbatim (s58_clamp_family_trial.py:222,
s58_e2_slice_trial.py:87, s58_nba_halftime_asof_trial.py:129, stacker.py:202, stacker.py:261). No shared tick-grain
purge+embargo+seal utility exists; each in-game row re-derives one, and S208 is the row caught with a leak-open one.
PREMISE (step 0): reproduce the 17-file count and the 5 duplicate seal sites; confirm cpcv_engine.cpcv_evaluate
(embargo-capable, called by stacker/hedge_trial_runner/three s58 trials) is the only tick-grain purge+embargo path
today; name every caller of both walkforward.py and cpcv_engine.py.
LIMIT (step 1): if a tick-grain wrapper cannot be added additively over cpcv_evaluate/walkforward.py without
editing either (both imported by >=2 shared token modules), report CLOSED AT LIMIT and name the exact coupling.
CHANGE (step 2): new module scripts/platformkit/eval_gate/walkforward_embargo_prereg.py (<=300 LOC, additive only):
`purge_embargo_walk_forward(states, predict_fn, embargo_days)` asserting embargo_days > 0 and every train row's
game-end precedes its test fold by >= embargo_days (raise on violation); `seal_prereg(path) -> sha256 hex` and
`assert_sealed(path, expected)` factoring the 5 duplicate call sites into one function. Callers NOT edited this row
-- propose the 5 one-line replacements as a PROPOSED snippet under docs/research/organization-sprint/. No edit to
ledger.py, backtest_runner.py, combo/fwer_budget.py, walkforward.py or cpcv_engine.py (import-only).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = planted-leak fixture: a synthetic tick series with one feature built from the tick's OWN future
                  outcome vs a leak-free sibling series built identically except the feature is properly lagged
  before         = 0 shared modules catch this construction today (S208's bespoke loop passed with it undetected)
  bar            = purge_embargo_walk_forward raises on the leaked series and does not raise on the leak-free
                  sibling, at embargo_days in {1, 2, 3}; seal_prereg(path) reproduces byte-identical across 2 runs
                  and assert_sealed rejects a 1-byte-mutated copy
  n              = 3 embargo values x 2 fixture arms = 6 (CONSTRUCT)
  eye check      = n/a (S-row); reproduction = the verifier re-imports the module, reruns both fixtures at all 3
                  embargo values, diffs the raise/no-raise outcome and the seal hex
  must not move  = walkforward.py / cpcv_engine.py source (imported, not edited); every existing threshold
NON-TAUTOLOGY: the fixture construction and both pass/fail rows are printed; a leak the module cannot ever catch at
any embargo_days is a REJECT of this row, not a hidden pass.
EVIDENCE: docs/evidence/harness/S233_walkforward_embargo_prereg_2026-09-04.md + the two fixture JSONs. ASCII only.
Calibration language only (no dollar, ROI or edge words).
TEST: one new per-file test (both fixture arms, all 3 embargo values), run only that file.
REPORT: 17-file and 5-site counts, 6-cell CONSTRUCT table, test line, SHA. Commit by pathspec, no push. NEVER PARK.
