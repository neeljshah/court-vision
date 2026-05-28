# Iter 74 — Polarity-Corrected Inplay Retrain (REVERT)

**Date:** 2026-05-28
**Probe:** `scripts/iter74_inplay_polarity_corrected_retrain.py`
**Results JSON:** `data/cache/iter74_inplay_polarity_results.json`
**Status:** REVERT — all 3 snapshots fail ship gate

## Hypothesis

The polarity bug audit ([[Polarity Bug Audit 2026-05-27]]) showed
`season_games.sim_win_prob` is inverted (corr with `home_won` = **-0.113** on
this dataset). The v6_hp models (Iter 68, lr=0.03/nl=15) learn to flip the
sign internally during training.

**Question:** Does training on the polarity-corrected signal directly
(`pregame_win_prob = 1.0 - pregame_win_prob`, applied at BOTH train and
inference time) produce SHARPER splits than relying on internal compensation?

## Method

- Same training-table builder as Iter 68 (linescores + season_games +
  quarter_features). 3,685 games, 11,055 snapshot rows.
- Two head-to-head WF runs per snapshot with identical HPs:
  - **(A) v6_hp-repro:** raw `pregame_win_prob` (the v6_hp recipe).
  - **(B) v9_polarity:** `1.0 - pregame_win_prob` applied to ALL rows.
- HPs frozen from Iter 68 winners per snapshot.
- 4-fold expanding WF, seed=42, identical to OOS validator.
- Ship gate: ≥3/4 folds improved AND mean delta ≤ -0.001 vs v6_hp.

## Results

| Snap  | v6_hp pub | v6_hp_repro | v9_polarity | Delta_pub | Delta_h2h | Folds | Ship |
|-------|-----------|-------------|-------------|-----------|-----------|-------|------|
| endQ1 | 0.2120    | 0.2120      | 0.2128      | +0.0008   | +0.0008   | 1/4   | no   |
| endQ2 | 0.1771    | 0.1771      | 0.1762      | -0.0009   | -0.0008   | 3/4   | no   |
| endQ3 | 0.1250    | 0.1250      | 0.1251      | +0.0001   | +0.0001   | 2/4   | no   |

**Reproduction is exact** — the v6_hp baseline numbers from the prompt
(0.2120 / 0.1771 / 0.1250) match the repro column to 4 decimals, validating
the head-to-head protocol.

Raw `pregame_win_prob` correlation with `home_won` = **-0.1128**.
Flipped correlation = **+0.1128** (sign-symmetric as expected).

## Verdict: REVERT

- endQ1: directionally HURTS (+0.0008, 1/4 folds).
- endQ2: marginally HELPS (-0.0009, 3/4 folds) but **misses the -0.001 mean
  gate by 0.0001** — within fold-noise.
- endQ3: WASH (+0.0001, 2/4 folds).

No `_v9_polarity.lgb` files written (gate gates saves).

## Interpretation

**Training-time polarity correction matches the v6_hp internal-flip baseline
within noise.** LightGBM trees of depth ≥ 4 with `num_leaves=15` and 300
estimators have ample capacity to flip a single feature's sign at the first
split — and that's exactly what they do. Splitting on `pregame_win_prob > 0.5`
in the inverted frame produces the same partition as splitting on
`pregame_win_prob < 0.5` in the corrected frame; the resulting leaf
probabilities are identical.

Tiny differences between A and B (≤0.0009) are **fold-boundary noise** from
how LightGBM's histogram binning interacts with feature distribution shifts
under the flip. Not signal.

## Connection to Polarity Cascade Plan

This iteration is the **training-data lever** of the polarity bug. It confirms:

1. **In-game v6_hp models are SELF-CORRECTING for the polarity bug.** No
   retrain cascade is needed for these specific models.
2. The polarity cascade should focus on the **decision-making code paths**
   listed in [[Polarity Bug Audit 2026-05-27]]:
   - `src/prediction/inplay_winprob.py` v2/v3 blend (85% pregame weight)
   - `src/prediction/inplay_bet_ranker.py`
   - Any consumer that uses `sim_win_prob` raw (not via the v6_hp .lgb).

The actual source patch at `src/prediction/win_probability.py:178` is still
warranted for display/CLV correctness, but **it will not move v6_hp Brier**.

## Related

- [[Polarity Bug Audit 2026-05-27]] — the original audit
- [[Iter68 Inplay HP Sweep]] — the v6_hp baselines being matched
- [[Iter69 Inplay Pregame Shrinkage]] — same lesson from a different angle:
  external alpha-blend of corrected pregame with model adds noise rather than
  signal because the model already internalizes the flip
