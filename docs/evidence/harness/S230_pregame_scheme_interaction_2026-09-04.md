# S230 pregame scheme interaction screen

Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
Preregistration: docs/evidence/harness/S230_pregame_scheme_interaction_prereg_2026-09-04.json; seal SHA-256: f690d620ce3baccec2a92d2fad0243d412ec96620f7ac66613bc80c2241806ec.
Machine: local worktree CPU; read-only local stores; no data writes, ledger, register, or deployment.

## Census before metrics

matchup_grid rows 4900; date range 2024-10-22 through 2026-04-12; paired home-away games 2450.
gate_corpus_nba_close rows joined 1814; joined rows with a pregame p_close 220; rows dropped after pairing 0.

## Model-relative calibration (not market-relative)

S108 reference: elastic net Brier difference +0.001360 at n 619; every coefficient was zero in 20 of 23 folds.
All interaction probabilities were produced by scripts.platformkit.eval_gate.walkforward.walk_forward with its 48-hour purge and 3-day symmetric embargo. The callback fits only its supplied training states and uses logit(p_base) with coefficient fixed at one.
| arm | ECE | Brier | log-loss |
| --- | ---: | ---: | ---: |
| incumbent | 0.053328 | 0.210960 | 0.609781 |
| interaction | 0.026757 | 0.213678 | 0.632114 |
| incumbent minus interaction, clustered 95 pct CI | [0.012557, 0.026571] | [-0.011861, 0.001677] | [-0.077162, 0.004029] |
Model-relative corpus_unit clusters 2; n_eff 2.

### Ten-bin reliability: incumbent, all joined rows

| bin | n | mean probability | observed frequency |
| --- | ---: | ---: | ---: |
| 0.0-0.1 | 1 | 0.090491 | 0.000000 |
| 0.1-0.2 | 25 | 0.158069 | 0.040000 |
| 0.2-0.3 | 100 | 0.258242 | 0.170000 |
| 0.3-0.4 | 180 | 0.353668 | 0.311111 |
| 0.4-0.5 | 251 | 0.453594 | 0.378486 |
| 0.5-0.6 | 301 | 0.552401 | 0.465116 |
| 0.6-0.7 | 368 | 0.649323 | 0.608696 |
| 0.7-0.8 | 325 | 0.751864 | 0.716923 |
| 0.8-0.9 | 220 | 0.841835 | 0.827273 |
| 0.9-1.0 | 43 | 0.920346 | 0.860465 |

### Ten-bin reliability: interaction, all joined rows

| bin | n | mean probability | observed frequency |
| --- | ---: | ---: | ---: |
| 0.0-0.1 | 19 | 0.057244 | 0.315789 |
| 0.1-0.2 | 70 | 0.162706 | 0.114286 |
| 0.2-0.3 | 137 | 0.257251 | 0.313869 |
| 0.3-0.4 | 227 | 0.346617 | 0.365639 |
| 0.4-0.5 | 261 | 0.450335 | 0.383142 |
| 0.5-0.6 | 296 | 0.550201 | 0.543919 |
| 0.6-0.7 | 327 | 0.648686 | 0.648318 |
| 0.7-0.8 | 274 | 0.750431 | 0.748175 |
| 0.8-0.9 | 158 | 0.842400 | 0.810127 |
| 0.9-1.0 | 45 | 0.931708 | 0.866667 |

## Pregame close limit

This subset uses only close_source=pregame_last_tick_before_commence and is not pooled with first-inplay rows.
Pregame close rows 220; n_eff 2; status NOT SCORABLE. No market-relative metric is published at this limit.

Ten-bin rule: np.linspace(0, 1, 11); [lo,hi) except final [lo,hi].
Reliability bin counts and predictions are reproducible from the CSV under that rule.

## Evidence and verdict

Per-row paired-loss archive: docs/evidence/harness/S230_pregame_scheme_interaction_2026-09-04_predictions.csv.
Verdict: CLOSED AT LIMIT. This screen makes calibration measurements only.

## Input inventory

- C:/Users/neelj/nba-track-a16/data/intelligence/matchup_grid.parquet; 141940 bytes; parquet team-game grain, 4900 rows.
- C:/Users/neelj/nba-track-a16/data/cache/combo/gate_corpus_nba_close.parquet; 217484 bytes; parquet event-game grain, 1814 rows.
- data/intelligence/archetype_scheme_interactions.parquet; 10084 bytes; parquet 108-row schema-only hypothesis freeze, never joined or fitted.
- data/intelligence/position_scheme_interactions.parquet; 24604 bytes; parquet 315-row schema-only hypothesis freeze, never joined or fitted.
- Code identity: scripts/platformkit/s230_pregame_scheme_interaction.py SHA-256 fc91bd2c59567c7cbd6e0a8a4cc07edc6eddc8ebb71ea1633806140154890027.
