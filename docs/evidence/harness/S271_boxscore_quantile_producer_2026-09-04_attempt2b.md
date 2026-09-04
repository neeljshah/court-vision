# S271 attempt 2b box-score quantile producer

## Result

Preregistration: `docs/evidence/harness/S271_boxscore_quantile_prereg_2026-09-04_attempt2b.md`
Seal SHA-256: `a613951b134a47a6c6e1bf7d3c17331e3e2b1c09eab584a75c415a185cfd71e9`

| Stat | Rows | Game clusters | Coverage (80 pct nominal) | 95 pct CI | Q50 pinball | 95 pct CI |
|---|---:|---:|---:|---|---:|---|
| PTS | 23458 | 1266 | 0.894066 | [0.8897599231586296, 0.8985272255604967] | 2.490382 | [2.4639772747937596, 2.516856070915167] |
| REB | 23458 | 1266 | 0.907494 | [0.9033385772482591, 0.9115629152330295] | 0.994293 | [0.9829246562295565, 1.0056820329486273] |
| AST | 23458 | 1266 | 0.900418 | [0.896317964137938, 0.9043498373761395] | 0.720440 | [0.7124337473892157, 0.7281570695819278] |

## Reproduction

- Metrics use evaluator output records only.
- Every held-out row has an exact NBA game id; bootstrap clusters use that id.
- Fit/predict consumes only evaluator train states; the evaluator applies a symmetric one-day embargo.
- Purge assertion: 0 scored rows have a feature source date at or after their game first date.
- Pod RSS MB before/after: 217.31/489.52; wall seconds: 68.21.
- Summary: `docs/evidence/harness/S271_boxscore_quantile_producer_2026-09-04_attempt2b.json`.
- Sample: `docs/evidence/harness/S271_boxscore_quantile_producer_sample_2026-09-04_attempt2b.parquet`.

## Pod log tail

```
RSS_MB before 217.31
FIT_PROGRESS stat=PTS players=500
FIT_PROGRESS stat=REB players=500
FIT_PROGRESS stat=AST players=500
RSS_MB after 489.52
S271_ATTEMPT2B_COMPLETE rows=70374 rss_mb=489.52 wall_seconds=68.21
POD_RUN_DONE rc=0
RSS_PEAK_KB=VmHWM: 1725740 kB
```

## NOT VERIFIED

- Calibration outside the specified 2025-26 held-out period.
- Comparative or deployment behavior; this is a calibration measurement only.
- The rejected attempt's date-cluster and callback-fit limitations are not used here; this rerun uses game clusters and evaluator-owned fitting.
