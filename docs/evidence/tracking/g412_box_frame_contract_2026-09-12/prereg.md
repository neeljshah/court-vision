# G412 sealed preregistration

## Scope and status

This is a prepare-only writer-contract study. It defines the finite inputs, constructive controls, coordinate equations, and retained outputs for a later finisher. This commit performs no premise re-measurement, native decode, rendering, comparison, rating, model invocation, scoring, pod job, deployment, restart, flag change, registry write, register write, or ledger write.

The later finisher must execute the G412 step-0 binding condition before treating the premise as true: rehash all selected G402/G406 draw, row, and source inputs; reproduce the 60 distinct ticks, 206 stored rows, five silent ticks, and the absence of a writer frame receipt from the named archived inputs. A missing route binding is PARTIAL. An equivalent receipt already present is FALSIFIED only after that exact condition is run and its output is quoted in the completed memo.

## Frozen inputs and boundaries

The decision set is exactly the 60 exact-even G406 ticks, 30 per kind, named by `docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11/draw.csv`; no replacement, reselection, or head-only slice is permitted. The rows are exactly the historical raw stored boxes bound by `associations.csv`, `per_tick.csv`, `frame_receipts.csv`, `input_hashes.csv`, `source_receipts.csv`, and `window_accounting.csv` in that same evidence directory. G402 meanings are bound by `docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/target_mask.csv` with expected SHA-256 `c2c4f57a56330afbc9a7772b61743864aa04d746d9715e0374743e724a79dc71`; G380 provenance is bound by `docs/evidence/tracking/g380_producer_provenance_2026-09-10/summary.json` with expected SHA-256 `2155b6f861fd2a611e61488f6ce7bb42af7d231c1860bfde324bee7b7c47dba9`.

Every path with another `nba-track-aNN` worktree prefix resolves under this worktree root. The finisher reads one store at a time and records full input path, byte size, SHA-256, native dimensions, rational PTS, receiver mapping, and failures. No model is exercised; the identity record therefore uses an explicit empty model set. G410 remains pending and is not a prerequisite.

## Frozen coordinate contract

For a stored cropped `xyxy` box `B = (x1, y1, x2, y2)`, the proposed native padded box is `(x1, y1 + 60, x2, y2 + 60)`. The proposed native unpadded detector-form box is `(x1 + 15, y1 + 75, x2 - 15, y2 + 45)`. Clip to cropped dimensions before restoring the native origin. The 60-pixel top origin and 15-pixel horizontal padding apply only to the bound fresh box-based route. Fresh box-based court writes use `((x1c + x2c) // 2, y2c, 1)` through `M` then `M1`; ankle, flow, prediction, and retained-point routes are explicit exceptions and receive `UNKNOWN` with a reason when unbound.

The writer proposal is additive only: `box_frame`, `box_crop_origin_y_px`, and `box_padding_px`. Existing bbox and position values, their ordering, and their interpretation remain byte-identical. Absent boxes produce an empty receipt. The receipt states coordinate representation and nominal stored padding only; it does not establish branch freshness or that a predicted box is an observed detector box.

## Frozen acceptance procedure

The finisher will enumerate all 32 constructive controls: two native sizes, four locations (interior, top crop boundary, right boundary, bottom boundary), two box states (fresh integer, fractional prediction), and two empty/nonempty statuses. The independent oracle checks tuple order, inward padding, clipping order, native origin, missing-value handling, additive receipt parsing, and legacy serialized field parity.

For native demonstration, all 60 cards are required, including five silence cards. The derived record retains raw cropped, native padded, and native unpadded boxes, source-frame and PTS joins, clipping effects, and route scope. Historical G406 comparator associations remain descriptive only: 51 pairs over 28 frames, never 51 independent frames. Its old signed centre `dy` median is `-58.2`; the planned algebra adds 60 before clipping, with clipping deltas logged separately. This does not establish physical court registration, geometry quality, live integration, branch freshness, or training suitability.

## Required completed artifacts

The later measurement commit must populate the evidence directory with `input_hashes.csv`, `source_receipts.csv`, `route_chain.json`, `reader_manifest.csv`, `transforms.json`, `construct_cases.csv`, `writer_compatibility.csv`, `per_frame.csv`, `paired_residuals.csv`, `eye_index.csv`, `renders/`, `summary.json`, `repeats.json`, `runtime_receipts/`, `q6_scan.json`, and `SHA256SUMS`; retain the named proposed diff and its digest. It must run only `python -m pytest tests/platformkit/test_g412_box_frame_contract.py -q` and append the required ledger line in that later commit.

SEAL sha256 f48ae105abc5d869864bc19d5e580870bcf8b98eafd33baf99a4e400882be916
