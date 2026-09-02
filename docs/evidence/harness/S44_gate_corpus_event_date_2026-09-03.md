# S44 -- a real date column on the four gate corpora (ACCEPT)

Gap (register): the gate corpora carry NO date/timestamp column, so
`walk_forward_recalibrate` (and any walk-forward over them) is chronological only
by row position; every leak-free claim built on these corpora is positional.
Fix at the builder or label every such artifact POSITIONAL-ORDER.

Calibration language only. Nothing is charged, promoted or served.

## Step 0 -- PREMISE (Q8): CONFIRMED, and the source HAS a date

`freshness_report` (landed by S41) reported `order_basis = POSITIONAL-ORDER` for all
four cached corpora -- none carried a date column. But every source parquet does:
`data/domains/mlb/games_current.parquet` `date` (datetime64), `basketball_nba/games.parquet`
`date` (datetime64), `soccer/matches.parquet` `date` (Timestamp), `tennis/matches.parquet`
and `wta_matches.parquet` `date` (object). Each builder already had the date IN HAND --
mlb and tennis from the walk-forward Elo frame, nba from the games merge, soccer from
`walk_forward_goals` -- and then dropped it in the final column selection. So this is
the fix-at-the-builder branch, not the label-it branch.

## CHANGE -- additive `event_date`, nothing renamed

Four one-line assignments in `scripts/platformkit/combo/corpus_cache.py`
(`df[DATE_COL] = df["date"]`, one per builder) plus `DATE_COL` added to each builder's
returned column list. **No column, key or signature was renamed or removed**; the
`DATE_COL` / `POSITIONAL_ORDER` constants already existed from S41.

Rebuild of all four (5.9 s total) is strictly additive -- verified column by column
against the pre-change parquets:

| sport | rows before -> after | added | removed | pre-existing columns identical (`DataFrame.equals`) |
|---|---|---|---|---|
| mlb | 39,162 -> 39,162 | `event_date` | none | **True** |
| nba | 1,814 -> 1,814 | `event_date` | none | **True** |
| soccer | 25,834 -> 25,834 | `event_date` | none | **True** |
| tennis | 41,886 -> 41,886 | `event_date` | none | **True** |

`freshness_report(sport)["order_basis"]` now reports `event_date` for 4/4 sports
(before: `POSITIONAL-ORDER` for 4/4).

## The measurement that matters: positional order is NOT chronological order

With a real date on the frame the question becomes answerable for the first time.
0 null dates on all four corpora.

| sport | date range | monotonic over the WHOLE frame | monotonic WITHIN each corpus_unit |
|---|---|---|---|
| mlb | 2010-04-04 .. 2026-07-12 | **True** | True (era_2010_2021, era_2022_2026) |
| nba | 2024-10-22 .. 2026-04-12 | **True** | True (2024-25, 2025-26) |
| soccer | 2015-08-07 .. 2026-05-24 | **True** | True |
| tennis | 2015-01-04 .. 2025-12-17 | **False** | True (ATP, WTA) |

**Tennis is the real finding.** `_build_tennis` concatenates the whole ATP frame
(30,616 rows, 2015-01-04 .. 2025-12-17) ahead of the whole WTA frame (11,270 rows,
2015-01-19 .. 2025-11-01). Each tour is chronological on its own, but the frame as a
whole jumps back ten years at row 30,616. Any GLOBAL positional walk-forward over the
tennis gate corpus therefore trains on 2025 ATP matches before scoring 2015 WTA ones.
That is not a leak in the strict sense -- the two tours are disjoint corpus_units with
no shared player state -- but it is not a chronological pass either, and it was
invisible before this row. Recorded, not repaired: re-scoring tennis in date order is a
different measurement and is filed below.

## Effect on the S05 calibration artifacts

The four artifacts were regenerated on the dated corpora. To keep the ordering claim
honest rather than merely present, `calibration_report._stamp` now separates two facts
that S05 conflated into one key:

- `order_basis` -- how the SCORING was ordered. It is `POSITIONAL-ORDER` and stays
  `POSITIONAL-ORDER`, because `walk_forward_recalibrate` consumes row order and never
  reads a date. Surfacing a date column does not by itself make a pass chronological.
- `corpus_date_column` -- what the corpus now carries: `event_date` on all four.

Diffed key by key against the S05 landing `504617a99`, **the only key that changed in
any of the four artifacts is the new `corpus_date_column`**. Every n, every bin, every
ECE, every Murphy term, every sharpness figure and every verdict is byte-identical,
and `reproduction_max_abs_diff` is still exactly 0.0 on all four.

## Test

`python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q`
-> **10 passed in 0.79s** (6 from S41 + 4 new, one per sport). The new case asserts each
real cached corpus carries `event_date`, that it has no nulls, that it is monotonic
WITHIN each `corpus_unit` (deliberately not across units -- that assertion would fail on
tennis, which is the point), and that `freshness_report` reports `event_date`. It skips
where `data/` is absent, since a git worktree has no data tree.

`python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q`
-> **6 passed in 2.00s**, unchanged by the `_stamp` split.

## ACCEPTANCE

metric = gate corpora carrying a real date column; denominator = 4.
before = 0/4 (`order_basis = POSITIONAL-ORDER` on all four). after = **4/4**
(`order_basis = event_date` from `freshness_report`).
n = 39,162 + 1,814 + 25,834 + 41,886 = 108,696 rows, 0 null dates.
must not move: every pre-existing column and value (verified identical on all four via
`DataFrame.equals`), every row count, no rename, no threshold, `data/registry/**`,
`data/cache/eval_gate/backtest_fwer.jsonl` (not opened; no `_charge_ledger`).

## NEW GAP

`NEW GAP: the tennis gate corpus is not globally chronological (ATP's 30,616 rows are
concatenated ahead of WTA's 11,270, so row order jumps from 2025-12-17 back to
2015-01-19 at row 30,616). Every global positional walk-forward over it -- including
S05's tennis figure, ECE 0.038691 -> 0.008403 -- trains on later ATP matches before
scoring earlier WTA ones. Re-score tennis ordered by event_date and report whether the
figure moves, or make the pass per-corpus_unit.`

## NOT VERIFIED

- `event_date` is the builder's own `date` field passed through unchanged; it was NOT
  audited for what the upstream source means by it (scheduled vs settled date, timezone,
  double-headers).
- tennis `date` arrives as an object dtype and is compared after `pd.to_datetime`; the
  stored column keeps the source dtype rather than being coerced, so a consumer must
  parse it.
- No consumer was changed to ORDER BY the new column. `walk_forward_recalibrate`,
  `batch_gate.py:193` and `close_join.py:91` all still consume row order; this row makes
  chronology checkable, not enforced.
- Only the four artifacts of this lane were regenerated. Any other number previously
  computed from these corpora is untouched and unre-verified.
