# G181: protected basketball sources remain unadjudicated

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A3,
A7, B3, and Q8. Verdict: **ACCEPT WITH CORRECTIONS** as a read-only diagnosis.
This memo changes no threshold, bar, coordinate contract, eligibility definition,
verdict, source file, pod process, daemon, or deployment.

## Q8 premise re-verification

At the live replacement-pod observation, both protected corpus files existed:

| Source file | Live size (bytes) | Matching tracking CSV | Matching harness verdict |
|---|---:|---|---|
| `data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | absent | absent |
| `data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 3,580,059,573 | absent | absent |

The current pod ledger is `data/tracking/track_daemon_ledger.jsonl`. Its
exhaustive game-ID search found three `wnba_01` rows and two
`ncaa_basketball_IB-_u4gW3ds` rows. No current durable verdict had appeared, so
the premise remains true and the diagnosis continued. These are the verbatim
matching ledger rows:

```json
{"game_id": "wnba_01", "sport": "wnba", "status": "thin", "adjudicated": false, "rows": 0, "verdict": null, "passed": null, "failure_heads": [], "failures": [], "coverage_pct": null, "coordinate_space": null, "rung": null, "evaluated_at": null, "seconds": 45, "finished_at": 1788448121, "source_fps": 30.0, "source_height": 1080, "source_duration": 5814.333333333333, "source_variants": [], "tail": "system/src/pipeline/unified_pipeline.py\", line 1097, in _build_court     map_2d = cv2.resize(map_img, (_rw, _rh))              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217: error: (-215:Assertion failed) !ssize.empty() in function 'resize'  ", "decoded_frames": null, "source_resolution": "1920x1080", "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
{"game_id": "ncaa_basketball_IB-_u4gW3ds", "sport": "ncaa_basketball", "status": "thin", "adjudicated": false, "rows": 0, "verdict": null, "passed": null, "failure_heads": [], "failures": [], "coverage_pct": null, "coordinate_space": null, "rung": null, "evaluated_at": null, "seconds": 30, "finished_at": 1788452256, "source_fps": 29.97002997002997, "source_height": 720, "source_duration": 6854.981466666667, "source_variants": [], "tail": "system/src/pipeline/unified_pipeline.py\", line 1097, in _build_court     map_2d = cv2.resize(map_img, (_rw, _rh))              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217: error: (-215:Assertion failed) !ssize.empty() in function 'resize'  ", "decoded_frames": null, "source_resolution": "1280x720", "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
{"game_id": "wnba_01", "sport": "wnba", "status": "thin", "adjudicated": false, "rows": 0, "verdict": null, "passed": null, "failure_heads": [], "failures": [], "coverage_pct": null, "coordinate_space": null, "rung": null, "evaluated_at": null, "seconds": 30, "finished_at": 1788452811, "source_fps": 30.0, "source_height": 1080, "source_duration": 5814.333333333333, "source_variants": [], "tail": "system/src/pipeline/unified_pipeline.py\", line 1097, in _build_court     map_2d = cv2.resize(map_img, (_rw, _rh))              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217: error: (-215:Assertion failed) !ssize.empty() in function 'resize'  ", "decoded_frames": null, "source_resolution": "1920x1080", "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
{"game_id": "ncaa_basketball_IB-_u4gW3ds", "sport": "ncaa_basketball", "status": "thin", "adjudicated": false, "rows": 0, "verdict": null, "passed": null, "failure_heads": [], "failures": [], "coverage_pct": null, "coordinate_space": null, "rung": null, "evaluated_at": null, "seconds": 30, "finished_at": 1788457306, "source_fps": 29.97002997002997, "source_height": 1080, "source_duration": 6854.981466666667, "source_variants": [], "tail": "system/src/pipeline/unified_pipeline.py\", line 1097, in _build_court     map_2d = cv2.resize(map_img, (_rw, _rh))              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217: error: (-215:Assertion failed) !ssize.empty() in function 'resize'  ", "decoded_frames": null, "source_resolution": "1920x1080", "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
{"game_id": "wnba_01", "sport": "wnba", "status": "thin", "adjudicated": false, "rows": 0, "verdict": null, "passed": null, "failure_heads": [], "failures": [], "coverage_pct": null, "coordinate_space": null, "rung": null, "evaluated_at": null, "seconds": 30, "finished_at": 1788457307, "source_fps": 30.0, "source_height": 1080, "source_duration": 5814.333333333333, "source_variants": [], "tail": "system/src/pipeline/unified_pipeline.py\", line 1097, in _build_court     map_2d = cv2.resize(map_img, (_rw, _rh))              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ cv2.error: OpenCV(5.0.0) /io/opencv/modules/imgproc/src/resize.cpp:4217: error: (-215:Assertion failed) !ssize.empty() in function 'resize'  ", "decoded_frames": null, "source_resolution": "1920x1080", "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
```

## Cause of the thin outcome

No target-named job-log sidecar survives beside the bridge files. The bridge
contains only the protected-name `.mp4.part` files, which this lane did not
touch. The daemon log independently records the repeated outcomes:

```text
tracking wnba_01 (wnba), 1 active
wnba_01 wnba thin rows=0 passed=None
tracking ncaa_basketball_IB-_u4gW3ds (ncaa_basketball), 2 active
ncaa_basketball_IB-_u4gW3ds ncaa_basketball thin rows=0 passed=None
```

The ledger's verbatim `tail` field supplies the failure cause for every one of
the five attempts: `_build_court` calls `cv2.resize(map_img, (_rw, _rh))`, but
OpenCV reports `!ssize.empty()`. The route therefore fails on an empty court-map
input before it writes a tracking table, emits a frame count, declares a
coordinate space, computes a geometry solve, or writes a harness verdict.
The NCAA attempts span both 720 and 1080 source-height rows and retain the same
failure, so a source-height change did not resolve it.

## Re-track decision and measured output

No scratch re-track was started. All retained attempts have the same terminal
empty-input failure, and G181 forbids changing the pipeline that produces it.
A new invocation of the unchanged `run_clip.py` route would not be a justified
measurement and could only repeat the same unadjudicated outcome. No file was
staged into `data/footage_bridge`; no footage was deleted; and no pod daemon or
keeper action was taken.

| Game ID | Retained attempts | Rows per attempt | Distinct emitted frames | Decoded frames | Harness verdict | Coordinate declaration | Solved-geometry share |
|---|---:|---:|---|---|---|---|---|
| `wnba_01` | 3 | 0 | not produced | null | absent; ledger `verdict: null` | null; not stamped | not measurable; no rows |
| `ncaa_basketball_IB-_u4gW3ds` | 2 | 0 | not produced | null | absent; ledger `verdict: null` | null; not stamped | not measurable; no rows |

The coordinate declaration and solved-geometry share are intentionally separate:
there is no declaration to treat as geometry evidence, and no table from which
to calculate a share.

These files cannot produce a durable verdict through the unchanged current
route. They are not established as permanently impossible: an authorized repair
to the empty court-map input could allow a future run to reach adjudication.
Until then they should remain explicitly recorded as unfinished and retained;
the retention decision remains with the orchestrator. This lane did not delete
or authorize deletion of either source.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added, so no per-file test applies.
- **A2:** Recomputed directly from the five quoted ledger rows: WNBA has three
  rows and NCAA has two; every row has `rows: 0`, `coverage_pct: null`, and
  `verdict: null`.
- **A3:** No table was produced, so no render decision set exists and no eye
  check applies.
- **A4:** The reporting unit is the two exhaustive protected source files;
  repeated ledger attempts are shown separately rather than counted as files.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `a2` only. It
  does not archive-land, append a results-ledger/register row, deploy, or alter
  the pod.
- **A7:** Before commit, the named repository evidence paths were checked:
  this memo, `G181_spec.md`, and `VERIFIER_CONTRACT.md` all exist.

### B

- **B1 CIRCULAR METRIC:** Clear. Both protected sources and all five matching
  current ledger rows are named; none were excluded from the diagnosis.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, status, field, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Both sources remain present and explicitly
  unfinished; neither was deleted, quarantined, or treated as a durable failure.
- **B4 RE-CLAIM LOOP:** Clear. No claim, retry, ownership, or queue logic changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No pod file was copied and no deploy,
  restart, or daemon/keeper action occurred.
- **B6 ORPHANS:** Clear. No module, import, test, or command was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The decision set is the exhaustive two-file
  construct; no render set was produced.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fit or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The construct denominator is two distinct
  protected source files; retries are reported separately.
- **B10 MOVED BAR:** Clear. No threshold, coordinate contract, eligibility
  definition, or verdict changed.

## NOT VERIFIED

- The exact producer state of `map_img` at each historical failure: the
  surviving logs identify the empty-input OpenCV failure but no per-game job
  sidecar survives to expose its preceding construction state.
- A repair outcome: G181 forbids modifying the responsible pipeline and no
  re-track was justified on the unchanged route.
- Any emitted-frame count, decoded-frame count, coordinate declaration, solved
  geometry, or harness verdict: no tracking table was written for either file.
