# G233c: Reindexed NCAA Seed Gate

## FAIL - the distance-zero projected court does not land on the painted court

This is the required hard-gate verdict. The yellow inverse-projected court runs through seating, baseline lettering, and broadcast-signage space rather than remaining on the visible painted court. The four red points are the fitted inputs, not independent validation. Per `docs/evidence/tracking/VERIFIER_CONTRACT.md` and the G233c acceptance rule, propagation, player-foot projection, in-court fractions, outside-distance distributions, later-distance renders, and labels-per-hour arithmetic were not run.

## Scope, machine, scheduling, and disk guard

This is a measurement-only result. The pod at `/workspace/nba-ai-system` was used solely because the read-only corpus video is resident there; the local worktree `C:\Users\neelj\nba-track-a5` rendered the committed exact decoded PNG and retains the evidence. At `2026-09-04T07:43:06Z`, an exact `/proc` argument-basename inventory found only the permanent `keep_track_daemon.sh` resident and no matching G232, G235, G236, G238, or G239 measurement worker. No resident, daemon, keeper, capture runner, adapter job, or foundry runner was waited on, killed, restarted, or changed.

Before any measurement output, the binding `dd if=/dev/zero ... bs=1M count=12 conv=fsync` probe passed at the explicit path `/workspace/nba-ai-system/data/.g233c_dd_probe_2967233`. `du -sm /workspace/nba-ai-system/data` was 32349 MB before and after. The 12582912-byte probe was removed. `df` was not used.

## Exact inputs and frame provenance

| Input | Full path | Bytes | Resolution / identity |
|---|---|---:|---|
| Corpus video | `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 3580059573 | 1920x1080 video stream; 205444 frames; 30000/1001 fps |
| G236 committed best-match still | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g236_label_reindex_existence_artifact\best_match_640x360.jpg` | 115720 | 640x360; SHA-256 `7630bf5366b57bd3cf1a6c15ff64a93d1a3814e9e1ef1b8b52521711fe133a72` |
| Exact decoded seed | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g233c_seed_gate_artifact\measurement\decoded_seed_frame_46154.png` | 3201691 | 1920x1080; SHA-256 `60144d1f836ad573ecba707897e78429e4f990166a19671ea24364945e8500c5` |

The seed is zero-based frame 46154. It was decoded frame-accurately with `ffmpeg -i VIDEO -vf select=eq(n\\,46154) -vsync 0 -frames:v 1`, followed by a PNG extraction. No input-side `-ss` was used. The bounded temporary pod job reported `rc=0 bytes=3201691`; its SHA-256 exactly equals the fetched local PNG SHA-256 above.

Before any homography construction, the decoded PNG was reduced to 640x360 with OpenCV `INTER_AREA` and compared to G236's committed matched frame. Colour MAD was 1.865680 of 255. The [committed side-by-side comparison](g233c_seed_gate_artifact/measurement/decoded_seed_frame_46154_vs_g236_best_match.png) was visually checked: court, players, crowd, and broadcast graphics agree. This verifies that the geometry gate below uses the G236-matched frame, not the incorrectly named index 28171.

## Fixed seed construction and render

The source labels are 640x360, and the video is 1920x1080. The scale factor is exactly 3.0. No coordinate was tuned.

| Role | Label px | Scaled native-video px |
|---|---:|---:|
| Near baseline left corner | `(38, 223)` | `(114, 669)` |
| Near baseline right corner | `(39, 289)` | `(117, 867)` |
| Near free-throw left corner | `(274, 224)` | `(822, 672)` |
| Near free-throw right corner | `(273, 282)` | `(819, 846)` |

The unchanged `court_points_for_sport("ncaa_basketball")` was used, giving the 12-foot NCAA lane points `[(19, 0), (31, 0), (19, 19), (31, 19)]`; the WNBA 16-foot lane was not used. The image-to-court homography is:

```text
[[-0.003363616984280291, 0.056501292359316474, -19.294683312439012],
 [ 0.022472194145923066, -0.0003404877900897448, -2.3340438010651896],
 [-0.00016425748617990242, -0.000041144626323545014, 1.0]]
```

The required [distance-zero seed render](g233c_seed_gate_artifact/measurement/seed_render_source_frame_46154.jpg) is the only court render because the gate failed. Its [traceability record](g233c_seed_gate_artifact/measurement/seed_gate_record.json) stores frame index, decode contract, source PNG identity, 3.0 scale, ordered labels, scaled points, sport, court points, homography, and render name.

## Code identity and cleanup

The local render harness [g233c_ncaa_seed_gate.py](../../../scripts/platformkit/tracking/g233c_ncaa_seed_gate.py) has SHA-256 `fb0c7963e353e801c15bb68f929087c420aa93650c69f21c4214c39a71da5cbb`; its unchanged G196 dependency has SHA-256 `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`. The pod used `/usr/bin/ffmpeg` SHA-256 `ed16af623947494a72e284b6eb8ff225f2da22b38b5d5069c2fd4b4ba3384e41`. No repository file was copied to the pod; the exact ffmpeg command was transient stdin-only process control.

After transfer validation, the owned pod temporary PNG, status, and log were removed: 3201691 + 19 + 0 = 3201710 bytes. Together with the required probe and a 2-byte local path probe, known temporary bytes freed are 15784624. No corpus source or label file was changed or deleted. The four committed measurement files total 4521381 bytes and are retained evidence, not temporary output.

## Verifier self-check and NOT VERIFIED

- A7: this memo and every linked evidence path exist before commit.
- B1: no post-gate metric was computed and no rows were excluded.
- B2-B6: this is additive measurement evidence only; no schema, lifecycle, deployment, production module, or retired module changed.
- B7: the decision set is the one specified distance-zero seed, not a selected head slice.
- B8: the exact four-point fit is not represented as independent validation; the failure is the out-of-sample rendered court.
- B9: no detector denominator or player metric was computed.
- B10: no threshold, bar, coordinate contract, court model, label, or harness threshold changed.

NOT VERIFIED: propagation behavior; player detection or feet; in-court fractions or outside-distance distributions; a labels-per-hour horizon; any automatic calibration (it remains 0/17); another clip, camera, or seed; a constant re-index offset for other labels; and whether plausibility would correspond to player accuracy. This consumes one hand label and is not automatic calibration. G140's single-source eye-label p90 repeatability is 11.39 px. The G222 feature horizon was measured on a different clip and is not assumed to transfer. Plausibility is necessary, never sufficient.
