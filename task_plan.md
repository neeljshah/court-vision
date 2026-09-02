# G93 Line Detection Limit Measurement

## Goal

Execute `docs/evidence/tracking/specs/G93_spec.md` exactly: measure candidate-group detection recall for visible basketball paint lines on the fixed G84 sample, write the required committed evidence and renders, and satisfy the verifier contract.

## Phases

### Phase 1: Contract and baseline discovery
**Status:** complete
- Read the verifier contract (including A7 and all B lines), G84/G87 evidence, and inspect the fixed sample/harness.

### Phase 2: Pre-registered measurement setup
**Status:** in_progress
- Record fixed correspondence and miss-reason vocabularies before candidate review; create the visibility-mark and render workflow without detector changes.

### Phase 3: Measurement and evidence
**Status:** pending
- Mark all 33 frames, run fixed detector parameters, calculate recall/Wilson intervals, render every frame, and write the evidence memo.

### Phase 4: Verification and commit
**Status:** pending
- Execute only the permitted focused test if code is added, self-check every verifier B requirement, commit explicit G93 paths, and report SHA.

## Decisions Made

| Decision | Reason |
|---|---|
| Use the existing G84 seeded sample and its exact detector configuration | Required for a commensurable precision/recall measurement. |
| Make no changes to human-gated `src/`, `kernel/`, `api/`, `scripts/team_system/`, or `intel/` trees | Repository policy and G93 prohibit detector/calibration modifications. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| Root `VERIFIER_CONTRACT.md` not found | 1 | Spec gives the canonical path under `docs/evidence/tracking/`; read that file next. |
| ImageMagick `magick` is unavailable for contact-sheet assembly | 1 | Use the existing indexed G84 renders directly in bounded batches; do not retry the unavailable command. |
| G84's source contact-sheet tree is absent, so raw-tile crop cannot open its first declared sheet | 1 | Preserve the fixed, committed G84 candidate overlays as the audit images; use their indexed detector lines plus stored endpoints for the hand-marking pass. No data download or detector rerun will be attempted. |
| Initial crop of G76 blind boards assumed row-major placement and yielded blank/wrong cells for some identities | 1 | Inspect one full board to recover its actual layout before using any crop; discard the derived temporary crops. |
| Initial focused test had an incorrect sixth-decimal Wilson expectation | 1 | Corrected the test expectation from the computed 0.104270; rerun the same sole focused test once. |

## Next Step

Inspect the G84 script/test, selection/manifest schema, original image availability, and the existing render convention; then preregister fixed correspondence and miss taxonomies before reviewing candidates.
