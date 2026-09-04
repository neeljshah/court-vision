# G236b: G196-validated WNBA still existence search

**Verdict: ACCEPT. The G196 YES-labelled still appears in the current corpus video at zero-based frame 19599, with decisive separation.** The refined 64x36 grayscale MAD is 0.903212, or 0.022212 of the complete stride-5 scan median 40.664062. This is a more dramatic outlier than G236's reference ratio of 0.036661. It is a match, not merely a nearest-neighbour index.

This is a measurement-only landing governed by `docs/evidence/tracking/VERIFIER_CONTRACT.md`. No label, label CSV, coordinate contract, production source, `src/`, `domains/`, pod checkout, daemon, keeper, seed gate, propagation path, or corpus source changed.

## Scope, machine, hold, and inputs

Machine: pod `/workspace/nba-ai-system`, because the named corpus source is pod-resident. G225's exact `python.exe -m scripts.platformkit.tracking.g225_detector_capacity_sweep` route was found active at the first hold check and was not interrupted. At `2026-09-04T08:05:22.4714817Z`, immediately before launch, the same exact-process check found no active G225 route; the scan then began. Permanent residents were neither waited on, stopped, restarted, nor changed. A later G225 launch occurred after this run was underway and was not disturbed.

| Input | Full path | Bytes | Resolution / identity |
|---|---|---:|---|
| Corpus video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080; 174,430 declared frames |
| G196 YES still | `C:\Users\neelj\nba-track-a3\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s01__f001600.jpg` | 621,798 | 1920x1080; labelled `source_frame` 1600; SHA-256 `e9ead024840b53be902376b3cd76918ef36ae9d7b40527c5c413cc21ce9183f8` |

Both inputs are 1920x1080. **No scale factor was applied.** Coarse scoring reduces each independently to 64x36 only for search ranking; confirmation and the named-index baseline compare native 1920x1080 pixels directly.

## Search, distribution, and separation

The G236 method was reused: one sequential `cv2.VideoCapture.read` pass from frame 0 through EOF, with every fifth decoded frame converted to grayscale, reduced via `INTER_AREA` to 64x36, and scored by mean absolute pixel difference against the identically reduced still. This retains all 34,886 stride-defined candidates while writing no decoded video frame on the pod. The best stride candidate was refined frame-accurately over 19595 through 19605 by a single `ffmpeg select=between(n,...)` native-resolution extraction to memory. The candidate and index-1600 baseline were each exact native-resolution `ffmpeg` extractions to memory.

The full temporal extent was decoded: 174,430 / 174,430 frames, or 100.0000 percent. The distribution is over all 34,886 stride-5 candidates, not a head slice; every pair is retained in [measurement.json](g236b_reindex_validated_frame_artifact/measurement.json).

| Quantity | Value |
|---|---:|
| Coarse stride | 5 |
| Coarse candidates | 34,886 |
| Whole-scan coarse min | 1.427951 at frame 19600 |
| Whole-scan p1 | 22.080013 |
| Whole-scan median | 40.664062 |
| Refined best | 0.903212 at frame **19599** |
| Best / whole-scan median | 0.022212 |
| G236 reference best / median | 0.036661 |
| Wall time | 583.776836 seconds |

The separation is decisive: the refined best is 97.7788 percent below the whole-scan median, 0.0409 of p1, and below even the stride-5 coarse minimum. The local temporal valley is also sharp: frame 19598 = 1.567274, 19599 = 0.903212, and 19600 = 1.427951. This satisfies the deliverable's requirement for a dramatic outlier rather than an unsupported nearest-neighbour claim.

## Frame-accurate confirmation and eye check

At native 1920x1080, mean absolute colour difference over BGR channels is **1.546192 of 255** at frame 19599. At the named labelled index 1600, the identical native comparison is **51.571621 of 255**. These are the same colour-MAD units used by G236 and G233c and are directly comparable because no rescaling is involved.

The matching court, players, scoreboard, and broadcast graphics are visible in [the labelled still beside the exact best frame](g236b_reindex_validated_frame_artifact/labelled_still_vs_best_match.jpg). The exact candidate is separately retained as [best match 1920x1080](g236b_reindex_validated_frame_artifact/best_match_1920x1080.jpg).

The recovered delta is `19599 - 1600 = +17999` frames. G236 recovered `+17983` on its other clip, a difference of only 16 frames. The two results are consistent with a shared near-constant re-index, but they do not establish a systematic rule, its cause, or transferability: this n=1 row and G236's n=1 row are insufficient to prove that conclusion.

## Disk guard, cost, and cleanup

`df` was not used. Before the scan, the pod worker recorded `du -sm /workspace/nba-ai-system/data = 32,424 MB`, ran `dd if=/dev/zero ... bs=1M count=4 conv=fsync`, observed a 4,194,304-byte probe, and removed it before decoding. The post-removal `du` result was 32,424 MB. The probe passed; 4,194,304 bytes were freed. No decoded frame, temporary video, source file, or worker file was written on the pod. The earlier failed hostname-resolution launcher never connected to the pod, so it ran neither a probe nor a decode and produced no metric.

## Code identity and focused test

The streamed pod worker SHA-256 is `3c93d0b3b583538f2b106c8b6869b2ae5018d0333b7a3d4985278a0a43418cc1`. The local launcher SHA-256 is `10e746a6ddde3df98286c127cb95c1b3ed0f75f5caecfbcdfb018715e36a7b89`; its additive source is `scripts/platformkit/tracking/g236b_reindex_validated_frame.py`. The pod reported OpenCV 5.0.0 and `/usr/bin/ffmpeg` SHA-256 `ed16af623947494a72e284b6eb8ff225f2da22b38b5d5069c2fd4b4ba3384e41`. The worker was streamed on stdin and never copied to the pod.

Focused test run: `python -m pytest scripts/platformkit/tracking/test_g236b_reindex_validated_frame.py -q -p no:cacheprovider` -> 2 passed. It asserts the `dd conv=fsync` guard and cleanup precede worker execution, the WNBA source and index-1600 baseline are fixed, and native 1920x1080 confirmation is used.

## Verifier self-check and NOT VERIFIED

- B1: all 34,886 stride-defined candidates are retained in the committed artifact; none was excluded after scoring.
- B2-B6: no schema, reader, lifecycle, gate, deployment, production code, or pod checkout changed.
- B7: the distribution is a complete stride-defined temporal scan; the committed image is the single global refined best, not a head sample.
- B8-B9: this is direct image comparison, not a fitted residual or recycled denominator.
- B10: no threshold, bar, or verdict moved; separation is reported against the unchanged G236 reference ratio and complete-scan distribution.
- A7: this memo, [measurement JSON](g236b_reindex_validated_frame_artifact/measurement.json), [candidate image](g236b_reindex_validated_frame_artifact/best_match_1920x1080.jpg), and [comparison image](g236b_reindex_validated_frame_artifact/labelled_still_vs_best_match.jpg) exist before commit.

NOT VERIFIED: a constant offset within either clip or across clips; the origin of the near-equal deltas; re-indexing any other still; label geometry beyond G196's prior eye check; the seed gate; propagation; player projection; or calibration. This existence match does **not** prove the seed gate passes. It only makes that separate test possible on geometry G196 validated.
