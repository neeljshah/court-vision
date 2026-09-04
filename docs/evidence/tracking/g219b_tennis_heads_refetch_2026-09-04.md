# G219b tennis heads refetch

## Verdict: ACCEPT (measurement and proposals only)

This memo follows [the tracking verifier contract](VERIFIER_CONTRACT.md), including the section-B self-check. It completes only the two G219 heads lost to the basename collision. No production code changed, `src/` was read only, no route was run, and no file was copied to the pod.

## Acquisition, premise check, and identity

S1 machine: analysis ran locally in `C:\Users\neelj\nba-track-a8`; the pod was used only to read the two CSVs mandated by the spec.

| G207 row | Full pod source path | Tracked local evidence path | Bytes | SHA-256 | Eligible denominator | G207 rows | Local rows |
|---|---|---|---:|---|---|---:|---:|
| `tennis_01` | `/workspace/nba-ai-system/data/tracking/tennis_01/tracking_data.csv` | `docs/evidence/tracking/g219b_inputs/tennis_01_tracking_data.csv` | 2,832,341 | `4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929` | all 19,437 emitted rows | 19,437 | 19,437 |
| `tennis_02` | `/workspace/nba-ai-system/data/tracking/tennis_02/tracking_data.csv` | `docs/evidence/tracking/g219b_inputs/tennis_02_tracking_data.csv` | 255,168 | `a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd` | all 1,637 emitted rows | 1,637 | 1,637 |

The full local measurement paths are `C:\Users\neelj\nba-track-a8\docs\evidence\tracking\g219b_inputs\tennis_01_tracking_data.csv` and `C:\Users\neelj\nba-track-a8\docs\evidence\tracking\g219b_inputs\tennis_02_tracking_data.csv`. They are tabular CSV inputs, so raster resolution is not applicable. Their metadata declares `coordinate_space=court_feet`, source FPS 59.94005994005994, and source height 1080 pixels; source width is not recorded. `tennis_01` declares a 4,592.1876-second source and `tennis_02` an 8,101.6936-second source. No video was opened, probed, decoded, or rendered.

Copy verification was explicit. The first completed copy used the distinct `tennis_01_tracking_data.csv` destination, then was verified to exist at 2,832,341 bytes with the hash above. The second completed copy used the distinct `tennis_02_tracking_data.csv` destination; immediately afterward the first file still existed, its hash was unchanged, and the byte sizes differed (2,832,341 versus 255,168). Thus no basename overwrite occurred. An initial local-only use of the nonexistent SSH alias `pod` failed during name resolution before a network connection or transfer; the only completed pod connections were the two read-only CSV downloads above.

G207's denominator ledger is `docs/evidence/tracking/g207_pod_ledger_rescore_rows_2026-09-03.csv`, 10,647 bytes, SHA-256 `d488e40e268a2d4d32a16719228f6e94308fe4ba40201346d91f61f558701511`. Its `rows` field names 19,437 and 1,637 and its `first_failure_head` fields name `jump_max 108.39 > 8.00` and `median_track_len 1.00 < 3.00`, respectively. The companion census is `docs/evidence/tracking/g207_pod_ledger_rescore_census_2026-09-03.md`, 14,412 bytes, SHA-256 `fc208f6c0d9aa0178023185d1c79fc80692b314bb9a5b8f3d715b0fbb0609039`.

G207 recorded pod harness SHA-256 `59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d`. The local definition source is `scripts/platformkit/tracking_harness.py`, 21,851 bytes, SHA-256 `c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95`. They differ. The local values below therefore reproduce the current harness definitions on the retained tables, not G207's pod score.

The local static-code sources opened were `domains/tennis/tracking/adapter.py` (16,970 bytes, SHA-256 `f7687c5646dfa3f9a8206d1559238941020b6f5828d28c160e11426699a2bac9`), `domains/tennis/tracking/identity.py` (1,356 bytes, SHA-256 `fdc97df1e514908e0d078f14b50718312e9bae5c6ec26b338a346dfbd6ff5fb5`), `scripts/platformkit/calibration/keypoint_calib.py` (8,994 bytes, SHA-256 `fcb4d08d5a5c2b7052af23c7edf2b654e6ca29c4f5e9922fff6622d615df4132`), and `scripts/platformkit/coordinate_provenance.py` (4,373 bytes, SHA-256 `f5ff5fcdf5e41cd90420c987eb4dd0bbaea0fdc013542b48f5a117e665ee0bff`). All are source text, so raster resolution is not applicable. No pod route-file hash is known for these non-deterministic historical tables.

The harness calculates player median track length from player rows grouped by `track_id` at `scripts/platformkit/tracking_harness.py:322-329`; it sorts those same player rows, uses the unique positive modal per-track frame stride, and computes `jump_max` within that stride at `:340-346` (with the modal-stride definition at `:195-201`).

## `tennis_02`: median_track_len 1.00 below 3.00

The retained table has 1,637 emitted rows: 1,504 player rows and 133 ball rows. It contains 414 player track IDs and the current local harness definition gives a median track length of 1.00, equal to G207's displayed 1.00. This agreement is reported beside, not as a reproduction of, G207 because the harness hashes differ.

| Player-track length bucket | Tracks | Player rows in bucket |
|---|---:|---:|
| 1 frame | 378 | 378 |
| 2 frames | 8 | 16 |
| 3-5 frames | 4 | 14 |
| 6+ frames | 24 | 1,096 |
| Total | 414 | 1,504 |

The requested fraction is 378 one-frame player rows divided by all 1,637 emitted rows: **23.091020 percent**. It is 25.132979 percent if the denominator is restricted to player rows; that is supplied only to make the named all-emitted-row denominator auditable.

The rows identify 207 contiguous two-ID epochs: IDs 1-2 through 413-414. Of those, 189 epochs emit exactly one frame for each player. Every post-first epoch begins at least 24 source frames after the preceding epoch's final player emission. The table's unique modal player stride is 6 frames, so every such boundary exceeds the current route's `3 * stride` reset condition (24 > 18).

The current tennis path explains the fragmentation mechanism. Before attempting association, it ends the current epoch when `source_frame - last_player_emission > 3 * stride` (`domains/tennis/tracking/adapter.py:227-230`), and `end_epoch` clears the centroids and advances the two-ID base (`domains/tennis/tracking/identity.py:7-9`). The next complete pair therefore receives new IDs. It is not an embedding, appearance-threshold, age, or hit-count rejection: the identity function always assigns its two supplied candidates, choosing direct versus crossed centroid continuity (`identity.py:12-25`).

The preceding no-emission interval can arise because the path does not call player association without a usable homography (`adapter.py:225-230`), and, with a homography, `detect_players` returns no pair unless it has one selected candidate in each projected court half (`adapter.py:181-197`). It also resets on a detected cut (`adapter.py:220-221`, `:140-145`). The retained CSV has no frame manifest, detector candidates, or cut labels, so it cannot distinguish which of those three upstream causes made each interval. What is established is the named temporal-reset condition that turns those intervals into one-frame identity epochs.

Judgement: **TENNIS-SPECIFIC for the observed failure.** The two-player, two-half selection and epoch namespace are in `domains/tennis/tracking/adapter.py` and `domains/tennis/tracking/identity.py`. `TemporalCalibrator` is shared machinery used by both tennis and soccer (`adapter.py:9`, `domains/soccer/tracking/adapter.py:13,43`), so a general calibration failure would have to be carried there; this table does not show that shared component is faulty. The shared harness code only measures the failure and is not its producer.

## `tennis_01`: jump_max 108.39 above 8.00

The retained table has 19,437 emitted rows: 16,766 player rows and 2,671 ball rows. Its unique modal player stride is 6 frames. Under the local definition, the maximum modal-stride movement is 108.390727 feet. G207 displayed 108.39, so the local value is 0.000727 above that rounded display; this is not reconciled away because the local and pod harness hashes differ.

The offending pair is track 159:

| Track | Previous frame | Previous court-feet coordinate | Next frame | Next court-feet coordinate | Frame gap | Distance |
|---:|---:|---|---:|---|---:|---:|
| 159 | 39,504 | (-7.592252, 32.259804) | 39,510 | (100.240433, 43.244423) | 6 | 108.390727 feet |

At the declared 59.94005994005994 FPS, the six-frame gap is about 0.1001 seconds. It is the normal modal stride, not a 40-frame absence and reacquisition. The adapter's court plane is explicitly 78 by 36 feet (`domains/tennis/tracking/adapter.py:21,124-126`), so the prior x is below 0 and the next x and y exceed 78 and 36. The table, rather than `tennis_ref01`, declares `court_feet` and source height 1080; no source width is recorded.

Classification: **a consecutive-frame apparent identity switch or false-player selection, not a large-frame-gap event**. The other player remains on track 160 across these same frames and moves only 0.404160 feet, while track 159 changes 108.390727 feet. Both rows carry `calibration_provenance=solved`; the following track-159 rows remain near (96.438072, 41.689747), (99.452263, 42.921032), and (99.492622, 42.918324), rather than returning to the prior left-side location. That same-frame control and the fixed coordinate declaration make a global coordinate-unit or scale change less consistent with the incident. Source images and the historical route manifest were not opened, so the physical person behind the false selection is NOT VERIFIED.

The static path can admit that failure: it projects every detector foot, splits on projected x = 39, chooses one candidate per half, and explicitly does not filter projected coordinates to the harness bounds (`domains/tennis/tracking/adapter.py:181-197`, especially `:188-195`). It then uses direct-versus-crossed centroid continuity to attach the two selected candidates (`domains/tennis/tracking/identity.py:17-25`). Thus an off-court or wrong-half candidate can remain associated to a tennis identity at the normal stride.

Judgement: **TENNIS-SPECIFIC for the observed failure.** The candidate choice, half split, and two-player identity association above are tennis adapter code. A truly general coordinate defect would instead have to be carried by shared `scripts/platformkit/calibration/keypoint_calib.py` or the shared coordinate provenance writer `scripts/platformkit/coordinate_provenance.py`; no evidence here identifies either as defective. The shared harness calculation at `tracking_harness.py:340-346` detects this jump but cannot create it.

## Human-gated proposals only

1. A human owner could preserve a per-frame manifest alongside every emitted tennis CSV, naming `homography unavailable`, `no_complete_player_pair`, and `cut` causes before aggregation. Expected effect: distinguish the upstream reason for the 189 one-frame epochs. Regression risk: a manifest/schema addition can affect downstream readers and storage, so it requires a reader survey and a new gated validation row.
2. A human owner could evaluate an explicit out-of-court candidate quarantine before tennis half selection, retaining rejected-candidate evidence rather than silently choosing it. Expected effect: prevent the observed track-159 style false selection from entering an identity epoch. Regression risk: imperfect homography can map a real player outside the nominal court and reduce coverage. This requires walk-forward, multi-corpus, truncation-invariance, permutation, and ablation gates before any production change.

Nothing was applied. No threshold, bar, verdict, coordinate contract, or `src/` file moved.

## Limitations and NOT VERIFIED

- These are two clips of one sport from a non-deterministic route. They diagnose these retained tables, not a stable population; a rerun need not reproduce them row for row.
- Tennis has two to four players while basketball has ten. Neither finding transfers by default.
- The retained CSV lacks source video, source width, frame-manifest labels, candidate boxes, and a historical route-file hash. The exact upstream cause of each long no-emission interval and the physical identity behind track 159 are NOT VERIFIED.
- The pod harness hash differs from the local harness hash. The local values are definition-faithful recomputations on the retained tables, not a claim that G207's pod score was reproduced.
- `tennis_ref01` was intentionally not reopened or re-diagnosed; G219 already established that tennis-path-specific duplicate finding.

## Tests and verifier self-check

No harness or production file was added or modified, so the spec's conditional per-file-test requirement did not apply. No full test suite was run. No allowlisted file grew, so contract A12 did not require a LOC-rail update.

Section B self-check: B1 uses every emitted row for each named denominator and names the player-only supplementary denominator; B2-B4 change no schema, gate, or claim logic; B5 made two inbound reads and no pod deployment; B6 moves no module; B7 has no render or sampled decision set; B8 fits no model; B9 uses actual table rows rather than recycled IDs; B10 changes no bar (8.00 and 3.00 remain quoted from G207). Q rules do not apply because G219b is not an S-row and makes no scored comparison. Every relative evidence path named above exists in this worktree at commit time.
