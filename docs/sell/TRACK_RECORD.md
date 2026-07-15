# Track Record

> Generated: 2026-07-15T15:41:08.007700+00:00  
> Window: all-time  
> Schema version: 1.0.0

## What this is

Calibrated predictor with a CLV-tracked paper trail. The sellable claim is out-of-sample calibration (Brier / ECE) and closing-line-value discipline under a leak-free, walk-forward, reproducible methodology -- NOT a dollar ROI or edge. A positive mean_clv_pct means bets were recorded at a better number than the close on average. CLV is computed by the vetted clv_ledger and never recomputed here. No dollar P&L is asserted anywhere on this record.

## CLV Summary

| Metric                 | Value            |
|:-----------------------|:-----------------|
| Settled bets (n)       | 2184               |
| Mean CLV               | 15.1570 %               |
| Pct beat close         | 37.00 %               |
| True-close grades      | 983               |
| Proxy-close grades     | 279               |
| edge_claimed           | False               |

## Calibration

| Metric   | Value        |
|:---------|:-------------|
| Status   | unavailable           |
| Brier    | unavailable           |
| ECE      | unavailable           |

## By Sport

| sport        |      n |         mean_clv_pct |       pct_beat_close |  n_true_cl |  n_proxy_cl |
|:-------------|-------:|---------------------:|---------------------:|-----------:|------------:|
| kbo          |     21 |            unavailable |              70.59 % |          0 |          17 |
| mlb          |   2016 |              14.6677 % |              35.38 % |        943 |         199 |
| npb          |     62 |            unavailable |              35.00 % |          0 |          60 |
| soccer_intl  |     42 |            unavailable |          unavailable |          0 |           0 |
| wnba         |     43 |              26.6907 % |              69.77 % |         40 |           3 |

## Signature

| Field   | Value                   |
|:--------|:------------------------|
| Status  | UNSIGNED (no SELL_API_SECRET at build time)                      |
| Algo    | HMAC-SHA256                      |

The opaque HMAC value is NOT rendered here; use `python -m sell.cli verify`
to independently verify the signature (exit 0 = verified).

## How to verify

```
python -m sell.cli verify
# 0 = SIGNATURE_VERIFIED
# 2 = artifact missing (run: python -m sell.cli build)
# 3 = UNSIGNED (no SELL_API_SECRET at build time)
# 4 = SIGNATURE_INVALID (tampered or wrong secret)
```
