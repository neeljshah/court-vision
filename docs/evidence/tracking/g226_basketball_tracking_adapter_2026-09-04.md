# G226: Basketball Tracking Adapter (Local Build Evidence)

## Scope and status

This memo records the local BUILD portion of
`docs/evidence/tracking/specs/G226_spec.md` and cites
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no `src/` file, no
harness, gate, threshold, coordinate contract, legacy basketball table, or
other-sport adapter.

G207's exhaustive pod census is the before state: WNBA has 0 scored / 2
excluded tables and NCAA basketball has 0 scored / 1 excluded table, all for
noncanonical columns. Basketball now has a registered adapter that emits the
canonical tracking schema. The adapter's only operational path is explicitly
un-calibrated `image_px`, so it must be SCORED and first fail
`coordinate_contract` rather than be EXCLUDED for a missing schema.

No G211 result artifact is present in this worktree. Its specification is not
a report. Per G226, no pod clip, disk-guard probe, pod deployment, or pod
harness run was attempted.

## Inputs opened for this local result

| Full path | Bytes | Resolution | Use |
|---|---:|---|---|
| `C:\Users\neelj\nba-track-a8\data\tracking\G83_tennis_09\tracking_data.csv` | 8,510 | Not a video | Direct canonical-header check. |
| `C:\Users\neelj\nba-track-a8\docs\evidence\tracking\g207_pod_ledger_rescore_census_2026-09-03.md` | 14,412 | Not a video | Exhaustive before-state and remote canonical-header record. |
| `C:\Users\neelj\nba-track-a8\docs\evidence\tracking\specs\G226_spec.md` | 8,957 | Not a video | Required acceptance and pod-hold instructions. |
| `C:\Users\neelj\nba-track-a8\docs\evidence\tracking\VERIFIER_CONTRACT.md` | 11,979 | Not a video | Required self-check contract. |

Focused tests generate a temporary two-frame 128x72 MJPG video under pytest's
temporary directory. It is a test fixture, not a retained source artifact and
not a pod or physical-tracking measurement.

## Implementation

- Added `domains/basketball/tracking/geometry.py` (29 LOC). Its court model
  directly reuses `court_points_for_sport` from G196: 94x50 feet, 19-foot
  paint depth, NCAA 12-foot lane, WNBA 16-foot lane.
- Added `domains/basketball/tracking/adapter.py` (169 LOC). It uses the shared
  detector shim with `sport="basketball"`, detects players only, emits
  bottom-centre source pixels, and refuses both ball tracking and court output
  without a validated homography route.
- Added basketball only to `ADAPTERS`, `PLAYER_ONLY`, and `IMAGE_SPACE` in
  `scripts/platformkit/adapter_run.py`; existing ball telemetry remains false.
- `domains/basketball_wnba/tracking/court_config.py` is not imported because it
  supplies palette, mask, and scorebug image helpers only, not a coordinate
  calibration. `line_calibration.py` is not invoked because it intentionally
  requires caller-identified physical lines and provides no validated
  homography route. Neither omission is a reimplementation of their work.

## Column-by-column schema comparison

The G207 record of the real canonical `tennis_01` table is the target; the
local `G83_tennis_09` direct header independently confirms the first thirteen
columns and their order. Basketball writes all target columns in that order.

| Column | Canonical role | Basketball image-space value |
|---|---|---|
| `frame` | Source-frame index | Source-frame index |
| `track_id` | Player identity | Nearest-centroid player identity |
| `cls` | Object class | `player` only |
| `x` | Declared-space horizontal coordinate | Observed source-pixel x |
| `y` | Declared-space vertical coordinate | Observed source-pixel y |
| `calibration_provenance` | Calibration evidence | `unavailable` |
| `projection_status` | Projection outcome | `not_projected` |
| `projection_rejection_reason` | Projection refusal | `calibration_unavailable` |
| `raw_projected_x_ft` | Raw court projection | null |
| `raw_projected_y_ft` | Raw court projection | null |
| `coordinate_space` | Coordinate declaration | `image_px` |
| `observation` | Observation type | `observed` |
| `calibration` | Transform class | `none` |
| `source_fps` | Source timing | Capture FPS when available |
| `source_height` | Source geometry | Capture frame height |
| `source_duration` | Source duration | Frame count / capture FPS when available |

This intentionally does not emit a court coordinate. The unchanged harness
accepts the normalized schema, then rejects `image_px` for basketball with
`coordinate_contract`, which is the expected visible failure.

## Local harness result

The focused adapter test generated declared source-pixel rows and called the
unchanged `tracking_harness.evaluate(rows, "basketball")`.

| Run type | Verdict | First failure head | Interpretation |
|---|---|---|---|
| Local synthetic contract test | `FAIL` | `coordinate_contract` | Canonical table is scorable; pixels are not court feet. |
| Required bounded pod clip | NOT VERIFIED | NOT VERIFIED | Held until G211 reports. |

This is a schema-path test, not an n=1 pod result or a claim about physical
tracking accuracy. The route is known to be non-deterministic; no single future
pod run will establish a stable property.

## Per-file tests (pasted)

```text
python -m pytest domains/basketball/tracking/test_geometry.py -q
3 passed in 0.92s

python -m pytest domains/basketball/tracking/test_adapter.py -q
5 passed in 1.20s

python -m pytest scripts/platformkit/test_adapter_run.py -q
9 passed in 0.73s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
24 passed in 0.82s

python -m pytest scripts/platformkit/test_coordinate_provenance.py -q
5 passed in 0.42s

python -m pytest scripts/platformkit/test_tracking_schema_coordinate_space.py -q
4 passed in 0.45s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 1.92s
```

No allowlisted file grew: `adapter_run.py` is 150 LOC, under the 300 LOC rail.
The two new production files are also below the rail; no A12 allowlist change
was needed.

## Disk guard and cleanup

| Check | Result |
|---|---|
| `dd` write probe | Not run: G211 has not reported. |
| `du -sm /workspace/nba-ai-system/data` | Not run: G211 has not reported. |
| Pod temporary-artifact cleanup | Not applicable; no pod artifact was created. |
| Bytes freed | 0 |

## Verifier-contract self-check (section B)

- B1: No metric excludes failures; the before-state names all three excluded
  basketball tables and the local result retains `coordinate_contract` failure.
- B2: Schema is additive. No existing column or status is renamed or removed;
  provenance and coordinate-schema reader tests pass.
- B3/B4: No gate or claim flow changed.
- B5: No pod file was copied or deployed.
- B6: No module moved or retired.
- B7/B8/B9: No render, fit residual, or denominator claim is made.
- B10: No harness or threshold file changed.

## NOT VERIFIED

- The required one-clip pod run, disk guard, emitted pod CSV, harness verdict,
  and first pod failure head remain NOT VERIFIED pending a G211 report.
- The adapter does not validate a basketball homography, physical position,
  detector accuracy, identity quality, or calibration correctness.
- Existing legacy basketball feature tables are preserved and are not claimed
  wrong; this creates a separate raw canonical tracking product beside them.
