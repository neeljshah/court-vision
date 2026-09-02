GAP S12 | sport all (signals) | worktree a13 AFTER S11 LANDS (same new package) | log cx_s12_tiers
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q (Q1-Q8) before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
GAP (verbatim from the register): no cost tiering and no fixed T1->T2 promotion rule; without one, cheap screens are the garden of forking paths with extra steps.
READ (read every signature on disk; line numbers drift): scripts/platformkit/foundry/grammar.py as landed by S11 (`Hypothesis`, `semantic_hash`) -- if absent, S11 has not landed: STOP and report BLOCKED; scripts/platformkit/combo/corpus_cache.py `load_gate_corpus(sport)` and `StaleCorpusError`; eval_gate/walkforward.py `assert_vintage`, `walk_forward`, `LeakError`; eval_gate/scoring.py `brier` (import the module symbol -- it is defined twice behind a fallback); eval_gate/cpcv_engine.py `cpcv_evaluate(states, predictor, n_groups=8, n_test_groups=2, embargo_days=1)`; eval_gate/pbo.py `cscv_pbo(matrix, y, s_blocks=16)`; eval_gate/dm_test.py `diebold_mariano`; eval_gate/deflated_metrics.py `deflated_p(p, k)`; eval_gate/backtest_runner.py `_charge_ledger` (THE only ledger writer); combo/fwer_budget.py `min_corpora_eff`.
PREMISE (step 0): `scripts/platformkit/foundry/tiers.py` is ABSENT and nothing refuses to charge a cheap screen -- before = 0/4 tier calls classified. If the module exists, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): n/a -- CONSTRUCT row; the four tier calls ARE the enumerated case set.
CHANGE (step 2), IN THIS ORDER -- the versioned spec is COMMITTED FIRST, before the runner (S16) ever takes a pass, and the verifier checks the commit timestamps:
  (a) NEW `docs/research/organization-sprint/FACTORY_TIERS_SPEC_2026-09-03.md` carrying the four tiers, the exact existing call per tier, charged yes/no, reportable yes/no, and the FROZEN promotion rule with a `spec_version`: `top_n=20 per family per ISO week by T1 Brier improvement`. The rule lives in this file and is NEVER a function argument.
  (b) NEW `scripts/platformkit/foundry/tiers.py` (<=300 LOC):
      T0 exists/covered/vintage = `load_gate_corpus(sport)` (raises `StaleCorpusError`) + `assert_vintage` on a 100-row sample + non-null >= 0.8 * rows -- NOT charged, NEVER reportable.
      T1 moves Brier on one corpus = `walk_forward` + `brier(p_model, y)` vs `brier(p_close, y)` -- NOT charged, verdict is `"SCREEN"` and renders as a NON-FINDING.
      T2 real after purging and selection = `cpcv_evaluate` + `cscv_pbo(matrix, y, s_blocks=16)` + `diebold_mariano` + `deflated_p(p, k)` with k from `_charge_ledger` AT LAUNCH -- CHARGED; reportable MATCH / BEHIND / AHEAD.
      T3 replicates = the T2 call on a second corpus or `corpus_unit` (ATP vs WTA; soccer D1,E0,E1,F1,I1,SP1; MLB eras; NBA seasons), count from `min_corpora_eff(n_corpora, k)` -- CHARGED; AHEAD only if met, else SINGLE-WINDOW.
      `run_tier(h, tier, *, states, ledger_path) -> TierResult(hash, tier, corpus, corpus_unit, n, n_eff, brier_model, brier_close, dm, raw_p, k_family, k_global, deflated_p, pbo, verdict, artifact_path)`; `promote(t1_results, rule) -> list[Hypothesis]`; `rule = PromotionRule.from_spec(path)` reading (a).
      THE REFUSAL: the ledger writer raises `TierNotChargeable` for T0 and T1. A T1 result can only reach the results DB (S15) as `verdict="SCREEN"`.
TEST: NEW tests/platformkit/foundry/test_tiers.py: a 60-row synthetic corpus and 4 tier calls against a TMP ledger path -- T0 and T1 raise `TierNotChargeable` and leave the tmp ledger at 0 rows; T2 and T3 each append exactly one row; `top_n=2` promotes exactly 2. Run ONLY that file: `python -m pytest tests/platformkit/foundry/test_tiers.py -q`.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tier calls correctly refused or charged; denominator = 4 tier calls (T0, T1, T2, T3)
  before        = 0/4 (module absent; nothing refuses a cheap screen)
  bar           = refusal 2/2 (T0, T1 raise TierNotChargeable, tmp ledger stays at 0 rows) AND charge 2/2 (T2, T3 append one row each), with FACTORY_TIERS_SPEC_2026-09-03.md committed with a timestamp EARLIER than the runner's first pass
  n             = 4 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = verifier reruns the test in master, re-reads the tmp ledger row counts, and checks the spec file's commit timestamp against S16's first pass
  must not move = `deflated_p`, `min_corpora_eff`, `cscv_pbo`'s s_blocks=16, every threshold under scripts/platformkit/eval_gate/, data/registry/** (never written), data/cache/eval_gate/backtest_fwer.jsonl (13 rows -- the test uses a TMP ledger only)
NON-TAUTOLOGY: all four tier calls are in the denominator and each is classified; no call is excluded to make the refusal count clean. No `_charge_ledger` call against the real ledger path -- the tmp ledger only.
EVIDENCE: docs/evidence/harness/S12_tiers_2026-09-03.md -- the tier table, the frozen promotion rule and its spec_version, the two commit timestamps (spec before runner), the tmp-ledger row counts per tier, test output, and a NOT VERIFIED list. Calibration language only (Q6): no dollar, ROI, profit or edge word; a SCREEN is never reported as a finding.
POD: none. No deploy before ACCEPT (B5).
COMMIT: explicit pathspec (the tiers spec doc, tiers.py, the test, the memo), in this worktree, no push. Last line of your report: `SHA: <sha>`.
NEVER PARK: run everything to completion this turn; never end waiting.
