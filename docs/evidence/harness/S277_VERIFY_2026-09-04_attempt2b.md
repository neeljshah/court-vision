# S277 verification memo: attempt 2b

## ATTEMPT 2b

This additive correction addresses Attempt 2's B2 compatibility rejection. The
per-tick CPCV route and sealed preregistration are unchanged. The focused test
now asserts that a row planted after a scored tick does not enter that tick's
market-price prior.

| Attempt 2 compatibility field | Attempt 2b representation |
|---|---|
| CSV `outcome_home_win` | Retained beside `y` |
| Summary `mode` | `SEALED_STRATIFICATION` |
| Summary attempt marker | `attempt=2` |
| Summary `rss_bytes` | Alias of `rss_after_bytes` |

The regenerated Attempt 2b CSV, summary, and memo use only new filenames with
the `_attempt2b` suffix. Prior artifacts and the sealed preregistration are
unchanged.

The required `a15` pod scorer completed with RSS before/after of 218894336 /
1124724736 bytes. Its fresh, stale, and pooled Brier table and all reported
confidence intervals reproduce Attempt 2 with max absolute difference
0.00000000000000000. The stale-minus-fresh interaction is 0.001247896101690
[0.000074232527603, 0.002549025437727].

## NOT VERIFIED

- RSS remains machine- and run-dependent.
- No external deployment was performed or verified.
- This memo does not independently re-run the scorer outside the required pod route.
- Non-default output-directory behavior and the absent isolated master test runner
  are outside this bounded correction.
