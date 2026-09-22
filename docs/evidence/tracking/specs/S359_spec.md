GAP S359 | sport mlb (soccer descriptive only) | worktree harness-h17 (master-based) | log cx_s359_four_arm_trial_runner
# Charged-trial runner for the SEALED four-arm baseline: charge the FWER ledger BEFORE the metric, read K at launch (contract Q2)

AUTHORITY: docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md (sealed, committed as de2acdc6d before any score) and
docs/evidence/tracking/VERIFIER_CONTRACT.md Q1, Q2, Q3, Q4. SINGLE PROBLEM: scripts/platformkit/ingame/baseline_four_arm.py refuses
to score without a sealed committed prereg, but nothing CHARGES the trial: contract Q2 requires the ledger row to be appended
before anything is computed and the K read AT LAUNCH to be the only K reported. The sanctioned charge path is
scripts.platformkit.eval_gate.backtest_runner._charge_ledger (see how scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py
uses it: FAMILY / TIER / START / END constants, `row = _charge_ledger(Path(ledger_path), SPEC_ID, sport, START, END, family=...,
tier=..., ...)`, then `k = int(row["k_cumulative"])` as the ONLY K used).

BINDING BEFORE-CONDITION (re-run, quote): `ls scripts/platformkit/ingame/s359_four_arm_trial.py` fails; the sealed prereg verifies
(`python -c` that re-computes the SHA256 line over LF-normalized bytes and prints True).

CHANGE (NEW files only; this row is PREPARE ONLY -- the BUILDER NEVER RUNS THE TRIAL AND NEVER TOUCHES THE REAL LEDGER):
1. scripts/platformkit/ingame/s359_four_arm_trial.py (<= 250 LOC; mirror s58_nba_halftime_asof_trial.py): constants SPEC_ID =
   "S359", FAMILY = "ingame_four_arm_mlb_r3" (a family of one, NOT frozen -- say so in the output exactly as the s58 trial does),
   TIER = "T2", sport "mlb", START / END = the first and last first-tick UTC dates in the sealed census (2026-06-27, 2026-07-12).
   `run(corpus_dir, manifest, prereg, out_dir, ledger_path)` does, IN THIS ORDER and failing closed at each step:
   (a) verify the prereg seal and that the file is committed (reuse the scorer's own validate function -- do not reimplement);
   (b) run the scorer's census path on the corpus and ASSERT the frozen denominators from the sealed text: 176 games, 31433 ticks,
       29887 eligible ticks, 12339 state-transition ticks, 15 folds of which 4 are warm-up; any difference -> stop BEFORE charging;
   (c) refuse if out_dir already holds a result (one charged attempt per out_dir; the sealed text allows at most two attempts in
       total, and the second needs an explicit --attempt 2 flag that is recorded);
   (d) CHARGE: `_charge_ledger(...)` with family, tier, the prereg SHA-256 seal value as prereg_sha256 and a hypothesis_hash =
       sha256 of the sealed prereg bytes + corpus manifest digest; write the returned ledger row and K to out_dir/charge.json
       BEFORE any loss is computed;
   (e) only then call the landed scorer (baseline_four_arm scoring entry point) and write its full output;
   (f) write out_dir/trial_summary.json: spec id, family (with the NOT-frozen note), tier, K at launch, the ledger row, the prereg
       seal, the manifest digest, the scorer commit, per-cell verdicts exactly as the scorer produced them (no re-labelling, no
       re-thresholding), and the SINGLE-WINDOW / no-AHEAD-authorized statement copied from the sealed text.
   A --descriptive-soccer flag runs the soccer revision-3 corpus WITHOUT a charge and stamps every cell UNDERPOWERED-DESCRIPTIVE;
   it refuses to print any verdict word for soccer.
2. tests/platformkit/ingame/test_s359_four_arm_trial.py: with a TEMP ledger path and synthetic corpora -- the charge row is written
   BEFORE the scorer is called (monkeypatch the scorer to assert charge.json exists); a census mismatch stops before charging (the
   temp ledger stays empty); an unsealed or uncommitted prereg stops before charging; a second run into the same out_dir refuses;
   K in the summary equals the K in the charge row; the soccer flag never charges and never emits a verdict word.
3. Memo docs/evidence/harness/S359_four_arm_trial_runner_2026-09-21.md with the EXACT finisher command for the real run:
   python -m scripts.platformkit.ingame.s359_four_arm_trial --corpus-dir data/cache/ingame_grade_joined/mlb_segmented_r3
   --manifest <canonical manifest path> --prereg docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md --out <dir>
   and a NOT VERIFIED list.

CONTROLS: the builder uses ONLY temp ledgers and synthetic corpora; it must never read or write
data/cache/eval_gate/backtest_fwer.jsonl and never run the real corpus. No bar, seed or threshold is restated differently from
the sealed text (Q3). ACCEPTANCE: the per-file test passes; `--help` works; diff = NEW files only. Vocabulary follows contract Q6;
automated scan required; assemble retracted-figure literals from single digits. The pod is OFF.

AMENDMENT 1 (orchestrator, 2026-09-21, after the independent verifier REJECT; binding).
VERIFIER FINDING (codex gpt-5.6-sol): the runner can charge a NON-CANONICAL ledger. With no ledger flag it resolved the path inside
the worktree it was imported from (an absent file there), and `_charge_ledger` CREATES an absent ledger, which yields K = 1 -- the
exact failure backtest_runner.py warns about near CANONICAL_LEDGER_PARTS ("a fresh path charges k_cumulative = 1"); the true
cumulative K on the canonical ledger is 18. Direct `run(..., ledger_path)` also accepted any relative path silently. A trial
charged at the wrong K is invalid and the one allowed attempt would be burned.
BINDING RULE: in REAL mode the runner (a) resolves the ledger ONLY through the canonical-ledger helper in
scripts/platformkit/eval_gate/backtest_runner.py (use `assert_canonical_ledger` if it exists there; if the helper has another
name, use the one backtest_runner itself uses and quote it in the memo); (b) REFUSES, before any reservation or charge, unless the
canonical ledger file EXISTS and already holds at least one valid prior row (an empty or absent canonical ledger means the
process is running from the wrong tree); (c) prints the absolute ledger path and the prior max k_cumulative it read, and writes
both into charge.json; (d) the ONLY way to use another ledger is an explicit test-only keyword argument
(allow_noncanonical_ledger_for_tests=True) that the CLI does not expose and that stamps "TEST LEDGER" into every output file.
Required tests: a worktree-relative absent ledger fails before reservation; a relative path fails; an empty canonical-looking file
fails; the test-only opt-out works and is stamped; the CLI exposes no way to pass the opt-out.
