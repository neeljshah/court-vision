# S209 MLB phase recalibration FWER (2026-09-04)

## Archive-only premise reproduction

Input: `docs/evidence/harness/s88_phase_recal_2026-09-04.csv` (4311731 bytes; SHA-256 `b7cc67e0ff39a8f20b9b12e981ce93c2ace55374b38d9805e092ada99f9ba91d`).
The one opened store contains 33920 evaluated ticks, 11087 informative ticks, and 127 informative game clusters.
S88 delta reproduction diffs (computed minus archived) are pooled 3.0357660829594124e-18, late|leading_big 6.9388939039072284e-18, and mid|trailing 6.9388939039072284e-18.

## BH q=0.05 across all 15 buckets

Raw p is the two-sided game-clustered DM p-value on the same equal-game loss series as delta and CI. Delta is incumbent Brier minus recalibrated Brier, so positive favors recalibration. The replication unit is ISO week 28; it has 90 evaluated game clusters. Labels require a BH survivor and a same-direction game-clustered replication CI.

| bucket | delta | raw p | BH-adjusted p | raw label | label after BH | week-28 delta (CI95) | replication |
|---|---:|---:|---:|---|---|---|---|
| early\|leading | +0.000898 | 0.918095 | 0.918095 | NO_CHANGE | NO_CHANGE | +0.004035 [-0.0169, +0.0247] | NOT REPLICATED |
| early\|leading_big | +0.001870 | 0.881686 | 0.918095 | NO_CHANGE | NO_CHANGE | +0.005246 [-0.0278, +0.0425] | NOT REPLICATED |
| early\|tied | -0.001826 | 0.785256 | 0.906065 | NO_CHANGE | NO_CHANGE | -0.002677 [-0.0178, +0.0131] | NOT REPLICATED |
| early\|trailing | -0.009335 | 0.166722 | 0.500167 | NO_CHANGE | NO_CHANGE | -0.010755 [-0.0250, +0.0039] | NOT REPLICATED |
| early\|trailing_big | -0.005454 | 0.517199 | 0.683868 | NO_CHANGE | NO_CHANGE | -0.000270 [-0.0079, +0.0085] | NOT REPLICATED |
| late\|leading | +0.005426 | 0.547094 | 0.683868 | NO_CHANGE | NO_CHANGE | +0.007987 [-0.0122, +0.0295] | NOT REPLICATED |
| late\|leading_big | +0.031643 | 0.014278 | 0.214164 | IMPROVED | NO_CHANGE | +0.031092 [+0.0010, +0.0656] | NOT REPLICATED |
| late\|tied | -0.012826 | 0.353118 | 0.607591 | NO_CHANGE | NO_CHANGE | -0.019349 [-0.0439, +0.0056] | NOT REPLICATED |
| late\|trailing | -0.007924 | 0.083080 | 0.382170 | NO_CHANGE | NO_CHANGE | -0.006105 [-0.0134, +0.0006] | NOT REPLICATED |
| late\|trailing_big | -0.007126 | 0.259409 | 0.607591 | NO_CHANGE | NO_CHANGE | -0.000926 [-0.0120, +0.0104] | NOT REPLICATED |
| mid\|leading | +0.004965 | 0.516701 | 0.683868 | NO_CHANGE | NO_CHANGE | +0.008915 [-0.0090, +0.0277] | NOT REPLICATED |
| mid\|leading_big | +0.005157 | 0.349835 | 0.607591 | NO_CHANGE | NO_CHANGE | +0.006676 [-0.0055, +0.0204] | NOT REPLICATED |
| mid\|tied | -0.007685 | 0.364555 | 0.607591 | NO_CHANGE | NO_CHANGE | -0.005105 [-0.0236, +0.0140] | NOT REPLICATED |
| mid\|trailing | -0.011964 | 0.038732 | 0.290492 | WORSE | NO_CHANGE | -0.007539 [-0.0204, +0.0053] | NOT REPLICATED |
| mid\|trailing_big | -0.007031 | 0.101912 | 0.382170 | NO_CHANGE | NO_CHANGE | -0.006627 [-0.0177, +0.0039] | NOT REPLICATED |

## ATTEMPT 2: equal-game DM correction

Attempt 1 used tick-weighted losses for raw p while its delta and CI were equal-game-weighted. Attempt 2 uses the equal-game loss series for all three quantities.

| bucket | attempt-1 raw p | attempt-1 BH p | attempt-2 raw p | attempt-2 BH p |
|---|---:|---:|---:|---:|
| late\|leading_big | 0.087888263 | 0.769386223 | 0.014277608 | 0.214164126 |
| mid\|trailing | 0.422857939 | 0.947188181 | 0.038732292 | 0.290492194 |

BH survivors: none.
Buckets losing their uncorrected label under BH: late|leading_big, mid|trailing.
No bucket survives BH or replicates. The pooled equal-game result is NO_CHANGE (raw p 0.501277735); it is outside the 15-bucket BH family and has no replication label.

## Corpus units

| unit | eval ticks | eval games | informative ticks | informative games |
|---|---:|---:|---:|---:|
| ISO week 27 | 15207 | 41 | 3796 | 41 |
| ISO week 28 | 18713 | 90 | 7291 | 90 |

## NOT VERIFIED

- No preregistration seal predating the first score is available for this archive-only re-score (Q1).
- The inherited S88 archive is not a purged, symmetric-embargo OOS evaluation (Q4).
- The original S88 full-window estimate includes both ISO-week sides; week 28 is a disjoint corpus-unit re-score, not a new store.
- No model was refit and no serving path, parameter artifact, or flag was changed.
