# G236: labelled-still existence search

**Verdict: ACCEPT. The committed labelled still appears in the current corpus video at zero-based frame 46154.** This is a clear match, not a nearest-neighbour claim: its refined 64x36 grayscale MAD is 1.944878, just 0.036661 times the whole-scan median 53.049913 and well below the required 0.5 separation ratio. The frame-accurate 640x360 colour MAD is 6.358071, compared with 61.625894 at the still's labelled index 28171.

This measurement follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no label, production source, `src/`, `domains/`, pod checkout, daemon, keeper, corpus source, threshold, bar, or coordinate contract.

## Scope, machine, hold, and inputs

Machine: pod `/workspace/nba-ai-system`, because the only current corpus source is pod-resident there. At `2026-09-04T06:57:46.661035+00:00`, then again at `2026-09-04T07:11:01.997788+00:00` before the final run, an exact `/proc` check matched Python executables plus basename-prefixed `G235` or `G220c` arguments. It found none. Permanent residents were neither waited on, stopped, restarted, nor changed.

The 640x360 JPEG was used rather than the 1080p variant because it is the committed label-resolution source and permits the required full-resolution-to-640x360 colour MAD to be directly commensurable with the stated labelled-index baseline.

| Input | Full path | Bytes | Resolution / identity |
|---|---|---:|---|
| Corpus video | `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 3,580,059,573 | 1920x1080; 205,444 declared frames |
| Labelled still | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg` | 106,044 | 640x360; SHA-256 `474f93a9a7cbf4e4e92822bb59ce582d28a2141fa1959cfe0b5b26b1e3528051` |

## Search and separation check

The final run decoded the video once, sequentially with `cv2.VideoCapture.read` from index 0 through EOF. It retained no decoded frames on the pod. Every fifth decoded frame (41,089 frames, 20.0001 percent of decoded frames) was converted to grayscale, reduced with `INTER_AREA` to 64x36, and scored by mean absolute pixel difference against the identically reduced JPEG. This metric is cheap, absolute, and retains scene structure sufficiently to rank one frame against the whole video.

The whole temporal extent was decoded: 205,444 / 205,444 frames, or 100.0 percent. The coarse comparison distribution covers every stride-5 candidate, not a head slice. The best coarse candidate at 46155 was refined frame-accurately over 46150 through 46160 using one `ffmpeg select=between(n,...)` range extraction to memory. The final candidate and the labelled index baseline were each extracted by `ffmpeg select=eq(n,index)` to raw memory, then downscaled from native 1920x1080 to 640x360 with `INTER_AREA`.

| Quantity | Value |
|---|---:|
| Coarse candidates | 41,089 |
| Coarse min | 5.231337 at frame 46155 |
| Coarse p1 | 25.779028 |
| Coarse median | 53.049913 |
| Refined best | 1.944878 at frame **46154** |
| Best / median | 0.036661 |
| Improvement below median | 96.3339 percent |

The separator is decisive. The result is far below the required `best < 0.5 * median` rule, and the nearest frames form the expected sharp temporal valley: 46153 = 5.029948, 46154 = 1.944878, and 46155 = 5.231337. The complete 41,089-pair distribution and refinement values are retained in [measurement.json](g236_label_reindex_existence_artifact/measurement.json), so this arithmetic can be recomputed without rerunning the pod scan.

## Frame-accurate confirmation and eye check

The candidate's full-resolution exact extraction, downscaled to 640x360, has colour MAD **6.358071 of 255** against the committed still. Repeating that identical comparison at the labelled index 28171 gives **61.625894 of 255**, reproducing the supplied approximately 61.33 baseline closely enough to make the two results commensurable. The side-by-side render shows the same players, court, scoreboard, and crowd at the same play moment: [labelled still versus best match](g236_label_reindex_existence_artifact/labelled_still_vs_best_match.jpg). The frame itself is separately retained as [best match 640x360](g236_label_reindex_existence_artifact/best_match_640x360.jpg).

The recovered index delta is `46154 - 28171 = +17983` frames. One matching still is consistent with a fixed re-index within this clip, but it does not establish that the offset is constant across this clip or transferable to other clips. A successor must validate another labelled still before applying a blanket offset.

## Disk guard, run cost, and cleanup

`df` was not used. No decoded frame or measurement artifact was written on the pod. The only pod writes were binding `dd if=/dev/zero ... bs=1M count=4 conv=fsync` probes, immediately removed.

| Attempt | Pod data size before probe | Probe and cleanup | Status |
|---|---:|---|---|
| First launcher, aborted before result | 32,168 MB | Passed; 4,194,304-byte probe removed | Stopped after identifying redundant per-frame refinement reads |
| Second launcher, aborted before result | Not returned after harness failure | Passed and removed; 4,194,304 bytes freed | Range path retained an erroneous one-frame output cap |
| Final launcher | 32,257 MB; 32,257 MB after removal | Passed; 4,194,304-byte probe removed | Complete evidence run |

Total known freed pod bytes are 12,582,912, exclusively the three probe files. The final complete run took 695.960 wall seconds. The first two attempts produced no evidence artifact and are not used for any metric.

## Code identity

The final pod worker SHA-256 was `5bd42890c6f4e774a02435fbe543613f9853c42088701d6af35065854400740d`; its local launcher SHA-256 is `2e3e94fddf2ecf02b1ca7df5f1194eeb97f43892f9c8f0b2d38b56de48f8045c`. The pod used OpenCV 5.0.0 and `/usr/bin/ffmpeg` SHA-256 `ed16af623947494a72e284b6eb8ff225f2da22b38b5d5069c2fd4b4ba3384e41`. The additive local launcher is [g236_label_reindex_existence.py](../../../scripts/platformkit/tracking/g236_label_reindex_existence.py); it was streamed as stdin code only, never copied to the pod.

## Verifier self-check and NOT VERIFIED

- B1: all 41,089 stride-defined candidates are retained; no bad candidate was excluded.
- B2-B6: no schema, lifecycle, gate, reader, production module, or pod deployment changed.
- B7: the decision set is the complete stride-defined scan; the committed image is the single global best candidate, not a head slice.
- B8-B9: this is direct image comparison, not a fit residual or recycled denominator.
- B10: the only separator is the pre-existing `best < 0.5 * median` rule; no threshold or bar moved.
- A7: this memo, [measurement](g236_label_reindex_existence_artifact/measurement.json), [candidate image](g236_label_reindex_existence_artifact/best_match_640x360.jpg), and [comparison image](g236_label_reindex_existence_artifact/labelled_still_vs_best_match.jpg) exist before commit.

NOT VERIFIED: a constant offset for other stills in this clip; re-indexing of any other clip; whether the 17,983-frame delta arose from a trim, an edit, or another provenance change; label geometry, seed-gate behaviour, propagation, player projection, or calibration. This is one clip and one still. It establishes this still's existence in this current file, not a corpus-wide re-index rule.
