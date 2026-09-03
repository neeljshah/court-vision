# G178: the manifest route is blocked, and the arithmetic route is promising but not yet safe

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A2, A7, Q8. Written by the
orchestrator because the lane correctly stopped and therefore wrote no memo.
**No code was changed. No bar, denominator, gate or verdict was touched.**

## What the lane did, and it was right

G178 was specced to correct the coverage denominator to EVALUATED frames by
routing the per-frame `evaluated` flag from `frame_manifest.csv` through
`build_decode_manifest`'s existing `non_play` slot. The spec required the lane to
verify that manifest is persisted per job FIRST, and to STOP if it is not.

It is not. Measured on the pod:

    TRACKING_JOB_DIRS=23
    TRACKING_CSV_JOBS=21
    FRAME_MANIFESTS=1

**One of twenty-one tracked jobs has a `frame_manifest.csv`** -- every MLB, KBO
and NPB row, plus soccer, tennis and football, lack it. `track_daemon.py` reads
an OPTIONAL adapter manifest, so absence is normal rather than a fault.

The lane made no change, ran no tests and created no commit, which is exactly
what the spec's STOP condition asked for. **The spec was wrong, not the lane:**
it named a mechanism on the assurance that the evaluated count was "a persisted
artefact, not an estimate", and for 20 of 21 jobs it is neither persisted nor
present.

## The arithmetic route, and why it is not a drop-in either

The evaluated set does not actually require the manifest. It is fixed before any
detection runs by `stride = round(fps * 0.1)`, and both `source_fps` and
`decoded_frames` are already persisted on every ledger row, so
`evaluated = ceil(decoded / stride)` is reproducible from the row alone.

Recomputed by the orchestrator:

| game | fps | stride | decoded | evaluated | coverage/decoded | coverage/evaluated |
|---|---:|---:|---:|---:|---:|---:|
| `tennis_ref01` | 29.97 | 3 | 28,773 | 9,591 | 0.0252 | **0.0757** |
| `mlb_...10893dca` | 59.94 | 6 | 39,035 | 6,506 | 0.1565 | **0.9390** |

Those reproduce the adjudication's expected values (tennis ~0.0756, baseball
~0.90-0.96) to rounding, which is a good sign for the route.

**But it is not safe yet.** `adapter_run.py:81` sets `--max-frames` to a default
of **30000**. `tennis_ref01` decodes 28,773 frames and is under that cap, so its
0.0757 stands. **`mlb_...10893dca` decodes 39,035 and is OVER it**, so the run
was truncated and `ceil(decoded / stride)` overstates what was actually
evaluated. The 0.9390 above is therefore NOT trustworthy: taking the ledger's own
implied emitting-frame count of about 6,109 against a truncation-aware evaluated
count nearer 5,000 would exceed 1.0, which is impossible and proves the
interaction is real rather than theoretical.

So the correct denominator is neither `decoded` nor a naive `ceil(decoded /
stride)`. It is the count of frames the adapter actually evaluated, which depends
on stride AND on where `max_frames` truncated the read.

## What is NOT claimed

- No fix is landed and none is designed here. The route above is a candidate.
- **0.9390 for baseball is explicitly NOT a result.** It is the number the naive
  arithmetic gives before accounting for truncation, shown so the truncation
  problem is visible rather than hidden.
- Nothing here revisits the adjudication: tennis at 0.0757 on evaluated frames
  against a 0.90 bar remains CLOSED AT LIMIT, and that figure is under the cap so
  truncation does not touch it.
- **This is still not a "baseball rescue"** -- G176 established baseball fails at
  `coordinate_contract` before coverage is evaluated at all.

## NOT VERIFIED

- Exactly how `max_frames` truncates: whether it caps source frames read,
  evaluated frames, or emitted rows. Quoted code, not inference, is needed.
- Whether the single surviving `frame_manifest.csv` agrees with
  `ceil(decoded / stride)` on its own job -- the one available cross-check.
- Whether any row's `decoded_frames` already reflects truncation rather than the
  full file, which would change the arithmetic again.
- The wnba and ncaa_basketball rows with `coverage_pct = None`.
