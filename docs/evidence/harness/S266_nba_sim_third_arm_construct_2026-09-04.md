# S266 NBA simulator third-arm construct acceptance

Spec: `docs/evidence/tracking/specs/S266_spec.md`.
Contract self-check: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B
and Q1-Q9.

## Scope, machine, and premise

This ran locally in `C:/Users/neelj/nba-track-a17` on the memory-limited
laptop using `C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe`. Nothing
was copied to a pod before this result. No register, ledger, K, feature flag,
or `data/` file was written.

The S266 binding before-condition was re-run before the CHANGE step and printed:

```text
PREMISE cluster_qualification qualifying=355/661
PREMISE archive ticks=79554 games=661
PREMISE market_brier=0.142876712852 recal_null_brier=0.144293050901 market_less_than_null=True
```

Inputs opened one store at a time were:

| full path | bytes | resolution | SHA-256 before and after |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a17/data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` | 38,630,145 | tabular CSV, 79,554 ticks / 661 clusters | `f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6` |
| `C:/Users/neelj/nba-track-a17/docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv` | 36,282 | tabular CSV, 661 clusters | `826f778104453f75bdf1e7517c2f0650bfa0a322318a346ca3a26df1575f487e` |
| `C:/Users/neelj/nba-track-a17/docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet` | 565,095 | tabular Parquet, 76,820 rows | `0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6e6` |
| `C:/Users/neelj/nba-track-a17/docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet` | 22,677 | tabular Parquet, 1,434 rows | `42932c26f308097afbc1187aed2e9e8e2efb176258f213e1c5e492a270e5c00e` |

All four before/after hashes are equal. The aggregate tracked `src/` hash was
`ca212a89b0dcef6936c0b66ada99c4cba1389ef1f6b83f4d2d81062e2886c260`
before and after the scorer assertion.

## Sealed construction

The pre-score preregistration is
`docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04_preregistration.md`,
committed alone as `078718c6734156e5469a2f2ac76500a5af1dac32`. Its LF staged-byte
prefix seal is `9b52164a6f2d8f2d501573c4e35fdd91bd8c1c269c61c674f35f250e3a6bbd55`.
After commit, `git show HEAD:docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04_preregistration.md | head -n 81 | sha256sum`
returned that same SHA-256.

Seed `2561001` selected the sealed 30 whole-game clusters and six frozen
elapsed-second targets `[120, 600, 1080, 1560, 2040, 2520]`, for exactly 180
unique game-target ticks. All three arms were scored on every sealed tick:
market `market_prob`, incumbent recalibrated-null `p_null`, and the
snapshot-only simulator. The shared `cpcv_evaluate` route used 8 chronological
groups, one test group per split, strict redaction, the shared 48-hour
same-team purge and 3-day same-matchup purge, plus a symmetric nonzero
3-calendar-day embargo.

Every unavailable simulator rate was filled through
`date_mean_ft_rate_q50_scaled_baseline` from the corresponding snapshot-date
league mean. The 180 named fill records cover these fields:
`ast_per_min, blk_per_min, dreb_per_min, fg3_pct, fg_mid, fg_paint, fg_rim,
ft_pct, ft_share, height, int_d, oreb_per_min, perim_d, pf_per_min,
self_create, stl_per_min, supp, tov_share, use_per_min, z_3, z_mid, z_paint,
z_rim`.

## Result and reproduction

| arm | tick-weighted Brier | 10-bin ECE |
|---|---:|---:|
| market | 0.180282738889 | 0.108594444444 |
| recalibrated-null | 0.178516135761 | 0.115852521417 |
| simulator | 0.255904134115 | 0.135156250000 |

Simulator improvement over recalibrated-null is `-0.077387998354`; the
game-clustered 95 percent CI is `[-0.156878091676, 0.002102094968]`. The fixed
`+0.004` calibration bar is unchanged. Verdict and legacy status are both
`BEHIND`.

The scorer printed `RSS BEFORE SCORING 154.66 MB`; its peak callback RSS was
485.750000 MB, below the 600 MB memory limit. The module also prints the
post-score RSS guard before writing outputs. No full-set call was made.

Independent recomputation from the archived 180-row tick series reproduced all
three Brier and ECE values above and the 30-cluster paired-loss CI exactly. Q9
artifacts are:

- `docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04/S266_selected_tick_series.csv` (53,203 bytes)
- `docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04/S266_per_game_paired_loss_series.csv` (2,970 bytes)
- `docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04/S266_summary.json` (87,562 bytes)

Compatibility outputs with the S256 construct names are retained beside the
primary outputs. `select_sample`, `price_snapshot_only`, and `evaluate` alias
`select_games`, `price`, and `score`; summary `status` aliases `verdict`; the
focused test exercises these aliases and the archived paired loss.

## Contract self-check

- B1/B7/B9: the sealed whole-game sample is outcome-independent, not a head
  slice, and has 30 unique clusters / 180 unique state keys.
- B2/B6: compatibility aliases and output aliases are additive; current reader
  survey found no production importer, and the focused test imports the module.
- B3/B4: no evidence gate, quarantine, or claim lifecycle is introduced.
- B5: local-only execution; no pod copy occurred.
- B8: source data are strictly prior-date S255 snapshots; no fitted outcome
  residual is used as evidence. B10/Q3: the bar remains `+0.004`.
- Q1: the committed LF preregistration seal predates scoring. Q2: this
  uncharged construct did not read K or change a ledger. Q4: all simulator
  probabilities use shared CPCV with purge and symmetric embargo. Q5 is not
  applicable to the `BEHIND` result. Q6 uses calibration language only. Q7
  meets the sampled rail. Q9 archives both tick and per-game differential data.

## Limitation

This is construct-scale evidence for 30 sealed clusters, not a 355-cluster
claim. The stage-2 pod row is the only route to a 355-cluster measurement.

Validation: `python -m pytest scripts/platformkit/ingame/test_s256_nba_sim_engine_v3.py -q -p no:cacheprovider` -> `1 passed`.
