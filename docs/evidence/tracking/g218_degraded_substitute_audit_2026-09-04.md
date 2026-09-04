# G218 Degraded-Substitute Audit

## Scope and method

This is a local, static code-reading audit performed in
`C:\Users\neelj\nba-track-a7` on 2026-09-03. No pod, SSH, corpus, video,
model artifact, production service, or `src/` write was used. Static reading
can establish what a handler can do; it cannot establish that it has fired in
production. It follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`.

The audited population is the output of:

```text
python scripts/platformkit/tracking/silent_handler_census.py --repo .
```

The re-measured census is 118 exception handlers, 57 silent handlers, and 37
silent-and-broad handlers. The eligible denominator is all 37 AST
`ExceptHandler` nodes which both (a) catch bare `except:` or `Exception`, and
(b) have a whole body classified by the census as `pass`, `continue`, `break`,
or a bare `return`.

The AST walks these seven route files only:

| Source input opened | Bytes | Resolution |
|---|---:|---|
| `C:\Users\neelj\nba-track-a7\scripts\run_clip.py` | 35853 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\pipeline\unified_pipeline.py` | 252711 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\tracking\advanced_tracker.py` | 94139 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\tracking\color_reid.py` | 9960 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\tracking\court_detector.py` | 7893 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\tracking\rectify_court.py` | 7374 | N/A (source text) |
| `C:\Users\neelj\nba-track-a7\src\tracking\video_handler.py` | 6741 | N/A (source text) |

The census implementation and its focused test were also opened:
`C:\Users\neelj\nba-track-a7\scripts\platformkit\tracking\silent_handler_census.py`
(4508 bytes) and
`C:\Users\neelj\nba-track-a7\scripts\platformkit\tracking\test_silent_handler_census.py`
(1763 bytes); both are source text with no resolution. The positive-control
review additionally opened
`C:\Users\neelj\nba-track-a7\src\tracking\osnet_reid.py` (23848 bytes) and
`C:\Users\neelj\nba-track-a7\src\tracking\ball_detect_track.py` (54349
bytes), also source text. No media input was opened.

Exclusions are named, not silently removed: 81 handlers in those seven files
are excluded because they are not both silent and broad; every handler outside
the seven `ROUTE_FILES` paths is outside this constructed census; and the two
positive controls below are not added to the denominator. The latter are
method-sensitivity checks, not additional census observations.

Classification rule: a handler is DEGRADED-SUBSTITUTE only when the caught
failure lets normal processing continue with a lower-fidelity substitute,
default, retained stale state, or partial observation and supplies no explicit
degradation signal. An equivalent performance-only acceleration is
OPTIONAL-FEATURE. Cleanup, diagnostics, and cache persistence are BENIGN.
When the source does not establish which of two tracker implementations is
more faithful, the classification is UNCLEAR.

## Exhaustive four-bucket classification

| File:line | Bucket | One-line reason |
|---|---|---|
| `scripts/run_clip.py:61` | OPTIONAL-FEATURE | Failure only disables an on-demand fault-handler stack dump, not tracking or an output feature. |
| `scripts/run_clip.py:524` | BENIGN | GPU/cache release is best-effort teardown after tracking results were already produced. |
| `src/pipeline/unified_pipeline.py:34` | BENIGN | Only warning suppression fails; runtime behavior is unchanged. |
| `src/pipeline/unified_pipeline.py:116` | DEGRADED-SUBSTITUTE | A non-import PyAV decode failure ends the generator, allowing a partial or empty decoded observation to stand in for the requested clip. |
| `src/pipeline/unified_pipeline.py:188` | OPTIONAL-FEATURE | DLPack conversion falls back to `asnumpy`, preserving the decoded pixels while losing only an acceleration path. |
| `src/pipeline/unified_pipeline.py:199` | DEGRADED-SUBSTITUTE | A failed sequential decode is silently replaced by omission of that source frame while the batch continues. |
| `src/pipeline/unified_pipeline.py:214` | OPTIONAL-FEATURE | A failed NVDEC/decord route falls through to PyAV, an equivalent decoded-frame route with lower throughput. |
| `src/pipeline/unified_pipeline.py:283` | DEGRADED-SUBSTITUTE | A decoder-thread exception is replaced by the normal EOF sentinel, making a truncated clip appear complete. |
| `src/pipeline/unified_pipeline.py:609` | DEGRADED-SUBSTITUTE | Failed detector inference returns a plausible empty-detection list and allows the frame pipeline to continue. |
| `src/pipeline/unified_pipeline.py:658` | OPTIONAL-FEATURE | cuDNN autotuning is a performance optimization and has no intended tracking-fidelity effect. |
| `src/pipeline/unified_pipeline.py:1171` | DEGRADED-SUBSTITUTE | Failure of the M1 sanity check leaves validation true, so an unvalidated recovered homography can be installed. |
| `src/pipeline/unified_pipeline.py:1283` | DEGRADED-SUBSTITUTE | A failed learned Kornia/LoFTR homography route silently uses the SIFT fallback. |
| `src/pipeline/unified_pipeline.py:1514` | DEGRADED-SUBSTITUTE | Failed PyAV frame-count reading silently uses a file-size estimate that can change clip stride and coverage. |
| `src/pipeline/unified_pipeline.py:2100` | BENIGN | `malloc_trim` is a platform-specific best-effort memory cleanup. |
| `src/pipeline/unified_pipeline.py:2115` | BENIGN | `malloc_trim` at the GC cadence is a platform-specific best-effort cleanup. |
| `src/pipeline/unified_pipeline.py:2133` | BENIGN | Failure only loses the secondary RSS diagnostic source within best-effort memory monitoring. |
| `src/pipeline/unified_pipeline.py:2169` | BENIGN | Emergency-path `malloc_trim` is best-effort cleanup, not a tracking substitute. |
| `src/pipeline/unified_pipeline.py:2171` | BENIGN | The outer handler protects diagnostic/emergency-memory housekeeping rather than installing a tracking fallback. |
| `src/pipeline/unified_pipeline.py:2851` | BENIGN | Checkpoint-time `malloc_trim` is explicitly platform-specific cleanup. |
| `src/pipeline/unified_pipeline.py:2864` | BENIGN | A checkpoint RSS print is best-effort logging only. |
| `src/pipeline/unified_pipeline.py:2966` | BENIGN | The handler is explicitly best-effort end-of-run resource teardown. |
| `src/pipeline/unified_pipeline.py:3134` | OPTIONAL-FEATURE | `StatsTracker` is documented in-code as best-effort and does not replace coordinate tracking. |
| `src/pipeline/unified_pipeline.py:3193` | DEGRADED-SUBSTITUTE | A convex-hull failure leaves the plausible `spacing=0.0` default in frame spatial output. |
| `src/pipeline/unified_pipeline.py:3401` | OPTIONAL-FEATURE | A corrupt team-map cache is retried through the normal API/fallback resolver; cache reuse itself is optional. |
| `src/pipeline/unified_pipeline.py:3688` | DEGRADED-SUBSTITUTE | Failed reload of checkpointed tracking rows leaves the final in-memory batch as a partial substitute for complete player statistics. |
| `src/pipeline/unified_pipeline.py:4168` | BENIGN | Cache-write failure does not alter the already computed and printed team mapping. |
| `src/tracking/advanced_tracker.py:286` | DEGRADED-SUBSTITUTE | A configured non-default player detector failure retains the base `yolov8n` model. |
| `src/tracking/advanced_tracker.py:348` | DEGRADED-SUBSTITUTE | Pose-model failure retains the documented `bbox_bottom` fallback for player foot location. |
| `src/tracking/advanced_tracker.py:380` | DEGRADED-SUBSTITUTE | Deep OSNet extractor initialization failure leaves downstream assignment on HSV appearance features. |
| `src/tracking/advanced_tracker.py:404` | UNCLEAR | The code selects custom two-stage matching when ByteTrack construction fails, but this source alone does not establish a fidelity ordering between the two implementations. |
| `src/tracking/advanced_tracker.py:490` | DEGRADED-SUBSTITUTE | A failed color-tracker reinitialization retains the prior per-game color-tracker object instead of a fresh one. |
| `src/tracking/advanced_tracker.py:500` | DEGRADED-SUBSTITUTE | A failed ByteTrack reinitialization retains its prior-game object and association state. |
| `src/tracking/advanced_tracker.py:1313` | DEGRADED-SUBSTITUTE | Failed blackout-frame optical flow silently replaces intended gap-fill positions with missing positions. |
| `src/tracking/advanced_tracker.py:1517` | DEGRADED-SUBSTITUTE | Failed deep embeddings silently fall back to HSV per detection. |
| `src/tracking/advanced_tracker.py:1655` | DEGRADED-SUBSTITUTE | Failed Kalman coordinate projection silently replaces a short-gap fill with a missing position. |
| `src/tracking/advanced_tracker.py:1700` | DEGRADED-SUBSTITUTE | Failed batched optical flow silently replaces intended lost-player fills with missing positions. |
| `src/tracking/color_reid.py:83` | DEGRADED-SUBSTITUTE | Failed dominant-color clustering returns a simple pixel mean instead of the dominant cluster. |

Totals: 19 DEGRADED-SUBSTITUTE, 6 OPTIONAL-FEATURE, 11 BENIGN, and 1
UNCLEAR = 37 eligible handlers. Every eligible handler has exactly one bucket.

## Positive-control sensitivity check

The criteria independently re-found both known defect shapes as
DEGRADED-SUBSTITUTE.

| Positive control | Result | Why it is outside the 37-handler denominator |
|---|---|---|
| `src/tracking/osnet_reid.py:459` | DEGRADED-SUBSTITUTE: on OSNet construction failure, the nested fallback creates `mobilenet_v2(weights=None)`, sets `available=True`, and enables `_use_mv2` at `:463-468`; the substitute is untrained rather than the intended trained re-ID representation, and no durable output/status marks that mode. | `osnet_reid.py` is not one of the seven AST route files, and this handler body builds a substitute so the census labels it `other`, not silent. |
| `src/tracking/ball_detect_track.py:79` | DEGRADED-SUBSTITUTE: absent intended engine and fine-tuned weights cause generic COCO `yolov8n.pt` installation with availability true at `:79-81`; the source explicitly says it has lower recall than the fine-tuned ball model, and there is no log or output status. | `ball_detect_track.py` is not one of the seven AST route files; the generic-model rung is an artifact-absence branch, not one of the 37 silent-and-broad AST bodies. |

The only readers of `_ball_yolo_is_coco` are internal inference branches in
`src/tracking/ball_detect_track.py:345` and `:365`; they do not expose a model
identity/status field. This audit obtained no runtime evidence for either
control and does not claim either is currently active.

## DEGRADED-SUBSTITUTE details and blast-radius ranking

Rank is by possible affected surface if the handler fires, not by measured
frequency or measured quality loss. "Hot path" means the normal tracking run
can encounter the resulting behavior while it processes frames.

| Rank | Handler | Substitute and fidelity lost | Observable signal if it fires | Blast radius / hot path |
|---:|---|---|---|---|
| 1 | `src/pipeline/unified_pipeline.py:283` | EOF sentinel replaces a decoder crash; remaining source observations are lost. | No decoder-failure status; a partial artifact can look normally completed. | One clip, potentially all remaining frames; hot path. |
| 2 | `src/pipeline/unified_pipeline.py:116` | Generator termination replaces a PyAV decode failure; remaining observations can be lost. | No decoder-failure status; only downstream row loss may be noticed. | One clip, potentially all remaining frames; hot path. |
| 3 | `src/pipeline/unified_pipeline.py:1171` | An unvalidated recovered M1 replaces a checked homography. | No validation result is emitted with the installed matrix. | All frames after that recovery; hot path. |
| 4 | `src/tracking/advanced_tracker.py:500` | Prior ByteTrack state replaces a fresh per-game tracker. | No reset-success/status field. | Subsequent clip associations, potentially every frame; hot path. |
| 5 | `src/tracking/advanced_tracker.py:490` | Prior color-tracker state replaces a fresh per-game color tracker. | No reset-success/status field. | Subsequent clip team classification, potentially every frame; hot path. |
| 6 | `src/tracking/advanced_tracker.py:286` | Base `yolov8n` replaces the configured player detector. | No loaded-model identity/status field. | Every processed frame in a clip; hot path. |
| 7 | `src/tracking/advanced_tracker.py:348` | `bbox_bottom` replaces pose ankle localization. | No explicit pose-mode status; downstream fields have no failure marker. | Every processed frame in a clip; hot path. |
| 8 | `src/tracking/advanced_tracker.py:380` | HSV appearance replaces deep OSNet appearance features. | No explicit deep-re-ID availability/status field. | Player association across a clip; hot path. |
| 9 | `src/pipeline/unified_pipeline.py:609` | Empty detections replace failed detector inference. | Empty detections resemble an ordinary no-player frame. | Each failed frame; repeated failure can affect every frame; hot path. |
| 10 | `src/pipeline/unified_pipeline.py:1283` | SIFT replaces the learned Kornia/LoFTR homography route. | No matcher-choice/status field. | Each homography refresh and its following coordinate frames; hot path. |
| 11 | `src/pipeline/unified_pipeline.py:1514` | File-size frame estimate replaces stream metadata. | No estimated-count marker. | Clip-wide sampling/stride choice; hot-path initialization. |
| 12 | `src/pipeline/unified_pipeline.py:199` | Omitted source frame replaces failed sequential decode. | Frame-index gaps may exist, but no failure reason/status is emitted. | One or more source frames; hot path. |
| 13 | `src/tracking/advanced_tracker.py:1517` | HSV per-detection appearance replaces deep embeddings. | No per-frame fallback counter/status. | Moving detections in affected frames; hot path. |
| 14 | `src/tracking/advanced_tracker.py:1313` | Missing positions replace blackout-frame optical-flow fills. | Missing rows/positions have no optical-flow failure cause. | YOLO-blackout frames; hot path. |
| 15 | `src/tracking/advanced_tracker.py:1655` | Missing positions replace Kalman-projected short-gap fills. | Missing rows/positions have no Kalman failure cause. | Briefly lost players in affected frames; hot path. |
| 16 | `src/tracking/advanced_tracker.py:1700` | Missing positions replace batched optical-flow fills. | Missing rows/positions have no optical-flow failure cause. | Lost players in affected frames; hot path. |
| 17 | `src/tracking/color_reid.py:83` | Pixel mean replaces dominant color cluster. | No color-method/status field. | Individual jersey crops, potentially many frames; hot path. |
| 18 | `src/pipeline/unified_pipeline.py:3193` | `spacing=0.0` default replaces computed convex-hull spacing. | The zero is present in output but is not marked as a failed computation. | Per-team spatial metrics in affected frames; hot path for derived metrics. |
| 19 | `src/pipeline/unified_pipeline.py:3688` | Final in-memory rows replace full checkpointed rows in player-stat aggregation. | Export has no full-versus-partial completeness marker. | One final player-stats export per clip; not tracking hot path. |

## Human-gated proposals only; no source change applied

All proposals below affect `src/` and are human-gated. No diff has been
applied.

1. Add a durable per-run degradation ledger/status object, emitted in the run
   summary and output metadata, rather than removing any fallback. It should
   record code, component, first frame (when relevant), count, and substitute
   selected. This gives decoder, detector, homography, model-init, tracker
   reset, and feature fallbacks an explicit observable trace.
2. In `src/pipeline/unified_pipeline.py`, record decoder source, skipped-frame
   count, premature-EOF cause, homography matcher and validation result, and
   whether frame count is estimated. Keep PyAV/SIFT/file-size fallbacks, but
   make their use visible.
3. In `src/tracking/advanced_tracker.py`, emit startup/per-game component
   identity and reset outcomes for configured player model, pose, deep re-ID,
   color tracker, and ByteTrack. For per-frame deep/flow/Kalman fallbacks,
   aggregate counters into the durable per-run status instead of logging every
   frame.
4. In `src/tracking/color_reid.py`, tag or count mean-color fallback use so a
   color result is distinguishable from a successful dominant-cluster result.
5. In `src/tracking/osnet_reid.py` and
   `src/tracking/ball_detect_track.py`, retain the availability-preserving
   fallbacks but report exact model family, weight source, trained/untrained
   state, and fallback reason in the durable status. This directly addresses
   both positive controls without making a long run fail merely because an
   artifact is missing.

## NOT VERIFIED

- No eligible handler is claimed to have fired in production; this audit has
  no runtime trace, import probe, pod access, or corpus execution.
- No relative detection, homography, pose, re-ID, color, tracking, or export
  quality was measured. The fidelity ordering used above is limited to what
  code comments and fallback roles establish.
- The actual availability, checksum, and deployment location of intended
  model artifacts were not inspected.
- The actual state-retention semantics inside the external ByteTrack object
  were not established, so `src/tracking/advanced_tracker.py:404` is honestly
  UNCLEAR rather than classified as degraded.
- No output schema or reader was changed or added, so there is no schema
  compatibility claim to verify.
- No visual sampling, scored metric, corpus comparison, or feature flag action
  occurred.

## Verification record

- Focused local test: `python -m pytest
  scripts/platformkit/tracking/test_silent_handler_census.py -q` -> 4 passed.
- Verifier contract read and self-checked: sections A and B. Section Q is not
  applicable because G218 is a constructed static source census with no scored
  quantitative/harness claim.
- B1: no rows excluded from the 37-handler metric without naming them; all
  exclusions and both out-of-denominator controls are named above.
- B2-B6 and B10: no production/schema change, deployment, claim-state change,
  module move, or threshold/bar change occurred.
- B7-B9: no render, self-fit comparison, or recycled-unit metric occurred; the
  denominator is one AST handler node per enumerated eligible case.
