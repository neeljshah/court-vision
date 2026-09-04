**GATE: FAIL (n=0 clips, 0 frames, 0 labellers): the named source file is absent, so no fit, independent withheld-geometry render, or pixel-offset measurement exists.**

# G256: Soccer Line-and-Conic Calibration

**Verdict: FALSIFIED (source premise; full success).** This measurement-only landing follows [the verifier contract](VERIFIER_CONTRACT.md). It makes no production, coordinate-contract, `IMAGE_SPACE`, `src/`, `domains/`, label, pitch-model, corpus, daemon, or deployment change. A different available football clip was not substituted for the named soccer input.

## Source identity before decode

The required logical source was `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`. This Windows environment has no `/workspace` mount: `C:\workspace` is absent, and `du -sm /workspace/nba-ai-system/data` exits 1 with `No such file or directory`. The shared worktree corpus junction resolves to `C:\Users\neelj\nba-ai-system\data\footage_corpus`; neither that directory nor the worktree alias `data\footage_corpus` contains the named file. Its direct listing contains one football video, two tennis videos, one football JPEG, and `g130_recensus/` only.

| Requested source identity field | Result |
|---|---|
| Full requested path | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Windows-equivalent path checked | `C:\workspace\nba-ai-system\data\footage_corpus\soccer__soccer_Z6NTDyxcODs.mp4` (absent) |
| Shared-local path checked | `C:\Users\neelj\nba-ai-system\data\footage_corpus\soccer__soccer_Z6NTDyxcODs.mp4` (absent) |
| Worktree corpus alias checked | `C:\Users\neelj\nba-track-a5\data\footage_corpus\soccer__soccer_Z6NTDyxcODs.mp4` (absent) |
| Bytes / SHA-256 / resolution / frames / fps / duration | UNAVAILABLE: no source file was opened or decoded |

This is the required premise-first check. The historical corpus inventory names other soccer files, but it is not evidence that the specifically required source is currently present. No video was opened; therefore there is no source checksum, frame count, frame survey, frame choice, or decoded image identity to report.

## Disk guard and retained state

`df` was not used. Before writing this evidence, a local worktree probe wrote 1,048,576 bytes with `dd if=/dev/zero of=.g256_dd_write_probe bs=1048576 count=1 conv=fsync`, verified that size, and removed the probe. The required `/workspace` `du -sm` command is recorded above as unavailable because the mount itself is absent. Two direct attempts against the available Git-Bash path `/c/Users/neelj/nba-ai-system/data` returned no result in the available command window; no substitute free-space measure was used.

No corpus source, `footage_bridge` partial, label, or existing artifact was deleted or changed. The only temporary artifact was the successfully removed 1,048,576-byte probe, so 1,048,576 temporary bytes were freed.

## Method status and gate

G253's landed harness, `scripts/platformkit/tracking/g253_line_conic_calibration.py`, was read but not changed or run; its SHA-256 at this landing is `d3eb9daa4196c4c25dbf9aacca819d38fbfeecf1ff979988c18fb0adf9aa07df`. No frame exists to survey for visible, unoccluded pitch geometry, and no identity crop can be committed honestly. Consequently:

| Required item | Status |
|---|---|
| Fitted lines | None |
| Fitted conic | None |
| Standard dimensions assumed | None |
| Non-standard pitch length or width used | No |
| Identity crops | None; no image exists to crop |
| Image-space line angle / observed conic circumference / condition number | NOT MEASURED; no configuration was fitted |
| Independent withheld geometry | NOT MEASURED; no projection exists |
| G252 24-px strong-edge search, censoring, median / p90 / max / no-candidate count | NOT MEASURED; the gate did not pass |

Had a fit been possible, only standard geometry would have been eligible: centre-circle radius 9.15 m; penalty-area depth 16.5 m and width 40.32 m; goal-area depth 5.5 m and width 18.32 m; and penalty-mark distance 11 m from the goal line. Pitch length and width are not fixed by the Laws and would not have been fitted constraints. Any non-standard dimension assumption would invalidate such a result. No numerical residual is reported because no fit was performed, and a self-fit residual would not be gate evidence in any event.

The hard gate FAIL is a source-availability failure rather than a claim about line-and-conic geometry: no fitted element was used as evidence, and no withheld penalty-area or goal-area render was possible. There is no basis to compare an unmeasured soccer offset with G252's WNBA reference (median 5 px, p90 19 px under its 24-px search and retained no-candidate censoring).

## Context and NOT VERIFIED

Before this attempt, soccer remained `image_px` only and outside the coordinate contract; the programme's prior soccer line census found no usable four-line configuration, and its earlier stated accepted-homography count was invalidated as a stale cached map. This row neither changes nor proposes changing that state. Automatic calibration remains 0/17: a future hand-fitted line/conic measurement would still not be automatic calibration.

NOT VERIFIED: recoverability of a soccer pitch homography; any feature identity; manual-label reliability; G253-harness output; degeneracy; independent geometry; pixel accuracy; propagation; coverage; detection; tracking; any coordinate output; and any claim beyond one unavailable requested clip. The intended scope would have been one clip, one frame, and one labeller; here it is zero decodable clips, zero frames, and zero labellers.

## Verifier self-check

A7: the on-tree paths named in this memo (the contract and G253 harness) exist; the absent requested source is explicitly named as unavailable, not silently treated as evidence. B1: there is no computed metric or excluded denominator. B2-B6: no schema, reader, lifecycle, deployment, module, or production state changed. B7: no sampled evidence is claimed. B8: no fit residual or fitted element is offered as independent evidence. B9: no metric denominator is recycled. B10: no bar, threshold, model, or contract changed. Q does not apply to this tracking measurement row. No harness was added or altered, so no per-file test is applicable.
