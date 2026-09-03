# G165 full-volume reap: exhaustive raise-site survey

## Result

ACCEPT (evidence and proposal only; no runtime change). The safe change is
larger than a local retention rearrangement. No `finally: retain(...)` change
was made or proposed.

This memo re-measured the row premise at HEAD
`24425729b85bc2908c5fc5041d673d4b80cfdf9e`. `track_daemon.py` was read from
that HEAD immediately before the line numbers below were recorded.

## Q8 premise re-measurement

The premise is confirmed.

- `_finish` calls the basketball capability writer at
  `scripts/platformkit/track_daemon.py:240-241`. The route is gated by
  `rows` and `job["sport"] in CLIP_SPORTS` at line 237; the set contains
  `nba`, `wnba`, `ncaa_basketball`, and `basketball` at line 73.
- `write_ball_telemetry_declaration` performs the unguarded sidecar
  `destination.write_text(...)` at
  `scripts/platformkit/tracking_schema.py:178-180`. Its adjacent
  `_BALL[job["sport"]]` lookup at `track_daemon.py:241` is also unguarded,
  although it is not a full-volume write.
- `_finish` invokes `verdict` at `track_daemon.py:242`, which invokes
  `adjudicate` at line 115. `adjudicate` calls `_atomic_json(...)` at
  `scripts/platformkit/track_daemon_done.py:155` without a caller-side
  handler.
- `tick` removes the job from `active` before either reap call, at
  `track_daemon.py:297` and `:305`. Neither branch catches `_finish`.
  `main` calls `tick(active, args.workers)` in its bare loop at line 374 with
  no handler. The premise is therefore not falsified.

The downstream condition that makes an already processed duplicate skippable
is `read_adjudicated(TRACKING, game_id)` plus a CORPUS hit at
`track_daemon.py:312`. The comments immediately above it state the intended
invariant: a missing verdict is re-tracked rather than inferred from rows
(`:309-311`).

## Exhaustive construct: full-volume operations in the reap path

**Construct declaration:** this enumerates every operation reached from
`_finish` and `adjudicate` that writes, flushes, syncs, renames, or creates a
filesystem entry and can observe an unwritable/full target. Read-only CSV,
manifest, ffprobe, DataFrame, harness, dictionary, and print operations are
not writers. `build_decode_manifest` is read-only on this call path; its
`write_csv` and `write_summary` methods are not invoked.

| Reachable operation | Full-volume raise behavior | Reap disposition |
|---|---|---|
| `stamp_tracking_csv` from `_finish` (`track_daemon.py:236`) | Its temporary CSV open/write/replace is at `tracking/source_timebase.py:64-72`. Its `OSError` and `csv.Error` are caught at `:74-75`. | Cannot escape `_finish`; it is not an open crash site. |
| Capability sidecar from `_finish` (`track_daemon.py:240-241`) | `tracking_schema.py:178-180` writes `tracking_capability.json` directly. An ENOSPC/OSError escapes. | **Open full-volume raise site #1.** It is above verdict, ledger, and retention. |
| Verdict call from `_finish` (`track_daemon.py:242`) | `track_daemon_done.py:155` invokes `_atomic_json` without a caller-side handler. | **Open full-volume raise site #2.** It is above ledger and retention. Its complete inner write construct is below. |
| Ledger record from `_finish` (`track_daemon.py:283`) | `_record` makes the parent directory, runs a write/flush/fsync/readback probe, then appends/writes/flushes/fsyncs at `track_daemon.py:140-148`; all can encounter ENOSPC. `_record_loudly` catches `RuntimeError` and `OSError` at `:203-209`. | Guarded. It logs the lost row and lets `_finish` continue; this is G151-CORR's distinct shape. |
| Retention from `_finish` (`track_daemon.py:287-288`) | `retain` creates the corpus directory and renames the source at `track_daemon_done.py:172-175`; its error handling attempts a `.failed` rename at `:176-183`. | Guarded inside `retain`, and sequenced below the two open sites. It must remain below durable adjudication for this failure mode. |
| Log cleanup (`track_daemon.py:289-292`) | `unlink` is deletion, not a full-volume allocation; any `OSError` is caught. | Not a full-volume crash site. |

`_atomic_json` is one caller-visible raise site with this complete inner
full-volume construct:

1. `path.parent.mkdir(...)` at `track_daemon_done.py:52` can fail allocating
   directory metadata.
2. The `.part` file open at `:55`, JSON serialization write at `:56`, newline
   write at `:57`, flush at `:58`, and `fsync` at `:59` can report ENOSPC or a
   related write failure.
3. The atomic replacement at `:60` can fail on the target filesystem. The
   cleanup at `:62` then runs and the exception is re-raised at `:63`; it does
   not convert failure into an adjudicated verdict.

`_fsync_csv` is not an additional open site: its `r+b` fsync is protected by
the `OSError` return-false path at `track_daemon_done.py:39-48`. The optional
decoded-frame and harness computations are caught inside `adjudicate` before
verdict publication (`:132-148`) and perform no writes on this path.

Thus the construct is complete: the two unguarded, caller-visible
full-volume raise sites are the capability sidecar and verdict sidecar; the
CSV timestamp, ledger, retention, and cleanup siblings were included and
classified rather than omitted.

## A5 reader survey

No schema, field, status, or writing order was changed. This survey is still
mandatory because a future pause/admission design could change when the
verdict sidecar, capability sidecar, or daemon ledger row becomes observable.

### Verdict sidecar: `harness_verdict.json`

- Runtime reader: `read_adjudicated` in
  `scripts/platformkit/track_daemon_done.py:159-167` reads and validates the
  sidecar together with a nonempty CSV.
- Runtime consumer: the duplicate-drop branch in
  `scripts/platformkit/track_daemon.py:312-317` uses that result and the
  CORPUS hit before retaining a staged duplicate.
- Direct test readers: `scripts/platformkit/test_track_daemon.py` and
  `scripts/platformkit/test_track_daemon_done.py`.
- Search hits in `domains/basketball_nba/*` and
  `intel_validation/nba_canonical_shooter_claims.py` name a different
  quality-gate verdict path; they are not readers of this daemon sidecar.

### Capability sidecar: `tracking_capability.json`

- Runtime file reader: `_producer_ball_telemetry` in
  `scripts/platformkit/tracking_schema.py:195-206` reads the file and validates
  `ball_telemetry_available`; `identify_tracking_schema` consumes it at
  `:209-217`.
- Runtime file reader/copy path: `copy_ball_telemetry_declaration` at
  `tracking_schema.py:183-192` checks the source file and copies it to a
  re-emitted CSV.
- Indirect runtime field consumers: `scripts/platformkit/tracking_harness.py`
  and `scripts/platformkit/metric_local_profile.py` consume the schema value,
  including the fail-closed `unknown_no_sidecar` state.
- Direct test readers: `scripts/platformkit/test_basketball_relabel_image_px.py`,
  `test_footage_cycle.py`, `test_track_daemon.py`,
  `test_tracking_harness.py`, and `test_tracking_schema_coordinate_space.py`.

### Daemon ledger row: `data/tracking/track_daemon_ledger.jsonl`

- Runtime reader: `_previous_sport_entry` in
  `scripts/platformkit/track_daemon.py:168-181` parses the preceding
  same-sport row for the diagnostic density-step field.
- Runtime report reader: `scripts/platformkit/night_report.py:25-43` reads
  JSONL; `build_report` consumes `sport`, `status`, `passed`, `rows`, and
  `failure_heads` with the legacy `failures` alias at `:78-80` and `:120-139`.
- Operational transfer/read-only probes: `scripts/platformkit/pod_pull_sync.sh`
  copies the exact ledger path, and `tracking/loop_status.sh` has a separate,
  stale `/workspace/track_daemon_ledger.jsonl` tail probe. Neither changes the
  row schema.
- Direct test readers: `scripts/platformkit/test_track_daemon.py`,
  `test_track_daemon_done.py`, `test_track_daemon_job_budget.py`,
  `test_track_daemon_timeout_verdict.py`,
  `test_track_daemon_ledger_denominator.py`,
  `test_g149_persist_decoded_denominator.py`,
  `test_g153_local_decoded_frames_producer.py`, and `test_night_report.py`.

## Isolated simulated-unwritable reproduction (Q7)

No real volume was filled and the pod was not contacted. Each reproduction
used `tempfile.TemporaryDirectory`, a one-row temporary CSV, a temporary
source, and a `unittest.mock` filesystem seam that raised
`OSError(errno.ENOSPC, "simulated unwritable target")` only for the intended
temporary sidecar target. The temporary directory is automatically removed at
the end of the run.

1. For the verdict path, `Path.open` was made to raise only for
   `harness_verdict.json.part`, then `tick()` was called with a finished
   temporary soccer job.
2. For the capability path, `Path.write_text` was made to raise only for
   `tracking_capability.json`, then `tick()` was called with a finished
   temporary NBA job.

Both runs produced the same material result (the capability run additionally
reported `capability_written: false`):

```json
{"active_after": [], "errno": 28, "message": "[Errno 28] simulated unwritable target", "raised": "OSError", "retained_calls": 0, "source_still_in_stage": true, "temp_root_removed_after_run": true, "verdict_written": false}
```

This directly establishes the failure chain: `active.pop` has already
occurred, the exception escapes `tick`, retention has not run, the source is
still staged, and no durable verdict exists. A keeper restart can then claim
the source again.

## Defended proposal: safe fix needs an admission/pause design

The smallest safe *design* is broader than moving a line in `_finish`:

1. Catch the recognized storage-write failure around reaping so an exception
   cannot kill `tick` after `active.pop`; do not retain the source in that
   branch. The source remains in STAGE and the absent verdict remains absent.
2. Introduce an explicit daemon storage-unwritable state. Before any new
   claim, probe the actual tracking-target filesystem with a small
   write/flush/fsync/readback/delete operation. While it fails, skip both
   claim and launch and print an ASCII `STORAGE UNWRITABLE` message on every
   poll cycle. Existing child jobs may drain; they must not induce source
   retention on failed adjudication.
3. Resume admission only after that probe succeeds. The stranded source then
   remains eligible to re-track exactly because it was not retained without a
   verdict. A persistent full volume idles loudly rather than consuming GPU;
   recovery permits an evidence-preserving retry.
4. Add one focused per-file regression test only when implementing the design:
   inject ENOSPC at each sidecar target, assert no retention and a staged
   source without a verdict, assert no new claim while the probe fails, and
   assert the source can be claimed after the probe succeeds.

The approach does not change a threshold, coverage definition, decoded-frame
denominator, eligibility definition, `MAX_POD_BACKLOG`, worker count, or any
verdict. It deliberately does not create a terminal "storage failed" outcome
from missing evidence.

## B self-check

- B1: Not a scored/filtering metric; the full construct names every included
  writer and its disposition.
- B2: No code or schema change. The A5 survey records all identified readers.
- B3: Pass. There is no `finally: retain(...)`; both reproductions show zero
  retention calls and the unadjudicated source remains in STAGE.
- B4: No changed claim state. The proposed pause blocks admission while storage
  is unwritable and retries only after a successful probe.
- B5: No pod file, process, restart, or deployment was touched.
- B6: No module moved or retired.
- B7, B8, B9: Not sampling or fitting work; not applicable.
- B10: No threshold or gate value changed.

## Not verified

- No implementation or regression test was landed; this is the specified
  enumeration and proposal outcome.
- No real full-volume failure was induced, and no pod action was taken.
- The future storage probe's exact state ownership, log wording, and recovery
  behavior require a separate designed implementation row and focused test
  before deployment.
