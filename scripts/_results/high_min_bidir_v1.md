# cycle 94c (loop 5) - high-min bidirectional bias probe (H2)

## Hypothesis source
error_strata_v2.md H2: on l10_min >= 30 rows, PTS/AST/TOV overshoot
(positive bias) while REB/BLK/STL undershoot (negative bias). A
stat-family-split adjustment can correct both directions; a single
global multiplier cannot. FG3M is skipped (no clear bias direction).

## Setup
- holdout: chronological 80/20 (n=19964 of full n=99818)
- l10_min coverage in holdout:
  - >= 28: 6755 rows (33.8%)
  - >= 30: 4956 rows (24.8%)
  - >= 32: 3308 rows (16.6%)
- affected stats: PTS, AST, TOV, REB, BLK, STL (fg3m skipped)
- volume stats (PTS/AST/TOV): pred *= shrink
- defense stats (REB/BLK/STL): pred *= inflate

## 9-combo sweep (per-stat MAE delta on single-split)

| thr | shrink | inflate | PTS | AST | TOV | REB | BLK | STL | agg6 |
|----:|-------:|--------:|----:|----:|----:|----:|----:|----:|-----:|
| 28 | 0.97 | 1.03 | -0.0111 | -0.0033 | -0.0002 | +0.0003 | -0.0000 | +0.0019 | **-0.0124** |
| 28 | 0.96 | 1.04 | -0.0119 | -0.0040 | -0.0001 | +0.0011 | -0.0000 | +0.0025 | **-0.0124** |
| 28 | 0.98 | 1.02 | -0.0088 | -0.0024 | -0.0002 | -0.0001 | -0.0000 | +0.0013 | **-0.0103** |
| 30 | 0.97 | 1.03 | -0.0075 | -0.0030 | -0.0003 | +0.0007 | -0.0000 | +0.0014 | **-0.0087** |
| 30 | 0.96 | 1.04 | -0.0077 | -0.0036 | -0.0002 | +0.0014 | -0.0000 | +0.0019 | **-0.0082** |
| 30 | 0.98 | 1.02 | -0.0062 | -0.0022 | -0.0002 | +0.0002 | -0.0000 | +0.0010 | **-0.0074** |
| 32 | 0.97 | 1.03 | -0.0045 | -0.0020 | -0.0002 | +0.0006 | +0.0000 | +0.0009 | **-0.0052** |
| 32 | 0.96 | 1.04 | -0.0043 | -0.0023 | -0.0002 | +0.0012 | +0.0000 | +0.0012 | **-0.0044** |
| 32 | 0.98 | 1.02 | -0.0039 | -0.0015 | -0.0002 | +0.0002 | +0.0000 | +0.0006 | **-0.0047** |

## Best combo
- threshold: **28** (l10_min >= 28)
- shrink (PTS/AST/TOV): **0.97**
- inflate (REB/BLK/STL): **1.03**
- aggregate-6 MAE delta: **-0.0124**
- stats strictly down (delta < -0.001): **2/6**

## Per-stat single-split detail (best combo)

| stat | n_affected | base_mae | adj_mae | delta |
|------|-----------:|---------:|--------:|------:|
| PTS | 6755 | 4.6221 | 4.6110 | -0.0111 |
| AST | 6755 | 1.3606 | 1.3573 | -0.0033 |
| TOV | 6755 | 0.8932 | 0.8930 | -0.0002 |
| REB | 6755 | 1.9025 | 1.9028 | +0.0003 |
| BLK | 6755 | 0.4398 | 0.4398 | -0.0000 |
| STL | 6755 | 0.7153 | 0.7172 | +0.0019 |

## Single-split ship gate: **FAIL**
- gate: >=4 of 6 strictly DOWN AND agg6 <= -0.005
- result: 2/6 strictly down, agg6 = -0.0124

## WF 4-fold chronological (best combo, no retrain)

| stat | fold | base | adj | delta | positive? |
|------|-----:|----:|----:|------:|:---------:|
| PTS | 1 | 4.6074 | 4.6027 | -0.0047 | YES |
| PTS | 2 | 4.5830 | 4.5676 | -0.0153 | YES |
| PTS | 3 | 4.6056 | 4.5901 | -0.0155 | YES |
| PTS | 4 | 4.6925 | 4.6837 | -0.0088 | YES |
| AST | 1 | 1.3497 | 1.3449 | -0.0048 | YES |
| AST | 2 | 1.3325 | 1.3292 | -0.0033 | YES |
| AST | 3 | 1.3811 | 1.3775 | -0.0036 | YES |
| AST | 4 | 1.3792 | 1.3775 | -0.0017 | YES |
| TOV | 1 | 0.8897 | 0.8904 | +0.0007 | no |
| TOV | 2 | 0.8854 | 0.8850 | -0.0004 | YES |
| TOV | 3 | 0.9090 | 0.9079 | -0.0011 | YES |
| TOV | 4 | 0.8888 | 0.8888 | -0.0000 | YES |
| REB | 1 | 1.8906 | 1.8889 | -0.0017 | YES |
| REB | 2 | 1.9284 | 1.9270 | -0.0014 | YES |
| REB | 3 | 1.9130 | 1.9150 | +0.0021 | no |
| REB | 4 | 1.8780 | 1.8803 | +0.0024 | no |
| BLK | 1 | 0.4351 | 0.4353 | +0.0002 | no |
| BLK | 2 | 0.4427 | 0.4427 | -0.0000 | YES |
| BLK | 3 | 0.4497 | 0.4495 | -0.0002 | YES |
| BLK | 4 | 0.4316 | 0.4315 | -0.0000 | YES |
| STL | 1 | 0.7047 | 0.7070 | +0.0023 | no |
| STL | 2 | 0.7174 | 0.7193 | +0.0019 | no |
| STL | 3 | 0.7465 | 0.7486 | +0.0021 | no |
| STL | 4 | 0.6927 | 0.6939 | +0.0013 | no |

WF folds positive per stat:
- PTS: 4/4
- AST: 4/4
- TOV: 3/4
- REB: 2/4
- BLK: 3/4
- STL: 0/4

## WF ship gate: **FAIL**
- gate: >=3 of 6 stats with 4/4 folds positive
- result: 2/6 stats achieved 4/4

## Verdict
**REJECT** - single-split gate failed (need >=4/6 down AND agg6 <= -0.005; got 2/6 down, agg6=-0.0124); WF gate failed (need >=3/6 stats at 4/4 folds; got 2/6).

Interpretation: per-row bias signs in strata table are population
averages on a holdout slice. Applying a uniform stat-family
factor compresses the SCALE of every prediction in the cell, which
only helps when most rows share the bias direction. On individual
rows the residual sign is mixed, so a small uniform factor often
trades intra-cell winners for losers and the aggregate barely moves.
