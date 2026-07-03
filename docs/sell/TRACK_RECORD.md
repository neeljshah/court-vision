# Track Record

> Generated: 2026-06-18T20:49:16.394490+00:00  
> Window: all-time  
> Schema version: 1.0.0

## What this is

Calibrated predictor with a CLV-tracked paper trail. The sellable claim is out-of-sample calibration (Brier / ECE) and closing-line-value discipline under a leak-free, walk-forward, reproducible methodology -- NOT a dollar ROI or edge. A positive mean_clv_pct means bets were recorded at a better number than the close on average. CLV is computed by the vetted clv_ledger and never recomputed here. No dollar P&L is asserted anywhere on this record.

## CLV Summary

| Metric                 | Value            |
|:-----------------------|:-----------------|
| Settled bets (n)       | 0               |
| Mean CLV               | unavailable               |
| Pct beat close         | unavailable               |
| True-close grades      | 0               |
| Proxy-close grades     | 0               |
| edge_claimed           | False               |

## Calibration

| Metric   | Value        |
|:---------|:-------------|
| Status   | unavailable           |
| Brier    | unavailable           |
| ECE      | unavailable           |

## By Sport

(no settled bets by sport)

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
