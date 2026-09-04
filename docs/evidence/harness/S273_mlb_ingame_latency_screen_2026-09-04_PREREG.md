# S273 MLB in-game latency screen preregistration

gap: S273
sealed_at_utc: 2026-09-04T00:00:00Z
machine: C:\\Users\\neelj\\nba-track-a17 (local worktree; resolved S254 cache is readable here)
input_store: data/cache/ingame_grade_joined
input_store_binding: The S254 memo's a13 prefix is resolved to this worktree root.
source_denominator: 47104 evaluated ticks, 14611 informative ticks, 158 informative game clusters
source_s254_summary: docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary.json
s213_latency_source: docs/evidence/harness/S213_ingame_latency_summary_2026-09-04.json
s213_delays_seconds: none=0.0, p50=41.0, p90=102.0
route: scripts/platformkit/ingame/s254_mlb_phase_recal_fwer_sealed.py
route_sha256_before_s273: bac7a7e6da8e290646c219729db6f17f822056464b0617cc3d0b976ae0edf142
comparison: Apply only the named delay to each record ts before S254 states() builds state_ts; state shifts later relative to price.
arms: none,p50,p90
family: early|leading,early|leading_big,early|tied,early|trailing,early|trailing_big,late|leading,late|leading_big,late|tied,late|trailing,late|trailing_big,mid|leading,mid|leading_big,mid|tied,mid|trailing,mid|trailing_big
evaluator: scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate
split_design: n_groups=8, n_test_groups=1, strict_redaction=true
purge_and_embargo: existing S254 purge plus symmetric nonzero 1-day embargo
bh_q: 0.05
primary_metric: pooled 15-bucket BH-survivor count and largest single-bucket delta (Brier incumbent minus candidate) with game-clustered 95 pct CI
minimum_clusters_per_arm: 30
acceptance_bar: Report all 15 buckets for each arm. Success is that the near-null improvement does not grow at either delay, or the p90 arm largest delta and survivors are less than or equal to no-delay; vanishing is permitted.
must_not_move: S254 summary.json, paired_loss.csv, bucket design, embargo, split design, +0.004 bar, backtest_fwer.jsonl, K, flags, data/registry
outputs: docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04.md; docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_summary.json; docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_none_paired_loss.csv; docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_p50_paired_loss.csv; docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_p90_paired_loss.csv
test: tests/platformkit/test_s273_mlb_ingame_latency_screen.py
scoring_starts_after_commit: true
seal_sha256: c00dc738ec7882ac50cec06eb8d82b448105dd721cb3948fb918cbce75e53da3
