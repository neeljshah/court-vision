VERDICT: PARTIAL -- the mixed-source census is complete over the whole ledger, but measured source height/fps covers only 130/1973 attempts (sources rotate) and complete evaluated schedules reach 29/30 and 26/30 per kind, short of the >=30-per-kind bar for a scored comparison.

G397 mixed-source producer census | lane a10 | prereg dd17e284b SEAL sha256 9c7544f867124d78ccceaaa66b91696976da4bab8015dd8dae69db5ee2baa402 | observational; no causal claim, no attribution to resolution or to frame rate.

PREMISE (step 0, measured, not assumed)
Daemon pid 3177187 `python3 -u scripts/platformkit/track_daemon.py --workers 8 --forever`, cwd /workspace/deploy/nba-ai-system, deploy HEAD 7eb25dc930f68491b63f5a236c57f49ee110e156, track_daemon.py sha256 9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac.
Cited ledger /workspace/deploy/nba-ai-system/data/tracking/track_daemon_ledger.jsonl RESOLVES to /workspace/data/tracking/track_daemon_ledger.jsonl. Census frozen 2026-09-11T12:33:58Z; snapshot 1973 records.
5c6d4c4c1ffd1827c15da21683e2650dd765e372ab7271823e5a874c524430a8  ledger_snapshot.jsonl
Producer argv, identical for all four clip sports (wnba, basketball, ncaa_basketball, nba): run_clip.py --video <src> --game-id <id> --no-show --frames 3000 --data-dir data/tracking/<id>. Decoder ffmpeg 6.1.1-3ubuntu5, cv2 4.14.0, python 3.12.3; native fps, no resampling. Route identity ORIGINAL for 1973/1973 attempts (one daemon, no rerun wrapper). No existing completed format-effect census exists, so the premise is NOT FALSIFIED. Nothing restarted, no flag, no registry write, no G395 dependency.
Policy boundary 2026-09-11T11:50:51Z (common_receipts/relaunch.log.txt "RESTARTED 11:50:51 fmt720 patch"): selector "$fmt/312/270" -> "$fmt/301/312/311/300/bv*[protocol*=m3u8][height>=720][height<=1080]"; probe bar `[ "${h:-0}" -lt 1080 ]` -> `-lt 720`. Feeder log SHIPPED height=1080 1113, height=720 50; DROP 71/1216 records with probe-reject 0 (liveness 40, too-small 28, duplicate 3).
PREMISE REFINED, not confirmed: the user-reported ~12:06Z admission time is wrong as a boundary. The earliest 720p60 attempt finished 2026-09-07T21:49:41Z. Pre-boundary 1944 attempts carry 14 720p60 sections; post-boundary 27 of 29 attempts are 720p60. The policy change SHIFTED the mixture; it did not create the kind.

CENSUS (whole current set; kind declared from the producer's own recorded source fields, never from an itag)
1973 attempts over 1599 unique sections. 1080p30 1072 attempts / 783 sections; 720p60 41 / 41; OTHER 860 / 775; UNKNOWN 0 / 0. OTHER decomposes as 1920x1080@60 421, @25 187, 1280x720@30 105, 640x360@30 70, 1920x1080@50 70, @24 6, @28 1.
Source bytes still present at the frozen census: 130/1973 attempts (141 objects probed across corpus and bridge). Measured-vs-declared agreement on those: height 130/130, fps 130/130, kind 130/130. Section output directories present 1663/1973.

DRAW (sealed rule floor(j*(N-1)/29+0.5), j=0..29, no replacement, no post-draw substitution)
30 sections per kind. 1080p30 drawn from a population of 783 (30 videos; basketball 11, ncaa_basketball 9, nba 5, wnba 5). 720p60 drawn from 41 (16 videos; ncaa_basketball 16, nba 14). Every attempt of every selected section is carried: 67 attempts over 60 sections (1080p30 26 sections x1, 1 x2, 3 x3 = 37; 720p60 30 x1 = 30). Source bytes retained for 22/60 (1080p30 2/30, 720p60 20/30); decoded-PTS census OK on 22/22 of those.

DENOMINATORS (median, with the per-kind n out of 30 in brackets; rows/decoded frame and rows/evaluated tick keep separate denominators)
1080p30: rows 3708.5 [30], raw rows 3945.5 [30], producer decoded_frames 3898 [27], source-decode PTS frames 3901 [2], evaluated ticks 1000 [29], suspended 0 [29], emitting 989 [29], zero-output evaluated ticks 5 [29], rows/decoded frame 1.058 [27], rows/evaluated tick 4.289 [29], held share 0.8452 [28], stride 3, cap-implied duration 100.0 s, elapsed source PTS 130.03 s [2], evaluated gap runs 2 [29], max gap 93 frames [29].
720p60: rows 1930.5 [30], raw rows 1930.5 [30], producer decoded_frames 7794 [26], source-decode PTS frames 7793 [20], evaluated ticks 500 [26], suspended 0 [26], emitting 485 [26], zero-output evaluated ticks 15 [26], rows/decoded frame 0.2278 [26], rows/evaluated tick 4.481 [26], held share 0.7775 [26], stride 6, cap-implied duration 50.05 s, elapsed source PTS 130.01 s [20], evaluated gap runs 2 [26], max gap 276 frames [26].
720p60 MINUS 1080p30 (medians, descriptive only): evaluated ticks -500, emitting ticks -504, rows -1778, raw rows -2015, rows/decoded frame -0.830, rows/evaluated tick +0.192, held share -0.0676, zero-output evaluated ticks +10, cap-implied duration -49.95 s, elapsed source PTS -0.020 s, max gap +183 frames, gap runs 0.
EQUAL-PTS AND EQUAL-CAP SUMMARIES KEPT APART: both kinds' sources span about 130 s of measured PTS (median difference -0.020 s), while the same 3000-frame cap spans 100.0 s at 30 fps and 50.05 s at 60 fps -- the tick shortfall is the cap meeting a doubled frame rate at an unchanged 130 s of video, not a producer-quality difference.
SOURCE-DECODE VERSUS PRODUCER-DECODE, named separately: on the 22 retained sources the ledger's decoded_frames tracks the SOURCE decode (3898 against 3901, and 7794 against 7793), not the producer-processed count under the cap. rows/decoded frame therefore carries a source-decode denominator and its cross-kind difference is a denominator artifact; rows per evaluated tick is the comparable rate, and it differs by only +0.192.
HELD PAIRS (byte-equal x/y for a shared player on consecutive evaluated ticks; no missing tick bridged): 1080p30 no-shared-player 1558/26513 adjacent evaluated pairs and no-output 907/26541 evaluated ticks; 720p60 868/12974 and 563/13000. Coordinates read from the producer's own x_position/y_position columns on 54/54 scored sections.

MISSINGNESS (retained, never collapsed to zero)
1080p30: schedule UNKNOWN 1/30 (ball_table_absent), held-share UNKNOWN 2/30 (that one plus one table_unreadable), attempts graded thin 3/30, ledger decoded_frames absent 3/30, source ABSENT 28/30. | 720p60: schedule UNKNOWN 4/30 (ball_table_absent), held-share UNKNOWN 4/30, attempts graded thin 4/30, source ABSENT 10/30.

PROVENANCE
Runtime field completeness across the whole census: source_height blank 0/1973, source_fps blank 0/1973; mismatch against a measured probe 0/130 checkable attempts. No runtime repair is warranted, so NO PROPOSED diff is filed. enriched_ledger.jsonl is an additive copy: it joins 67/67 selected attempts exactly once, 0 duplicate attempt ids, every original field byte-preserved, and adds only g397_join_status, g397_probe_width, g397_probe_height, g397_probe_fps. Join outcome 22/67 MATCH and 45/67 UNKNOWN (source pruned before the census).

EYE REVIEW
60 evenly ordered cards, 30 per kind: 22 carry a native interior frame with the producer's output points and an evaluated/suspended timeline strip, 38 are metadata-only because the source had rotated, 0 render errors. Every card prints measured against declared height and fps. Cards reviewed confirm measured 1280x720/59.94006 equals the declared 720/59.94006, and show that several 1080p30 sections have broken evaluated-tick timelines consistent with their sub-1000 tick counts.

REPRODUCTION
Two fresh-process recomputations of every canonical table are byte-identical (repeats.json identical=true, digests below). Q6 vocabulary scan over every committed text artifact: 0 non-opaque hits, no matched text printed. Per-file test: 13 passed on the pod and 13 passed on the PC.

NOT VERIFIED
Measured height/fps for 1843/1973 census attempts and 38/60 selected sections -- the quota guard prunes source bytes about 45 minutes after tracking, so those sources cannot be probed at any later census. Active ledger/schema wiring and the daemon remain read-only and unchanged; the enriched copy is never consumed by the runtime. Overlay point-to-player registration is not established here: the cards mark the producer's own bbox top-left in image pixels, and G380 identity remains 0/30. No causal resolution-only or fps-only attribution is made. Full tracking_data.csv bytes stay on pod scratch only, with per-section sha256, byte count and line count recorded in source_receipts.csv; committed snapshots/ carry ball_tracking.csv, evaluated_frame_count.json and harness_verdict.json.

ROW VERDICTS (spec ACCEPTANCE RULE)
Format/attempt accounting: PARTIAL. 30 unique sections each kind and all 1973 attempts / 1599 section identities accounted, but measured fps/height exists for only 130/1973 attempts and 22/60 selected sections.
Producer denominators and held share: NOT VALIDATED for the scored comparison. All 60 records retained, zero silent omission, rates reproduce exactly, but complete evaluated schedules are 29/30 (1080p30) and 26/30 (720p60), under the >=30-per-kind bar. The complete diagnostic is recorded regardless of direction.
Filterable ledger provenance: DONE. Exact missing/mismatch counts reported, the enriched copy joins every selected attempt once with no invented values; active wiring explicitly NOT VERIFIED.

DIGESTS (sha256, full 64 hex, path on the same line; SHA256SUMS covers every file in the directory except itself)
2ce40d3ac71130e88d6e225fbe949fc4589aa5be82a2d33fae4b789855fcf538  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/policy_receipt.json
d9271da5839011640410c692f662cedfcee4c068ec356bf6e460487f522bd397  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/census.csv
bbf68a23a4442093e1cdf4edadf9d6907a549e7f08596d11f93e99a22b384875  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/draw.csv
980ed60a8378336653ed1b159bcf7d758cab2503ae2ac6c9156380efc67bbbfc  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/source_probes.csv
7fdbe77d7429a74c88f2a98f25682f7e83939afcd972c9fb4fefef0e4e5bd28e  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/source_receipts.csv
9d2281ccaba9365b35803069ce85412894869d23899acc835fbd70ac4d9876b2  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/enriched_ledger.jsonl
0417951347524ff29e176101119d451df1370cd33bf2ecae308bf3d40870c0fe  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/per_section.csv
b599489368609c3bffcad7e611e314be386af6f511c508404884846fc0e57f74  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/evaluated_ticks.csv
7549f5feacd210fd874134b8e9ec5a70d74bcd326db5f58fc258390d64540efa  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/held_pairs.csv
2cac9f583856d832ab83ac5793839dfb314a1199ea87d437a485cd9297e54bb1  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/eye_index.csv
b6c31fc1a1f2341c37165bcee83357ec20b9fe11f4a3d267a4cfb32de68ac251  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/summary.json
bcb46af0ae79005fd671c9325f018ddfa9bb25ac7bc4806d4299e3fdf5cc6aa0  docs/evidence/tracking/g397_mixed_source_producer_census_2026-09-11/repeats.json
