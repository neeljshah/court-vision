# S240 Boxscore Prop Census - ATTEMPT 2b

## Scope

This is a read-only four-sport census for calibration eligibility. It follows
`docs/evidence/tracking/specs/S240_spec.md` and self-checks
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. It opens no
source larger than 300 MB, reads NBA payloads one file at a time, streams JSONL
one line at a time, and writes no files under `data/`.

## ATTEMPT 2 visibility correction

Attempt 1 recorded NBA as zero files because the documented store was not
visible in this worktree at that time. The orchestrator ruled that a
store-visibility artefact, not a lane attempt. The store is now visible at the
declared worktree path below, so this attempt replaces the prior NBA zero row
with a fresh measurement of all 77 payloads. No substitute store was used.

## ATTEMPT 2b contract correction

Attempt 2b restores the attempt-1 additive output contract: every per-sport
artifact carries `real_market_price_cluster_basis`; the combined summary carries
`real_market_price_source_count` and `unparsed_source_count`; and stdout uses
the original `source_count`, `price_sources`, and `price_clusters` column names.
It also restores relative `source_path` while adding `source_absolute_path`.
NBA tidy rows now include `outcome_name` from the source outcome. The fresh
regeneration retained exactly 48,515 NBA tidy rows before and after this
additive field; no row or source count changed.

## Inputs and method

| Sport | Declared input path | Bytes | Input unit | Cluster unit |
|---|---|---:|---|---|
| NBA | `C:/Users/neelj/nba-track-a17/data/cache/cv_fix/closing_props` | 6,491,336 | JSON file | source filename stem, one game per file |
| MLB | `C:/Users/neelj/nba-track-a17/data/frontend/prop_history_corpus_mlb.jsonl` | 1,283,918 | JSONL row | `ts` calendar date; the corpus has no game-id field |
| Soccer | `C:/Users/neelj/nba-track-a17/data/frontend/prop_history_corpus_soccer.jsonl` | 0 | JSONL row | `ts` calendar date; no rows |
| Tennis | `C:/Users/neelj/nba-track-a17/data/frontend/prop_history_corpus_tennis.jsonl` | 1,230,398 | JSONL row | `ts` calendar date; the corpus has no game-id field |

`scripts/platformkit/boxscore_prop_census.py` emits one deterministic JSON
artifact per sport and `summary.json`. For every NBA file it emits a JSONL row
per outcome to `S240_boxscore_prop_census_2026-09-04/nba_tidy.jsonl`, with the
exact columns `game`, `player`, `outcome_name`, `stat`, `line`, `price`, `book`,
and `timestamp`. `outcome_name` preserves the source outcome side/name, so
paired outcomes remain distinguishable when their prices coincide. `game` is
the source filename stem; `timestamp` is market `last_update`, then bookmaker
`last_update`, then `commence_time` as fallback. The tidy table has 48,515 rows
before and after this correction; its byte count is now 8,337,153 because of
the additive outcome-name field.

A concrete finite `price` is a real NBA market price. A concrete finite
`market_prob` is a real JSONL market price. Counts retain every source file and
every JSONL row, including null prices. The price-cluster denominator is every
declared cluster unit, not only price-bearing units. The 30-cluster rail is
unchanged.

Fresh reproduction command:

```text
python -m scripts.platformkit.boxscore_prop_census
```

The local route SHA-256 for this fresh-process reproduction is
`4fed264637dd066fdd6c456d382215db4492851a5b56d07b449a52c2ae95df9f`.
No pod route was exercised.

## Fresh complete-store census

| Sport | Rows or files | Players | Stats | Date range | Price nulls / price-row denominator | Real-price source count | Real-price clusters / exact denominator | Unparsed | Verdict |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| NBA | 77 files; 48,515 tidy rows | 357 | 3 | 2025-12-11 to 2026-04-11 | 0 / 48,515 (0.0%) | 77 files; 48,515 tidy rows | 77 / 77 file-game clusters | 0 | SCORABLE: n=77 >= 30 |
| MLB | 3,000 rows | 22 | 1 | 2022-04-19 to 2026-06-19 | 3,000 / 3,000 (100.0%) | 0 rows | 0 / 777 date clusters | 0 | NOT SCORABLE: n=0; requires >=30 |
| Soccer | 0 rows | 0 | 0 | none | 0 / 0 (not applicable) | 0 rows | 0 / 0 date clusters | 0 | NOT SCORABLE: n=0; requires >=30 |
| Tennis | 3,000 rows | 44 | 1 | 2015-02-09 to 2025-07-14 | 3,000 / 3,000 (100.0%) | 0 rows | 0 / 389 date clusters | 0 | NOT SCORABLE: n=0; requires >=30 |

The four per-sport artifacts are `S240_boxscore_prop_census_2026-09-04/nba.json`,
`mlb.json`, `soccer.json`, and `tennis.json`; `summary.json` is their combined
table. All four report zero unparsed files or rows, including the combined
summary table. NBA is eligible for a later calibration evaluation on the
cluster-count rail only; no evaluation is fitted or scored here.

## NOT VERIFIED

- This census does not verify a market close timestamp or whether any NBA
  payload is the final pre-game snapshot.
- MLB, soccer, and tennis lack a game-id field in these corpora, so their
  cluster unit is the explicit `ts` date proxy, not independently verified
  individual game identity.
- No outcome, model, calibration score, or comparison is computed by this
  census.
- No price normalization, duplicate-line reconciliation, or cross-book
  selection is performed; every outcome row is retained in the NBA tidy table.

## Contract self-check

- B1: every source file and JSONL row is counted before price eligibility; the
  null-price sets are named in the table.
- B2-B6: this standalone reader preserves the prior field and stdout names,
  adds only the documented fields, and has no callers, gate, deployment, or
  claim loop.
- B7-B9: the census is exhaustive, not a head sample, fitted result, or
  recycled denominator.
- B10 and Q3: the SCORABLE rail is exactly 30 price-bearing clusters.
- Q1-Q5 and Q9: no scored comparison, charged trial, or confidence interval is
  produced.
- Q6: this memo makes calibration-eligibility statements only.
- Q7: n=4 is the specified exhaustive sport construct; the table enumerates all
  four sports and states each cluster denominator.
- Q8: Attempt 2 re-measured the formerly invisible NBA premise before using it.
