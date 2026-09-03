# G206: route emits an evaluated-frame sidecar

## Result

`scripts/run_clip.py` now writes `evaluated_frame_count.json` beside its normal
outputs before the Stage 1 tracking branch. It is additive: no column was added
to `tracking_data.csv`, and the direct harness reads the sibling sidecar only
when its named source facts and recomputed count validate. A missing, malformed,
or explicitly-null sidecar remains fail-closed.

The count is intentionally only emitted for an uncapped, zero-offset run. In
this route, `--frames` is converted after stride selection and the existing
termination check is `gameplay_frames >= self.max_frames`
(`src/pipeline/unified_pipeline.py:1530-1533,1672-1677`). That is
detector-selected, so calling it an exact pre-detection evaluation cap would be
B1. The sidecar records `evaluated_frames: null` and
`max_frames_is_detector_dependent_in_this_route` whenever that option is set.
This is a fail-closed result, not an estimate.

## Source count, validation, and formula

The writer (`scripts/run_clip.py:107-156`) gets only container metadata before
tracking. It first checks ffprobe's `nb_frames` against `duration * r_frame_rate`
within 1 frame, following G186. It additionally requires the cv2 properties the
route itself will see to agree. If `nb_frames` is absent or invalid, the
metadata-validated fallback accepts cv2's count only when cv2's count also
agrees with ffprobe duration times rate within 1 frame. Every other case writes
`null` with a machine-readable reason; there is no decode-count pass, heuristic,
emitted-table read, gameplay result, or ball-table fallback.

The stride is derived from the read-only route, not assumed. At
`src/pipeline/unified_pipeline.py:1528-1529`, the route chooses:

```text
base_stride = max(_FRAME_STRIDE, round(source_fps / 10.0)) if source_fps > 35 else _FRAME_STRIDE
stride = base_stride if source_frame_count > _FRAME_STRIDE_THRESH else 1
```

`_FRAME_STRIDE` and `_FRAME_STRIDE_THRESH` are 3 and 3,000 at lines 374-381 of
that same file. The writer imports those values rather than copying a literal
(`scripts/run_clip.py:159-163`). For its countable route state the recorded
formula is:

```text
evaluated_frames = ceil(decoded_frames / stride)
```

The direct scorer retains G204's CSV-metadata path and adds a sidecar fallback
at `scripts/platformkit/attempted_frame_count_source.py:157-205`; the only
harness change supplies the CSV path to that reader
(`scripts/platformkit/tracking_harness.py:411-418`). The reader verifies the
schema version, null reason, formula, source path and byte size, source count,
fps, stride, zero start frame, null cap, and recomputed count before returning
the denominator.

## One bounded local route invocation

One local route invocation was run against the available real file
`data/videos/bridge/kbo_08.f299.mp4` with `COURTV_NO_OCR=1`, `--no-show`,
`--skip-tracking`, and a new ignored output directory. `--skip-tracking` made
this bounded invocation a sidecar-write verification only: no tracking loop was
entered and no corpus file was changed. It wrote the following sidecar before
the Stage 1 branch:

```json
{
  "decoded_frames": 71536,
  "evaluated_frames": 11923,
  "formula": "ceil(decoded_frames / stride) when max_frames is null and start_frame is 0",
  "frame_count_validation": "cv2_count_validated_by_ffprobe_duration_rate",
  "max_frames": null,
  "reason": null,
  "schema_version": "g206-v1",
  "source_fps": 59.94005994005994,
  "source_frame_count": 71536,
  "source_path": "C:\\Users\\neelj\\nba-track-a7\\data\\videos\\bridge\\kbo_08.f299.mp4",
  "source_size_bytes": 104178186,
  "start_frame": 0,
  "stride": 6
}
```

Recomputation is `ceil(71,536 / 6) = 11,923`. The source has more than 3,000
frames and fps is above 35, so the cited route rule gives
`max(3, round(59.94005994005994 / 10)) = 6`.

## Corrected worked cases

### Uncapped: `mlb_2026-08-30_10893dca`

This is G204's corrected direct-path construct: decoded frames `D = 39,035`,
source fps `F = 60`, stride `S = 6`, and evaluated cap `M = 30,000`.

```text
N = ceil(39,035 / 6) = 6,506
E = min(6,506, 30,000) = 6,506
```

It is uncapped even though 39,035 is greater than 30,000: the cap is on
evaluations, not source frames. This is the G204 arithmetic construct, not a
claim that an old direct CSV has gained source provenance.

### Capped: `npb_01`

G204's true capped construct is `D = 426,072`, `F = 30`, `S = 3`, and
`M = 30,000`:

```text
N = ceil(426,072 / 3) = 142,024
E = min(142,024, 30,000) = 30,000
```

The G206 route writer does not label a `run_clip --frames` invocation as this
kind of cap because that route's cap is detector-dependent, as documented
above. It emits null for that route state instead of borrowing this adapter
arithmetic.

## Historical direct tables

The four G197 tables predate this sidecar and remain `None`; G206 does not
retrospectively score them:

| Table | Result |
|---|---|
| `g96_jump_flips/nyyk_720p_tracking_data.csv` | `None`, fail closed |
| `g96_jump_flips/tennis_10_tracking_data.csv` | `None`, fail closed |
| `g69_metric_local/metric_local_clean_rows.csv` | `None`, fail closed |
| `football_imagepx_snap/schema_sample_head30.csv` | `None`, fail closed |

They have neither stable G204 CSV metadata nor a G206 sibling sidecar.

## Invariance

The count write is at `scripts/run_clip.py:471-476`, before the unchanged
`UnifiedPipeline(...)` constructor and `pipeline.run()` call at 499-508. The
diff adds metadata inspection and one JSON write; it does not alter the
constructor arguments, tracking loop, detection calls, ordering, output CSV
writer, coordinates, thresholds, bars, or verdicts. Opening and releasing a
separate metadata handle is before tracking and does not pass any frame to the
pipeline. That diff argument, rather than a cross-run row count, is the basis
for the tracking-behavior claim: G189/G195/G198 established that the route is
non-deterministic, so row-count comparison would not prove byte identity.

`tracking_data.csv` remains schema-identical; the only new artifact is the
sibling JSON. `src/`, daemon path, pod daemon, keeper, and corpus were not
edited. No threshold, bar, or verdict changed. The exact
`DEFAULT_CONFIG_VERSION` through `CONFIG_VERSIONS` slice was compared with
HEAD:

```text
config_byte_identical=True
head_config_sha256=29dc6380c05af2fbdf5bdb364497a323aba0173674f0409bbedff87aec7a3cbc
worktree_config_sha256=29dc6380c05af2fbdf5bdb364497a323aba0173674f0409bbedff87aec7a3cbc
```

The zero-context harness diff is only:

```diff
-        attempted_frames=evaluated_frames_from_tracking_table(frame),
+        attempted_frames=evaluated_frames_from_tracking_table(frame, path),
```

## Tests

All tests were run as individual files; no full test suite was run.

```text
python -m pytest scripts/test_run_clip_g206_route_evaluated_count.py -q
..                                                                       [100%]
2 passed, 2 warnings in 16.94s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
........................                                                 [100%]
24 passed in 3.05s

python -m pytest scripts/platformkit/test_tracking_harness_g197.py -q
..                                                                       [100%]
2 passed in 1.19s

python -m pytest scripts/platformkit/test_attempted_frame_count_source.py -q
...                                                                      [100%]
3 passed in 2.31s

python -m pytest scripts/platformkit/test_evaluated_frame_count_direct_path.py -q
....                                                                     [100%]
4 passed in 2.56s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
.                                                                        [100%]
1 passed in 2.58s
```

The new route-sidecar regression fails before this change because neither the
sidecar builder nor writer exists. The direct-path regression proves a plain
tracking CSV with no new columns receives its count from the self-validating
sibling sidecar. The allowlisted harness remains exactly 425 lines, so no LOC
allowlist increase was required; the rail was nevertheless run.

## NOT VERIFIED

- No real tracking run was performed; the sole permitted local invocation used
  `--skip-tracking` to verify the pre-tracking sidecar write only.
- Consequently, no locally produced real tracking CSV has yet been scored with
  its sidecar. Direct consumption is unit-tested.
- No `run_clip --frames` count is emitted because the current route gives that
  option detector-dependent semantics. It correctly produces null with a
  reason; no capped route claim is made.
- The G204 MLB and NPB calculations are preserved arithmetic constructs, not
  newly produced route tables or revised quality verdicts.
- VFR, missing-metadata, corrupt-container, nonzero-start-frame, and explicit
  `--frames` files have not been run end to end; their sidecars fail closed by
  construction and regression coverage covers the detector-dependent cap case.
