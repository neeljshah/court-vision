# Inplay Win-Probability OOS Validation — 2026-05-27

**Models validated:** `inplay_winprob_endq1.lgb`, `inplay_winprob_endq2.lgb`, `inplay_winprob_endq3.lgb`
**Trained at:** 2026-05-27T22:40:55Z (probe `R10_M5_inplay_winprob`)
**Validation script:** `scripts/oos_validate_inplay_2026_05_27.py`
**Results JSON:** `data/cache/inplay_oos_validation_2026_05_27.json`
**Method:** 4-fold expanding-window walk-forward, fresh LightGBM re-fits on each fold's training slice using the EXACT hyperparams + feature list from each `_meta.json`. The production `.lgb` files were never loaded for prediction (they were trained on the full data, so any prediction on training-period rows is leaked). Seed = 42.

## Headline

| Snapshot | In-sample Brier (leaked) | OOS Brier (mean ± std) | OOS AUC | OOS Acc | vs corrected pregame baseline | Verdict |
|----------|--------------------------|-------------------------|---------|---------|-------------------------------|---------|
| endQ1    | 0.1026                   | **0.2221** ± 0.0045     | 0.7161  | 0.671   | -0.0199 (4/4 folds)           | PASS    |
| endQ2    | 0.0695                   | **0.1860** ± 0.0070     | 0.8039  | 0.732   | -0.0560 (4/4 folds)           | PASS    |
| endQ3    | 0.0301                   | **0.1354** ± 0.0129     | 0.9012  | 0.806   | -0.1067 (4/4 folds)           | PASS    |

All three models beat the polarity-corrected pregame baseline at 4/4 folds with tight std. The in-sample Briers were heavily inflated by leakage — true OOS is ~2× to ~4.5× higher than the meta JSON in-sample numbers, but still strong.

## Critical finding — pregame baseline polarity is INVERTED

`season_games.sim_win_prob` (used as `pregame_win_prob` feature) is anti-correlated with home wins on the full dataset:

- Global AUC of `sim_win_prob → home_won`: **0.434**
- Brier of as-encoded baseline: 0.2665 (constant-prior baseline: 0.2493)

The as-encoded baseline is **worse than a flat 52.6% home-win prior**. Beating it is trivial and meaningless. The honest test uses the polarity-corrected baseline `1 - sim_win_prob` (mean Brier ≈ 0.2420 across folds), and the models still beat it convincingly at every snapshot.

This is a separate problem from the inplay models themselves — the inplay models LEARN around the inverted feature (they see it during training and apparently learn to flip its sign internally — AUC of the model is 0.72-0.90). But it means:

1. Anything downstream that consumes `sim_win_prob` directly is using it backwards.
2. Other models that include `sim_win_prob` as a feature may be quietly compensating, OR may be regressed by it.
3. The pregame WP source (`scripts/probe_R11_M2v5_pregame_winprob.py`) needs an orientation audit.

## Per-snapshot detail

### endQ1
- 4 folds: Brier 0.2252 / 0.2150 / 0.2218 / 0.2265 — very tight std
- AUC 0.6993 – 0.7247
- vs corrected baseline (0.2347 / 0.2378 / 0.2384 / 0.2568): -0.0094 / -0.0228 / -0.0166 / -0.0303
- Overfit gap (OOS − in-sample): **+0.1195** — large but expected given limited Q1 signal

### endQ2
- 4 folds: Brier 0.1791 / 0.1810 / 0.1971 / 0.1869
- AUC 0.79 – 0.82
- vs corrected baseline: -0.0556 / -0.0568 / -0.0410 / -0.0699
- Overfit gap: +0.1165

### endQ3
- 4 folds: Brier 0.1414 / 0.1462 / 0.1405 / 0.1133 — fold 3 (most recent games) is best
- AUC 0.89 – 0.92
- vs corrected baseline: -0.0933 / -0.0916 / -0.0976 / -0.1436
- Overfit gap: +0.1052
- Three optional features (`q1_usg_avg`, `halftime_pace_shift`, `trailing_team_q4_usg_hhi`) have low coverage (32% / 32% / 14%) — LightGBM handles via missing-value splits, but this is a fragility worth tracking

## Calibration assessment

Mean weighted-ECE per snapshot:

- endQ1: 0.0905 (model) vs 0.0815 (corrected baseline)
- endQ2: 0.0898 (model) vs 0.0815 (corrected baseline)
- endQ3: 0.0800 (model) vs 0.0815 (corrected baseline)

All three models are **over-confident at the extremes**. Most striking from fold 3 (most recent games):

- endQ1 bin [0.90,1.00): predicts 0.949, actual 0.706 — gap −0.243 (n=34)
- endQ2 bin [0.80,0.90): predicts 0.861, actual 0.731 — gap −0.130 (n=52)
- endQ3 bin [0.70,0.80): predicts 0.759, actual 0.500 — gap −0.259 (n=18, small bin)
- endQ3 bin [0.90,1.00): predicts 0.980, actual 0.958 — gap −0.022 (n=120, well-calibrated)

endQ3 is the best-calibrated overall (the high-confidence bin is dominant and accurate). endQ1 and endQ2 systematically over-state confidence in late-game ranges that they shouldn't be reaching at those snapshots — this is downstream-relevant for any betting consumer that converts predicted prob to EV without isotonic calibration.

## Recommendation

**SHIP the models as-is** — they all beat the honest baseline and are internally consistent across folds.

**Follow-ups (separate work, not blocking):**

1. **AUDIT `sim_win_prob` orientation** in `season_games_*.json` and in whatever produced it. The naive baseline being worse-than-random is a red flag for any downstream consumer that doesn't have the model's ability to learn around it.
2. **ISOTONIC CALIBRATE** the three inplay models. With 4/4 fold improvement vs baseline but ~9% mean calibration drift, an isotonic head fitted on a held-out tail (~last 600 games) would directly improve betting EV without retraining.
3. **endQ3 feature coverage** — `trailing_team_q4_usg_hhi` is non-null in only 14% of games. Either backfill it or drop it; it's adding ~zero average signal while inflating overfit risk.

## Linked notes
- [[Model Performance]] — update endQ1/Q2/Q3 entries with honest OOS Briers (replace the 0.103 / 0.069 / 0.030 in-sample numbers)
- [[Engineering Knowledge]] — add: "verify pregame baseline polarity before treating it as a beat-the-baseline floor; AUC < 0.5 means the feature is inverted, not bad"
- Probe results: `data/cache/probe_R10_M5_inplay_winprob_results.json`
