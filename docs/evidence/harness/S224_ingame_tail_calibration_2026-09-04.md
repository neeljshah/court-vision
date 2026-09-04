# S224 NBA in-game tail calibration (2026-09-04)

## Verdict: CLOSED AT LIMIT

All twenty frozen one-percent tail bins are UNDERPOWERED at the unchanged
`+0.004` Brier bar. This is a descriptive calibration measurement only; no arm
was fit, no flag changed, and neither the register nor the ledger was opened.

## Input and premise

The sole input opened was
`C:\Users\neelj\nba-track-a13\data\cache\inplay_odds\nba_checkpoints_full.parquet`
(2,829,826 bytes; parquet, so resolution is not applicable). It has 465,249
ticks in 1,593 game clusters. The module reads it once, assigns every valid
probability to exactly one frozen tail bin or the explicit MIDDLE band, and
raises rather than silently dropping an invalid probability.

The premise reproduces: the low tail (`market_prob <= 0.10`) contains 136,809
ticks / 775 game clusters with realized rate 0.006652. The mirror high tail
(`market_prob >= 0.90`) passes through the same binning path and contains
171,947 ticks / 963 game clusters with realized rate 0.992300. Together the
tails contain 308,756 ticks / 1,590 game clusters. The remaining 156,493 ticks
are explicitly MIDDLE, so 465,249 = 308,756 + 156,493 and 0 ticks are dropped.

S123's default leak-free incumbent is its unchanged market probability. The
incumbent Brier column is therefore identical to market Brier by construction;
the identity is named in the JSON rather than presented as a fitted comparison.

## Frozen reliability tables

`ECE_W` is the bin's count-weighted ECE contribution within the complete
20-bin tail family. `N_EFF` is the game-clustered effective sample size of that
bin's market Brier loss. MDE uses `(z_0.975 + z_0.80) / sqrt(N_EFF)` with the
bounded paired-Brier-difference scale fixed at 1 before scoring. This is the
80 percent-power minimum detectable Brier delta; no model-specific variance is
assumed.

### Low tail

| bin | n | realized | market Brier | incumbent Brier | ECE_W | N_EFF | MDE | status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 00-01 | 118601 | 0.000228 | 0.000227 | 0.000227 | 0.000225 | 718.00 | 0.104554 | UNDERPOWERED |
| 01-02 | 2646 | 0.007181 | 0.007171 | 0.007171 | 0.000062 | 496.00 | 0.125795 | UNDERPOWERED |
| 02-03 | 2513 | 0.027855 | 0.027085 | 0.027085 | 0.000034 | 470.01 | 0.129226 | UNDERPOWERED |
| 03-04 | 2152 | 0.020446 | 0.020258 | 0.020258 | 0.000095 | 457.01 | 0.131051 | UNDERPOWERED |
| 04-05 | 1915 | 0.043864 | 0.041978 | 0.041978 | 0.000001 | 460.01 | 0.130623 | UNDERPOWERED |
| 05-06 | 1861 | 0.058033 | 0.054631 | 0.054631 | 0.000026 | 451.01 | 0.131921 | UNDERPOWERED |
| 06-07 | 2366 | 0.061285 | 0.057456 | 0.057456 | 0.000029 | 508.02 | 0.124298 | UNDERPOWERED |
| 07-08 | 1580 | 0.070253 | 0.065277 | 0.065277 | 0.000031 | 445.01 | 0.132807 | UNDERPOWERED |
| 08-09 | 1601 | 0.083073 | 0.076137 | 0.076137 | 0.000017 | 450.01 | 0.132067 | UNDERPOWERED |
| 09-10 | 1574 | 0.107370 | 0.095974 | 0.095974 | 0.000058 | 440.01 | 0.133559 | UNDERPOWERED |

### High tail

| bin | n | realized | market Brier | incumbent Brier | ECE_W | N_EFF | MDE | status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 90-91 | 2669 | 0.900712 | 0.089441 | 0.089441 | 0.000027 | 606.01 | 0.113806 | UNDERPOWERED |
| 91-92 | 2364 | 0.915821 | 0.077048 | 0.077048 | 0.000017 | 594.01 | 0.114949 | UNDERPOWERED |
| 92-93 | 2623 | 0.926420 | 0.068154 | 0.068154 | 0.000023 | 593.01 | 0.115046 | UNDERPOWERED |
| 93-94 | 2716 | 0.944404 | 0.052580 | 0.052580 | 0.000094 | 606.01 | 0.113805 | UNDERPOWERED |
| 94-95 | 2751 | 0.958924 | 0.039609 | 0.039609 | 0.000135 | 598.01 | 0.114564 | UNDERPOWERED |
| 95-96 | 2524 | 0.956418 | 0.041692 | 0.041692 | 0.000019 | 581.01 | 0.116228 | UNDERPOWERED |
| 96-97 | 2878 | 0.964906 | 0.033876 | 0.033876 | 0.000007 | 601.01 | 0.114278 | UNDERPOWERED |
| 97-98 | 3080 | 0.972078 | 0.027173 | 0.027173 | 0.000024 | 622.01 | 0.112332 | UNDERPOWERED |
| 98-99 | 4142 | 0.985514 | 0.014279 | 0.014279 | 0.000007 | 672.01 | 0.108073 | UNDERPOWERED |
| 99-100 | 146200 | 0.999685 | 0.000313 | 0.000313 | 0.000234 | 889.01 | 0.093962 | UNDERPOWERED |

The 20-bin weighted ECE is 0.001167. Scorable bins: 0 of 20. Every MDE
exceeds the unchanged 0.004 bar, including the least conservative tail-bin
MDE of 0.093962; the result is consequently CLOSED AT LIMIT rather than a
fitted calibration comparison.

## Reproduction artifacts and checks

- `docs/evidence/harness/S224_ingame_tail_calibration_2026-09-04_per_bin.csv`
  is the deterministic 20-row verifier-diff artifact.
- `docs/evidence/harness/S224_ingame_tail_calibration_2026-09-04_summary.json`
  records the full source identity, denominator assignment, exact bin values,
  MDE method, and verdict.
- Route SHA-256: `6FEBF95646BCC70166A88A83580A5933FC920AB071D595CE888B45EF92BA21C1`
  for `scripts/platformkit/ingame/s224_nba_tail_calibration.py`.
- The optional garbage-time store was not opened or joined; the result has no
  exclusion based on game state.
- Focused construct test: `python -m pytest
  scripts/platformkit/ingame/test_s224_nba_tail_calibration.py -q -p
  no:cacheprovider` -- 1 passed. It freezes all 20 bin labels and reproduces
  its synthetic rates, including 0.10, 0.90, and 1.00 boundary placement.

## Contract self-check

- B1: no row or lopsided game is excluded; all source ticks are assigned or
  named MIDDLE. B2-B6: the landing is additive and has no changed readers,
  schemas, deployment, callers, or removals. B7-B9 do not apply to this
  exhaustive, game-clustered numeric measurement. B10: the 0.004 bar is read
  as a constant and is not changed.
- Q1-Q5 do not apply because no candidate is fit, scored, or advanced. Q6 is
  satisfied: this memo and artifacts make calibration statements only.
