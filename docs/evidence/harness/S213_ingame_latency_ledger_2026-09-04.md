# S213 In-Game Latency Ledger: Attempt 2

Date: 2026-09-03
Worktree: C:/Users/neelj/nba-track-a16
Spec: docs/evidence/tracking/specs/S213_spec.md
Contract checked: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9

## Outcome

The five-sport ledger is complete. MLB has a measured receipt-to-source
distribution over 90 paired game clusters. NBA, WNBA, soccer, and tennis are
NOT MEASURABLE because their archived Kalshi price-series ticks lack our receive
timestamp field, `captured_at`. No proxy timestamp was substituted.

The denominator for every coverage value is the printed `ticks` count in the
table: every in-play tick object/row from that sport's listed source store. Lag
quantiles use nearest rank, `ceil(p * n) - 1`, and are independently
recomputable from the archived CSV alone.

| Sport | Ticks (denominator) | Game clusters | Paired ticks | Paired clusters | Coverage pct | Lag p50 s | Lag p90 s | Lag max s | Status / missing field |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| NBA | 8,399,632 | 1,835 | 0 | 0 | 0.000000 | n/a | n/a | n/a | NOT MEASURABLE: `captured_at` absent |
| WNBA | 967,102 | 287 | 0 | 0 | 0.000000 | n/a | n/a | n/a | NOT MEASURABLE: `captured_at` absent |
| MLB | 44,015 | 123 | 40,291 | 90 | 91.539248 | 41.0 | 102.0 | 1660.0 | MEASURED: `captured_at - ts` |
| Soccer | 2,466,338 | 324 | 0 | 0 | 0.000000 | n/a | n/a | n/a | NOT MEASURABLE: `captured_at` absent |
| Tennis | 1,854,100 | 986 | 0 | 0 | 0.000000 | n/a | n/a | n/a | NOT MEASURABLE: `captured_at` absent |

The acceptance reporting bar is met: all five required sports are enumerated;
one has a distribution over at least 30 paired clusters and the other four name
the absent field. The four non-measurable routes are CLOSED AT LIMIT under the
current archive schema.

## Attempt 2 and the attempt-1 artefact

Commit `eccaabe1c` recorded attempt 1 as FALSIFIED because its worktree could
not see the named stores. That was a store-visibility artefact, not an absence
of the underlying archives. The current worktree exposes the read-only junctions
at `data/frontend/ops`, `data/domains/mlb/gumbo_live`,
`data/cache/inplay_odds`, and `data/cache/ingame`. This attempt replaces the
attempt-1 missing-store table with the real ledger above.

The re-measurement also corrects two stale count statements in the original
step-0 text: `gumbo_live` has 123 JSONL tick files in `_archive` (and 124 files
including its state JSON), rather than one file, and
`data/cache/depth_history/mlb` is not present in this worktree. Neither fact
changes the timestamp eligibility rule used here.

## Step-0 premise re-measurement

- `C:/Users/neelj/nba-track-a16/data/frontend/ops/inplay_tick_latency.json`
  (2,800 bytes; structured JSON, resolution n/a) has no `lag_p90_sec` or
  `src_ts_coverage_pct` in any `by_sport` result. Its source module's `SPORTS`
  list is `mlb`, `soccer_intl`, `soccer`, `tennis`; NBA is absent.
- `C:/Users/neelj/nba-track-a16/data/frontend/ops/latency_audit.json`
  (1,568 bytes; structured JSON, resolution n/a) reports
  `median_lag_seconds = 34.0`. Its own caveat says 129/135 (95.6 pct) matched
  events had moved on Kalshi before the local tick. This cross-venue number is
  not used as a receipt-to-source lag.
- The GUMBO archive has both `captured_at` and `ts` on 40,291 of 44,015 MLB
  tick objects. `ts` uses the recorded GUMBO timestamp format
  `YYYYMMDD_HHMMSS`; `captured_at` is the local receipt time.
- The Kalshi price-series schemas for NBA, WNBA, soccer, and tennis contain
  `ts` and `event_key`, but no `captured_at`. They therefore cannot make the
  metric meetable by construction.
- `data/cache/ingame` was inspected through Parquet metadata only: 55 Parquet
  files, one with `captured_at`, zero with `ts`/`src_ts`/`venue_ts`, and zero
  with both fields. JSONL files at or over the 300 MB guard were not opened.

## Inputs, bounded read discipline, and reproduction

The ledger module is
`scripts/platformkit/ingame/s213_latency_ledger.py` (207 LOC). It streams one
GUMBO JSONL file at a time. For each price-series Parquet it opens metadata and
then only the `event_key` column for one row group at a time. It reads the
in-game state archive through Parquet metadata only. It makes no network call,
does not write under `data/`, and changes no gate or flag.

The exact absolute source paths, byte sizes, and `N/A (structured ...)`
resolution for every opened GUMBO JSONL and Parquet file are in the summary
manifest below. Per-sport source totals are: NBA one Parquet / 25,140,428 bytes;
WNBA one / 3,270,899 bytes; MLB 123 JSONL / 15,920,996 bytes; soccer two /
6,454,870 bytes; tennis one / 4,948,107 bytes. The in-game metadata manifest
lists 55 Parquet inputs / 17,482,148 bytes.

- Summary and exact input manifest:
  `docs/evidence/harness/S213_ingame_latency_summary_2026-09-04.json`
  (42,725 bytes).
- Archived per-tick differential:
  `docs/evidence/harness/S213_ingame_latency_per_tick_2026-09-04.csv`
  (5,362,735 bytes; 40,291 rows). It carries sport, cluster id, both raw
  timestamps, lag seconds, and source file. Recomputing nearest-rank p50/p90
  from its `lag_seconds` column gives 41.0 / 102.0 seconds; max is 1660.0.

## Frozen gates, re-printed unchanged

- `EVENT_REACTIVE_LAG_P90_SEC = 5.0`
- `EVENT_REACTIVE_COVERAGE_PCT = 95.0`
- `SLOW_STATE_TICK_P90_SEC = 120.0`

The existing EVENT_REACTIVE check remains fail-closed as written: it requires a
non-null lag p90 and coverage meeting both constants. No source file containing
these constants changed, and no flag was enabled.

## NOT VERIFIED

- NBA, WNBA, soccer, and tennis have no archived `captured_at` receipt clock,
  so their venue-to-receipt lag distributions and coverage beyond zero paired
  ticks are not verified.
- The price-series `ts` values are not treated as a replacement for the absent
  receipt clock; their raw trade-tape provenance and millisecond precision were
  not independently verified here.
- The cross-venue 34.0-second audit statistic is adjacent context only, not a
  venue-truth-to-feature measurement.
- The metadata-only state archive and skipped large JSONL files do not establish
  live-capture lag for any sport.
- This archive measurement does not establish current daemon behavior or change
  either frozen EVENT_REACTIVE half.

## Contract self-check

B1: all ticks remain in each printed denominator; excluded paired rows are named
by the missing timestamp field. B2-B6 and B10: additive module and evidence
only; no schema, reader, gate, deployment, or claim-loop change. B7-B9: no
render or fitted metric applies. Q1-Q5: no scored comparison or charged trial.
Q6: calibration language only. Q7: every sport is enumerated and the measured
MLB route has 90 paired clusters. Q8: the premise was re-measured. Q9: the CSV
archives each paired tick's cluster, raw timestamps, and lag, allowing the
distribution to be recomputed without rereading a store.
