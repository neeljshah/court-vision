# S208 NBA phase recalibration (2026-09-04)

## ATTEMPT 2 -- CLOSED AT LIMIT

This replaces attempt 1's false stop. S208 was completed on the S86 SCREEN-side representation with the S123 default market incumbent. Calibration measurement only. No flags, ledger, register, or data paths were changed.

### Source and premise

The only opened store was `C:\Users\neelj\nba-track-a16\data\cache\inplay_odds\nba_checkpoints_full.parquet` (2,829,826 bytes). It contains 465,249 traded ticks / 1,593 games from 2024-10-22 through 2026-06-13, with zero nulls in the required score fields; units are 656 (2024-25) and 937 (2025-26). The S123 module `scripts/platformkit/foundry/ingame_incumbent_nba.py` exists and its `market` default was asserted byte-identical to the incumbent vector before fitting.

The scored tick and ECE source is the **S86 SCREEN CSV decimal representation**, reconstructed in memory from that bounded parquet input using the S86 game-block screen partition (seed 0): 232,951 ticks / 797 games before walk-forward burn-in. This is the representation used by S94's cited P2 close ECE 0.064157, so it is the appropriate choice for the S208 premise. The raw parquet retains `0.30000000000000004` while the CSV renders `0.3`; at that bin boundary, 34 P1 and 44 P2 close ticks (78 total) change adjacent ECE bins. Brier and paired losses do not change at the reported precision.

S94's global target-cell calibration result remains SCREEN NEGATIVE. This S208 evaluation re-scores a global single-bucket recalibration on the same representation before the phase-conditioned candidate.

### Leak-free method

The baseline is S123 `market`, which is also the printed market column. The candidate alone changes: it is fitted with the frozen `bucket_recalibration.SPECS` (`phase_platt`, `phase_platt_margin`). NBA phase is preregistered as early = P1-P2, mid = P3, and late = P4/OT; margin is S86 `close_le5`, `mid_06_12`, or `blowout_gt12`. All nine phase|margin buckets are enumerated below.

The outer pass is expanding game-first-date walk-forward with a fixed 20 percent train-only burn-in (54 dates). Every fold asserts `train_date_max < test_date` and is game-disjoint by that first-date construction. Each outer fold selects between the two frozen specs only on the final 20 percent of its own training dates, then refits the selected spec on the whole outer training history before scoring its held-out date. There are 213 scored outer dates, from 2025-01-03 through 2026-06-10. No calibrator sees its scored game or a later game.

The held-out denominator is 177,475 ticks / 618 game clusters. Delta is incumbent Brier minus candidate Brier, so positive favors recalibration. CI95 is the fixed 2,000-resample, seed-42 game-cluster bootstrap from the S88 machinery. `n_eff` is the clustered effective sample size of the paired loss differential. ECE is diagnostic only.

### Step 1 global single-bucket null and limit

| row | ticks | clusters | n_eff | Brier incumbent | Brier recal | Brier market | ECE incumbent | ECE recal | ECE market | delta (CI95) | label |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| global recal null | 177475 | 618 | 1887.3 | 0.078913 | 0.078861 | 0.078913 | 0.012896 | 0.010101 | 0.012896 | +0.000018 [-0.000472, +0.000505] | NO_CHANGE |
| pooled phase recal | 177475 | 618 | 2058.9 | 0.078913 | 0.078861 | 0.078913 | 0.012896 | 0.007395 | 0.012896 | +0.000119 [-0.000612, +0.000866] | NO_CHANGE |

The phase candidate's tick-weighted Brier (0.078860809) is fractionally higher than the global null's 0.078860545. The global and pooled CIs both include zero. Therefore phase conditioning does not clear the step-1 comparison and the S208 construct is **CLOSED AT LIMIT**. The required exhaustive bucket table follows; it is not suppressed by this limit.

### Complete phase|margin table

| bucket | ticks | clusters | n_eff | Brier incumbent | Brier recal | Brier market | ECE incumbent | ECE recal | ECE market | delta (CI95) | label |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| early\|blowout_gt12 | 7664 | 316 | 350.2 | 0.110117 | 0.111319 | 0.110117 | 0.023249 | 0.019343 | 0.023249 | +0.000113 [-0.002006, +0.002334] | NO_CHANGE |
| early\|close_le5 | 21587 | 618 | 653.0 | 0.222733 | 0.221745 | 0.222733 | 0.054612 | 0.037865 | 0.054612 | -0.000142 [-0.002207, +0.001997] | NO_CHANGE |
| early\|mid_06_12 | 15115 | 613 | 681.4 | 0.195677 | 0.196066 | 0.195677 | 0.035626 | 0.038375 | 0.035626 | -0.000450 [-0.002419, +0.001547] | NO_CHANGE |
| late\|blowout_gt12 | 46325 | 407 | 1894.4 | 0.003347 | 0.003077 | 0.003347 | 0.002070 | 0.001744 | 0.002070 | -0.000938 [-0.001895, -0.000090] | WORSE |
| late\|close_le5 | 29657 | 341 | 1049.2 | 0.050386 | 0.050398 | 0.050386 | 0.006173 | 0.004411 | 0.006173 | +0.001037 [-0.000393, +0.002506] | NO_CHANGE |
| late\|mid_06_12 | 36601 | 470 | 1000.1 | 0.016592 | 0.016781 | 0.016592 | 0.003636 | 0.004927 | 0.003636 | -0.001002 [-0.002462, +0.000375] | NO_CHANGE |
| mid\|blowout_gt12 | 6912 | 364 | 427.7 | 0.063216 | 0.062982 | 0.063216 | 0.020048 | 0.020299 | 0.020048 | -0.000646 [-0.002212, +0.000919] | NO_CHANGE |
| mid\|close_le5 | 6720 | 399 | 426.0 | 0.230052 | 0.229819 | 0.230052 | 0.053133 | 0.037670 | 0.053133 | -0.000715 [-0.002989, +0.001484] | NO_CHANGE |
| mid\|mid_06_12 | 6894 | 503 | 563.4 | 0.167645 | 0.168434 | 0.167645 | 0.035327 | 0.028274 | 0.035327 | -0.000460 [-0.002236, +0.001330] | NO_CHANGE |

No bucket has fewer than 30 game clusters; therefore none is labelled NOT SCORABLE. The late|blowout_gt12 interval is WORSE and remains in the pooled result and BH family.

### Benjamini-Hochberg across the complete nine-bucket family

BH uses the two-sided game-clustered DM p value for every enumerated bucket, including any tiny or empty bucket had one existed. The CI remains the S88 fixed cluster bootstrap.

| rank | bucket | raw p | BH threshold (q=0.05) | survivor |
|---:|---|---:|---:|---|
| 1 | late\|mid_06_12 | 0.125608 | 0.005556 | no |
| 2 | late\|blowout_gt12 | 0.221541 | 0.011111 | no |
| 3 | early\|blowout_gt12 | 0.282808 | 0.016667 | no |
| 4 | early\|close_le5 | 0.429571 | 0.022222 | no |
| 5 | mid\|mid_06_12 | 0.462759 | 0.027778 | no |
| 6 | early\|mid_06_12 | 0.724099 | 0.033333 | no |
| 7 | mid\|blowout_gt12 | 0.805866 | 0.038889 | no |
| 8 | mid\|close_le5 | 0.880784 | 0.044444 | no |
| 9 | late\|close_le5 | 0.965595 | 0.050000 | no |

BH survivors: none.

### Archives and reproduction

- `docs/evidence/harness/S208_nba_phase_recal_2026-09-04_summary.json` (79,953 bytes): source identity, folds, complete table, and BH output.
- `docs/evidence/harness/S208_nba_phase_recal_2026-09-04_bucket_outputs.csv` (2,797 bytes): complete per-bucket and pooled output.
- `docs/evidence/harness/S208_nba_phase_recal_2026-09-04_paired_losses.csv` (653,054 bytes): 5,267 per-game paired-loss rows with evaluation, bucket, cluster id, game-date timestamp, tick count, and summed incumbent/candidate/market losses. It independently reproduced all 11 global, nine-bucket, and pooled Briers/deltas/CIs exactly using the archived series alone.

### NOT VERIFIED

- This is one NBA SCREEN-side corpus only; no second corpus replication was performed.
- Nothing is wired into a serving path, and no calibration parameters are persisted for use.
- The absent local historical S86 CSV was reconstructed from the stated raw bounded store with S86's deterministic screen partition; its CSV decimal semantics, rather than raw parquet binary floats, are what this report scores.
- An independent verifier has not yet rerun the focused test and archive reproduction in master.
