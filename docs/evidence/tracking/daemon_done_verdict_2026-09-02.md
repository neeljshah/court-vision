# G15: daemon completion is an adjudicated verdict -- 2026-09-02

## Before

At the start of this lane, completion status was row-count based:

```python
rows = tracking_rows(job["game_id"])
status = "timeout" if timed_out else (
    "tracked" if rows >= MIN_TRACKING_ROWS else "thin")
```

Those were `scripts/platformkit/track_daemon.py:220-223` before this change.
The harness result was appended to the ledger, but it did not define whether the
job was complete. The re-stage fast path separately required a row threshold
plus a PASS:

```python
if tracking_rows(game_id) >= MIN_TRACKING_ROWS \
        and verdict(sport, game_id).get("passed"):
    path.unlink(missing_ok=True)
```

The daemon ordinarily moved finished footage to `data/footage_corpus`, rather
than deleting it. Two unsafe unlink paths nevertheless remained: a re-staged
passing duplicate, and the retain-error fallback. Thus the historical claim is
not exactly current at this HEAD, but the row-count completion condition was
still present and needed removal.

## After

`track_daemon_done.adjudicate()` now reads and fsyncs the emitted nonempty CSV,
counts decoded frames with `ffprobe -count_frames`, builds the independent
decoded-frame manifest, and invokes frozen `tracking_harness.evaluate()` on an
in-memory frame table padded to that decoded denominator. It atomically writes
`data/tracking/<game>/harness_verdict.json.part` then renames it to
`harness_verdict.json`.

Each sidecar includes `passed`, `failure_heads`, `coverage_pct`,
`coordinate_space`, `rung`, and `evaluated_at` (plus `csv_fsynced` and
`decoded_frames` for durability/provenance). A completed daemon job is `done`
only when that call returned after the sidecar write. `passed: false` is still
`done`: it is an honest, adjudicated FAIL. Missing or empty CSVs are recorded
as `unadjudicated`.

The JSONL ledger now records the same verdict fields. A staged duplicate can be
removed only when a nonempty CSV and a complete, fsynced verdict sidecar exist,
and a retained original already exists. Finished source footage is moved into
the corpus; a move failure leaves it in the stage. Corrupt staged files are
moved to `data/footage_quarantine`, not unlinked.

## Local regression evidence

```text
python -m pytest scripts/platformkit/test_track_daemon_done.py -q
3 passed

python -m pytest scripts/platformkit/test_track_daemon.py -q
26 passed
```

The focused fake-harness test proves all three G15 cases:

- no sidecar: not done and footage stays staged;
- a FAIL sidecar: done, durable, ledgered, and footage retained;
- empty CSV: unadjudicated and footage retained, never deleted.

## G15b: ledger compatibility and failed-retain recovery

G15 changed completion semantics but accidentally renamed the append-only
ledger's established `tracked` and `thin` values to `done` and
`unadjudicated`. G15b restores the compatible values: `tracked` means a
durable harness sidecar exists, regardless of PASS or FAIL; `thin` means no
sidecar was published. `adjudicated: true|false` is additive. New rows also
emit `failures` as an alias of `failure_heads`, alongside the verdict fields.

`night_report.build_report()` now accepts either ledger shape. Its failure,
coordinate-contract escalation, and declared-image-space corpus paths prefer
`failure_heads` when present and otherwise read legacy `failures`. A mixed
old/new fixture reports `tracked=2`, retains the one PASS, and preserves the
new-row coordinate-contract escalation.

The failed-retain path now renames a staged source to `<name>.failed` after a
corpus or quarantine move error. The filename no longer matches STAGE's
`*.mp4` claim glob. A corrupt-file ledger row is written once with
`status: corrupt`, `retain_failed: true`, and a `retain_failed` failure head;
it is not re-appended on the next tick. This keeps the original failed source
locally visible for operator inspection without repeatedly consuming a worker.

The retained safety comments are intentional: atomic rename must not gain
size-stability polling; the 5400-second clip timeout comes from its measured
checkpoint table; the 262-byte staged-file incident establishes the minimum
video floor; and orphan reaping prevents two processes from writing one CSV.

```text
python -m pytest scripts/platformkit/test_track_daemon_done.py -q
3 passed

python -m pytest scripts/platformkit/test_track_daemon.py -q
27 passed

python -m pytest scripts/platformkit/test_night_report.py -q
4 passed
```

## Restart and deployment boundary

No daemon was restarted and nothing was deployed to the pod in this lane. The
pod keeper remains `/workspace/keep_track_daemon.sh`; restart is pending an
operator-approved deployment. No live pod game has exercised this change.

## Not verified

- The fake frame counter verifies the decoded-frame denominator plumbing, not
  a real pod `ffprobe` execution on a broadcast clip.
- No full tracking run, harness verdict, sidecar, or ledger row was observed on
  the pod under this commit.
- No production footage was deleted, moved, staged, or otherwise touched.
- G15b's failed-retain path was exercised with a filesystem fake, not a real
  cross-device, permission, or storage failure on the pod.
