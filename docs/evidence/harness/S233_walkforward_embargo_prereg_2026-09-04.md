# S233 Walk-Forward Embargo Prereg

## Verdict

FALSIFIED at premise step 0. No implementation, fixture JSON, proposed
replacement, or test was created. Q8 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md` requires this close when a
premise is false.

## Scope and machine

Static source survey only, run locally in
`C:\Users\neelj\nba-track-a17` because S233 step 0 is a repository premise
check. No data store, video, pod, ledger, register, or external input was
opened. The direct inputs were:

```text
docs/evidence/tracking/specs/S233_spec.md, 3939 bytes, no resolution
docs/evidence/tracking/VERIFIER_CONTRACT.md, 11650 bytes, no resolution
scripts/platformkit/eval_gate/cpcv_engine.py, 5341 bytes, no resolution
scripts/platformkit/eval_gate/stacker.py, 21095 bytes, no resolution
```

## Reproduction

The full source-root scan, including tracked and untracked files, used:

```powershell
$platformPaths = (Get-ChildItem -Path 'scripts/platformkit' -Recurse -File -Filter '*.py').FullName
Select-String -Path $platformPaths -Pattern '^[\s]*def[\s]+walk_forward\b' |
    Select-Object -ExpandProperty Path -Unique
Select-String -Path $platformPaths -SimpleMatch 'seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()'
```

It produced 18 `walk_forward` definition files, rather than 17:

```text
scripts/platformkit/nfl_game_model.py
scripts/platformkit/nfl_run_pass.py
scripts/platformkit/analytics_showcase/market_strength_atlas.py
scripts/platformkit/eval_gate/s103_nba_sigma.py
scripts/platformkit/eval_gate/s115_ingame_models.py
scripts/platformkit/eval_gate/s116_pooled_ingame.py
scripts/platformkit/eval_gate/s80_player_grain_screen.py
scripts/platformkit/eval_gate/s84_nba_lineup_at_tick.py
scripts/platformkit/eval_gate/s92_nba_lineup_dynamic.py
scripts/platformkit/eval_gate/s94_nba_early_shrinkage.py
scripts/platformkit/eval_gate/s96_nba_overreaction.py
scripts/platformkit/eval_gate/s97_nba_sensor_fusion.py
scripts/platformkit/eval_gate/s98_nba_better_prior.py
scripts/platformkit/eval_gate/walkforward.py
scripts/platformkit/ingame/ingame_layer_gate_nba.py
scripts/platformkit/ingame/ingame_sp_fatigue_velo_gate_mlb.py
scripts/platformkit/ingame/sp_fatigue_gate_mlb.py
scripts/platformkit/ingame/surface_hold_gate.py
```

It produced four exact duplicate seal sites, rather than five:

```text
scripts/platformkit/eval_gate/s58_clamp_family_trial.py:222
scripts/platformkit/eval_gate/s58_e2_slice_trial.py:87
scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py:129
scripts/platformkit/eval_gate/stacker.py:202
```

`stacker.py:261` computes a seal from `PREREG`, not from `Path(prereg_path)`,
so it is not the claimed verbatim fifth duplicate.

## Route survey

`scripts/platformkit/eval_gate/cpcv_engine.py` was inspected directly. Its
`_purged` helper applies a symmetric calendar-day condition with
`abs(train_ts - test_ts)`, plus imported matchup and team conditions. Its
exact-import callers are:

```text
scripts/platformkit/hedge_trial_runner.py
scripts/platformkit/test_hedge_trial_arms.py
scripts/platformkit/eval_gate/s58_clamp_family_trial.py
scripts/platformkit/eval_gate/s58_t2_first_trial.py
scripts/platformkit/eval_gate/stacker.py
scripts/platformkit/eval_gate/test_cpcv_engine.py
scripts/platformkit/foundry/charge_path_followups.py
```

All import callers of `scripts/platformkit/eval_gate/walkforward.py` are:

```text
scripts/platformkit/calibration_record.py
scripts/platformkit/reliability_diagram.py
scripts/platformkit/self_improve.py
scripts/platformkit/test_hedge_trial_arms.py
scripts/platformkit/edge_engine/score.py
scripts/platformkit/edge_engine/test_score.py
scripts/platformkit/eval_gate/baseline.py:86
scripts/platformkit/eval_gate/backtest_runner.py
scripts/platformkit/eval_gate/catalog_rescreen.py
scripts/platformkit/eval_gate/combo_search.py
scripts/platformkit/eval_gate/cpcv_engine.py
scripts/platformkit/eval_gate/pbo.py
scripts/platformkit/eval_gate/run_gate.py:35
scripts/platformkit/eval_gate/s112_rescore_vs_close.py
scripts/platformkit/eval_gate/schema.py:13
scripts/platformkit/eval_gate/student_gate.py
scripts/platformkit/eval_gate/test_close_join_soccer.py
scripts/platformkit/eval_gate/test_cpcv_engine.py
scripts/platformkit/eval_gate/test_leak_contract.py
scripts/platformkit/eval_gate/test_redteam2.py
scripts/platformkit/eval_gate/test_student_gate.py
scripts/platformkit/foundry/family_combo_screen.py
scripts/platformkit/foundry/tiers.py
scripts/platformkit/governance/leak_audit.py:33
scripts/platformkit/market_coverage/edge_finder.py
scripts/platformkit/market_coverage/test_edge_finder.py
tests/platformkit/foundry/test_family_combo_screen.py
```

## Consequence

The six-cell construct and its conditional fixture files are not applicable:
their required change depends on a true step-0 premise. No scored comparison
was run. The specified shared routes, thresholds, ledger, register, and data
paths were not changed.

## Verifier self-check

- B1-B10: no metric, schema, threshold, deployment, or route change was made.
- Q1-Q6 and Q9: no scoring or charged trial occurred.
- Q7: no construct was entered because the premise failed.
- Q8: satisfied by the full-source remeasurement and this FALSIFIED memo.

## NOT VERIFIED

- The six-cell construct was not built.
- The two fixture JSON files were not created.
- The focused test `scripts/platformkit/eval_gate/test_walkforward_embargo_prereg.py` was not created or run.
- The scoring comparison was not run.
