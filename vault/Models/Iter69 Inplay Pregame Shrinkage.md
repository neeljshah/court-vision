# Iter 69 — Inplay Pregame Shrinkage (REVERT)

**Date:** 2026-05-27
**Status:** REVERT — no snapshot meets ship gate
**Type:** post-isotonic shrinkage overlay (zero-touch on `.lgb` and `.joblib`)

## Hypothesis

For each in-play snapshot (endQ1, endQ2, endQ3), hand-tune a shrinkage
weight `alpha` that blends:

```
blended = (1 - alpha) * pregame_corrected + alpha * iso_model_pred
```

where `pregame_corrected = 1.0 - sim_win_prob` (polarity flip — the raw
`sim_win_prob` field is anti-informative; global AUC vs `home_won` = 0.434).

Intuition: early-game (endQ1 — only 12 minutes played) might benefit from
anchoring to the pregame prior, since `score_margin` and `q1_delta` have
high variance over a single quarter.

## Method

- Same data + WF splits as Iter 62 (3685 games, 4 expanding-window folds).
- Per fold: train fresh LGB (matches Iter 62 procedure), get raw OOS preds,
  apply Iter 62 isotonic overlay → `iso_model_pred`.
- Grid `alpha ∈ {0.0, 0.1, …, 1.0}`. Pick alpha minimizing mean WF Brier
  with guardrail "no fold regresses > 0.005 vs alpha=1.0 (pure model)".
- Ship gate: `mean_brier_delta <= -0.001` vs alpha=1.0.

## Results

| Snapshot | Best alpha | Baseline Brier (a=1) | Shrink Brier | Delta | Ship? |
|----------|-----------:|---------------------:|-------------:|------:|:-----:|
| endQ1    |        0.9 |               0.2094 |       0.2091 | -0.0003 | NO  |
| endQ2    |        1.0 |               0.1758 |       0.1758 | +0.0000 | NO  |
| endQ3    |        1.0 |               0.1310 |       0.1310 | +0.0000 | NO  |
| Aggregate|            |                      |              | -0.0001 | NO  |

Per-fold pregame_corrected Brier ≈ 0.239–0.247 across all snapshots — the
polarity-flipped pregame anchor is far worse than the isotonic-calibrated
in-play model at every snapshot. The model already absorbs whatever signal
exists in `pregame_win_prob` (which is in the feature set), so external
shrinkage just averages in noise.

## Decision

**REVERT.** endQ1 came closest at alpha=0.9 (delta -0.0003) but missed
the -0.001 ship gate by 3x.

## Lessons / takeaways

1. **The "weak-signal early-game" intuition was wrong.** Even at endQ1 with
   only 12 minutes of in-play info, the LGB model + isotonic overlay
   dominates the pregame anchor by a wide margin (~0.21 vs ~0.24 Brier).
2. The LGB already includes `pregame_win_prob` as a feature — it learns
   the polarity flip and the optimal weighting internally. External
   shrinkage is duplicative.
3. As `alpha → 1.0`, mean Brier monotonically improves on every snapshot.
   The full sweep is a textbook "model dominates anchor" curve.
4. **Where future inplay gains will come from:** richer in-play state
   (PBP microstructure, lineup-on-court at snapshot, foul trouble, possession
   counts) — NOT from more clever blending of existing features.

## Files

- Script: `scripts/iter69_inplay_pregame_shrinkage.py`
- Per-snapshot α JSONs: `data/models/inplay_pregame_shrink_endq{1,2,3}.json`
- Full results: `data/cache/iter69_inplay_shrink_results.json`

## Cross-refs

- [[Inplay Win Probability Models]] — production endQ1/Q2/Q3 LGB + Iter 62 isotonic
- Iter 62 (shipped): isotonic overlay
- Iter 68: HP sweep (preceded this iter)
