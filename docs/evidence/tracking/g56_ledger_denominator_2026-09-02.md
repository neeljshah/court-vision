# G56 - daemon ledger denominators

## Premise and limit

The local pre-change `_finish` writer recorded `rows` but none of
`decoded_frames`, `source_resolution`, or `fresh_solves`: 0/3 requested fields.
That makes a low row count unable to distinguish a collapsed run from a short
or lower-resolution source. Commit `f16b3863a` documents the tennis change that
stopped stale calibration reuse; this memo does not alter its behavior.

The requested live reproduction could not be completed: `ssh config.pod` was
reachable on 2026-09-02, but `/workspace/track_daemon_ledger.jsonl` was absent.
No pod file was copied, changed, or deployed.

## Additive schema and marker

Every newly written daemon row now appends these fields:

```json
{"decoded_frames": 100, "source_resolution": "1920x1080", "fresh_solves": 3}
```

`decoded_frames` comes from the adjudication sidecar when available, otherwise
from the tennis adapter's per-frame manifest. `fresh_solves` is the manifest's
maximum cumulative `fresh_solve_count`, so drift-checked reuse is not counted
as a fresh solve. A missing independent source is represented as `null`, never
invented from emitted rows. Source resolution is captured at daemon launch.

The separate additive `rows_per_decoded_frame_step_change` marker compares the
current row only with the immediately previous readable row for the same sport.
`ROW_DENSITY_STEP_FACTOR = 5.0`; a strictly greater than 5x change records the
previous game id, direction, and measured factor. It does not alter any harness
threshold, verdict, status, or G15b done-definition.

Before (legacy row shape, reproduced in the test):

```json
{"game_id":"legacy","sport":"tennis","status":"tracked","rows":1000,"passed":true,"failures":[],"seconds":1}
```

After (the simulated normal row):

```json
{"game_id":"normal","sport":"tennis","status":"timeout","rows":600,"decoded_frames":100,"source_resolution":"1920x1080","fresh_solves":3,"rows_per_decoded_frame_step_change":null}
```

The next simulated tennis row has 10 rows / 100 decoded frames. Its marker is:

```json
{"previous_game_id":"normal","direction":"decrease","factor":60.0}
```

## Reader enumeration and compatibility

`git grep` found these ledger consumers and they were checked:

- `scripts/platformkit/night_report.py` is the JSONL parser. The new test feeds
  it one old-shape row plus all three new-shape writes; `build_report` succeeds.
- `scripts/platformkit/pod_pull_sync.sh` copies the ledger file without parsing
  its JSON fields.
- `scripts/platformkit/tracking/loop_status.sh` prints only the last line.
- `scripts/platformkit/test_night_report.py` is existing parser coverage.
- `scripts/platformkit/track_daemon.py` is the writer and now performs the
  prior-same-sport lookup before its append.

No old field was renamed, removed, or reassigned. The test asserts that its
legacy row round-trips byte-for-structure equal to the original dictionary.

## Test and acceptance computation

Only the requested new per-file test was run:

```text
python -m pytest scripts/platformkit/test_track_daemon_ledger_denominator.py -q
1 passed in 0.88s
```

Constructed writes: one old-shape tennis row, then a new-schema corrupt row, a
new-schema normal tennis row, and a new-schema tennis step-change row. The
metric denominator is the three newly written rows; all three carry all three
requested fields: 3/3 = 100%. The old row is deliberately excluded because it
predates the additive schema, not because it fails a metric.

Files a verifier would deploy after acceptance, and only those code files:

- `scripts/platformkit/track_daemon.py`
- `scripts/platformkit/track_daemon_ledger.py`
- `scripts/platformkit/tracking/source_timebase.py`

## Verifier-contract B self-check

- B1: completeness counts every new simulated row, including the corrupt row.
- B2: fields are appended only; all readers above were enumerated and the parser
  was mixed-schema tested.
- B3/B4: no gate, quarantine, claim, or retention behavior changed.
- B5: no pod deployment, copy, or scp occurred.
- B6: no module moved or retired.
- B7/B8: no render sample or fitted metric is claimed.
- B9: the marker denominator is independently recorded decoded frames, not
  emitted rows or a constant identifier.
- B10: no existing harness threshold, field name, or done-definition changed;
  5.0 is a new diagnostic marker constant only.

## NOT VERIFIED

- The current pod ledger row could not be read at the supplied path because the
  file is absent there.
- No live daemon run has yet produced these fields, and no pod deployment was
  attempted.
- A `null` fresh-solve value means no adapter frame manifest was available; it
  must not be interpreted as zero fresh solves.
- Concurrent workers can append close together; this change makes the lookup
  before append and does not introduce a cross-process ledger lock.
