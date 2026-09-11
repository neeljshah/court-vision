# G408 runtime review requirements (for the existing USER G401 decision)

This row supplies mechanics and an un-applied proposal. It supplies NO runtime
result. Everything below is a prerequisite the user's G401 deployment review
still needs, and none of it is measured here.

## Why a runtime review is unavoidable

The landed clip cap is 3000 source frames. `src/pipeline/unified_pipeline.py`
sets `_VRAM_FLUSH_INTERVAL = 3000` inside the same loop. Under arm B or arm C a
59.94 fps section admits about 5990 frames, so a run crosses that flush boundary
for the first time in this route. The proposal does not change the interval, the
stride computation, or the flush site; it only lets more frames reach them.

## Smoke prerequisites, none of them satisfied by this row

1. One GPU run per cap arm on the same section, with wall time, peak VRAM, peak
   RSS and the produced row counts recorded for each.
2. Receipt retention across the first flush: confirm the CSV writers, the
   scoreboard log and the evaluated-frame sidecar survive frame 3000 intact.
3. Tracking-quality comparison before and after frame 3000 on the same run, so
   a longer window is not bought with degraded rows in its second half.
4. Producer-emitted tick coverage under the longer window, which G401 already
   records as unverified against the DECLARED stride opportunities.
5. Concurrency: the landed comment at `build_command` documents an 18000-frame
   job still running after 18216 s at daemon concurrency. A ~2x longer clip must
   be shown to finish inside `JOB_TIMEOUT_SECONDS` at the live worker count.
6. Decoder coverage: the proposal reads a presentation timestamp from decord,
   PyAV and cv2. Each path needs one run proving a timestamp is actually
   produced, because an absent timestamp terminates UNKNOWN by design.

## Rollback prerequisites

- Without `--duration-seconds` the argv is byte-identical to the landed command,
  so rollback is removing the argument from the caller, with no data migration.
- The receipt fields are additive. A consumer that ignores them is unaffected;
  `requested_duration_s` is null on every legacy run.
- The diff is applied nowhere. Reverting is deleting the un-applied text.

## Separate and still pending

G393 parser repair and G395 live overlay remain independent open rows. Nothing
in this row changes, closes, or depends on either.

## NOT VERIFIED

Runtime cost, VRAM or RSS behaviour past frame 3000, receipt retention across
the flush, tracking quality under any arm, producer tick coverage, decoder
timestamp availability on the pod, and any deployment, restart or flag change.
