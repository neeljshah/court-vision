# S229 matchup player vs defender screen

Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
Attempt 2 preregistration: docs/evidence/harness/S229_ATTEMPT2_PREREG_2026-09-04.md; pre-seal SHA-256: 6ca56099a0bac5067f68740ae7d9ac2bdbf1d2c6fa71e75728ace6e1210ef1e7.
Machine: local worktree CPU; all inputs are local read-only stores below 300 MB.
Atlas half: BLOCKED-ON-S223 and never opened or joined.

## ATTEMPT 2

| verifier correction | candidate 60f290074 | Attempt 2 |
| --- | --- | --- |
| direct DEF-OPP join coverage | not reported before target merge | reported before target merge |
| preregistration | absent | sealed before fresh scoring |
| OOS date folds | no purge or symmetric embargo | cluster purge plus symmetric one-day embargo |

## Coverage table (printed before metrics)

| step | rows | share of 99,498 |
| --- | ---: | ---: |
| sidecar universe | 99498 | 100.0000 pct |
| null twin, identical 17-column shape | 99498 | 100.0000 pct |
| non-null scheme deviation | 97995 | 98.4894 pct |
| non-null opponent PTS split | 79648 | 80.0499 pct |
| direct DEF-OPP sidecar join before target merge | 79597 | 79.9986 pct |
| target-readable DEF-OPP join | 69345 | 69.6949 pct |
| both plus game cluster bridge | 69345 | 69.6949 pct |
| scorable finite joined subset | 69339 | 69.6888 pct |

Rows lost are named above. The residual target surface has 77867 OOF-readable rows, so 21631 of the 99,498 sidecar rows lack an archived OOF PTS expectation.
Full target-readable PTS base rate 10.800557; joined subset PTS base rate 11.332410.
Full target-readable residual spread 5.944951; joined subset residual spread 6.052213.

## Matched walk-forward result

Baseline uses [player_pts_vs_HELP_DEF_diff, player_opp_pts_diff_vs_overall]; candidate uses [player_pts_vs_HELP_DEF_diff, player_opp_pts_diff_vs_overall, scheme_x_opponent]. The assertion CANDIDATE_COLUMNS[:-1] == BASE_COLUMNS passed.
All folds train strictly before test game_date with a cluster purge and symmetric one-day embargo. Metrics are game-equal-weighted from the archived paired series; positive delta favors the added interaction.
Baseline: RMSE 6.021814 MAE 4.643778
Real interaction: RMSE 6.021847 MAE 4.643862 delta_rmse -0.000033 [-0.000188, 0.000116] delta_mae -0.000084 [-0.000222, 0.000046]
Null-twin interaction: RMSE 6.021754 MAE 4.643570 delta_rmse 0.000061 [-0.000206, 0.000331] delta_mae 0.000208 [-0.000054, 0.000486]
Game clusters 3049; n_eff 2921.877.

Verdict: SCREEN NULL. This is an offline calibration measurement only; no charge, ledger, register, deployment, or production wiring.

## NOT VERIFIED

- No production behavior, deployment, or external outcome is verified by this local screen.
- The atlas half remains BLOCKED-ON-S223 and was not evaluated.

## Input inventory

- data/intelligence/player_def_archetype_sidecar.parquet, 9,812,855 bytes, player_id plus game_date.
- data/intelligence/player_def_archetype_sidecar_null.parquet, 9,799,223 bytes, player_id plus game_date.
- data/intelligence/player_opp_splits_sidecar.parquet, 5,013,638 bytes, player_id plus game_date.
- data/intelligence/pts_decomposition_predictions.parquet, 3,460,398 bytes, player_id plus date; archived OOF PTS expectation and target.
- data/intelligence/schedule_strength_7d.parquet, 1,025,217 bytes, game cluster bridge.

Differential archive: docs/evidence/harness/S229_matchup_player_vs_defender_per_game_residuals.csv; it embeds the Attempt 2 preregistration path and seal.
