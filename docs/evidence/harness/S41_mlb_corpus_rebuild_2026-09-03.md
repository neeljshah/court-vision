# S41 -- mlb gate corpus rebuild + freshness_report (ACCEPT)

Gap (register): `data/cache/combo/gate_corpus_mlb.parquet` built 2026-07-05, a source
parquet changed 2026-07-16, so `load_gate_corpus('mlb')` raises `StaleCorpusError` and
blocks every read-only 4-sport row (it blocked S05 attempt 1).

Calibration language only. Nothing here is scored, promoted or charged.

## Step 0 -- PREMISE (Q8): CONFIRMED

Sidecar `gate_corpus_mlb.sources.json` recorded 4 sources at build time 2026-07-05 14:40.
Two had moved:

| source | mtime at build | mtime now | verdict |
|---|---|---|---|
| data/domains/mlb/games.parquet | 2026-06-12 19:07 | 2026-06-12 19:07 | unchanged |
| data/domains/mlb/games_current.parquet | 2026-06-17 10:38 | 2026-07-16 08:59 | CHANGED |
| data/domains/mlb/asof_park.parquet | 2026-06-14 10:15 | 2026-07-08 15:01 | CHANGED |
| data/domains/mlb/asof_features.parquet | 2026-06-13 18:14 | 2026-06-13 18:14 | unchanged |

The other three sports were re-measured at the same time and were NOT stale
(nba 3/3, soccer 2/2, tennis 5/5 sources unchanged) -- mlb was the only blocked sport.

## Step 1 -- rebuild (no build semantics changed)

`build_gate_corpus('mlb')` was called with the builder code UNCHANGED: the diff in
this row adds `freshness_report` and two label constants and touches no builder,
no column list and no merge. The rebuild is the same function over newer sources.

| fact | before (2026-07-05) | after (rebuild) |
|---|---|---|
| rows | 38,809 | 39,162 (+353) |
| column set | 8 cols | 8 cols -- **identical**, 0 added, 0 removed |
| corpus_unit era_2010_2021 | 27,983 | 27,983 (unchanged) |
| corpus_unit era_2022_2026 | 10,826 | 11,179 (+353) |
| distinct event_id | 38,809 | 39,162 |
| y non-null | 38,809 / 38,809 | 39,162 / 39,162 |
| p_base non-null | 38,809 / 38,809 | 39,162 / 39,162 |

Column set (both): `event_id, corpus_unit, y, p_base, p_home_elo, sp_first6_diff_ew,
park_factor, sp_ra_diff_asof`. A changed column set would have been a NEW GAP; there
is none.

Row-level agreement on the overlap: 38,800 event_ids appear in both. On those rows
`y` mismatches = 0/38,800 and `max|p_base_old - p_base_new|` = 0.0 -- the rebuild is
value-identical where the source did not move. **362 event_ids are new and 9 old
event_ids are GONE** (38,809 - 38,800): the refreshed `games_current.parquet` dropped
them upstream. That is a source fact, reported not repaired.

`load_gate_corpus('mlb')` now returns 39,162 rows instead of raising. Rebuild wall
time 3.3 s.

## Step 2 -- additive `freshness_report(sport) -> dict`

New public function in `scripts/platformkit/combo/corpus_cache.py`. Read-only: it never
rebuilds and, unlike `load_gate_corpus`, never raises on a stale cache -- it returns
`stale` as a plain bool so a caller can report instead of refuse. Keys: `sport`,
`corpus_path`, `cache_exists`, `sidecar_exists`, `cache_mtime`, `built_at`,
`n_rows_at_build` (what the sidecar recorded), `n_rows_cached` (what the parquet holds
now), `sources` (per source: `exists`, `mtime_at_build`, `mtime_now`, `changed`),
`stale`, `stale_reason`, `order_basis`.

Live output, all four sports, after the rebuild:

| sport | stale | n_rows_at_build | n_rows_cached | order_basis | built |
|---|---|---|---|---|---|
| mlb | False | 39,162 | 39,162 | POSITIONAL-ORDER | 2026-09-02 09:05 |
| nba | False | 1,814 | 1,814 | POSITIONAL-ORDER | 2026-07-05 16:18 |
| soccer | False | 25,834 | 25,834 | POSITIONAL-ORDER | 2026-07-05 14:41 |
| tennis | False | 41,886 | 41,886 | POSITIONAL-ORDER | 2026-07-05 14:41 |

4/4 sports now load. `order_basis` is S44's fact surfaced here: no gate corpus carries
a date column today, so any walk-forward over them is ordered by row position only.

Additive check (B2): no existing name, column, status value or signature changed;
`__all__` gains three names and loses none. Both readers of the module
(`combo/batch_gate.py:193`, `eval_gate/close_join.py:91`) call `load_gate_corpus`,
which is untouched.

Downstream effect, named not hidden: `autoloop/standing_prereg._gate_corpus_sha('mlb')`
hashes the sidecar's `{source: sha256}` manifest, so the mlb corpus watermark moves with
this rebuild. That is the watermark working as designed (the corpus really did change),
not a defect.

## Test

`python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q`
-> **6 passed in 0.63s**. Cases (all on a tmp cache dir, real files, no mocks):
fresh cache -> `stale is False` and counts agree; source rewritten -> `stale is True`
and `stale_reason` names the file; missing cache -> stale; no date column ->
`order_basis == POSITIONAL-ORDER`; date column present -> `order_basis == event_date`;
unknown sport -> ValueError.

## ACCEPTANCE

metric = mlb corpus loadable + freshness_report correct; denominator = 4 sports.
before = 3/4 loadable (mlb raised StaleCorpusError). after = **4/4**.
n = 6 (CONSTRUCT) for the freshness test -- the enumeration of the report's branches
(fresh / changed source / missing cache / two order bases / bad sport) is exhaustive;
39,162 real mlb rows for the rebuild.
must not move: build semantics (unchanged -- 0 builder lines touched), every existing
column (0 changed), `data/registry/**` (untouched),
`data/cache/eval_gate/backtest_fwer.jsonl` (untouched, no `_charge_ledger` call).

## NOT VERIFIED

- The 9 dropped and 362 added event_ids were NOT traced to an upstream reason; only
  counted.
- `freshness_report` was exercised against real data only in the read-only table above;
  the stale branch on a real corpus is proven only on the tmp copy in the test.
- No downstream consumer was re-run on the new mlb corpus in this row: any prior mlb
  number computed from the 38,809-row build is now computed on a different corpus and
  must be recomputed before it is compared to anything.
- `corpus_cache.py` is 335 lines, over the 300-line rail by 35. Kept as one module
  deliberately: `freshness_report` reads the two private path helpers and the builder
  registry, and splitting it would export those privates across modules.
- `order_basis` reports what the CACHED parquet carries, not what the source could
  carry -- that is S44's row.
