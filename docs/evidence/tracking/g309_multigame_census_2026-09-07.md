# G309 -- multi-game tracking census (2026-09-07)
VERDICT: DESCRIPTIVE, COMPLETE. 15 games censused, 58,678 data rows, 8 NEW GAPs. No pass bar; this row scores nothing. Verified codex-sol: ACCEPT WITH CORRECTIONS (`G309_VERIFY_2026-09-07.md`); both corrections -- the mis-transcribed row total and the 8 omitted table columns -- are applied above. Prereg sealed BEFORE the pod run: `g309_prereg_2026-09-07.md`, SHA-256 `f79cb63ab17a93d1b219b2e020af68c764d670241189d40a61bf0f387eca50e0`.
PREMISE (binding, census 2026-09-07T21:51:17Z): 21 ledger lines, `passed != null` = **13** (bar >= 6), HOLDS; all 13 are `passed=false`, so this is a distribution of FAILING runs, written while it was read.
ACCEPTANCE: 15 census rows, 0 duplicates, 0 ledger game_ids with a CSV missing from the census; every metric recomputed from the CSVs; **13/13 match the ledger `rows` EXACTLY and `coverage_pct` at 4 dp -- zero disagreements.**
Table `g309_multigame_census_2026-09-07.csv` (15 rows, 32 cols). Pod read-only, no GPU (923 of 24,576 MiB used, 2 foreign compute apps), daemon pid 25560 untouched.

| metric | median | min | max | n |
|---|---|---|---|---|
| rows | 4,345 | 1 @ ncaa_tiUvyvWOCxo | 6,623 @ ncaa_zqBCKovJCQU | 15 |
| frames_emitted | 970 | 1 @ ncaa_tiUvyvWOCxo | 1,000 @ wnba_02 | 15 |
| coverage_attempted_frames_pct | 0.1037 | 0.0748 @ ncaa_sRtHQbywiTE | 0.1628 @ ncaa_IB-_u4gW3ds_1080p | 13 |
| coverage_decoded_pct | 0.0346 | 0.0136 @ okc_dal_2025 | 0.0543 @ ncaa_IB-_u4gW3ds_1080p | 13 |
| distinct_track_ids | 10 | 1 @ ncaa_tiUvyvWOCxo | 10 @ wnba_06 | 15 |
| median_track_len_rows | 449.0 | 1 @ ncaa_tiUvyvWOCxo | 627.5 @ wnba_02 | 15 |
| id_churn_per_detection | 0.002301 | 0.001510 @ ncaa_zqBCKovJCQU | 1.0 @ ncaa_tiUvyvWOCxo | 15 |
| ball_detected | 678 | 1 @ ncaa_tiUvyvWOCxo | 975 @ ncaa_WFl3V7ZY4ss | 15 |
| ball_valid_share | 0.803 | 0.302 @ ncaa_sRtHQbywiTE | 1.0 @ ncaa_tiUvyvWOCxo | 15 |
| p95_disp_norm | 0.7317 | 0.4348 @ ncaa_sRtHQbywiTE | 0.8594 @ wnba_05 | 13 |
| zero_step_share | 0.0867 | 0.0176 @ den_phx_2025 | 0.3799 @ ncaa_IB-_u4gW3ds_1080p | 14 |
| share_frames_ge6_boxes | 0.2747 | 0.0 @ gsw_lakers_2025 | 0.8330 @ wnba_04 | 15 |
| frames_attempted | 9,601 | 5,872 @ den_phx_2025 | 9,647 @ ncaa_zqBCKovJCQU | 13 |
| decoded_frames | 28,815 | 17,983 @ ncaa_IB-_u4gW3ds_1080p | 35,516 @ okc_dal_2025 | 13 |
| stride | 3 | 3 @ g220c_jh3fnwMi7dM | 6 @ okc_dal_2025 | 13 |
| ball_rows | 1,000 | 1 @ ncaa_tiUvyvWOCxo | 1,000 @ wnba_06 | 15 |
| ball_inferred | 1 | 0 @ gsw_lakers_2025 | 311 @ wnba_05 | 15 |
| ball_none | 191 | 0 @ ncaa_tiUvyvWOCxo | 698 @ ncaa_sRtHQbywiTE | 15 |
| n_steps | 4,335 | 0 @ ncaa_tiUvyvWOCxo | 6,613 @ ncaa_zqBCKovJCQU | 15 |
| source_height | 1,080 | 720 @ den_phx_2025 | 1,080 @ wnba_06 | 13 |

DENOMINATORS (CORRECTED by the verifier: the total was mis-transcribed as 52,678): `rows` = data rows in `tracking_data.csv`, **58,678 over 15 games**; `frames_emitted` = distinct `frame`; `frames_attempted` = ledger/harness `evaluated_frames`, else ceil(decoded/stride); `coverage_attempted_frames_pct` = frames_emitted / frames_attempted; `coverage_decoded_pct` = frames_emitted / decoded_frames; `id_churn` = distinct ids / rows; every `ball_*` over `ball_rows`; `p95_disp_norm` and `zero_step_share` over `n_steps` (0-6,613 per game); `share_frames_ge6_boxes` over `frames_emitted`.
CONVENTIONS: footpoint = bbox bottom-centre ((bbox_x1+bbox_x2)/2, bbox_y2); a step is consecutive same-`player_id` observations ordered by frame with no interpolation across a gap; p95 is nearest-rank; displacement is Euclidean image px divided by `source_height`; zero-step means exactly 0.0.

HEADLINE -- THE LEDGER'S COVERAGE DENOMINATOR IS NOT THE FRAMES THE ROUTE ATTEMPTED. All 15 games carry `max_frames = 3000` in `evaluated_frame_count.json` (measured), but `evaluated_frames` = ceil(decoded/stride) ignores that cap. Against the frames the route actually attempted -- min(ceil(decoded/stride), ceil(3000/stride)) -- coverage is **median 0.9790, min 0.7210 @ ncaa_sRtHQbywiTE, max 1.0000, n = 13**, not the ledger's 0.0346. This is post-hoc arithmetic on committed columns, labelled as such: it moves no bar and is NOT in the sealed metric list.

OUTLIERS. `ncaa_tiUvyvWOCxo` (1 row, 1 id) and `gsw_lakers_2025` (717 rows, no `source_height`, no `coordinate_space`, no ledger row) were in flight at census time -- partial writes, not results. `ncaa_sRtHQbywiTE` is the worst completed game on four columns at once (coverage 0.0748, ball_valid_share 0.302, p95 0.4348, and 0.0388 of frames with >= 6 boxes). Densest: `wnba_04` 0.8330 and `ncaa_zqBCKovJCQU` 0.8010 of frames with >= 6 boxes.

NEW GAP: all 13 completed games report EXACTLY 10 distinct `player_id` values -- a uniform id count across five sports and two resolutions is a cap or a re-use policy, not a measurement. No cause is asserted here.
NEW GAP: `ball_valid_share` equals `ball_detected / ball_rows` in all 15 games, so the 0-311 `ball_inferred` rows per game carry NO `ball_x2d`/`ball_y2d` -- the inferred flag is set without a coordinate.
NEW GAP: median p95 per-track step is 0.73 of frame height (min 0.43, max 0.86, n = 13); a 95th-percentile stride of most of the frame between consecutive same-id observations is an association signal, not a motion one. Image space only.
NEW GAP: `zero_step_share` above 2x the cross-game median (0.0867) in 6 games -- ncaa_IB-_u4gW3ds_1080p 0.3799, wnba_06 0.3776, ncaa_WFl3V7ZY4ss 0.3474, okc_dal_2025 0.3418, g220c 0.3391, ncaa_sRtHQbywiTE 0.2581.
NEW GAP: `id_churn_per_detection` above 2x the cross-game median in gsw_lakers_2025 0.013947, ncaa_sRtHQbywiTE 0.006049, okc_dal_2025 0.005900, ncaa_tiUvyvWOCxo 1.0.
NEW GAP: 2 games hold a `tracking_data.csv` with NO ledger row -- the daemon writes the table before the ledger line, so any reader keyed on the ledger misses in-flight games.
NEW GAP: the ledger `coverage_pct` denominator ignores `max_frames = 3000` (see headline), so every coverage figure carried in the register understates the attempted share by roughly 10x-30x.
NEW GAP: `harness_coverage_pct = 0.0` on EVERY adjudicated ledger row (15/15 at re-check, 13 at census time) while `coverage_pct` is non-zero -- the two coverages disagree by construction and only one is censused.

NOT VERIFIED: no ground truth of any kind -- not one metric here is recall, precision, accuracy or registration, and a game can score well on every column and still be tracking the wrong things.
Image space only (`coordinate_space = image_px`; blank on the 2 in-flight games): no court, foot, metre or registration claim is made, implied, or may be read into these numbers.
The 15 games are whatever the feeder queued, not a sample of anything; nothing here generalises past these files, and all 13 adjudicated games are `passed=false`.
The 10-id uniformity, the empty inferred-ball coordinates and the `harness_coverage_pct = 0.0` cause were NOT traced to source; the `max_frames` correction was NOT re-run through the harness.
Unread: `source_fps`, `source_duration`, `features.csv`, `events_log.csv`, `resolver_debug.json`. No per-game wall time was measured. Nothing was re-decoded from video. The pod tree was mutating during the census.
