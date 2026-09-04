# S254 MLB phase recalibration FWER sealed (2026-09-04)

## Seal and inputs

Preregistration: `docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_PREREG.md`; seal SHA-256 `91aa52f7948a4cf0abc9106f6163172ace74b454478cfece41fc3fd94efdb096`; LF header lines `31`; sealed at `2026-09-04T08:08:26.2449950Z`.
First score started at `2026-09-04T08:20:14.375571+00:00` (after seal: true).
Input store: `C:\Users\neelj\nba-track-a13\data\cache\ingame_grade_joined` (505 JSONL files, 73485324 bytes; non-media input, so no resolution applies).
Code SHA-256: `e78079898aec0a92e7a57fc478c7962066ac1ae431c497c76d48bcd090ff18e9`.

## Denominator and purge

Evaluated ticks 47104; informative ticks 14611; informative game clusters 158; whole-game replication clusters 158.
CPCV used a symmetric 1-day embargo. Exact excluded game-cluster reasons for every split are in `S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary.json` under `purge.splits`.

## BH q=0.05 across all 15 buckets

| bucket | delta | raw p | BH p | raw label | after BH | replication CI95 | replication |
|---|---:|---:|---:|---|---|---|---|
| early\|leading | +0.007123 | 0.374520 | 0.674211 | NO_CHANGE | NO_CHANGE | [-0.012910, +0.030447] | NOT_REPLICATED |
| early\|leading_big | -0.004174 | 0.681217 | 0.786020 | NO_CHANGE | NO_CHANGE | [-0.039223, +0.003705] | NOT_REPLICATED |
| early\|tied | +0.000473 | 0.929935 | 0.929935 | NO_CHANGE | NO_CHANGE | [-0.017754, +0.012292] | NOT_REPLICATED |
| early\|trailing | -0.006923 | 0.138650 | 0.346625 | NO_CHANGE | NO_CHANGE | [-0.024271, +0.002819] | NOT_REPLICATED |
| early\|trailing_big | -0.002059 | 0.595519 | 0.744398 | NO_CHANGE | NO_CHANGE | [-0.015255, +0.011601] | NOT_REPLICATED |
| late\|leading | +0.007808 | 0.476312 | 0.714468 | NO_CHANGE | NO_CHANGE | [-0.013315, +0.044012] | NOT_REPLICATED |
| late\|leading_big | +0.014748 | 0.064068 | 0.346625 | NO_CHANGE | NO_CHANGE | [-0.000396, +0.043015] | NOT_REPLICATED |
| late\|tied | -0.019918 | 0.130852 | 0.346625 | NO_CHANGE | NO_CHANGE | [-0.073320, +0.009022] | NOT_REPLICATED |
| late\|trailing | -0.011157 | 0.030850 | 0.346625 | WORSE | NO_CHANGE | [-0.039920, -0.000900] | NOT_REPLICATED |
| late\|trailing_big | -0.002637 | 0.404527 | 0.674211 | NO_CHANGE | NO_CHANGE | [-0.016347, +0.006612] | NOT_REPLICATED |
| mid\|leading | +0.005209 | 0.381436 | 0.674211 | NO_CHANGE | NO_CHANGE | [-0.008294, +0.023527] | NOT_REPLICATED |
| mid\|leading_big | +0.000523 | 0.889132 | 0.929935 | NO_CHANGE | NO_CHANGE | [-0.007758, +0.011105] | NOT_REPLICATED |
| mid\|tied | -0.003315 | 0.570185 | 0.744398 | NO_CHANGE | NO_CHANGE | [-0.021828, +0.009921] | NOT_REPLICATED |
| mid\|trailing | -0.005401 | 0.129003 | 0.346625 | NO_CHANGE | NO_CHANGE | [-0.016199, +0.003132] | NOT_REPLICATED |
| mid\|trailing_big | -0.004264 | 0.098120 | 0.346625 | NO_CHANGE | NO_CHANGE | [-0.015099, -0.000562] | NOT_REPLICATED |

BH survivors: none.

## NOT VERIFIED

- No calibration improvement is claimed; the measurement is a sealed, purged CPCV family score.
- No flags, FWER ledger, or serving artifact changed.
