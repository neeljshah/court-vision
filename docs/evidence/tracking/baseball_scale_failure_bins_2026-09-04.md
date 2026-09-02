# G33 baseball scale failure bins -- premise falsified

Date: 2026-09-02. Lane: G33. Sport: baseball. Worktree: `a7`.

Verdict: **FALSIFIED -- stop before the binning measurement.** The requested
input file, `baseball_scale_validation_2026-09-01/summary.json`, does not
reproduce the stated 9/36 premise by itself. It contains only the two Window A
clips. Its segment fields total 9 validated of 30 total, not 9 of 36.

## Premise reproduction

| source read | validated segments | pitch segments | pitch-view frames |
|---|---:|---:|---:|
| `summary.json` (the named premise input) | 9 | 30 | 322 |
| `night_stride20/summary.json` (separate, not named by the premise) | 0 | 6 | 10 |
| both files combined | 9 | 36 | 332 |

The top-level file has `segments_validated` values 7 and 2, against `segments`
19 and 11. The additional 6 segments are only present in the nested night
summary (1 plus 5). Thus the headline 9/36 and 73/332 can be reconstructed
only by silently adding a second artifact; they cannot be reproduced from the
single artifact the contract names.

The top-level rounded frame-agreement rates imply 66 plus 7 = 73 validated
pitch-view frames, but its denominator is 322. Adding the nested 10
pitch-view frames produces 73/332. This confirms the provenance discrepancy;
it does not authorize treating `summary.json` alone as the four-clip result.

## Stopped work

No 108 renders were made. No failing or validated segment was assigned a bin.
No bin table or bin counts are reported, because producing them after the
failed premise would violate G33's explicit stop instruction.

No detector, adapter, gate, tolerance, threshold, status value, or pod file
was changed. No pod job was started, no module was copied to a pod, and no
feature flag was changed.

## NOT VERIFIED

- The 27-failure breakdown is not verified.
- The five required bin counts are not verified.
- The control bins for the 9 validated segments are not verified.
- The 108 evenly spaced renders and their eye check are not verified.
- Whether `resolution_360p` is the dominant bin is not verified; G36 must not
  be dispatched on the basis of G33.
- The requested binning-helper test was not added: the premise-stop rule ended
  the lane before a helper or binning measurement was authorized.

## Verifier contract B self-check

| condition | result |
|---|---|
| B1 circular metric | Clear: the named artifact's complete rows were summed; no row was excluded. |
| B2 non-additive schema | Clear: no schema or reader changed. |
| B3 fall-through loss | Clear: no gate changed. |
| B4 re-claim loop | Clear: no failure handling changed. |
| B5 pre-verification deploy | Clear: no pod operation occurred. |
| B6 orphans | Clear: no module moved or retired. |
| B7 head-slice evidence | Clear: no renders were used after the premise stop. |
| B8 self-fit as independent | Clear: no fitted result was reported. |
| B9 degenerate denominator | Clear: denominators are the explicit JSON segment sums, 30 and 6. |
| B10 moved bar | Clear: no tolerance, same-row rule, rubber constant, status, or harness threshold changed. |

Required corrective action before any future G33 measurement: name both JSON
artifacts in the premise (or replace the top-level summary with an aggregate
that actually contains all four clips), then re-dispatch from the corrected
premise. This lane makes no inference about additional baseball footage.
