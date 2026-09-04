# S205 calibration bakeoff

This is calibration-only evidence. No calibrator is served, promoted, or
enabled. The sealed verdict is unchanged: `IMPROVES` requires lower ECE, lower
Murphy reliability, and no fall in Murphy resolution. Every other result is
`FLATTENED`.

## Preregistration and inputs

The fold, regime-key, bin, and verdict contract is the sealed S05 preregistration
at `docs/evidence/harness/S05_calibration_prereg_2026-09-03.md`, seal
`9051BB6E3BD89F7309A799F9739C8E61EA6DB3530E52AD87666568220591DF8A`.
S205's dispatched spec is commit `75d7b37079634d148ef348afc0e1b2caeed9f802`.
The opened input paths, byte sizes, and SHA-256 values are recorded per sport in
`docs/evidence/harness/S205_calib_bakeoff_2026-09-04.json`.

Each arm used every finite-probability, binary-outcome row. The source files were
opened sequentially: nba 201706 bytes, mlb 1645142 bytes, soccer 6053712 bytes,
and tennis 2745405 bytes. They are tabular inputs, so resolution is n/a.

## Premise and resolution budget

The unchanged isotonic arm reproduced S05 exactly: nba 1814 / 0.024842542;
mlb 39162 / 0.008076825; soccer 25834 / 0.009301789; tennis 41886 /
0.008403090 (scored rows / after-ECE). `premise_abs_diff` is 0.0 for all four.

The isotonic resolution budget spent before testing the new arms was nba
0.002682371, mlb 0.000055251, soccer 0.000578093, and tennis 0.000680171.

## Twelve-cell result

| sport | arm | ECE | Murphy REL | Murphy RES | sharpness | log-loss | resolution tax | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| mlb | isotonic | 0.008076825 | 0.000446162 | 0.003991299 | 0.006063212 | 0.688173233 | +0.000055251 | FLATTENED |
| mlb | temperature | 0.004679844 | 0.000037974 | 0.004000465 | 0.004677174 | 0.681249053 | +0.000046086 | FLATTENED |
| mlb | beta | 0.017660220 | 0.000380310 | 0.004048948 | 0.005728801 | 0.682089586 | -0.000002398 | FLATTENED |
| nba | isotonic | 0.024842542 | 0.001346556 | 0.037208760 | 0.040265354 | 0.647664874 | +0.002682371 | FLATTENED |
| nba | temperature | 0.034828317 | 0.001742072 | 0.038059725 | 0.032764018 | 0.606610245 | +0.001831406 | FLATTENED |
| nba | beta | 0.043432376 | 0.002794143 | 0.038678002 | 0.030277160 | 0.611819398 | +0.001213129 | FLATTENED |
| soccer | isotonic | 0.009301789 | 0.000747767 | 0.002236293 | 0.004096912 | 0.694214808 | +0.000578093 | FLATTENED |
| soccer | temperature | 0.007261579 | 0.000289772 | 0.001995079 | 0.002989128 | 0.688264821 | +0.000819307 | FLATTENED |
| soccer | beta | 0.008130583 | 0.000342001 | 0.001581514 | 0.003213489 | 0.689058526 | +0.001232872 | FLATTENED |
| tennis | isotonic | 0.008403090 | 0.000139348 | 0.031035905 | 0.034790111 | 0.629501559 | +0.000680171 | FLATTENED |
| tennis | temperature | 0.007238871 | 0.000073030 | 0.031449365 | 0.033502460 | 0.623861874 | +0.000266710 | FLATTENED |
| tennis | beta | 0.008634880 | 0.000087460 | 0.031458636 | 0.033059052 | 0.623995146 | +0.000257440 | FLATTENED |

No new cell reaches `IMPROVES` (0/8). The result is closed at the sealed
resolution limit; no threshold or bin boundary was changed.

## Bin tables and differential archive

The complete per-sport, per-arm ten-bin tables (bin, n, mean probability,
observed frequency, and gap) are embedded in
`docs/evidence/harness/S205_calib_bakeoff_2026-09-04.json` at
`sports.<sport>.arms.<arm>.reliability_bins`; empty bins remain present. All
three arms have ten bins, and their bin counts each sum to the named sport
denominator.

The paired per-row archive is:

- `S205_calib_bakeoff_2026-09-04_predictions_nba.json` (1814 rows)
- `S205_calib_bakeoff_2026-09-04_predictions_mlb.json` (39162 rows)
- `S205_calib_bakeoff_2026-09-04_predictions_soccer.json` (25834 rows)
- `S205_calib_bakeoff_2026-09-04_predictions_tennis.json` (41886 rows)

Each row retains event id, corpus unit, date, outcome, raw probability, all
three calibrated probabilities, strict fit-history position, and paired raw and
arm log losses. Thus the calibration metrics and row-level differentials can be
recomputed from the committed evidence alone.

## Verification

`python -m pytest scripts/platformkit/eval_gate/test_s205_calib_bakeoff.py -q`
reported `3 passed`. The post-run artifact check recomputed each cell's ECE,
Murphy terms, bin counts, and log loss from the per-row archive; it found four
exact isotonic premise matches and zero dropped rows. No registry, ledger,
data file, feature flag, gate threshold, or S05 artifact was changed.

## Attempt 2: sealed purged CPCV

Verdict: CLOSED AT LIMIT -- the sealed S05 isotonic run cannot be reproduced exactly under the purged CPCV partition (max abs diff 0.020533142); per-cell self-reproduction is not the spec's S05 reproduction result.

Attempt 2 is calibration-only evidence. Before this fresh bakeoff, the
arm-complete preregistration named isotonic, temperature, and beta and embedded
seal `4477066E64105687647CF3E55B72E25727589E8635518BEEDDABBDDE9EF8D5D2` in
`docs/evidence/harness/S205_calibration_prereg_2026-09-03_attempt2.md`.
Every arm used `cpcv_evaluate` with 8 groups, one test group, the engine's
same-team and matchup purge, and a symmetric 1-day embargo. Each sport was
opened and archived independently; the final 12-cell summary was regenerated
in one fresh process at
`docs/evidence/harness/S205_calib_bakeoff_2026-09-04_attempt2.json`.

| sport | arm | ECE | Murphy REL | Murphy RES | sharpness | log-loss | resolution tax | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| mlb | isotonic | 0.004300352 | 0.000062871 | 0.003916546 | 0.005305580 | 0.681666516 | +0.000130005 | FLATTENED |
| mlb | temperature | 0.001975398 | 0.000010598 | 0.003964831 | 0.004690804 | 0.681129055 | +0.000081719 | FLATTENED |
| mlb | beta | 0.001337367 | 0.000006629 | 0.004033128 | 0.004579374 | 0.681207772 | +0.000013422 | FLATTENED |
| nba | isotonic | 0.045375684 | 0.003465095 | 0.039688859 | 0.046017613 | 0.642151198 | +0.000202272 | FLATTENED |
| nba | temperature | 0.031403117 | 0.001533369 | 0.037454855 | 0.038265330 | 0.607120388 | +0.002436276 | FLATTENED |
| nba | beta | 0.044317364 | 0.002697516 | 0.038499079 | 0.033276201 | 0.609779235 | +0.001392052 | FLATTENED |
| soccer | isotonic | 0.003015714 | 0.000305696 | 0.002654998 | 0.003270503 | 0.689877792 | +0.000159388 | FLATTENED |
| soccer | temperature | 0.005239656 | 0.000079204 | 0.002150858 | 0.002803011 | 0.687292331 | +0.000663528 | FLATTENED |
| soccer | beta | 0.012568194 | 0.000179099 | 0.002180677 | 0.003629966 | 0.688128723 | +0.000633709 | FLATTENED |
| tennis | isotonic | 0.005598083 | 0.000053628 | 0.030962340 | 0.032927013 | 0.626113842 | +0.000753736 | FLATTENED |
| tennis | temperature | 0.005559305 | 0.000054427 | 0.031490481 | 0.032403968 | 0.623771465 | +0.000225595 | FLATTENED |
| tennis | beta | 0.005959596 | 0.000065004 | 0.031026205 | 0.031093212 | 0.624343863 | +0.000689871 | FLATTENED |

The four separately remeasured legacy S05 premise values match their published
after-ECE values at 0.0 difference. The CPCV isotonic column intentionally uses
a different OOS partition than S05's legacy prefix process; its maximum absolute
ECE difference from the legacy values is 0.020533142. All 108696 rows remain in
the twelve-cell table and all verdicts remain FLATTENED. The fresh row archives
are `S205_calib_bakeoff_2026-09-04_attempt2_predictions_nba.json`,
`S205_calib_bakeoff_2026-09-04_attempt2_predictions_mlb.json`,
`S205_calib_bakeoff_2026-09-04_attempt2_predictions_soccer.json`, and
`S205_calib_bakeoff_2026-09-04_attempt2_predictions_tennis.json`.

## NOT VERIFIED

- The original exact S05 isotonic-reproduction bar is not met by the mandatory
  CPCV partition; the reported maximum difference is 0.020533142.
- No calibrator is served, promoted, or enabled by this evidence-only work.
- No independent verifier process has yet recomputed every attempt-2 cell from
  the newly archived row predictions.
