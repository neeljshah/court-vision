# In-play multi-snapshot blend probe — cycle 95e (loop 5)

**Games analyzed:** 50  ·  fit=30  val=20

Asks whether a WEIGHTED blend of endQ1 + endQ2 + endQ3 snapshot projections (cycle-88 projector) beats the single-snapshot endQ3 baseline (cycle 94d). Each blend is MAE'd on the validation set (last 20 games) using ONLY (game, player, stat) triples that have ALL THREE snapshots — apples-to-apples denominator. The `nnls_fit` scheme is per-stat: weights fit on the first 30 games minimizing L2 residual to actuals, then evaluated on the holdout.

## Validation MAE per scheme

| stat | q3_only | q3_90_q2_10 | q3_80_q2_20 | q3_70_q2_20_q1_10 | q2_q3_equal | exp_lambda_0_5 | exp_lambda_0_7 | exp_lambda_0_9 |
|------|------|------|------|------|------|------|------|------|
| pts | 2.5272 | 2.5537 | 2.6074 | 2.7618 | 3.0214 | 2.9810 | 3.3164 | 3.6489 |
| reb | 0.9314 | 0.9432 | 0.9731 | 1.0617 | 1.1981 | 1.1870 | 1.3445 | 1.4961 |
| ast | 0.6586 | 0.6766 | 0.6966 | 0.7636 | 0.8278 | 0.8439 | 0.9571 | 1.0697 |
| fg3m | 0.4746 | 0.4821 | 0.4908 | 0.5326 | 0.5860 | 0.5895 | 0.6727 | 0.7496 |
| stl | 0.3255 | 0.3282 | 0.3317 | 0.3518 | 0.4181 | 0.3947 | 0.4437 | 0.4871 |
| blk | 0.2042 | 0.2060 | 0.2087 | 0.2190 | 0.2680 | 0.2475 | 0.2749 | 0.2977 |
| tov | 0.4522 | 0.4567 | 0.4622 | 0.4966 | 0.5683 | 0.5512 | 0.6252 | 0.7009 |

## Per-stat best blend (vs Q3-only baseline)

| stat | n | Q3_only_mae | best_blend_mae | best_scheme | weights (Q1,Q2,Q3) | delta |
|------|---|-------------|----------------|-------------|-------------------|-------|
| pts | 360 | 2.5272 | 2.5272 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| reb | 360 | 0.9314 | 0.9314 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| ast | 360 | 0.6586 | 0.6586 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| fg3m | 360 | 0.4746 | 0.4746 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| stl | 360 | 0.3255 | 0.3255 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| blk | 360 | 0.2042 | 0.2042 | q3_only | (0.00,0.00,1.00) | +0.0000 |
| tov | 360 | 0.4522 | 0.4522 | q3_only | (0.00,0.00,1.00) | +0.0000 |

## NNLS-fit per-stat weights

| stat | w_Q1 | w_Q2 | w_Q3 | sum | val_mae | n |
|------|------|------|------|-----|---------|---|
| pts | 0.000 | 0.016 | 0.984 | 1.000 | 2.5311 | 360 |
| reb | 0.000 | 0.025 | 0.975 | 1.000 | 0.9333 | 360 |
| ast | 0.000 | 0.018 | 0.982 | 1.000 | 0.6618 | 360 |
| fg3m | 0.002 | 0.032 | 0.967 | 1.000 | 0.4773 | 360 |
| stl | 0.000 | 0.000 | 1.000 | 1.000 | 0.3255 | 360 |
| blk | 0.000 | 0.013 | 0.987 | 1.000 | 0.2044 | 360 |
| tov | 0.000 | 0.000 | 1.000 | 1.000 | 0.4522 | 360 |

## Verdict

**Best blend beats Q3-only on 0/7 stats** (threshold delta>=0.05 MAE: 0/7).

**Q3-ONLY REMAINS BEST.** The cycle-88 endQ3 single-snapshot projection already captures the most-informative state. Blending in earlier snapshots adds bias (stale state) faster than it reduces variance (regularizing toward Q2 mean). The hypothesis that Q3 noise dominates Q2 stability is rejected.

