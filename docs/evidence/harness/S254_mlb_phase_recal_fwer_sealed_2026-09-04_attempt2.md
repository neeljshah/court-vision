# S254 MLB phase recalibration FWER sealed: ATTEMPT 2 (2026-09-04)

## Seal and inputs

Preregistration: `docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_PREREG_attempt2.md`; seal SHA-256 `030eb13aad94edbafeb0c54c18aa88bbb5f82da448e4ab3378fec5d8be13e136`; LF header lines `35`; sealed at `2026-09-04T09:14:35.1765197Z`.
First score started at `2026-09-04T09:29:12.544286+00:00` (after seal: true).
Input store: `C:\Users\neelj\nba-track-a13\data\cache\ingame_grade_joined` (505 JSONL files, 73485324 bytes; non-media input, so no resolution applies).
Code SHA-256: `c0d7a306cb89170f278a317386bce40afc0e24c583dedeb806f666d7c1b61f17`.

## Denominator and purge

Evaluated ticks 47104; informative ticks 14611; informative game clusters 158; whole-game replication clusters 75.
CPCV used a symmetric 1-day embargo. The hash split is 83 primary and 75 replication game clusters. Exact excluded game-cluster reasons and evaluated n_train assertions for every split are in `S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary_attempt2.json` under `purge.splits`.

## ATTEMPT 2 corrections

| finding | attempt 1 | attempt 2 |
|---|---|---|
| MLB identity | 53 of 158 IDs became game-unique | all 158 resolve through `parse_mlb_ticker` |
| purge audit ordering | unsorted | sorted exactly as `cpcv_evaluate` |
| audit route count | four logged/scored mismatches | eight asserted audit/evaluated n_train pairs |
| hash replication partition | reported 158 | primary 83; replication 75 |

## BH q=0.05 across all 15 buckets

| bucket | delta | raw p | BH p | raw label | after BH | replication CI95 | replication |
|---|---:|---:|---:|---|---|---|---|
| early\|leading | +0.006505 | 0.420529 | 0.700882 | NO_CHANGE | NO_CHANGE | [-0.013216, +0.031744] | NOT_REPLICATED |
| early\|leading_big | -0.002373 | 0.805009 | 0.907362 | NO_CHANGE | NO_CHANGE | [-0.035150, +0.005100] | NOT_REPLICATED |
| early\|tied | -0.000692 | 0.907362 | 0.907362 | NO_CHANGE | NO_CHANGE | [-0.023460, +0.010578] | NOT_REPLICATED |
| early\|trailing | -0.011605 | 0.059005 | 0.311641 | NO_CHANGE | NO_CHANGE | [-0.036252, -0.000717] | NOT_REPLICATED |
| early\|trailing_big | -0.003020 | 0.517886 | 0.706209 | NO_CHANGE | NO_CHANGE | [-0.020509, +0.012498] | NOT_REPLICATED |
| late\|leading | +0.007877 | 0.473326 | 0.706209 | NO_CHANGE | NO_CHANGE | [-0.013436, +0.045475] | NOT_REPLICATED |
| late\|leading_big | +0.015260 | 0.062328 | 0.311641 | NO_CHANGE | NO_CHANGE | [-0.000357, +0.045003] | NOT_REPLICATED |
| late\|tied | -0.021503 | 0.114012 | 0.325866 | NO_CHANGE | NO_CHANGE | [-0.078925, +0.006691] | NOT_REPLICATED |
| late\|trailing | -0.012657 | 0.030280 | 0.311641 | WORSE | NO_CHANGE | [-0.046424, -0.001456] | NOT_REPLICATED |
| late\|trailing_big | -0.003000 | 0.386273 | 0.700882 | NO_CHANGE | NO_CHANGE | [-0.018874, +0.006590] | NOT_REPLICATED |
| mid\|leading | +0.005632 | 0.368791 | 0.700882 | NO_CHANGE | NO_CHANGE | [-0.007940, +0.025380] | NOT_REPLICATED |
| mid\|leading_big | +0.000696 | 0.860043 | 0.907362 | NO_CHANGE | NO_CHANGE | [-0.007562, +0.013125] | NOT_REPLICATED |
| mid\|tied | -0.003599 | 0.576773 | 0.720966 | NO_CHANGE | NO_CHANGE | [-0.024974, +0.010433] | NOT_REPLICATED |
| mid\|trailing | -0.006301 | 0.114619 | 0.325866 | NO_CHANGE | NO_CHANGE | [-0.020299, +0.002143] | NOT_REPLICATED |
| mid\|trailing_big | -0.004999 | 0.130346 | 0.325866 | NO_CHANGE | NO_CHANGE | [-0.019762, -0.000749] | NOT_REPLICATED |

BH survivors: none.

## NOT VERIFIED

- No calibration improvement is claimed; the measurement is a sealed, purged CPCV family score.
- No flags, FWER ledger, or serving artifact changed.
