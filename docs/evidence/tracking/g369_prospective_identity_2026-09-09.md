VERDICT: PARTIAL -- 32 of 35 attempted fresh sections PINNED with 100 pct of the 17 required bindings, 0 collisions and byte-identical exports, but only 8 distinct source ids, under the sealed ">= 10 games" part of the bar; the ">= 30 sections" (32) and "3 competitions" (4) parts are met.
# G369 prospective source identity
Spec `docs/evidence/tracking/specs/G369_spec.md`; VERIFIER_CONTRACT A/B, Q1/Q3/Q6/Q8 self-checked. Seals recomputed here over the LF-normalised bytes above their seal lines, all predating every number below (Q1): prereg `g369_prospective_identity_2026-09-09/g369_prereg_2026-09-09.md` 2eafe59528e614b12fb76b1075dfe2a094e752eec51cfef142af3cd968416bb9; Amendment 1 (weight paths) 1017e4df5bf94ed64696389cb01fbf8ea5c653e08bd07fd512427c48d2217906; Amendment 2 (summary/hashes) 9fb3fa36292ba398ad3744c759a29010fd15d579f329d852e99bda3f7335227c.
WHERE: POD 213.192.2.120 in `/workspace/wt/a19`, lane tip eb375156, CPU only, zero GPU, OMP/MKL/OPENBLAS/OPENCV threads = 1. `data/` was opened read-only and every write is under this row's evidence dir; daemon, feeder, deploy tree, MAIN checkout, register and `data/registry/` untouched.

## PREMISE (sealed step 0) -- HOLDS
    g361_class_counts={"ALIGNED": 21, "EXACT": 19, "UNKNOWN": 844}
    g361_known_deploy_manifest_sha256=0/884
    fresh_sections_with_source=35
    PREMISE HOLDS
The spec's "on/after 2026-09-09T17:47Z" clause resolves to THIS pod's fresh rows: the previous pod was lost on 2026-09-09, and every fresh row in the snapshot finished between 2026-09-10T15:21:36Z and 16:03:18Z. Snapshot `ledger_snapshot.jsonl` copied 16:04:24Z, 910 rows (855 restored historical + 55 fresh), sha256 1e24b1aa8d89b381d76d13b05a739d201a98a271cd9761ca0233b2fc994ec876, 1064521 bytes.
MEASURED ROTATION, the boundary this row exists to prevent: of the 55 fresh sections only 35 (63.6 pct) still had source bytes on disk at PIN time and 20 (36.4 pct) were already gone inside a 42-minute window; read-only eligibility counts moved 38 at 15:46Z, 29 at 15:58Z, 35 at 16:04Z.

## PIN -- 32 / 35 attempted, binding_status DONE
All 17 required fields are present on all 32 pinned rows (`sources.csv`): source sha256 and byte size, ffprobe codec/fps/width/height/nb_frames/first_pts, crop rule, pixel transform, producer config, and the full ledger row. Sources are 1920x1080 h264 throughout; fps 25.0 / 29.97 / 30.0 / 59.94; nb_frames 3280-8020.
Competitions by the sealed game_id-prefix derivation: fiba 11, untagged 13, euroleague 6, N 2 = 4 distinct. Distinct source ids 8 (-x4DRmtYn4Q 5, 6FlZaoWSfFw 3, 7HQqWMaKxpA 6, 8ue528gaVyY 6, G8bPOW37Sp0 2, N-eE7ZwTuno 2, XCaGht2GmPg 5, fXLNra4sjjU 3) -- below the sealed 10, and the bar was NOT lowered.
3 ABSENT, each counted in `attempts.csv`: N-eE7ZwTuno_s4962, N-eE7ZwTuno_s90, fiba--x4DRmtYn4Q_s4218. Named cause, re-probed read-only after the run: `first_pts` UNKNOWN, because their leading packets carry negative presentation stamps past the 5.0 s probe window so no frame stamp is returned. Their bytes were on disk.
CODE IDENTITY (A11), hashed at PIN time and never quoted from a manifest -- routes, byte-identical in the lane worktree and in the exercised deploy tree `/workspace/deploy/nba-ai-system`, verified by sha256:
    src/pipeline/unified_pipeline.py   c4eae385bfeebd4e44c8161c791ef7ed4589697020f424d3dde7aec6816d9226
    src/tracking/ball_detect_track.py  cbc7cd9dfb7e18691f310b7594be046ac0d3184a279c43d8eb427210355bc9ea
    scripts/run_clip.py                ccd08d32c8c4cb8625ec5ef67535206f74f4df307a8e191ec01f5700fb40d8c2
Weights, present only in the deploy tree: yolov8n.pt f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36; yolov8n_ball.pt bc979654e281c5de6e0e992e1f9587b3a9faa2eec996ea41b1b03954ba0b6e52; osnet_x0_25_imagenet.pth f54941a66bad4ddd07f2907f498c810ce639ce7a1abeaf2a151f8da118d84693. manifest_sha256 2444276558d030b5191e1160000829b299fb82cc5306b1c24c0c2f5a477bb3b0. Crop provenance TOPCUT = 60 at `src/tracking/video_handler.py:11,61`; pixel transform (x, y) -> (x, y-60).

## ALIGNMENT, REPEATABILITY, COLLISIONS, EYE CHECK
The pinned bytes ARE the original source bytes carried with their own ledger row, so the join is EXACT BY CONSTRUCTION, not a re-fetch: `alignment.csv` records 996 landmarks over 32 sections, 31 or 32 per section (every section at or above the 30-landmark floor), with error_frames 0.0000 and within_bar 1 on all 996. No re-fetch join was used, so the <= 1 native frame re-fetch clause did not bind. Sign convention retained: error = re-fetched presentation stamp minus archived tick timestamp in native frames, positive means later.
REPEATABILITY: two exports on identical inputs, both 57eb12d26dc30417cd700ac64e378f78eb0cd513e77e587a588f2cbe6528c09f, byte_identical true, empty diff. COLLISIONS: 0 over 32 parsed (source_id, requested_start_s) pairs, and 0 unparseable ids.
EYE CHECK: 32 strips (the sealed even rule takes all at n <= 40, so no head slice), max 164170 bytes against the 204800 cap, middle landmark per section. Archived boxes are drawn in producer coordinates and so sit 60 px above their content on the uncropped frame: that offset is the recorded TOPCUT, not drift.

## DEVIATIONS (disclosed; no bar, threshold, sampling rule or required field changed)
1. Amendment 1's three relative weight paths were resolved under the exercised deploy tree, because the lane worktree carries no weight bytes at all; routes stayed on the sealed `--repo .` and are proven identical to the deploy tree above.
2. `--ledger` pointed at an immediate copy of the live append-only ledger rather than the live file, so premise, PIN and alignment read one coherent snapshot (the G361 precedent); that copy is committed with this row.
3. Three defects in the prepared module were fixed BEFORE any valid number existed: (a) the manifest emitted the crop key `rule` while the required field is `crop_rule`, which the test fixture masked and which failed every row's binding; (b) ffprobe 6.1.1 returns no frames for `-read_intervals "%+#1"`, so the window became `%+5.0`; (c) `alignment.csv` lacked the `refetched_pts` column the G361 strip renderer reads. Superseded runs: 16:01:32Z pinned 0 (premise read crash), 16:02:49Z pinned 0, 16:03:13Z pinned 8; the accepted run is 16:04:24Z. No run was chosen on its result -- each earlier one was broken code, not a measurement.
4. `git sparse-checkout add` brought the already-committed G361 evidence dir into the lane so the sealed premise command could read it.

## ARTIFACTS, TESTS, DIGESTS
    sources.csv           1b2b8ffdc1f4c1d48494ad3601bf26cc5db956b47e821b270ab21561920610b1
    attempts.csv          065eede23175e13af54c4857a87815aa03f32a76db3c2bfa605e12ece05e0000
    manifests.json        aae17849bd7e804511fc7257346fd7aa4192a407c3b3c1f2aea7533916ac3fde
    alignment.csv         18c03aaf983e0895c6ccac7c01da19889c7bcf71c3f320e4d91460fde86405e4
    summary.json = export_1 = export_2   57eb12d26dc30417cd700ac64e378f78eb0cd513e77e587a588f2cbe6528c09f
    g369_prospective_identity.py         bf4ea9269f4c3e941b03c7869c2a03b2f2c9cb76732f9617d9a05e44f3af594f
`SHA256SUMS.txt` lists all 44 evidence files (32 strips + 12). Tests, per-file only: test_g369_prospective_identity.py 5 passed, test_loc_rail_scope.py 1 passed; the module is 248 lines, under the 300 rail, so no allowlist entry was needed (A12).
Q6 automated scan: 0 findings.

Wall time: accepted measurement 2026-09-10T16:04:24Z to 16:07:25Z = 181 s; whole finisher session 15:30Z to 16:12Z, including premise scouting, diagnosis and the three superseded runs.

## NOT VERIFIED
- That 8 distinct source ids would reach the sealed 10; this row does NOT claim the games part of the bar, and no top-up was attempted after the count was seen.
- Any producer-attribution claim for the 855 restored historical rows: they keep G361's UNKNOWN class and `deploy_manifest_sha256` remains unknown for all 884 archived ids.
- That the 20 fresh sections whose bytes were already gone can be recovered. They cannot.
- Whether the 3 ABSENT sections would pin under a wider probe window; that was not retried in this row.
- Any pixel content of a strip beyond the recorded TOPCUT offset; no rating or detector claim is made here.
