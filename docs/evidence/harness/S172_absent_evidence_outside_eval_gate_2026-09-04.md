# S172 absent-evidence escapes outside eval_gate

Date: 2026-09-04

## Premise measurement

The required before scan covered test files under both `scripts/platformkit` and
`tests/platformkit`. It found 61 worktree-only absent-evidence escapes outside
`scripts/platformkit/eval_gate`.
The S165 pair-grammar file had a separate unguarded CSV dependency, so it is
guarded as an additional precondition; it is not counted in N because it was not
an existing skip/return escape.

Metric: 61 / 61 routed through `worktree_marker.is_worktree_checkout()`.
Before: 0 / 61. Bar: 61 / 61. Result: 61 / 61.

## File and path table

| File:line before | Guarded path | Before | After |
|---|---|---:|---:|
| combo/test_corpus_cache_freshness.py:85,202 | `cc._corpus_path(sport)`, `cc._sidecar_path(sport)` under data/cache/combo | 2 | 2 |
| combo/test_corpus_cache_soccer_enrich.py:45,54 | data/domains/soccer/matches.parquet; cached soccer corpus | 2 | 2 |
| data_frontier/test_milb_statsapi.py:123 | batter_pitch_profiles.parquet under the matchup cache | 1 | 1 |
| improve/test_clv_lifecycle_reconcile.py:464 | DEFAULT_LEDGER | 1 | 1 |
| ingame/test_hist_mlb_forward_gate.py:168 | DEFAULT_CAPTURE_DIR; DEFAULT_BOXSCORE_PARQUET | 1 | 1 |
| ingame/test_hist_mlb_outcome_resolver.py:150 | DEFAULT_BOXSCORE_PARQUET | 1 | 1 |
| ingame/test_ingame_sigma_serve.py:138,361 | data/models/ingame_sigma_table.json | 2 | 2 |
| ingame/test_nba_logistic_pricer.py:134 | p.ARTIFACT_PATH | 1 | 1 |
| intel_validation/test_claims_validator_pairkey.py:104 | listed proof-claims artifact path | 1 | 1 |
| intel_validation/test_tennis_claims_v4.py:112 | tcv4._SURFACE_SPLITS_SRC | 1 | 1 |
| intel_validation/test_verdict_claim_check.py:119 | data/cache/intel_claims/nba_quality_claims.jsonl | 1 | 1 |
| intel_validation/test_verdict_claims_validator.py:183 | claims_path | 1 | 1 |
| interaction_factory/test_builders_soccer_setpiece.py:103 | statsbomb match metadata, soccer matches, events directory | 1 | 1 |
| interaction_factory/test_builders_tennis_chain.py:67 | tc._TENNIS_MATCHES | 1 | 1 |
| pod_sprint/test_player_value_asof.py:127 | player_boxscores.parquet | 1 | 1 |
| signals/test_market_coherence.py:66 | data/cache/line_history | 1 | 1 |
| signals/test_market_micro_asof.py:82 | data/cache/line_history | 1 | 1 |
| vault_feed/test_vault_feed.py:111,168 | intel_claims_validation.json; CLAIMS_DIR | 2 | 2 |
| test_clv_ledger_betid_backfill.py:355,366,376 | data/frontend/clv_ledger.jsonl | 3 | 3 |
| test_clv_ledger_status_append.py:573 | DEFAULT_LEDGER | 1 | 1 |
| scripts/platformkit/test_pm_best_trades.py:344 | data/frontend/clv_ledger.jsonl | 1 | 1 |
| tests/platformkit/analytics_verify/test_attribution.py:92 | A.GRADED; A.CLV | 1 | 1 |
| tests/platformkit/analytics_verify/test_regrader.py:168 | R.CARD_LEDGER; R.CARDS | 1 | 1 |
| tests/platformkit/analytics_verify/test_sentinel.py:139 | S.GRADE_SUMMARY_PATH; DEFAULT_LEDGER | 1 | 1 |
| tests/platformkit/canary/test_stack_canary.py:399 | data/frontend/predict_service/nba/latest.json | 1 | 1 |
| tests/platformkit/combo/test_fwer_families_bh.py:84 | data/cache/eval_gate/backtest_fwer.jsonl | 1 | 1 |
| tests/platformkit/foundry/test_ingame_grammar_nba.py:40 | data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv | 1 | 1 |
| tests/platformkit/foundry/test_ingame_screen_nba.py:28 | N.S86_CSV | 1 | 1 |
| tests/platformkit/foundry/test_ingame_screen_soccer_a2.py:8 | data/cache/eval_gate/s117_soccer_ingame_screen_2026-09-03_series.csv | 1 | 1 |
| tests/platformkit/ingame/test_s103_nba_sigma_a2.py:8 | data/cache/eval_gate/s103_nba_sigma_2026-09-03.csv | 1 | 1 |
| tests/platformkit/ingame/test_s115_ingame_models_a2.py:8 | data/cache/eval_gate/s115_ingame_models_2026-09-03.csv | 1 | 1 |
| tests/platformkit/ingame/test_s116_pooled_ingame_a2.py:13 | data/cache/eval_gate/s116_pooled_ingame_2026-09-03.csv | 1 | 1 |
| tests/platformkit/ingame/test_s116_pooled_ingame_a2.py:14 | data/cache/eval_gate/s116_pooled_ingame_2026-09-03_rerun.csv | 1 | 1 |
| tests/platformkit/ingame/test_s92_nba_lineup_dynamic_a2.py:8 | data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_rated.csv | 1 | 1 |
| tests/platformkit/ingame/test_s94_nba_early_shrinkage_a2.py:8 | data/cache/eval_gate/s94_nba_early_shrinkage_2026-09-03.csv | 1 | 1 |
| tests/platformkit/ingame/test_s96_nba_overreaction_a2.py:8 | data/cache/eval_gate/s96_nba_overreaction_2026-09-03.csv | 1 | 1 |
| tests/platformkit/ingame/test_s97_nba_sensor_fusion_a2.py:8 | data/cache/eval_gate/s97_nba_sensor_fusion_2026-09-03.csv | 1 | 1 |
| tests/platformkit/live_edge/test_foul_attr.py:28 | SIM2_POSSESSIONS_PATH | 1 | 1 |
| tests/platformkit/live_edge/test_paper_bridge.py:133 | data/omni/live_edge/shadow/2026-07-14.jsonl | 1 | 1 |
| tests/platformkit/live_edge/test_player_attr.py:36 | SIM2_POSSESSIONS_PATH | 1 | 1 |
| tests/platformkit/live_edge/test_slate_trader.py:111 | data/cache/line_history/tennis/2026-07-14.jsonl | 1 | 1 |
| tests/platformkit/live_edge/test_wnba_wc_wire.py:111 | data/cache/line_history/wnba/2026-07-14.jsonl | 1 | 1 |
| tests/platformkit/live_edge/test_wnba_wc_wire.py:125 | data/cache/line_history/soccer_intl/2026-07-14.jsonl | 1 | 1 |
| tests/platformkit/test_asof_common.py:170 | tennis asof_hold corpora | 1 | 1 |
| tests/platformkit/test_asof_quarter_shape.py:122 | data/domains/basketball_nba/linescores.parquet | 1 | 1 |
| tests/platformkit/test_clv_ledger_write_path_guard.py:147 | real CLV ledger path | 1 | 1 |
| tests/platformkit/test_feature_spec_nba.py:150 | data/domains/basketball_nba/games.parquet | 1 | 1 |
| tests/platformkit/test_feature_spec_tennis.py:86 | data/domains/tennis/matches.parquet | 1 | 1 |
| tests/platformkit/test_gate_run_tennis_setdetail.py:112 | gr._ATP; gr._WTA | 1 | 1 |
| tests/platformkit/test_mlb_parity.py:117 | data/domains/mlb/games.parquet | 1 | 1 |
| tests/platformkit/test_omni_signals_orphan_asof.py:63 | data/cache/signals/<name>.parquet | 1 | 1 |
| tests/platformkit/test_omni_signals_orphan_asof.py:84 | data/cache/signals | 1 | 1 |
| tests/platformkit/test_orphan_hb_check.py:87 | daemon_heartbeats directory | 1 | 1 |
| tests/platformkit/test_soccer_intl_parity.py:117 | data/domains/soccer_intl/results.parquet | 1 | 1 |
| tests/platformkit/test_soccer_parity.py:112 | data/domains/soccer/matches.parquet | 1 | 1 |

S165 addition: `tests/platformkit/foundry/test_ingame_grammar_nba_pairs.py`
now requires data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv with the
same worktree-skip/main-repository-fail behavior.

## Worktree verification

Each touched file was run once, one file per command. Results: all commands
completed without failures. Files whose evidence is absent skipped only their
evidence-dependent test; files with evidence present ran their unchanged test
count. No module, FWER ledger, register, or assertion text was changed.

## Main-repository reproduction

NOT VERIFIED: this lane is a worktree. In `C:\Users\neelj\nba-ai-system`, run
each command separately and confirm the before/after test-item count is equal
and the result has zero new skips:

```text
python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q
python -m pytest scripts/platformkit/combo/test_corpus_cache_soccer_enrich.py -q
python -m pytest scripts/platformkit/data_frontier/test_milb_statsapi.py -q
python -m pytest scripts/platformkit/improve/test_clv_lifecycle_reconcile.py -q
python -m pytest scripts/platformkit/ingame/test_hist_mlb_forward_gate.py -q
python -m pytest scripts/platformkit/ingame/test_hist_mlb_outcome_resolver.py -q
python -m pytest scripts/platformkit/ingame/test_ingame_sigma_serve.py -q
python -m pytest scripts/platformkit/ingame/test_nba_logistic_pricer.py -q
python -m pytest scripts/platformkit/intel_validation/test_claims_validator_pairkey.py -q
python -m pytest scripts/platformkit/intel_validation/test_tennis_claims_v4.py -q
python -m pytest scripts/platformkit/intel_validation/test_verdict_claim_check.py -q
python -m pytest scripts/platformkit/intel_validation/test_verdict_claims_validator.py -q
python -m pytest scripts/platformkit/interaction_factory/test_builders_soccer_setpiece.py -q
python -m pytest scripts/platformkit/interaction_factory/test_builders_tennis_chain.py -q
python -m pytest scripts/platformkit/pod_sprint/test_player_value_asof.py -q
python -m pytest scripts/platformkit/signals/test_market_coherence.py -q
python -m pytest scripts/platformkit/signals/test_market_micro_asof.py -q
python -m pytest scripts/platformkit/vault_feed/test_vault_feed.py -q
python -m pytest scripts/platformkit/test_clv_ledger_betid_backfill.py -q
python -m pytest scripts/platformkit/test_clv_ledger_status_append.py -q
python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba_pairs.py -q
python -m pytest scripts/platformkit/test_pm_best_trades.py -q
python -m pytest tests/platformkit/analytics_verify/test_attribution.py -q
python -m pytest tests/platformkit/analytics_verify/test_regrader.py -q
python -m pytest tests/platformkit/analytics_verify/test_sentinel.py -q
python -m pytest tests/platformkit/canary/test_stack_canary.py -q
python -m pytest tests/platformkit/combo/test_fwer_families_bh.py -q
python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba.py -q
python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q
python -m pytest tests/platformkit/foundry/test_ingame_screen_soccer_a2.py -q
python -m pytest tests/platformkit/ingame/test_s103_nba_sigma_a2.py -q
python -m pytest tests/platformkit/ingame/test_s115_ingame_models_a2.py -q
python -m pytest tests/platformkit/ingame/test_s116_pooled_ingame_a2.py -q
python -m pytest tests/platformkit/ingame/test_s92_nba_lineup_dynamic_a2.py -q
python -m pytest tests/platformkit/ingame/test_s94_nba_early_shrinkage_a2.py -q
python -m pytest tests/platformkit/ingame/test_s96_nba_overreaction_a2.py -q
python -m pytest tests/platformkit/ingame/test_s97_nba_sensor_fusion_a2.py -q
python -m pytest tests/platformkit/live_edge/test_foul_attr.py -q
python -m pytest tests/platformkit/live_edge/test_paper_bridge.py -q
python -m pytest tests/platformkit/live_edge/test_player_attr.py -q
python -m pytest tests/platformkit/live_edge/test_slate_trader.py -q
python -m pytest tests/platformkit/live_edge/test_wnba_wc_wire.py -q
python -m pytest tests/platformkit/test_asof_common.py -q
python -m pytest tests/platformkit/test_asof_quarter_shape.py -q
python -m pytest tests/platformkit/test_clv_ledger_write_path_guard.py -q
python -m pytest tests/platformkit/test_feature_spec_nba.py -q
python -m pytest tests/platformkit/test_feature_spec_tennis.py -q
python -m pytest tests/platformkit/test_gate_run_tennis_setdetail.py -q
python -m pytest tests/platformkit/test_mlb_parity.py -q
python -m pytest tests/platformkit/test_omni_signals_orphan_asof.py -q
python -m pytest tests/platformkit/test_orphan_hb_check.py -q
python -m pytest tests/platformkit/test_soccer_intl_parity.py -q
python -m pytest tests/platformkit/test_soccer_parity.py -q
```

## Contract self-check

B1-B10: no metric excludes a selected escape; schema, gate values, production
deployment, modules, ledger, and register are unchanged. Q1, Q2, Q4, Q5, and
Q9 are not applicable because S172 scores no model or corpus. Q3 is unchanged.
Q6 is satisfied: this memo uses calibration language only and contains no
financial performance language.

## New gap

Four previously touched test files exceed 300 LOC: `test_clv_lifecycle_reconcile.py`
(485), `test_ingame_sigma_serve.py` (398), `test_clv_ledger_betid_backfill.py`
(410), and `test_clv_ledger_status_append.py` (594). Tests are exempt from the
module rail; this pass does not trim them.
