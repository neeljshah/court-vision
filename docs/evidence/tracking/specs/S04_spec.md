GAP S04 | sport all (harness) | worktree a12 | log cx_s04_student_gate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q (Q1-Q8) before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
GAP (verbatim from the register): the teacher->student gate is a RULE, not code: no module runs student vs id-fixed-effect baseline vs student+ids, so no "tracking improved a model" claim is permissible today.
READ (exact symbols): scripts/platformkit/eval_gate/walkforward.py `walk_forward`, the vintage assertion helper, `LeakError`; scripts/platformkit/eval_gate/dm_test.py `diebold_mariano(d, cluster_ids)`; scripts/platformkit/eval_gate/deflated_metrics.py `deflated_p(raw_p, k)`; scripts/platformkit/eval_gate/scoring.py `brier`; scripts/platformkit/ingame/gap_effective_n.py `intraclass_correlation`, `effective_sample_size`; scripts/platformkit/eval_gate/backtest_runner.py `_charge_ledger(path, spec, sport, start, end) -> dict` (THE only ledger writer -- tests pass a tmp path, NEVER the default); scripts/platformkit/framing_distill.py `shrunk_effects` (lift the empirical-Bayes shrinkage pattern); scripts/platformkit/combo/fwer_budget.py `min_corpora_eff`. Read the signatures on disk; the line numbers in the plan may drift.
PREMISE (step 0): scripts/platformkit/eval_gate/student_gate.py is ABSENT -> before = 0 cases pass. If it exists, STOP and report FALSIFIED.
LIMIT (step 1): n/a (CONSTRUCT row: two synthetic cases enumerated).
CHANGE (step 2): NEW scripts/platformkit/eval_gate/student_gate.py (<=300 LOC):
  @dataclass(frozen=True) StudentVerdict(verdict: str, delta_brier: float, dm_ci: tuple[float, float], raw_p: float, deflated_p: float, k_cumulative: int, n_eff: float, detail: dict)   # verdict in TEACHES | NULL | INSUFFICIENT
  id_fixed_effect_baseline(train, test, id_key="player_id", prior_strength=50.0) -> float   # EB-shrunk per-id deviation from the train mean; unseen id -> global rate; train rows only
  run_student_gate(states, student_fn, *, id_key="player_id", ledger_path: Path, charge_spec: str, name: str) -> StudentVerdict
  Order inside run_student_gate: (1) vintage assertion on every state (empty feature_avail -> LeakError propagates); (2) `_charge_ledger(ledger_path, charge_spec, sport, start, end)` BEFORE any metric -- K is read HERE, once, stored as k_cumulative (Q2); (3) three walk_forward arms on the SAME states: baseline (ids only) / student (teacher value only) / student+ids; (4) paired per-state d_t = brier(baseline) - brier(student), game-clustered DM 95 pct CI; (5) n_eff from the student's own residuals (ICC from the scored window, never a stored constant); (6) deflated_p(dm p-value, k_cumulative).
  VERDICT RULE (prereg text in the module docstring, NOT sealed today -- no real trial): TEACHES iff (i) delta_brier >= 0.004 vs the id-fixed-effect baseline, (ii) DM 95 pct CI excludes 0, (iii) deflated_p < 0.05 at launch K, (iv) brier(student) - brier(student+ids) <= 0.004 (if ids alone carry it, the teacher taught nothing). INSUFFICIENT when n_eff < 30 or clusters < 20. Otherwise NULL. Runtime purity: a student whose registered inputs carry runtime_available=False is refused with a clear error.
  Output JSON data/cache/eval_gate/student_gate_<name>.json: prereg sha256 (of the rule text + bars), k_cumulative, three arm Briers, n_eff, the ledger row. Tests write under tmp_path only (module accepts an output dir).
TEST: NEW scripts/platformkit/eval_gate/test_student_gate.py (beside the module), synthetic, fixed seed, n >= 1,000 rows each, tmp ledger_path: (a) outcome ~ sigmoid(latent[id]), teacher = noise -> NULL; (b) outcome ~ sigmoid(teacher), teacher orthogonal to id -> TEACHES; (c) empty feature_avail -> LeakError; and the tmp ledger's K equals the JSON k_cumulative with its row appended before the first Brier. Run ONLY that file with `python -m pytest scripts/platformkit/eval_gate/test_student_gate.py -q`.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = verdict on the two synthetic corpora; denominator = 2 cases at n >= 1,000 rows each
  before        = module absent (0 pass)
  bar           = NULL on (a) and TEACHES on (b), both reproduced by the verifier; (c) raises LeakError
  n             = 2 x >= 1,000 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test in master
  must not move = the 0.004 bar, data/cache/eval_gate/backtest_fwer.jsonl (13 rows -- NEVER charge the real ledger; no real trial today), every eval_gate threshold, data/registry/**
NON-TAUTOLOGY: both cases are scored on all their rows; nothing excluded.
EVIDENCE: docs/evidence/harness/S04_student_gate_2026-09-03.md -- the three arm Briers per case, DM CI, deflated p, K, n_eff, test output, a NOT VERIFIED list (the first REAL teacher is blocked on S26 -- say so). Calibration language only (Q6): no dollar, ROI, profit or edge word.
POD: none.
COMMIT: explicit pathspec (module, test, memo), in this worktree, no push. Last line of your report: `SHA: <sha>`.
NEVER PARK: run everything to completion this turn; never end waiting.
