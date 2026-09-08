# G322 PREREG -- oversized boxes census + producer trace + sealed contact-sheet check (2026-09-07)
ATTEMPT 2 -- re-sealed after a Q6 vocabulary defect in the attempt-1 prereg (c00d0f6ca); census rule, secondary cuts, sheet selection rule, categories, thresholds UNCHANGED.
Sealed and committed ALONE before the first metric, the first frame and the first label.
Spec: `docs/evidence/tracking/specs/G322_spec.md` (master 2beaa82ee, SHA-256
`5d19c06554b8ba8a8aeea8ede735dd9ea367845d16975335d914f0e0351d87b2`).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A3, A7, A9, A11, A12, B1-B11, Q1, Q6, Q7, S1, S4).

## 1. Inputs, fixed now
The census set is every row of `track_daemon_ledger_snapshot.jsonl` with `status == "tracked"` and
`rows > 0`: **107 distinct games**, snapshot SHA-256
`443bc83d0640bb646c0cd58615b5f3a3de02238235e7b4a869bff2aaeef02004`, 132 ledger lines, copied
READ-ONLY from `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl` on the pod.
Per-game input = `/workspace/nba-ai-system/data/tracking/<game>/tracking_data.csv`, fetched
READ-ONLY into the lane scratchpad by one `tar czf - -T -` stream over `ssh`; the SHA-256 in section
10 is over the LOCAL FETCHED BYTES, which are the bytes measured. The pod tree is mutating under a
running 16-worker `track_daemon`; nothing on the pod is written, signalled or killed by this row.
All 107 source videos exist on the pod as `data/footage_corpus/<sport>__<game_id>.mp4` (checked
before this seal; 124 files present, 0 of the 107 missing).

## 2. Definitions, fixed now
- A **player observation** = one row of `tracking_data.csv`. The denominator of every share below is
  that game's own row count in its own table. No row is excluded for any reason except a missing or
  non-numeric `bbox_y1`, `bbox_y2` or `source_height`, and those are COUNTED and REPORTED per game.
- `box_h` = `bbox_y2 - bbox_y1` **exactly as written in the CSV**. Known property, stated before
  measurement: the writer adds `PAD = 15` to each vertical border (`src/tracking/player_detection.py:20`,
  `src/tracking/advanced_tracker.py:1336`), so the CSV `box_h` is **30 px taller** than the detector's
  own box.
- `frame_h` PRIMARY = the table's **own `source_height` column**, per row. The ledger's
  `source_height` field is reported beside it and every game where the two disagree is named (S4).
- Secondary/diagnostic, sealed now, moving nothing: `frame_h_posttopcut = source_height - 60`
  (`TOPCUT = 60`, `src/tracking/video_handler.py:11`), and `box_h_padremoved = box_h - 30`.

## 3. Metric and thresholds, FIXED NOW AND NEVER MOVED
Per game and per source resolution: the share of player observations with
- PRIMARY cut `box_h > 0.50 * frame_h`
- SECONDARY cuts `box_h > 0.33 * frame_h` and `box_h > 0.25 * frame_h`
each printed with its own n. Diagnostics printed beside them: `box_h > 0.50 * frame_h_posttopcut`,
`box_h_padremoved > 0.50 * frame_h`, and `max(bbox_y2)` per game against `frame_h` and
`frame_h - 60`.
**VERDICT RULE: PREMISE HOLDS if and only if at least one game's PRIMARY share is `>= 0.10`.**
Below that on every game, the premise is FALSIFIED and the row STOPS with the memo (Q8).

## 4. Panel-game selection rule, FIXED NOW (sealed before any panel exists)
Eligible = an enumerated game with `>= 100` rows above the PRIMARY cut and a source video present.
Four panel games, five panels each, twenty panels total:
- for each source resolution in the order `1920x1080`, `1280x720`, `640x360`: the eligible game at
  the **nearest-rank MEDIAN** of that resolution's eligible games ordered ascending by PRIMARY
  share, i.e. rank `ceil(n/2)` (1-based), ties broken by `game_id` ascending;
- plus the eligible game with the **highest** PRIMARY share corpus-wide; if it is already selected,
  take the next-highest not already selected.
- If a resolution has no eligible game its slot is dropped and refilled by the next-highest
  corpus-wide PRIMARY share not already selected, so the count stays four games / twenty panels.
This is deliberately **NOT a top-tail selection**: three of the four games are per-resolution
medians and exactly one is the maximum (A3 / B7).

## 5. Panel-row selection rule, FIXED NOW
Within a panel game, take its rows above the PRIMARY cut, sort ASCENDING by `box_h / frame_h`, ties
broken by (`frame`, `player_id`) ascending, and take the **five odd-decile midpoints**: 1-based ranks
`r_i = ((2*i + 1) * n + 9) // 10` for `i = 0..4` in exact integer arithmetic (the 10th, 30th, 50th,
70th and 90th percentile by nearest rank), clipped to `[1, n]`. The five panels therefore sweep that
game's whole oversized distribution rather than its top tail.

## 6. Rendering rule, FIXED NOW
Frames are cut ON THE POD, read-only, with `ffmpeg -i <source> -vf select=eq(n,<frame>) -frames:v 1`
into `/tmp/g322/`, then `scp`-ed out; panels are drawn LOCALLY and HEADLESS with PIL, never
`cv2.imshow`. The tracker's boxes are **post-TOPCUT** (`src/pipeline/unified_pipeline.py:1689`,
`src/tracking/video_handler.py:61`), so a box is drawn on the full extracted frame at
`y = bbox_y1 + 60 .. bbox_y2 + 60`. That assumption is CHECKABLE from the census diagnostics of
section 3: if `max(bbox_y2)` exceeds `frame_h - 60` for a panel game, the assumption is falsified,
the memo says so, and that game's panels are re-rendered with no offset. Each panel is captioned
with game, `frame`, `player_id`, `box_h`, `frame_h` and the ratio. Panels are laid out as
**two contact sheets of ten** (games 1-2, games 3-4), JPEG, `<= 500 KB` each.

## 7. Classification rubric, FIXED NOW (written before any panel was viewed)
Exactly ONE label per panel:
- `crowd` -- the box is mostly spectators / stands.
- `bench_or_courtside` -- mostly bench players, coaches, staff, media, officials at the sideline.
- `broadcast_graphic` -- mostly a score bug, lower third, replay wipe or other overlay.
- `two_or_more_players` -- two or more on-court players substantially inside one box.
- `one_player_close` -- one on-court player, genuinely near the camera, correctly boxed.
- `other` -- none of the above (net, rim, floor, wall, empty court, off-frame sliver).
- `unreadable` -- the panel does not support any of the calls above.
`NON_SINGLE_PLAYER` = `{crowd, bench_or_courtside, broadcast_graphic, two_or_more_players}`.
**A PROPOSED diff under `docs/research/organization-sprint/` is written IF AND ONLY IF
`count(NON_SINGLE_PLAYER) >= 15` of the 20 panels.** Otherwise nothing is proposed. Nothing under
`src/`, `domains/`, `api/`, `kernel/`, `intel/` or `data/registry/` is edited either way.

## 8. The rater, and its declared limit
ONE declared **MODEL rater: Claude Opus 5 (`claude-opus-5[1m]`)**, the lane itself. G315 measured
that two model raters agreed on only **14 of 30** of its panels (0.4667 on a three-label task), so
this row **reports COUNTS PER CLASS and never a rate**, quotes no per-class share, and names
**human labels as the limit** on any content claim. These 20 panels are an EYE CHECK, not a sampled
or scored metric (Q7).

## 9. What this row may NOT do
No write to the pod, `src/`, `domains/`, `api/`, `kernel/`, `intel/`, `data/registry/`,
`scripts/platformkit/tracking_harness.py`, the register, or any historical ledger row. No threshold
moved, no flag flipped, nothing deployed. No forbidden market-language tokens (Q6): the word
for a box side is `boundary` or `border`. Image space only (`coordinate_space = image_px`): no
court, foot, metre or registration claim.

## 10. Game list with table hashes (107 games; SHA-256 of the fetched bytes)
game_id | source_resolution | ledger source_height | ledger rows | bytes | sha256
0022400909_s1015 | 1280x720 | 720 | 6030 | 2345160 | 34d07939c5d2f7e33a1680596ad2ed2b4061527196f82a72b8a23981bf8d4d3c
0022400909_s1397 | 1280x720 | 720 | 1956 | 754773 | 9eba7dfafa748874f148ec2d7a04c06250fef875cd548ea24025fbb5439d60ae
0022400909_s1588 | 1280x720 | 720 | 5826 | 2323673 | ec555ba307502e9139abdcbf6459b2b9965ce2c77da32e59e694667213bb12e4
0022400909_s1779 | 1280x720 | 720 | 4928 | 1943035 | 37eebd7d2bb3402979501a3e4d4fce4f4e6aaf9b3a3d9356c584845a73db5426
0022400909_s1970 | 1280x720 | 720 | 4371 | 1752140 | 9c9945555168810533183322a06cd975d06758cdd2bd22a8df797f254b69d143
0022400909_s2161 | 1280x720 | 720 | 5877 | 2384295 | 735c19f335f6b72a16f1f5c2051318801be526fb3b0de16f51e897007ee78a81
0022400909_s2352 | 1280x720 | 720 | 5226 | 2091020 | 3fe19d44e542cf92dc2237cc9b0f0ed6b877a9d34827747898530c844776c09b
0022400909_s251 | 1280x720 | 720 | 4394 | 1738798 | 5971de7aa6f288f49a95884699902da36ec489f59b11e218834aebd0f3c2b406
0022400909_s2734 | 1280x720 | 720 | 4334 | 1723136 | 349c2c9c8611042cd7279c47216bdb92b34ab9b189b03a0ce2d7d2676a387b2e
0022400909_s2925 | 1280x720 | 720 | 4251 | 1682866 | 9f8b67eee871ea24eb62ff12c7a9bd828ef7498407dc1dd052b85be1f432f0df
0022400909_s3116 | 1280x720 | 720 | 5538 | 2133098 | 1d67b6a37caac9220a62dfdc393277a79a3b50dee170aac035cc249a029eb238
0022400909_s3307 | 1280x720 | 720 | 5761 | 2239435 | fa8cfc9e8d29855505f4e5999c9a8eae6aac8b8c00814b627e4034847f0c9106
0022400909_s3498 | 1280x720 | 720 | 5604 | 2262749 | a2842502a485d289d68ad48fc25e8954960ac2e8cdf51f49a9f91fcd970be585
0022400909_s3689 | 1280x720 | 720 | 1242 | 482637 | e93e6d86624f54bad9e0aacde45bd5b947e6955a582c621853c526b87b00bb3d
0022400909_s3880 | 1280x720 | 720 | 4425 | 1698061 | 3f8286f587543606453cb7aacce07df57aef5be8c3729bdc41e8f0e97f630e52
0022400909_s3900 | 1280x720 | 720 | 4255 | 1673539 | 9081177b113670d0e96fb06335e1b729f2d5635c18ff207a79cbe7144f865682
0022400909_s4071 | 1280x720 | 720 | 4454 | 1736194 | 355009b8c96abe936c57544c4de41d329b444483886eba7cee8b624c422d9aaa
0022400909_s4262 | 1280x720 | 720 | 5267 | 2033446 | 641dc413d2f585b9f494a7aced98bd0cdd3cb969eb525ac13310a56cda9716d2
0022400909_s442 | 1280x720 | 720 | 4864 | 1931412 | 6256290520f48cf09907d4f908f07a8bb7c1e6a14b25549ec3d650bfa01e7e35
0022400909_s4453 | 1280x720 | 720 | 1700 | 649758 | 0a026bf42947bb7a694befec24a9c11fa4cabbadfcd8194bfba5ca9c0b0b3087
0022400909_s4644 | 1280x720 | 720 | 4058 | 1600442 | 9c54262d905fec4988786e60d2031dbc4a5c646c3ae17faf4c675e0e11513fed
0022400909_s5026 | 1280x720 | 720 | 3540 | 1405572 | 2886c25327f36d43a198daf9007bf0c88ad7897b6dee4a4ae1e540f2b34a6f37
0022400909_s5217 | 1280x720 | 720 | 5945 | 2342953 | 61978c9b44211ea532c3db014cc35c40faa16f3a7c0b937ecd5ae689087afe17
0022400909_s5400 | 1280x720 | 720 | 4016 | 1625559 | a934369b6b04972826e152859b2edb0eb89ac939833f1cdd6278da9eb7bfd269
0022400909_s5408 | 1280x720 | 720 | 3425 | 1343808 | 807bcce00eac61ae42116f8a98b0cf6334aca271947072be81d68b76cbdac3e4
0022400909_s60 | 1280x720 | 720 | 4516 | 1792929 | 0f6fb66f5d1baae9e3accd16d9f91374d592f41e6be04df329c25b5dab9bb716
0022400909_s633 | 1280x720 | 720 | 4905 | 1977791 | 60086c9f5c151eb25c6a2af63b98469a3ede0ef775dd921f2aeeb7fe4d131e1d
0022400909_s824 | 1280x720 | 720 | 1326 | 506567 | 63f0dbe945f719eedf0488ee5970086df546dd75ec8861ac78b3d9bda8c5ed1b
0022400909_s900 | 1280x720 | 720 | 5603 | 2188931 | f98b58290a0aca0da09da4862abe7e298b18ed800ca831e24bbc1c9c3f2b0f65
0022401156_s1182 | 1280x720 | 720 | 4880 | 1835357 | 0e6eb9a3b5096048f89991c02079abb0c4f4d7151bbd3740d41c5767d5665b70
0022401156_s1369 | 1280x720 | 720 | 4781 | 1862992 | 2328e0ab6960e94725c35c2e2844a15110635c985987eb9378cce8dad8a48079
0022401156_s247 | 1280x720 | 720 | 4893 | 1866540 | d4f0503e0f2bcd975477337b4c47697808c0780f0ef83a39305afd78381a304e
0022500575 | 640x360 | 360 | 2459 | 972165 | 5207ee8e0228f231cb46a7519a8c8b0b4b8ad81f9e303957d6134d52a0714c0e
0022500575_s1500 | 640x360 | 360 | 6066 | 2375233 | 9da26a0da0ce5809f49d8f403888af844006b76d6fd338b44312002e08a244d7
0022500575_s2100 | 640x360 | 360 | 1853 | 736934 | 436fc2df69eb5f0a6e536030135f9b424985128cc587d58630848c7df9e703c6
0022500575_s2700 | 640x360 | 360 | 5746 | 2321081 | d22da18c4e7f2eaa58d9967c98a86bbdd237c4ce7a57df5fd33341982a30b520
0022500575_s300 | 640x360 | 360 | 2208 | 879780 | 720a1ddd11d4c99300ec33cb93c2f50cf3a7449418693b14a592787f878f2a19
0022500575_s3300 | 640x360 | 360 | 4403 | 1763052 | bae38779915ff2866c01af46fac5d25db86fe8b52d5eded8112d94d52ad6b252
0022500575_s3900 | 640x360 | 360 | 5116 | 2022181 | 1492e44ccb113781bab51abb5c1d7a964386bf0e99411b48694b734531885542
0022500575_s5400 | 640x360 | 360 | 3211 | 1246816 | 0ce9525f0ddc8612a833baec9e3862aeaffb1e7265efee6d3049d6ed1d997104
0022500575_s6000 | 640x360 | 360 | 3161 | 1242815 | 4e54d09b0f683016cf714c8baaa8fb27ed0f41c34011746dd35b270f8c20c8ba
0022500575_s6600 | 640x360 | 360 | 3573 | 1430484 | 7aca82bc9be7e9ea43763a91878ed1ca36daa9a10224db7d4ecf313b711eb13e
0022500575_s7200 | 640x360 | 360 | 2620 | 996052 | 82fb57537879ee64bf3e1cf70b7c16fb61fc06039109245c275d711ce5232678
0022500575_s8100 | 640x360 | 360 | 3461 | 1387888 | cabeb4034d315a0503151c6b79c889a2e6a48ebcf37daa542e87626e94135358
0022500575_s8700 | 640x360 | 360 | 3113 | 1222539 | 9d9698509508025a23218f4b23a12250a02cd54a98547c9c79610c98bcf32cea
0022500575_s900 | 640x360 | 360 | 3303 | 1319456 | 28a0ccb31820a59c180c66e6c18fe1e45284f7b25e2f1e6052dec9c764f41011
0022500592_s1500 | 640x360 | 360 | 3151 | 1217557 | 6fe26b97b8464b61ca0d4d764d94617fab31ec611b31e4c2a8a8762a95ceb258
0022500592_s2100 | 640x360 | 360 | 5267 | 2049752 | 80e23606401a26b06d45ff768f6f038889668ca9b8675ad65337eaa87d008c8e
0022500592_s3300 | 640x360 | 360 | 6394 | 2576067 | f2938c6701d47c71409efa4bc20001dabc50145b1af6f45c578ff726e8373aa3
0022500592_s3900 | 640x360 | 360 | 4269 | 1718453 | 969d64a2ddbbeff87f944323e492686ea4520e3c2776a3e76aad7cb64f9a08f9
0022500592_s5400 | 640x360 | 360 | 3578 | 1374914 | df5f61572e83a86f8a15cedeb058ebb5a37473bb9242725c83210cb6071ded3f
0022500592_s6000 | 640x360 | 360 | 2517 | 980774 | 36fce07634e0cee136baf0efab6b49fe83ac33e233f51c7f7894fb9218ab7f22
0022500592_s6600 | 640x360 | 360 | 5044 | 2069523 | 56dda1ec56475f3f12d1b71d30888dc01337df2dd8baa70140c7d4a77fb203eb
0022500592_s7200 | 640x360 | 360 | 4319 | 1727678 | 1aebeb90e756c228dea39cd147915a09f9ee60e2536a085a28f0452c175847e6
0022500592_s8100 | 640x360 | 360 | 4745 | 1896922 | 3562368fe07c30c1ce8f8e3164f6679b813e8142471cf43a366f4b0832c1557b
0022500592_s8700 | 640x360 | 360 | 3594 | 1465155 | 0e92f8f70dc51031f8db5c6758f20f5079f1facc383d7afcedbe8be82b9794dd
0022500592_s900 | 640x360 | 360 | 2508 | 996741 | fff710ff41cb35c4ff3556c9639ffd90a45c8bedd3917a33729c15f4b7c7a9cd
0022500594_s1500 | 640x360 | 360 | 4291 | 1616038 | 9636572ca15d177eef9da3430da95e256a5df700c1735699bc894ef01edf72b3
0022500594_s2100 | 640x360 | 360 | 4750 | 1838250 | 2c550b103a32e78a76245a90ce48e3ea317438bece6adaa340c1b869744337d7
0022500594_s2700 | 640x360 | 360 | 1188 | 446286 | 08be7e9a94c0f5d11b4ad298c53ea4e52a48b3cd4f9f5152a6aca21725df7855
0022500594_s300 | 640x360 | 360 | 413 | 149911 | ad9980768efa50b2bf2b86094096253cdc5841c06164a66cf432af134ca49631
0022500594_s3300 | 640x360 | 360 | 3466 | 1329886 | 9662159bb9a342d46f3d0e073884dcd6932c248100259853f7d7e17c55dc30b1
0022500594_s3900 | 640x360 | 360 | 3839 | 1474999 | 46bb22303db4e8850561104d1098849a1d504bd734369a850a93df633af31331
0022500594_s5400 | 640x360 | 360 | 4170 | 1536796 | 3332351c96f3fd353315af19e6b22007d68751ecdb71ce7ebd1b45e78cb9ac8e
0022500594_s6000 | 640x360 | 360 | 1103 | 422457 | 16c6d66f0298b01bbc91160e91958ddf8449cc26892ac111fd74a20096587400
0022500594_s6600 | 640x360 | 360 | 3850 | 1414973 | 1c7d736e755ede0f3e09b3902a8aff251340edf1bfa015d015ba1ac2d5d475ee
0022500594_s7200 | 640x360 | 360 | 5357 | 2070434 | 92978798acc83fe36e38b9bbeaaed16f99fcd1e5192841bbeb8ead45122a806d
0022500594_s8100 | 640x360 | 360 | 3764 | 1471327 | d41d74e3650bafa6d80f013b1ac20ab89d5762e51165a20e28b1c004e962b039
0022500594_s8700 | 640x360 | 360 | 4204 | 1611858 | fdfddb8b046baeb52f43cd3f6de57c912962fecdcc68cefcf6a50b6d23de8a29
0022500594_s900 | 640x360 | 360 | 3294 | 1256583 | 3e4f4c5861be1654842488e8c86aa399a87e3fcab7081d6a0996618d59079ba4
0022500594_s9300 | 640x360 | 360 | 3253 | 1232123 | 1c99afec0173af608ff40a43c1fe312fc52a361a95956186e3c45ad4d35eac86
0022500594_s9900 | 640x360 | 360 | 4180 | 1523917 | 55138d5da7a46343d0f4cb2d6230f86eea80c872cbcd0752ac70fda0087ca048
0022500621_s1500 | 640x360 | 360 | 1414 | 560577 | cf9d43779ebbf53b320d033961888cce929ef40f1bee790b380ed1014479307f
0022500621_s2700 | 640x360 | 360 | 4664 | 1822533 | 9526dcac5ffb5ffae8ee6b47088a67f144b6c6b3519a5f5850c5f76fc13232e8
0022500621_s300 | 640x360 | 360 | 3529 | 1397414 | 20a5f0ed7212a59ea3144f0883936951785afdd1c6f681459d24177a3a7e6261
0022500621_s3300 | 640x360 | 360 | 4616 | 1769733 | a00ce2e12635cabfa577573af0deedeb60d622a9558781f9158fe035138f6119
0022500621_s3900 | 640x360 | 360 | 5823 | 2378784 | a05f7abadd7b6a6203f9996d2799c8df68e23fe8112e7d7deb88d11e13628a3d
0022500621_s4500 | 640x360 | 360 | 1760 | 695111 | f249cc702b2d62b225cbb5bc71ef4b0872204cb05124e1ef66fb99d4d601ec83
0022500621_s5400 | 640x360 | 360 | 4361 | 1726719 | 3689509237bdc543cb7509fb8d281c70ee495ef8e8bd0280231518f51d9b7e0c
0022500621_s6600 | 640x360 | 360 | 4764 | 1832984 | 45bf1dbd7fb7b427e783038fc29dc9a6d79dfcb0d261c3c8956fc90ddb75af3d
0022500630_s1500 | 640x360 | 360 | 3735 | 1494100 | de23f236dc39c483794327027c170ce4312c94b64cd215e8a7fafda30adb244b
0022500630_s2100 | 640x360 | 360 | 4787 | 1914575 | fcb5e26f18313a097093f43de164eb73e632fce126dbfe697006709f0abcd42f
0022500630_s2700 | 640x360 | 360 | 1334 | 522965 | 7beb7c9adbc0833743bce846dec81c41b27076f5602e0b55b2b50a3a109fd3df
0022500630_s300 | 640x360 | 360 | 2027 | 804566 | bc03e8d18d3692eed5e63f6fe713d08bf57ddd624c9ef23b28322674abb0e35d
0022500630_s3300 | 640x360 | 360 | 4137 | 1655847 | 42b38d847e0502b1d4b89103596773384af72caaf9cbc1e5d4c376b62d6862b4
0022500630_s3900 | 640x360 | 360 | 5176 | 1928768 | fe51b50bba53844e24471bfe9949d48e6fc3209b092fcd652eb104a7646b91d8
0022500630_s4500 | 640x360 | 360 | 465 | 184970 | de92754fa10509b66569942a79068afdcbb89de5acb8ed799cc5c294719a467a
bos_mia_playoffs | 1280x720 | 720 | 1941 | 756625 | 4f20f4eb82852c61e5819511d00f49faf9657ef6f6f824e870c65984ca90f656
cavs_broadcast_2025 | 1280x720 | 720 | 1273 | 467563 | a1b7a930c3d5557d95eb42420a7808a8b11508a3fd5056ca8f617569f626c9e3
den_phx_2025 | 1280x720 | 720 | 2972 | 1178187 | 7ce5a0df4f41afbf65292a5c386eee2fb0cb8c82342cde81b2ea9d116429e5d1
g220c_jh3fnwMi7dM | 1920x1080 | 1080 | 4543 | 1671141 | d66250dda4d1257ce9b0249587f330bf4c2f8f864e40949bf3a2bbfecec9298e
gsw_lakers_2025 | 1280x720 | 720 | 717 | 273832 | be95e010c4d4b898d191d233be3f8777e3637d35166b0349b8135269da73e833
mem_nop_2025 | 1280x720 | 720 | 2192 | 862843 | d41a4143b518172377c5206791f813ff8f343d4fd08dec4da09bc227be26cd59
mia_bkn_2025 | 1280x720 | 720 | 37 | 14683 | b519936272dacd20916b7efcbf2892793dea178e8b3f9225de62ca5e53c15607
mil_chi_2025 | 1280x720 | 720 | 2642 | 1027533 | 6b7631ae23455610fa56b067d024d947e6b83478352fda7318639ea1a10528c0
ncaa_basketball_IB-_u4gW3ds_1080p | 1920x1080 | 1080 | 4143 | 1638857 | 86aebb3ea059c9f384e5c3bd885581257a4a0700922f1dd2af4623a5f0ffaa30
ncaa_basketball_WFl3V7ZY4ss | 1920x1080 | 1080 | 4345 | 1657788 | b5d3acd9eecd13dd786b5dba47093c3497f957dbbd4be49bf09c511653d35478
ncaa_basketball_mRkuGgeECak | 1920x1080 | 1080 | 5580 | 2200297 | ff7dd38010d1ce72a870e7b38ee4a790eecb48d691570bb533348e2df77e16c4
ncaa_basketball_sRtHQbywiTE | 1280x720 | 720 | 1653 | 640087 | 8710101b683bec92ad945a389dee63ae0780bb86557e6420a60bcdc2c1433a75
ncaa_basketball_tiUvyvWOCxo | 1280x720 | 720 | 3778 | 1469791 | ad484b9b2aa8bde96f6290490de7f513577b92cf7594b85c37e0387b4819342e
ncaa_basketball_zqBCKovJCQU | 1920x1080 | 1080 | 6623 | 2507670 | 3cb03652870964b608e4ef73be07e2556b0335b7b3b6a077475e490594dd93d3
okc_dal_2025 | 1280x720 | 720 | 1695 | 654915 | 3a348ac2e294290a36171308253238803e5593d6f0ecdb4dbccce9210605ab97
wnba_01_1080p | 1920x1080 | 1080 | 5588 | 2009017 | 1f2863ea84a8d48cbd9b64ab56852890f563ef64137f9d871532bd0dfaeabad6
wnba_02 | 1280x720 | 720 | 6287 | 2398304 | 5c7d174bda1503d5cf5b2f0af6085c8052692a9337d2bbde3cb1552c0fab8d43
wnba_04 | 1280x720 | 720 | 6189 | 2342293 | 593088d261da1e8251f0b5e054ea39327da031cb4604babc611e1b835cc355d5
wnba_05 | 1280x720 | 720 | 4736 | 1759850 | 07077b311c50b1c9482ded969f4e9f736cf05f0b0d130c288cbd5cd407f59413
wnba_06 | 1920x1080 | 1080 | 3606 | 1327735 | fa66b0027ca72ea250d9453affa4f61228680835c6089b01421a2daff3d92feb

## SEAL
SHA-256 of every LF-normalized byte above this line: 60dea2d35090f443c550064742863e797b229abb30f51f6290275985a55bd92c
