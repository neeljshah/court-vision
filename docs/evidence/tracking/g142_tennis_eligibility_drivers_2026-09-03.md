# G142: tennis jump-gate eligibility drivers

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), section A (including
A7) and section B. Verdict: **ACCEPT** as a read-only evidence census. It
changes no threshold, 10-table bar, coordinate contract, queue, bridge, cookie
jar, pod file, or pod process.

## Census moment and unit

At **2026-09-03T02:18:10Z to 2026-09-03T02:18:11Z**, a single read-only pod
glob of `/workspace/nba-ai-system/data/tracking/*/tracking_data.csv` found
**16 distinct tennis source-table directories**. One directory is one unit;
rows, frames, retries, and daemon-ledger outcomes are not units.

The full one-row-per-table census is
[table_census.csv](g142_drivers/table_census.csv). First blockers use G109's
ordering and vocabulary, compressed only where this specification requires it:
empty/header-only before prerequisites; a declared `image_px` value would be a
coordinate-contract rejection; a missing coordinate declaration or required
schema is `other`; `INSUFFICIENT_DATA` is under 30 distinct frames only after
the preceding prerequisites; and the remaining table must have usable player
fields plus one unique positive modal same-track stride to reach the gate.

| First blocker | Tables | Share of all 16 |
|---|---:|---:|
| reaches gate | 8 | 8/16 |
| coordinate-contract rejection | 0 | 0/16 |
| INSUFFICIENT_DATA | 1 | 1/16 |
| empty or header-only | 2 | 2/16 |
| other: missing coordinate declaration | 5 | 5/16 |

The eight gate-reaching tables are `g89_tennis_09`, `g89_tennis_10`,
`g89_tennis_nyYk2nPZAwY_720p`, `tennis_06`, `tennis_07`, `tennis_08`,
`tennis_3x3eEWCZmWQ`, and `tennis_nyYk2nPZAwY`. The eligible count remains
**8 of 16**, so two additional independently eligible tables are needed to
reach the unchanged bar of 10.

## Eligible-versus-rest comparison

The additive comparison is in
[attribute_comparison.csv](g142_drivers/attribute_comparison.csv). The useful
result is not a source-quality separation:

- Rows: gate-reaching tables total 45,065 rows with median 2,476.5; the other
  eight total 29,377 with median 2,428. Five of the eight non-eligible tables
  already have at least 1,951 frames, so raw table size is not sufficient.
- Distinct frames: the gate group totals 18,267 with median 1,053; the rest
  total 16,549 with median 2,428. Five of eight non-eligible tables clear the
  30-frame floor but stop earlier on the missing coordinate declaration.
- Coordinate declaration: 8/8 gate-reaching tables are `court_feet`; only
  1/8 of the rest is `court_feet` (the two-frame `tennis_09`). The other 7/8
  are five missing declarations and two header-only outputs. There are no
  tennis `image_px` coordinate-contract rejections.
- Source duration/resolution: direct current fields survive for only 3/8 gate
  tables (`tennis_06`--`tennis_08`: 25 fps, 720 high, 963.4/962.04/2583.84 s)
  and 0/8 rest tables. A historical inventory has conflicting frame totals for
  same-named inputs, so it is not used as a source-duration or coverage join.
- Coverage: a directly comparable current `coverage_pct` is retained for only
  those same 3/8 eligible tables (0.0059, 0.1216, and 0.0) and for 0/8 rest
  tables. It cannot support an eligible-versus-rest coverage claim.
- Acquisition queue/search term: 0/16 table records retains a per-table queue
  entry or search query. The read-only daemon ledger identifies outcomes, not
  source-query provenance; no acquisition-term comparison is possible.

Two required raw checks opened non-eligible source files. `tennis_01` has
populated rows but only the bare `frame,track_id,cls,x,y` schema, confirming
`other` for its missing coordinate declaration. `tennis_10` has a header and
no data rows, confirming empty/header-only. The exact observations are in
[raw_file_checks.csv](g142_drivers/raw_file_checks.csv).

## Driver and acquisition implication

**The observed driver is output provenance, not source size: every gate-reaching table carries a `court_feet` declaration, while five of eight non-eligible tables have abundant rows and frames but lack that declaration.**

Acquisition should therefore prefer new tennis sources that enter the current
court-feet-capable tennis tracking route; there is no retained evidence for a
particular duration, resolution, queue, or search phrase to prefer. The cost
is ordinary acquisition and tracking capacity, plus a user cookie refresh if
the documented tennis HTTP 403 source block persists; no queue, duration
floor, cookie, or bridge was changed here.

## Forecast

Forecast refused again. G133's only time-bounded terminal measurement remains
2 tracked tennis games in 1.978056 hours, with 2/2 eligible. This census adds
classification breadth (8/16) but no new timestamped terminal measurement or
per-table acquisition timing, so it does not increase that forecast sample.
The conditional arithmetic remains two tables needed divided by 2 eligible
tables per 1.978056 hours, or 1.978056 hours, only if future terminal rate,
conversion, uniqueness, and operating conditions repeat exactly. With n=2 and
unmeasured acquisition timing, that is not a forecast.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added, so no per-file test exists to rerun.
- **A2:** Recomputed from `table_census.csv`: 16 unique table names; bucket
  counts 8, 0, 1, 2, and 5 sum to 16; the eight named gate-reaching tables are
  unique.
- **A3:** No render decision set applies to this exhaustive CSV census. The
  two required raw-file checks cover two different non-eligible categories,
  not a leading file slice.
- **A4:** `table_census.csv` has 16 unique table names. Each count uses one
  source-table directory, never its rows, frames, or daemon attempts.
- **A5:** Evidence only; no production field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `a2` only. It
  does not archive-land, append a results-ledger/register row, deploy, or
  alter the pod; landing remains verifier/orchestrator work.
- **A7:** Before commit/report, every named repository path is checked: this
  memo; all three `g142_drivers/` CSVs; G131; G133; G109; the tracking gap
  register; and `VERIFIER_CONTRACT.md`.

### B

- **B1 CIRCULAR METRIC:** Clear. The full live tennis glob is classified
  before group comparison; every excluded table and first blocker is named.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Missing declaration, insufficient frames,
  and empty output remain explicit blockers rather than a bad-quality verdict.
- **B4 RE-CLAIM LOOP:** Clear. No queue, claim, retry, or ownership path changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. Pod access was read-only; no file was
  copied, created, restarted, killed, or re-tracked.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The census is the complete one-pass glob;
  raw checks cover distinct non-eligible buckets.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The denominator is distinct source-table
  directories, not recycled rows, frames, tracks, or ledger outcomes.
- **B10 MOVED BAR:** Clear. No threshold, coordinate contract, verdict, or
  10-table bar changed.

## NOT VERIFIED

- A source-duration, resolution, or coverage driver across all 16 tables:
  current direct source metadata exists for only 3 eligible tables and none of
  the rest; a same-name historical inventory conflicts with current frame data.
- Any queue or search-term driver: no per-table acquisition-query provenance
  survives in the available read-only artifacts.
- A time-to-10 forecast or stable conversion rate: the only time-bounded
  post-repair terminal sample remains G133's n=2.
- Whether a new `court_feet` table will be eligible or pass downstream quality
  checks. This result concerns only reachability of the frozen jump input.
