# m2_family Multitask MLP — Rollout Runbook (R31_X3 / R32_Y1)

## What it is

R31_X3 trained a multitask MLP for the four m2_family game-level targets
(`total`, `spread`, `home_pts`, `away_pts`) and saved it to
`data/models/m2_family_mlp/`. R31_X3 also wired the dispatch:
`src/prediction/game_models.py::_predict_m2_family()` checks an env flag
and routes to either the legacy multi5 ensemble or the MLP.

The MLP wins all 4 targets on the 2025-26 holdout vs the multi5 ensemble:

| target     | multi5 MAE | MLP MAE | delta    |
|------------|-----------:|--------:|---------:|
| total      | (baseline) | -1.80%  | improved |
| spread     | (baseline) | -2.85%  | improved |
| home_pts   | (baseline) | -1.90%  | improved |
| away_pts   | (baseline) | -6.15%  | improved |

All 8 head-to-head walk-forward folds favour the MLP.

## How to enable

Set the env var **before** importing `src.prediction.game_models`:

```bash
# Linux / macOS
export M2_FAMILY_USE_MLP=1

# Windows PowerShell
$env:M2_FAMILY_USE_MLP = "1"
```

Truthy values (case-insensitive, whitespace-trimmed): `1`, `true`, `yes`.
Everything else (including `0`, `false`, `no`, empty string, unset) routes
to the legacy multi5 ensemble. The flag is read fresh on every call to
`_predict_m2_family`, so flipping it mid-session works without restart.

### Per-process vs global

For a single one-off prediction, prefer the per-process env var (the
example above). To enable for an entire shell session, set it in your
shell rc / PowerShell profile. **Do not** bake `M2_FAMILY_USE_MLP=1` into
the bot loop, retrain scripts, or any commit until the prod readiness
review approves the rollout — see "Rollout checklist" below.

## Who is affected

Every consumer that eventually calls `src.prediction.game_models.predict()`:

| consumer | how | affected |
|---|---|---|
| `api/predictions_router.py` | via `game_orchestrator.predict_game` | yes |
| `scripts/run_daily_slate.py` | direct call at line 306 | yes |
| `src/prediction/player_props.py` | direct call at line 1562 | yes (one game-level feature in the player-prop feature row) |
| `src/pipeline/prediction_orchestrator.py` | direct call at line 939 | yes |
| `src/prediction/game_orchestrator.py` | direct call at line 116 | yes |
| `scripts/predict_slate.py` | player-prop only | no |
| `scripts/build_prediction_cache.py` | player-prop only | no |
| `scripts/live_recommendation_engine.py` | reads pre-built parquet | no |

Validation matrix: `data/cache/probe_R32_Y1_results.json` (regen with
`python scripts/improve_loop/probe_R32_Y1_mlp_wirethrough.py`).

## Expected behaviour

Sample game `0022500001` (HOU @ OKC 2025-10-21):

| target | multi5 | MLP | delta |
|---|---:|---:|---:|
| total_est    | 217.1 | 216.2 | -0.9 |
| spread_est   | 4.7   | 4.2   | -0.5 |
| home_pts_est | 108.8 | 110.5 | +1.7 |
| away_pts_est | 108.3 | 105.3 | -3.0 |

`confidence` stays `"m2_family"`, but `ensemble` switches from
`"M2_family_v1 (5 models × 4 targets, equal-weight)"` to
`"M2_family_mlp_v1_R31_X3 (multitask MLP, 3-seed ensemble)"`.

## Cache behaviour

The R21_N5 prediction cache
(`data/cache/m2_family_predictions_cache.json`) is keyed by the multi5
model directory's mtime. The MLP path **bypasses this cache entirely** —
it does not read it (to avoid serving stale multi5 values when the MLP is
on) and it does not write to it (to avoid overwriting valid multi5 cache
entries with MLP values). This means MLP predictions cost the full
forward-pass time per request; if that becomes a hot spot, add a parallel
`m2_family_mlp_predictions_cache.json` keyed by `.pt` mtimes.

## Rollback

To roll back: unset the env var (or set `M2_FAMILY_USE_MLP=0`). No data
on disk changes; the MLP artifacts stay at `data/models/m2_family_mlp/`
but are inert.

```bash
unset M2_FAMILY_USE_MLP                       # bash
Remove-Item env:M2_FAMILY_USE_MLP             # PowerShell
```

To purge the MLP artifacts as well (only if they're regressing):

```bash
rm -rf data/models/m2_family_mlp/             # bash
Remove-Item -Recurse -Force data/models/m2_family_mlp/   # PowerShell
```

The dispatch then falls through to multi5 on any caller that had the flag
on, because `_try_load_m2_family_mlp` returns False when the manifest is
missing and `_predict_m2_family_mlp` returns None, which the predict()
caller treats the same as a multi5 miss.

## Rollout checklist

- [ ] R32_Y1 probe green (`probe_R32_Y1_mlp_wirethrough.py` ship_gate true)
- [ ] R32_Y1 tests green (`pytest tests/test_R32_Y1_mlp_wirethrough.py`)
- [ ] R27_T5 e2e smoke green in BOTH flag states (`status: PASS`, 12/12)
- [ ] Backtest harness profitable (or at least no worse than multi5) with
      MLP on across the historical bet log
- [ ] Drift watchlist: alert on `|MLP_total - multi5_total| > 8 pts` for
      any game on the day's slate (catches scaler corruption)
- [ ] Bot loop env var added to `.claude/commands/start-day.md` (NOT
      committed until all above are checked)

## Who to alert when it breaks

If predictions look wrong after enabling the flag:

1. Check `data/cache/probe_R32_Y1_results.json` — re-run the probe. If
   `ship_gate_overall` flips to false, the wire-through is broken.
2. Check `data/models/m2_family_mlp/manifest.json` exists and lists 3
   seed models (mlp_s42.pt, mlp_s7.pt, mlp_s100.pt).
3. Check `data/models/m2_family_mlp/feature_scaler.joblib` is loadable
   via joblib (corrupted scalers are the #1 silent-fail mode).
4. If the issue is the MLP regressing on a specific game (not a wire
   bug), file under `vault/Models/Model Performance.md` and roll the
   flag back to off pending a re-train.

## References

- Wire: `src/prediction/game_models.py:394-587` (env flag + MLP loader +
  predictor) and `:680-687` (dispatch inside `_predict_m2_family`).
- Probe (training): `scripts/improve_loop/probe_R31_X3_m2_multitask_mlp.py`.
- Probe (validation): `scripts/improve_loop/probe_R32_Y1_mlp_wirethrough.py`.
- Tests (training): `tests/test_R31_X3_multitask_mlp.py`.
- Tests (wire-through): `tests/test_R32_Y1_mlp_wirethrough.py`.
