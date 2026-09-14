# Q16 win-prob feature challenger vs the close (2026-09-14)

Honest negative: the as-of feature challenger is BEHIND Elo and BEHIND the Shin-devigged close; the blend collapses onto the close. Calibration only; no monetary claim.

# Q16 win-prob feature challenger vs the close

edge_claimed: false

## Premise check

```
{
  "reproduced": false,
  "packet": {
    "model_brier": 0.208,
    "market_brier": 0.198
  },
  "live": {
    "status": "ok",
    "n_overlap": 743,
    "n_holdout": 372,
    "model_brier": 0.1735,
    "market_brier": 0.1672,
    "model_logloss": 0.5259,
    "market_logloss": 0.5038,
    "brier_gap_to_market": 0.0063,
    "corr_model_market": 0.833,
    "verdict": "OUR model MATCHES the close (Brier 0.1735 vs 0.1672, gap +0.0063)",
    "note": "Win-prob accuracy vs the devigged close on real outcomes. calibration only; no monetary claim."
  },
  "as_of": "2026-09-14T16:46:12.228040+00:00",
  "corpus_max_date": "2026-05-24",
  "gap_model": 0.0345,
  "gap_market": 0.0308,
  "reason": "live n_overlap=743, packet has no recorded n (likely a stale snapshot). gaps model=0.0345 market=0.0308 (tol 0.002)."
}
```

## 2024-25

data_limited: fewer than 60 odds-joined rows for this season (odds.parquet covers only 2025-26 today) -- NOT ENOUGH DATA. (n_ml_accuracy_overlap=743, n_after_games_join=0)

## 2025-26

n_ml_accuracy_overlap=743 n_after_games_join=588 n_after_feature_dropna=529 n_train=222 n_test=223 test_date_range=['2026-02-26', '2026-04-12'] best_C=0.1 blend_w=0.17

close is Shin-devigged; close_naive matches ml_accuracy's own proportional (non-Shin) devig of the same odds.

| arm | brier | logloss |
|---|---|---|
| elo | 0.16696 | 0.51231 |
| challenger | 0.18442 | 0.54467 |
| close | 0.15796 | 0.48558 |
| close_naive | 0.15903 | 0.48932 |
| blend | 0.15847 | 0.48746 |

positive mean_diff = the second-named arm has LOWER loss (better)
| pair | mean_diff | dm_p | boot_ci95 | verdict |
|---|---|---|---|---|
| elo_minus_challenger | -0.01746 | 0.0413 | [-0.03449, -0.00074] | BEHIND |
| close_minus_challenger | -0.02646 | 0.0027 | [-0.0438, -0.00995] | BEHIND |
| close_minus_blend | -0.0005 | 0.7238 | [-0.0033, 0.00232] | UNDERPOWERED |
