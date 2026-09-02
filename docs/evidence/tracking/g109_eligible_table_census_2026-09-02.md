# G109 eligible-table census

**Verdict: ACCEPT WITH CORRECTIONS.** This is a read-only, point-in-time
census of the live pod's canonical
`data/tracking/*/tracking_data.csv` tables. It follows
`VERIFIER_CONTRACT.md`, including A7 and every B condition. No threshold,
verdict, coordinate contract, pod file, pod process, or G107 artifact changed.

## Premise and frozen population

G107's committed snapshot is the starting point, not a reconstruction target:
it recorded 193 tables and 6 jump-gate-eligible tables. The fresh, one-pass
read-only glob for this census contained **196 distinct source-table
directories**. Its population is therefore 196, not the stale 193.

The G107 premise is partly falsified by ordinary corpus growth. In particular,
`tennis_06` is now a 340-row, 141-frame `court_feet` table and is eligible,
raising the eligible count from 6 to **7**. Two additional source directories
also appeared during the interval. The live corpus can continue to grow after
this snapshot; this memo does not chase it.

Each source directory is one unit. The complete frozen classification is
`g109_eligibility/table_census.csv`; its summary is
`g109_eligibility/bucket_summary.csv`.

## First-blocker order

A table is assigned exactly one bucket, in this order:

1. unknown sport routing;
2. empty or header-only output;
3. an all-`metric_local` scope;
4. a declared `image_px` coordinate-contract rejection;
5. missing coordinate declaration or another required schema prerequisite;
6. `INSUFFICIENT_DATA` (`n_frames < 30`) after the preceding prerequisites;
7. eligible to reach the court-feet jump calculation.

This ordering deliberately distinguishes the G107 snapshot's
`not_all_court_feet` cases (declared `image_px`) from its
`missing_required_columns` cases. The latter is an observed sixth bucket,
not an assumption hidden inside the coordinate-contract bucket. A table never
appears twice: the counts below sum to 196.

## Census

| First blocker | Tables | Eligible-table gain if that blocker alone is fixed |
|---|---:|---:|
| declared `image_px` coordinate contract | 131 | 131 |
| missing coordinate declaration or required schema | 48 | 46 |
| empty or header-only output | 7 | 0 |
| insufficient data | 2 | 1 |
| metric-local scope | 0 | 0 |
| unknown sport routing | 1 | 0 |
| already eligible | 7 | 0 |
| **Total** | **196** | **not additive** |

The gain column is intentionally not a second count of the buckets. It asks
whether a table reaches the jump calculation after only its assigned blocker is
repaired, while every later prerequisite stays as observed. Thus the
two missing-schema tables without the required downstream prerequisites do not
contribute to that bucket's 46; only `tennis_09` contributes to the
insufficient-data gain because `tennis_07` also lacks a unique modal stride.
Empty output supplies no rows from which to establish later prerequisites, so
it has no demonstrated isolated gain.

The per-sport cross-tab is
`g109_eligibility/sport_bucket_summary.csv`. In compact form:

| Sport | image_px | missing coord/schema | empty | insufficient | eligible | unknown |
|---|---:|---:|---:|---:|---:|---:|
| baseball | 25 | 10 | 1 | 0 | 0 | 0 |
| basketball | 4 | 2 | 0 | 0 | 0 | 0 |
| football | 31 | 8 | 4 | 0 | 0 | 0 |
| kbo | 28 | 9 | 0 | 0 | 0 | 0 |
| npb | 20 | 5 | 0 | 0 | 0 | 0 |
| soccer | 16 | 9 | 0 | 0 | 0 | 0 |
| tennis | 0 | 5 | 2 | 2 | 7 | 0 |
| wnba | 7 | 0 | 0 | 0 | 0 | 0 |
| UNKNOWN | 0 | 0 | 0 | 0 | 0 | 1 |

## Lever ranking and reachability

1. **Declared-image-pixel coordinate contract: +131 mechanically.** Every
   member already satisfies the other recorded jump-input prerequisites, so an
   accepted, valid court-feet representation would let it reach the
   calculation. This is a mechanical upper bound, not a claim that those
   tables would pass quality bars.
2. **Missing coordinate/schema prerequisite: +46 mechanically.** Two of the
   48 have another downstream blocker, so a coordinate/schema-only repair
   cannot count them.
3. **Insufficient data: +1 demonstrated.** Extending `tennis_09` to at
   least 30 frames while preserving its observed usable fields and modal
   stride would add one table. `tennis_07` needs both more frames and a
   unique modal stride, so it is not credited to a one-blocker repair.
4. **Empty/header-only, metric-local, and unknown routing: +0 demonstrated.**
   No isolated repair of any of those buckets establishes all later jump
   prerequisites.

The rank is not a claim that the first lever is currently reachable. G91 and
G101 establish that soccer `court_feet` is not reachable from this broadcast
corpus by either the current point or straight-line route. The 25 soccer rows
(16 declared `image_px`, 9 missing coordinate/schema) therefore cannot be
credited as an actionable calibration project today. Removing those rows
leaves a 106-table non-soccer mechanical ceiling across the two
coordinate/schema levers, still requiring sport-specific production work rather
than one cheap switch.

## Tennis control

Tennis now has 16 tables: 7 eligible, 5 missing a coordinate declaration or
schema prerequisite, 2 empty/header-only, and 2 `INSUFFICIENT_DATA`; it has
zero declared-`image_px` first blockers. The two insufficient tables are
`tennis_07` and `tennis_09`, exactly the two G80 reclassified from ordinary
`FAIL` to `INSUFFICIENT_DATA` because they have 4 and 2 frames. That correct
verdict change removed two falsely normal-looking reports, but it is not the
main explanation for the seven-of-sixteen gate population: five tennis tables
are missing the coordinate/schema prerequisite and two are empty. In the
G107 jump definition, the two sub-30-frame tables were excluded anyway, so
G80 made the verdict honest rather than shrinking an already valid jump
denominator.

## Required raw-file check

The largest bucket is declared `image_px`. At
`2026-09-02T22:33:31Z`, three opened, non-head, cross-sport files confirmed
the assigned label from their header and first player row:

| Table | Observed declaration |
|---|---|
| `football_20pezoC5jRQ` | `coordinate_space=image_px`, `calibration=none` |
| `kbo_10` | `coordinate_space=image_px`, `calibration=none` |
| `mlb_231Mmqijar8` | `coordinate_space=image_px`, `calibration=none` |

These were read with `sed -n '1,2p'` over the pod connection only. No pod
file was copied, changed, rescored, or re-tracked.

## One-sentence constraint

**The binding constraint is that only 7 of 196 live tables reach court-feet
jump evaluation; the cheapest demonstrated relaxation is normal acquisition
that extends `tennis_09` past 30 frames with its existing usable stride,
adding one table without moving a bar.**

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added, so no new per-file test exists to rerun.
- **A2:** The headline counts were recomputed from
  `g109_eligibility/table_census.csv`: 196 unique table names, with bucket
  counts 131, 48, 7, 2, 1, and 7 as shown above.
- **A3:** No renders apply to this exhaustive verdict census. Three source
  tables from the largest bucket were opened across football, kbo, and
  baseball.
- **A4:** The unit is one distinct source-table directory. The committed
  census has 196 unique `table` values.
- **A5:** Evidence only: no field, schema, or reader changed.
- **A6:** This lane uses an explicit-path evidence commit in its worktree; no
  archive-to-master, ledger append, register edit, deployment, or pod action
  was attempted.
- **A7:** At final check, every repository evidence path named here exists:
  this memo; `g109_eligibility/table_census.csv`;
  `g109_eligibility/bucket_summary.csv`;
  `g109_eligibility/sport_bucket_summary.csv`;
  `g107_jump_statistic_policy_2026-09-02.md`;
  `g107_policy/pod_table_snapshot.csv`;
  `g80_insufficient_data_verdict_2026-09-02.md`;
  `g91_soccer_landmarks_2026-09-02.md`;
  `g101_soccer_reachable_solve_2026-09-02.md`; and
  `VERIFIER_CONTRACT.md`.

### B

- **B1 CIRCULAR METRIC:** Clear. Every table in the one-pass glob is
  classified before gain calculation; no failing outcome was excluded.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No production schema, field, status, or
  reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Missing, empty, thin, and unknown inputs
  are explicit buckets, not silently quarantined or treated as bad quality.
- **B4 RE-CLAIM LOOP:** Clear. No claim, queue, retry, or ownership path
  changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. Pod interaction was read-only; no
  deploy, copy, restart, kill, re-track, or durable pod artifact occurred.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or
  retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The metric is the complete frozen glob,
  and the three raw checks are spread over sports rather than a head slice.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is
  claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. Each denominator unit is one distinct
  canonical source-table directory, not a row, frame, or recycled track ID.
- **B10 MOVED BAR:** Clear. No harness threshold, verdict, coordinate
  contract, or gate value changed.

## NOT VERIFIED

- Whether any mechanical coordinate/schema counterfactual would pass its
  downstream quality bars after a real, valid court-feet production path.
- A soccer calibration repair: G91 and G101 close the current point and line
  routes at limit.
- Whether a future `tennis_09` acquisition will retain its modal stride; the
  +1 is a bounded counterfactual, not a deployment prediction.
- Any pod count after the frozen 196-table read.
- No focused test was run because no code was added; no full test suite ran.
