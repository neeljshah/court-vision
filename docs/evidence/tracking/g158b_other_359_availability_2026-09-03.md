# G158b - other 359 availability measurement

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A3, A7,
Q8, and section B. This is local-only, read-only evidence. No tracking table,
`src/` file, provenance helper, `run_clip.py`, eligibility definition,
threshold, or verdict was changed. No pod, SSH, network, re-track, repair, or
deployment action occurred.

## Q8 premise first

Before measuring the frozen construct, the worktree exposed 3,378 recursive
tracking table files under `data/tracking/`: 3,003 CSV, 373 JSON, and 2 JSONL.
This is hundreds-level provisioning, not Attempt 1's stale one-table store.
The premise is therefore **CONFIRMED**: the 359 named inputs are visible here.

## Frozen construct and result

The eligibility definition is untouched: select every G154
`table_census.csv` row whose `rollup_bucket` is `other`, sort by its already
recorded table name, and read that table's existing
`data/tracking/<table>/tracking_data.csv`. The enumeration is complete by
construct: **359 unique names, 359 source files present, 0 absent**. Every
share below uses the **eligible denominator of all 359 tables**.

Raw, per-table observations and all groupings are under
[`g158b_availability/`](g158b_availability/). The read-only generator rejects
an absent frozen target rather than dropping it.

### Modification-date grouping

| Local modification date | Tables | Share of 359 |
|---|---:|---:|
| 2026-05-29 | 354 | 98.6072% |
| 2026-09-01 | 2 | 0.5571% |
| 2026-09-02 | 3 | 0.8357% |
| **Total** | **359** | **100.0000%** |

### Sport-routing grouping

These are the frozen G154 routing labels, not a new routing rule.

| Sport routing label | Tables | Share of 359 |
|---|---:|---:|
| basketball | 358 | 99.7214% |
| UNKNOWN | 1 | 0.2786% |
| **Total** | **359** | **100.0000%** |

### Distinct header shapes

There are exactly **two** distinct header shapes. Their exact lines are in
[`header_shape_summary.csv`](g158b_availability/header_shape_summary.csv).

| Shape name | Exact header identity | Tables | Share of 359 |
|---|---|---:|---:|
| unified-pipeline-rich | SHA-256 prefix `53276d7b82fca1e3`; `frame,timestamp,...,homography_valid` | 358 | 99.7214% |
| canonical-pixel-smoke | SHA-256 prefix `bfe93c5e172da148`; `frame,track_id,cls,x,y` | 1 | 0.2786% |
| **Total** |  | **359** | **100.0000%** |

The full unified-pipeline-rich line is:

```text
frame,timestamp,player_id,team,x_position,y_position,x_norm,y_norm,velocity,acceleration,direction_deg,court_zone,ball_possession,distance_to_ball,nearest_opponent,nearest_teammate,event,team_spacing,spacing_hull_area,team_centroid_x,team_centroid_y,paint_count_own,paint_count_opp,possession_side,handler_isolation,bbox_x1,bbox_y1,bbox_x2,bbox_y2,ball_x2d,ball_y2d,ball_velocity,distance_to_basket,vel_toward_basket,drive_flag,ft_x,ft_y,dist_to_basket_ft,fast_break_flag,possession_id,possession_duration,confidence,play_type,paint_touches,off_ball_distance,shot_clock_est,scoreboard_shot_clock,scoreboard_game_clock,scoreboard_period,scoreboard_score_diff,scoreboard_confidence,possession_duration_sec,possession_type,ankle_x,ankle_y,contest_arm_angle,jump_detected,dribble_hand,ball_shot_arc_angle,ball_peak_height_px,ball_pass_speed_pxpf,player_name,jersey_number,team_abbrev,dribble_count,lineup_id,homography_valid
```

## Timeline against the writers

Git history reports that the current `_tracking_csv_fields` list was last
changed in `03c40b51cb677273806c271cfea6de6ac0245544` at
2026-04-02T10:43:08-05:00, subject `feat: add RunPod sync scripts + fix spatial
gap-fill zeros`. Its diff added `ft_x`, `ft_y`, `dist_to_basket_ft`,
`team_abbrev`, and `homography_valid` to that list.

`scripts/platformkit/coordinate_provenance.py` entered the repository in
`7914c648661cd10320b986f2688e35bbdbea1684` at
2026-09-01T06:48:26-05:00, subject `refactor(tracking): one shared provenance
helper; football and baseball keep their detections`.

All 359 target files postdate the April field-list change. Relative to the
September provenance-helper entry, 355/359 (98.8858%) are before it: the 354
May files plus header-only `failclosed_smoke` at 2026-09-01T05:03:04-05:00.
The remaining 4/359 (1.1142%) are after it: `lanetest2` at
2026-09-01T09:29:01-05:00 and three September 2 basketball files.

The dates and the 358 identical rich headers are **consistent with a single
live unstamped writer continuing across the provenance-helper introduction**.
They do not prove that no additional historical producer ever existed. This
uses Attempt 1's landed finding that `_checkpoint_csv` is the live unstamped
writer; it does not re-derive that finding.

## Geometry available without re-tracking

Every header has a coordinate pair: 358/359 (99.7214%) have the rich
`x_position,y_position,x_norm,y_norm,ft_x,ft_y` geometry schema and 1/359
(0.2786%) has the canonical `x,y` schema. Thus **359/359 have geometry columns
and 0/359 have no geometry columns**. The one canonical-pixel-smoke file is
header-only (no data row), which is separately recorded in
[`data_presence_summary.csv`](g158b_availability/data_presence_summary.csv);
it has `x,y` columns but no actual coordinate records.

Accordingly, the 359 schemas are potentially re-stampable from existing file
columns without re-tracking. This is a statement about available columns only,
**not** permission to re-stamp any table. No table was modified.

## Today's local production cross-check

Today is 2026-09-03. No basketball target CSV has a local modification date of
2026-09-03; the latest observed target date is 2026-09-02. There is therefore
no locally available basketball table produced today from which to report
whether `run_clip.py`'s late stamp succeeded or was skipped. No pod was used to
fill that gap.

## Evenly spaced hand checks

The positions are the fixed systematic indices
`floor((i + 0.5) * 359 / 5)` for `i = 0..4`: 35, 107, 179, 251, and 323.
They are distributed across the full sorted construct, not taken from its head.
The exact header line for each observation is retained per row in
[`hand_checks.csv`](g158b_availability/hand_checks.csv); each is the full
unified-pipeline-rich line printed above.

| Index | Table | Header line observed | Classification |
|---:|---|---|---|
| 35 | `0022500041` | full unified-pipeline-rich line above | rich position geometry; data row present |
| 107 | `0022500330` | full unified-pipeline-rich line above | rich position geometry; data row present |
| 179 | `0022500575` | full unified-pipeline-rich line above | rich position geometry; data row present |
| 251 | `0022500892` | full unified-pipeline-rich line above | rich position geometry; data row present |
| 323 | `0022501147` | full unified-pipeline-rich line above | rich position geometry; data row present |

## Verifier-contract self-check

### A

- **A2:** The generated raw artifact has 359 rows, 359 unique table names, and
  its five date counts, two sport counts, and two header-shape counts sum to
  359. The focused test also constructs and checks a 359-target fixture.
- **A3:** This is an exhaustive construct. The five required direct header
  checks use evenly spaced systematic positions, not a head slice.
- **A4:** The denominator is one distinct frozen G154 table name per unit; no
  rows, frames, or IDs are reused as units.
- **A5:** No existing field, reader, or production source changed. The new
  evidence utility has no production caller.
- **A7:** Before commit, the memo, every `g158b_availability/` CSV, frozen G154
  census, verifier contract, generator, and focused test all exist.

### B

- **B1 CIRCULAR METRIC:** Clear. The fixed 359-name population is complete;
  absent targets raise rather than being excluded.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No source schema, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Missing frozen inputs would be named with a
  `FileNotFoundError`, never treated as bad data or silently discarded.
- **B4 RE-CLAIM LOOP:** Clear. No claim, retry, queue, or ownership flow changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No deploy, pod, SSH, copy, restart, or
  table write occurred.
- **B6 ORPHANS:** Clear. No existing module, import, test, or command moved or
  retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The construct is exhaustive and hand
  checks are evenly distributed across it.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted residual or independent
  performance claim is made.
- **B9 DEGENERATE DENOMINATOR:** Clear. Each unit is one distinct table name.
- **B10 MOVED BAR:** Clear. No eligibility definition, threshold, coordinate
  contract, or verdict changed.

## NOT VERIFIED

- Whether a future `run_clip.py` invocation's late stamp will succeed or skip;
  no locally dated-today basketball output is available.
- Which individual execution path produced any particular historical target;
  timestamps and headers establish consistency, not execution provenance.
- Any re-stamp result, because the measurement deliberately did not modify a
  tracking table.

## Focused test

`python -m pytest tests/scripts/platformkit/tracking/test_g158b_availability.py -q`
passed: `1 passed`.
