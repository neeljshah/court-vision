# S274 MLB Distributional Evaluator Route

## Verdict

ACCEPT. The naive empirical MLB batter/pitcher distribution reproduced the
four archived calibration losses through the shared distributional CPCV route
on all 777 date clusters and 3,000 rows. The market-conditioned arm is NULL:
the complete premise census found zero non-null `market_prob` rows, so no
market row was excluded or scored.

This local work occurred in `C:\Users\neelj\nba-track-a15` on branch
`track-a15`. It implements `docs/evidence/tracking/specs/S274_spec.md` and
self-checks sections B and Q1-Q9 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No pod copy, deployment,
ledger, register, or write under `data/` occurred.

## Premise and preregistration

The required evaluator presence binding was run before the preregistration:

```text
FullName: C:\Users\neelj\nba-track-a15\scripts\platformkit\eval_gate\cpcv_distribution.py
Length: 3245
```

The required complete S244 streaming census was also run before the
preregistration and produced:

```text
S244_STREAMING_CENSUS_ROWS=3000
S244_STREAMING_CENSUS_NON_NULL_MARKET_PROB=0
```

The preregistration is
`docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md`.
It was committed alone at `1c806e5005250d4565cb218a1fe0060ddabbe33f` before
the score. Its staged-prefix seal and independent committed-blob verification
are both:

```text
S274_PREREG_SEAL_SHA256=059b9f66161845a9582c99fab16c9fb3949e3f8c02f7d80940e5813fe91c3ed0
```

The focused seal test reads the preregistration file itself, normalizes CRLF
to LF, and hashes the bytes above the seal line; it does not use Git history.
This is a fixed baseline reproduction rather than a charged candidate trial,
so Q2 does not apply and the ledger remains untouched.

## Inputs and route identity

Each input was opened read-only and separately. No opened store was over 300
MB; all resolution fields are none.

| Full path | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `C:\Users\neelj\nba-track-a15\data\frontend\prop_history_corpus_mlb.jsonl` | 1,283,918 | `97a6ebd51c89c456588119c39128099f6492185d414f49a26031a2c10a6c1d0d` | none |
| `C:\Users\neelj\nba-track-a15\docs\evidence\harness\S244_attempt_2_naive_row_series_2026-09-04.csv` | 1,755,183 | `87d5cb75ddb5c9cb49a85f6411df09c7734f1f6d5a00b1445cc3185cbcb6f4a0` | none |
| `C:\Users\neelj\nba-track-a15\scripts\platformkit\eval_gate\cpcv_distribution.py` | 3,245 | `ea6bc6b811d9ad8e71b8ad9a1840fa4d0e17765db07806fe39e2ebfdaa9d0b0b` | none |
| `C:\Users\neelj\nba-track-a15\scripts\platformkit\mlb_batter_pitcher_line_dist.py` | 8,598 | `9d47948779367416bd84bdd97b9ccf879d3e1a51f95392c101cad6d4c5bc4ac4` | none |

The new adapter is
`scripts/platformkit/mlb_batter_pitcher_line_dist_cpcv.py` (10,226 bytes,
SHA-256 `0afed2bbaed6696b9a22470e7381d1341b8fac6a3c7459026b0ecb3b782323a8`).
It maps every CorpusRow to a valid state and calls only
`cpcv_evaluate_distributional` with `n_groups=778`, `n_test_groups=1`, and
the unchanged symmetric `embargo_days=3`. The callback asserts the embargo for
every supplied training state and alone emits CRPS plus pinball q10/q50/q90.
A declared pre-corpus anchor makes the earliest real date testable; it is
excluded from the named real-row denominator. The pre- and post-score hashes
of both protected route files match exactly and are archived in the JSON.

## Shared-route reproduction

The report unit is the unweighted mean of date-cluster means. Every one of the
3,000 parsed real corpus rows is retained in the 777-cluster denominator.

| Quantity | Archived S244 | Shared route | Delta |
|---|---:|---:|---:|
| CRPS | 0.5098297809224259 | 0.5098297809224259 | 0.0 |
| Pinball q10 | 0.08655308369594088 | 0.08655308369594088 | 0.0 |
| Pinball q50 | 0.37323931073931077 | 0.37323931073931077 | 0.0 |
| Pinball q90 | 0.2013804110232682 | 0.2013804110232682 | 0.0 |

Each absolute delta is within the unchanged `<= 1e-9` bar. RSS was 143.171875
MB immediately before scoring and 163.644531 MB immediately after; both are
below the 600 MB limit. The run would abort above that limit.

## Evidence and tests

| New artifact | Bytes | SHA-256 |
|---|---:|---|
| `docs/evidence/harness/S274_mlb_distribution_evaluator_route_2026-09-04.json` | 1,576 | `fb127925a3a042e4ff186c118db5f275efce60552dcf8253724652ddd83a5d7d` |
| `docs/evidence/harness/S274_mlb_distribution_evaluator_route_paired_losses_2026-09-04.csv` | 1,999,926 | `9620dbcdb88418935a21c83c4ef3e51b33460e2c004856435c9cdf598eb4ea18` |

The paired-loss CSV is the Q9 differential archive. For every state it stores
the cluster id, timestamp, state id, reconstructible empirical forecast
samples, training count, archived and route losses, and delta for each of the
four quantities. Both evidence files are below 50 MB.

```text
python -m pytest tests/platformkit/test_s274_mlb_distribution_evaluator_route.py -q -p no:cacheprovider
2 passed in 15.58s
```

The test makes exact assertions only on its seeded fixture. Its real-corpus
checks are structural only: 3,000 unique row states, 777 clusters, the anchor
count, the fixed three-day embargo, and the shared-route row and cluster
denominators.

## Contract self-check and not verified

- B1 and Q7: all 3,000 rows and all 777 clusters are named; the NULL market
  count is coverage, not a dropped subset.
- B2-B6: the changes are additive; no schema reader, deployment path, claim
  loop, ledger, or register changed.
- B7-B9: this is a complete enumeration without a sampled display, fitted
  candidate, or recycled denominator.
- B10 and Q3: the archived values, shared evaluator, and three-day embargo
  are unchanged.
- Q1: the sealed preregistration predates scoring. Q4: scoring uses the shared
  CPCV evaluator with its normal purge and symmetric nonzero embargo. Q5 does
  not apply because no AHEAD result is possible. Q6 uses calibration language
  only. Q8 is the complete premise re-measurement. Q9 is the paired archive.

Not verified: no market-conditioned distribution, price coverage beyond the
complete zero-row census, live deployment, or downstream production behavior.
