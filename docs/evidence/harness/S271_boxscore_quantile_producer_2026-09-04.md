# S271 box-score quantile producer

## Result

Preregistration: `docs/evidence/harness/S271_boxscore_quantile_prereg_2026-09-04.md`
Seal SHA-256: `49058380e65a769345a4a93310170d1abedd10350132de489706b7edb5d809d9`

## Source remeasurement and before condition

Each named input was opened separately (each is below 1 MB). The exact census
was 101765 rows and 2022-10-18 through 2026-05-24 for PTS, REB, and AST.
Evenly spaced realized-target rows were:

| Stat | player_id | date | realized target |
|---|---:|---|---:|
| PTS | 2544 | 2022-10-18 | 31.0 |
| PTS | 1627750 | 2025-02-12 | 55.0 |
| PTS | 1629651 | 2023-03-03 | 2.0 |
| PTS | 1630695 | 2024-04-11 | 2.0 |
| PTS | 1643257 | 2026-04-12 | 0.0 |
| REB | 2544 | 2022-10-18 | 15.0 |
| REB | 1627750 | 2025-02-12 | 4.0 |
| REB | 1629651 | 2023-03-03 | 12.0 |
| REB | 1630695 | 2024-04-11 | 1.0 |
| REB | 1643257 | 2026-04-12 | 0.0 |
| AST | 2544 | 2022-10-18 | 8.0 |
| AST | 1627750 | 2025-02-12 | 5.0 |
| AST | 1629651 | 2023-03-03 | 2.0 |
| AST | 1630695 | 2024-04-11 | 0.0 |
| AST | 1643257 | 2026-04-12 | 0.0 |

The binding before-condition output was:

```text
BEFORE NO_PER_PLAYER_Q10_Q90_PRODUCER scripts/platformkit/boxscore_quantile_producer.py
BEFORE NO_PLATFORMKIT_BOXSCORE_Q10_Q90_TEXT_MATCHES
```

| Stat | Rows | Game-date clusters | Coverage (80 pct nominal) | 95 pct CI | Q50 pinball | 95 pct CI |
|---|---:|---:|---:|---|---:|---|
| PTS | 23458 | 199 | 0.894066 | [0.889661124520483, 0.8981981054371772] | 2.490382 | [2.46101141444376, 2.5199278734064494] |
| REB | 23458 | 199 | 0.907494 | [0.9034145232403569, 0.911678654744431] | 0.994293 | [0.9815681317611183, 1.006778277739069] |
| AST | 23458 | 199 | 0.900418 | [0.8964142050582201, 0.9044465511835874] | 0.720440 | [0.7125883526707519, 0.7276653350139071] |

## Reproduction

- Inputs are the three separately opened q50 source parquets named in the preregistration.
- The sample parquet contains every held-out scored row, including interval failures.
- Purge assertion: 0 rows have a feature source date at or after the scored date.
- The shared evaluator used a symmetric one-day embargo and returned each held-out state once.
- RSS MB before/after: 143.11/245.12.
- Summary: `docs/evidence/harness/S271_boxscore_quantile_producer_2026-09-04.json`.
- Sample: `docs/evidence/harness/S271_boxscore_quantile_producer_sample_2026-09-04.parquet`.

## Verifier self-check

- B1: PASS. Coverage and q50 pinball use every held-out row; interval misses
  remain in the sample denominator.
- B2-B6: PASS. This is additive evidence and new standalone modules only; no
  schema, gate, deployment, or module lifecycle changed.
- B7-B9: PASS. There is no visual sample, self-fit scoring, or recycled unit.
  The uncertainty unit is one calendar-date cluster with 199 clusters per stat.
- B10: PASS. The fixed model and metric definitions are the preregistered ones.
- Q1: PASS. The preregistration path and raw-staged-byte SHA-256 seal are above.
- Q2: NOT APPLICABLE. This measurement has no charged trial or ledger action.
- Q3: PASS. The nominal 80 pct coverage and n-at-least-30 cluster bar remain
  the specified values.
- Q4: PASS. Every held-out state ran through `cpcv_evaluate` with a symmetric
  one-day embargo; the output records each state once.
- Q5: NOT APPLICABLE. This memo makes no comparative AHEAD claim.
- Q6: PASS. This artifact reports calibration metrics only.
- Q7: PASS. Every stat has 199 scored game-date clusters.
- Q8: PASS. The source and producer-absence before conditions are remeasured
  above before the change.
- Q9: PASS. The sample parquet archives all per-row targets, quantiles,
  coverage outcomes, q50 losses, source dates, and cluster dates needed to
  reproduce the reported metrics.
