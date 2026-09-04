# S244 MLB Batter Pitcher Line Distribution

## Verdict

SUCCESS: NOT SCORABLE against a market. The complete streaming census found
exactly 0 non-null `market_prob` rows and 0 price-bearing date clusters, below
the unchanged 30-cluster rail. ATTEMPT 2 scores the preregistered naive-only
baseline on all 777 date clusters. No market arm was scored or described.

## Machine and inputs

This work ran locally in `C:\Users\neelj\nba-track-a13` on branch `track-a13`.
No pod, deployment, ledger, register, or external input was used. Each data
store was opened separately; no opened store exceeded 300 MB.

| Path | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `data/frontend/prop_history_corpus_mlb.jsonl` | 1283918 | `97A6EBD51C89C456588119C39128099F6492185D414F49A26031A2C10A6C1D0D` | none |
| `data/domains/mlb/player_gamelogs.parquet` | 3510200 | not separately hashed | none |
| `docs/evidence/harness/S233_walkforward_embargo_prereg_2026-09-04.md` | 5604 | `19CE44E3DB42213E614D0F08E430344411F98581E9AD2E5172524D154CC1B1DB` | none |
| `docs/evidence/harness/S241_nba_minutes_distribution_2026-09-04.md` | 5118 | `DF6F86478A53CC3F3CC0DF57288DDD095032229E11261C8657D493F88DD230BF` | none |

The declared feature sidecars were surveyed by filename before any modeling:
`mlb_batter_context_platoon_*.parquet` matches = 0 and `*vs_pitch_type*`
matches = 0. They were not assumed to have columns.

## Binding before-condition and premise census

The before-condition in S244 is that 0 MLB player-prop rows have previously
been scored against either a market or a baseline. The exact S244 artifact and
module binding was rerun before this landing and produced:

```text
S244_EVIDENCE_FILES=0
S244_MODULE_FILES=0
```

The S244 price premise was then measured in one complete streaming JSONL pass.
It produced:

```text
MLB_PARSE_TOTAL=3000
MLB_PARSE_DISTINCT_PLAYERS=22
MLB_PARSE_DISTINCT_PROP_STATS=1
MLB_PARSE_NON_NULL_MARKET_PROB=0
MLB_PARSE_UNPARSED=0
MLB_PARSE_PROP_STATS=strikeouts
```

The single stat family selected by the census is `strikeouts`. No row was
silently skipped. The corpus date clusters total 777; exactly 0 carry a
non-null price.

## Parsed schemas and settlement join

The streamed JSONL object schema is:

```text
sport, market_type, status, model_prob, market_prob, prop_side, outcome,
line, realized_stat, prop_player, prop_stat, ts, bet_id, market, clv_status,
edge_claimed, executed
```

The separately opened box-score schema provides `player_id` and `date` for the
required join, plus player and batting/pitching counting-stat fields. The
`prop_player + date` join produced:

```text
BOX_JOIN_SETTLED_CORPUS_ROWS=3000
BOX_JOIN_DISTINCT_PROP_PLAYER_DATE_KEYS=2975
BOX_JOIN_MATCHED_PLAYER_DATE_KEYS=2975
BOX_JOIN_MATCHED_SETTLED_ROWS=3000
```

Thus all 3,000 settled corpus rows have an on-disk box-score player-date key.

## Attempt 1 evaluator limit

S244 requires walk-forward scoring through
`scripts/platformkit/eval_gate/walkforward_embargo_prereg.py` (S233), with
purge and a symmetric nonzero embargo. Its existence binding was rerun:

```text
S233_ROUTE_EXISTS=False
S233_ROUTE_MATCHES=0
```

S233 itself is a premise-falsified landing and records that no such shared
module was created. S241 independently applies this same absent-route binding
as CLOSED AT LIMIT. ATTEMPT 1 therefore made no score. ATTEMPT 2 uses the
spec-permitted smallest additive helper, documented below, without changing an
`eval_gate` module.

## CRPS and pinball table

ATTEMPT 1 had no scored comparison. ATTEMPT 2's sealed preregistration and
complete naive-only score supersede its uncomputed naive cells.

| Comparison | Game clusters | CRPS | Pinball q10 | Pinball q50 | Pinball q90 | Status |
|---|---:|---:|---:|---:|---:|---|
| Distribution versus naive as-of baseline | 777 of 777 total; 3,000 rows | 0.5098297809224259 | 0.08655308369594088 | 0.37323931073931077 | 0.2013804110232682 | SUCCESS: complete naive-only baseline score |

No market loss row is emitted: the exact price-bearing denominator is 0 of 777
clusters, so this table contains the required naive loss alone.

The additive row series and cluster series are listed in ATTEMPT 2. They retain
every scored quantity needed to recompute the table without reopening the
source corpus.

## Focused test

ATTEMPT 2: `python -m pytest tests/platformkit/test_mlb_batter_pitcher_line_dist.py -q -p no:cacheprovider`
returned `2 passed in 0.51s`. The LOC rail command
`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`
returned `1 passed in 1.80s`.

## Attempt 1 verifier self-check

- B1: all 3,000 JSONL rows were counted, including all null-price rows; no
  metric was filtered or computed.
- B2-B6: no schema, reader, gate, deployment, claim path, source module, data
  file, ledger, or register was changed.
- B7-B9: no sampled render, fitted comparison, or metric denominator was used.
- B10 and Q3: the 30-cluster rail is unchanged.
- Q1, Q2, Q4, Q5, and Q9: no scored or charged comparison occurred, no ledger
  was touched, no OOS result was claimed, and no differential is applicable.
- Q6: this memo uses calibration-only language.
- Q7: no construct is claimed.
- Q8: both the before-condition and the complete price premise were rerun
  before deciding this close.

## Attempt 1 not verified

The additive distribution module, its mixed-price fixture, sealed
preregistration, walk-forward baseline score, CRPS, pinball losses, and
per-cluster differential were unverified at the ATTEMPT 1 close because the
required shared evaluator route was absent.

## ATTEMPT 2: sealed naive-only scoring

The preregistration was committed before the first score at commit
`370a9c980b03ee434cd0f475b67a5cf944fea283`. Its seal is the SHA-256 of the
LF bytes above its seal line, verified from `git show HEAD` before scoring:

```text
S244_PREREG_SEAL_SHA256=76F24D16D406B5D44DDA14D533C441A2D07DFA1B11C873F9C0B3C07C6F79315B
S244_PREREG_PREFIX_BYTES=3059
```

The additive route is
`scripts/platformkit/mlb_batter_pitcher_line_dist.py` (152 lines; SHA-256
`EF71679808249C6709F6C453114D5182D427B54CF14868784B045C57A7565A5F`). It
uses one chronological fold per date cluster. For each scored date, training
observations are strictly at least four calendar days earlier, and the callback
asserts that every retained training date is more than three calendar days from
every scored row in that fold. This is the fixed past-only purge plus symmetric,
nonzero three-day embargo. The shared binary `cpcv_evaluate` interface cannot
receive an empirical continuous-distribution callback; no shared evaluator file
was changed.

The callback uses the player's own earlier `realized_stat` values as empirical
forecast samples. It retains every raw prior settled observation, including
same-player same-date entries, because 25 repeated player-date keys are not all
equal. It records, rather than excludes, the 48 rows with no eligible player
history; their preregistered cold-start distribution is the point mass at 0.0.

| Quantity | ATTEMPT 1 | ATTEMPT 2 |
|---|---|---|
| Scored naive date clusters | 0 | 777 of 777 |
| Row denominator | 0 | 3,000 parsed settled rows |
| Naive CRPS | not computed | 0.5098297809224259 |
| Naive pinball q10 | not computed | 0.08655308369594088 |
| Naive pinball q50 | not computed | 0.37323931073931077 |
| Naive pinball q90 | not computed | 0.2013804110232682 |

The table is an unweighted mean of the 777 per-date cluster means. The named
underlying row denominator is 3,000; no null-price, duplicate, or cold-start
row was silently excluded. The full reparse and score output is:

```text
MLB_PARSE_TOTAL=3000
MLB_PARSE_UNPARSED=0
MLB_PARSE_DISTINCT_PLAYERS=22
MLB_PARSE_PROP_STATS=strikeouts
MLB_PARSE_NON_NULL_MARKET_PROB=0
MLB_DATE_CLUSTERS=777
MLB_SCORE_CLUSTER_COUNT=777
MLB_SCORE_ROW_DENOMINATOR=3000
MLB_SCORE_COLD_START_ROWS=48
```

| Additive artifact | Bytes | SHA-256 | Contents |
|---|---:|---|---|
| `docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv` | 1752182 | `C6A7C48D8717B1AC74A1CC7F344D4AC67B9E45F8D219CC05409BED6366A01653` | 3,000 row forecasts, samples, and losses |
| `docs/evidence/harness/S244_attempt_2_naive_cluster_losses_2026-09-04.csv` | 55618 | `6026F5B02B8BD7914DD0FA3C1A88DF62173856C878DD8D77A4417F6AB4E6B84F` | 777 date-cluster losses |

The immutable corpus remains 1283918 bytes with SHA-256
`97A6EBD51C89C456588119C39128099F6492185D414F49A26031A2C10A6C1D0D`.
The A1 test recomputes CRPS and q10 pinball for the archived 2024-05-13 cluster
from its row-level empirical samples, then matches the cluster archive to
1e-12. Its additional fixture proves mixed null/non-null prices parse and that
the naive path does not require a market column.

### ATTEMPT 2 verifier self-check

- B1: all 3,000 parsed rows form the named denominator; the 48 cold starts are
  recorded in both archives rather than excluded.
- B2-B6: the new module and archives are additive; no schema, source data,
  protected evaluator, deployment, claim path, ledger, or register changed.
- B7-B9: this is a complete 777-cluster enumeration with no fitted candidate.
- B10 and Q3: the 30-cluster rail is unchanged.
- Q1: the committed preregistration and its Git-blob seal predate scoring.
- Q2: no charged candidate trial or ledger field exists for this naive-only
  non-market baseline.
- Q4: the additive callback asserts the fixed past-only purge and symmetric
  nonzero embargo for every scored fold.
- Q5: no AHEAD claim is made. Q6: calibration language only. Q7: the complete
  scored set has 777 clusters. Q8: the premise was re-parsed in full. Q9: the
  row and cluster archives retain all forecast samples and per-unit losses.

### ATTEMPT 2 NOT VERIFIED

- A market or closing-line distribution is not verified: exactly 0 corpus rows
  and 0 clusters have a non-null `market_prob`.
- No feature-conditioned candidate distribution is verified; this is the
  required naive-only baseline at the non-price limit.
- No statement beyond the archived naive-loss calibration values is verified.
