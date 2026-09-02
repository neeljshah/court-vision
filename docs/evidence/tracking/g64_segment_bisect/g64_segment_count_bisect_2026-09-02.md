# G64: baseball DAY segment-count bisect

Date: 2026-09-02. Worktree `a2`; log `cx_g64_segment_count_bisect`.

Verdict: **NOT VALIDATED.** Code is ruled out. Environment and footage cannot be separated because the historic environment stamp and source hashes do not survive. No causal axis is named; claiming one would violate B1. G36 remains blocked.

## Complete count

The retained `baseball_scale_validation_2026-09-01/summary.json` was only read; it was not regenerated or overwritten.

| Clip | Retained | Pod rerun | Delta |
|---|---:|---:|---:|
| `mlb_2iosUkpL0Bc` | 19 | 19 | 0 |
| `mlb_ARtRmUHC7dw` | 11 | 13 | +2 |
| Total | 30 | 32 | +2 |

Both arms decoded all 600 sampled frames per clip at stride 3. The one-clip movement rules out a uniform all-clip effect but not a clip-specific environment/decode or footage difference.

## Code axis: ruled out

Original measurement commit: `1942be94b748cb11546cdb5975a3fa7c5d083c56`. The original scale driver, segmenter, and landmark module hash-match on pod; only geometry differs. Full original geometry executed transiently in memory on the read-only pod, holding clips and environment fixed. Historic and current geometry both returned 19 + 13. Counts, starts, hashes, and `run_environment` stamps: [controlled_code_axis.json](controlled_code_axis.json). No pod file was written, copied, deployed, or restarted.

## Environment and footage: tested, not isolated

The original memo says the run was local but has no stamp. This local worktree is currently OpenCV 4.11.0; the pod is Python 3.12.3 / OpenCV 4.14.0 / NumPy 2.1.2 / Torch 2.8.0+cu128. The clips are absent locally, so same-byte cross-environment counts cannot be made. G52 makes this a serious hypothesis, not a conclusion.

Today's pod SHA-256 values and a run stamp are in [footage_environment_inventory.json](footage_environment_inventory.json): `2iosUkpL0Bc` = `641345b2c4b9ce7744e9c6b1075a22e1467999a381c388f925483476b162e455` (148216834 bytes); `ARtRmUHC7dw` = `fdece11e4072b866dff13c92679f643a8e1d8bb183d42ba9e3ec7d4a45aa6ab7` (125624139 bytes). No historic hash exists, so byte identity is **NOT VERIFIED**.

## Eye check

I viewed both complete excess positions from current second-clip segments 12 and 13: [frame 1710](extra_current_segment_12_f001710.png) and [frame 1719](extra_current_segment_13_f001719.png). Both are adjacent first-base-side field views with first base, umpire, fielders, and outfield; neither has a mound or pitcher. They are false pitch-view episodes, not new game action. Historical segment-boundary alignment is unavailable. See [render_manifest.json](render_manifest.json).

## NOT VERIFIED

- OpenCV version used by the original local process.
- Same-byte local-4.11 versus pod-4.14 counts.
- Byte identity of either current clip with its 2026-09-01 source.
- Historic segment alignment for the two surplus positions.
- A causal environment or footage conclusion.

## Verifier self-check

| Requirement | Self-check |
|---|---|
| A7 | Clear: this memo, retained summary, JSON artifacts, render manifest, and PNGs exist. |
| B1 | Clear: no rows excluded to recreate 30. |
| B2-B6 | Clear: no code, schema, gate, claim behavior, deployment, or reference changed. |
| B7 | Clear: both excess positions were viewed. |
| B8 | Clear: no model is reported. |
| B9 | Clear: complete two-clip denominators are named. |
| B10 | Clear: budget, stride, segment definition, thresholds, G11, and retained artifact did not move. |
