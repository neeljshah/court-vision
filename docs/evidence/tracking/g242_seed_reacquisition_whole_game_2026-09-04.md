# G242: Whole-game direct reacquisition from one validated WNBA seed

## Verdict

**ACCEPT (measurement only): 89/89 sampled frames acquired under G222's unchanged literal matcher, 1.000000 of the named denominator.** This is not a correctness or arena-camera conclusion. Independent overlays show that the literal matcher also accepts close-ups, replays, graphics, and the other hoop end, where a projected court is visibly wrong or cannot be judged. The operational unit therefore remains **NOT VERIFIED**; G241's contiguous result is not displaced by this measurement.

This landing follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production code, label, label CSV, coordinate contract, threshold, daemon, keeper, corpus source, `src/`, or `domains/` file changed.

## Hold, source identity, and disk guard

At 2026-09-04 04:02:21 -05:00 I checked the pod before beginning. Its long-running G241 stdin-Python measurement was active (later observed at about 46 CPU minutes); I did not interrupt it. This was the permitted second lane.

The pod was used because it holds the read-only corpus. `df` was not used. `du -sm /workspace/nba-ai-system/data` was 32835 MB, then `dd if=/dev/zero of=/workspace/nba-ai-system/g242_disk_probe.bin bs=1M count=1 conv=fsync` passed; its 1048576-byte probe was removed. Each run streamed a single sequential decode and retained no full decode. The preliminary current-tree run was deleted as a 10482697-byte duplicate. The final pod temporary artifacts removed were 10481358 bytes; the committed final artifacts total 12394749 bytes.

The final run streamed the exact G233d source blobs read-only from `C:\Users\neelj\nba-track-a3`; their SHA-256 values match G233d: G196 `f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`, G215 `b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a`, and G222 `2b99a30f3ff6dd1d633e0d088dee150c379f655e2fb78556589b5a948743d8c4`.

## Inputs and exact seed reproduction

| Input | Full path | Bytes | Identity |
|---|---|---:|---|
| Corpus | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2931985407 | 1920x1080, 174430 frames, 30 fps |
| G236b reference | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g236b_reindex_validated_frame_artifact\best_match_1920x1080.jpg` | 623686 | 1920x1080; SHA-256 `aa0f63cf53073550e903b2961fc6d0be0ac45a236f49b9ff83ca476c1e6a0d1e` |
| G140 labels | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g140_corner_targets\corner_pixel_targets.csv` | 15633 | SHA-256 `9ede0561441a062125bb708ee4496e7d22786608872e345d4079c70113000096` |

Frame 19599 was independently decoded with `ffmpeg -i VIDEO -vf select=eq(n\,19599) -vsync 0 -frames:v 1 -f rawvideo -pix_fmt bgr24 pipe:1`, with no input-side seek. Its BGR MAD against the reference was 1.087048. The four CSV labels were `(350,400)`, `(835,420)`, `(390,696)`, `(990,730)`. Both images are 1920x1080, so scale is exactly 1.0. `court_points_for_sport("wnba")` supplied `[(17,0),(33,0),(17,19),(33,19)]`, and the reproduced image-to-court matrix matches G233d with maximum absolute difference 0.0:

```text
[[0.050071754999888064, 0.01225404716365722, 2.3351407383547964],
 [-0.0047586809476217904, 0.1153980129798286, -44.493666860263815],
 [3.054485397744623e-05, 0.0011147252900901028, 1.0]]
```

## Sampling and literal G222 result

One `cv2.VideoCapture` pass decoded frames 0 through 174429 sequentially. The sample is stride-2000 frames 0 through 174000 plus the explicit seed: **89 unique frames**, including 10 before the seed and 78 after it. The independent frame-exact re-decode of sampled frame 100000 had BGR MAD **0.0** against its streamed counterpart; the streamed seed likewise had MAD 0.0 against the exact seed.

G222's unchanged acceptance is ORB `nfeatures=2000, fastThreshold=12`, Hamming ratio `< 0.75`, at least four matches, `cv2.findHomography(..., RANSAC, 3.0)`, and a finite matrix. It accepted 89/89. Match / inlier / ratio / RMS distributions (including the constructed seed row) were respectively 87/309/549.8/2000, 50/265/508.2/2000, 0.565217/0.851211/0.938741/1.000000, and 0.000000/0.472978/0.610621/1.400314 (min/median/p90/max). The zero seed RMS is construction, not evidence.

The complete signed-distance table, including every match diagnostic and render path, is [CSV](g242_seed_reacquisition_whole_game_artifact/per_sample_table.csv) and [measurement JSON](g242_seed_reacquisition_whole_game_artifact/g242_measurement.json). The most distant accepted negative is [frame 0, -19599](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_000000.jpg); the most distant positive is [frame 174000, +154401](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_174000.jpg).

## Failure inventory and independent render review

There are **zero literal G222 acquisition failures**. Accordingly there is no honest failed-frame class to count and no invented failed render. That itself is the finding: the acceptance rule is not a geometry-validity rule.

I opened all 89 retained overlays, represented evenly in ten [contact sheets](g242_seed_reacquisition_whole_game_artifact/acquired_contact_sheets/). Their source-scene inventory is 52 normal court views, 29 tight player/bench/crowd/commentary views, 6 replay or overhead views, and 2 graphic/partial-court views. Every category passed G222. Examples: [frame 8000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_008000.jpg) is the other hoop end and its yellow seed-end court does not land on the visible paint; [frame 24000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_024000.jpg) is a player close-up; [frame 46000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_046000.jpg) is replay/overhead; and [frame 18000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_018000.jpg) is graphic-obscured.

In contrast, independent painted arc, free-throw circle, sideline, and baseline geometry visibly agrees at the seed and several same-end views, including [19599](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_019599.jpg), [74000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_074000.jpg), [122000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_122000.jpg), and [174000](g242_seed_reacquisition_whole_game_artifact/acquired_renders/frame_174000.jpg). The fitted paint corners were never used as the judgment. The renders, not their inlier counts, establish that 1.0 is a literal-match fraction only.

## Labels-per-hour and limitations

Literal arithmetic is `ceil(30 * 3600 / 174430) = 1` hand label per hour if one such seed were sufficient for every sampled frame. It is **not** a usable coordinate-label rate because the same rule accepts visibly invalid maps. This consumes one hand label and says nothing about automatic calibration (still 0/17), ground truth, repeatability beyond G140's 11.39 px p90, dense temporal coverage, other arenas, other broadcasts, or a correctness gate. One clip, one seed, and a wide stride cannot measure shot duration or replace G241's contiguous horizon.

## Contract self-check

A7 evidence paths exist; B1 includes all 89 named sample rows; B2-B6 change no schema, lifecycle, deployment, production module, or moved module; B7 uses all ten evenly spread contact sheets; B8 does not present fitted corners or distance-zero residual as independent; B9 uses frames, not recycled identifiers; B10 retains G222 settings. Q does not apply.
