SCREENING ROW, BAR NOT MET, CLOSED AT LIMIT (source availability): premise HOLDS (route-observed detector input 640 < 1920); 1 of 3 games completed BOTH arms post-prereg inside 3,600 s (wnba_01_1080p: ARM P 1,668.4 s, ARM N 2,193.4 s; emitted-frame denominators 458 and 469 frames-with-rows, the predeclared evaluated-frames denominator being null by the route's own report); the other 2 games ran 0 post-prereg arms because the pod's track_daemon deleted every 1920x1080 source mid-row; proxies MIXED; nothing adopted, nothing proposed, no quality claim.

# G310 -- daemon route, native-input arm (SCREENING)
Spec `docs/evidence/tracking/specs/G310_spec.md`. Prereg `docs/evidence/tracking/g310_prereg_2026-09-07.md`, seal `528211D145F773FEB428647C15157567C56B9DB3AD37033315F6E6D20A70DCD5`, verified to reproduce over the LF-normalised bytes above the seal line, committed ALONE at `0e901359e` BEFORE any scored output below.

PREMISE (step 0, measured post-prereg, NOT inferred from the source constant): the ARM P run recorded `imgsz_at_construction [640]` and `imgsz_observed_at_call_site [640]` from a passive recorder wrapped around the detector's own YOLO callable. 640 < 1920, so the before-condition HOLDS. (`player_detection.py:82` sets `_infer_imgsz = 640`, read back at `unified_pipeline.py:917`/`:1021` via `getattr`; the value above is the OBSERVED one.)

SOURCES (A9; ffprobe on the pod; 3 named of 22 probed, 15 rejected as not 1920x1080), all under `/workspace/nba-ai-system/data/footage_corpus/`:
| game_id | file | bytes | WxH | fps | frames | dur s |
|---|---|---|---|---|---|---|
| wnba_01_1080p | wnba__wnba_01_1080p.mp4 | 308078882 | 1920x1080 | 30/1 | 18060 | 600.067 |
| ncaa_basketball_IB-_u4gW3ds_1080p | ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4 | 328260234 | 1920x1080 | 30000/1001 | 18115 | 600.099 |
| ncaa_basketball_mRkuGgeECak | ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4 | 487249282 | 1920x1080 | 30000/1001 | 28905 | 964.5245 |

ARMS, ONE DIFFERENCE: ARM P is the production route unmodified, no attribute set. ARM N is the same route with the detector INSTANCE attribute `_infer_imgsz` set to 1920 after construction -- a runtime instance attribute, never a source edit; nothing under `src/`, `domains/`, `api/`, `kernel/` was edited and no production default on disk moved. Same weights, conf, classes, start frame and frame cap (1500); the arms' recorded argv differ only in `--data-dir`. Both carry the same passive recorder, forwarding every argument unchanged. No third difference. Observed imgsz: ARM P 640, ARM N 1920. FOOTPOINT convention: image-space bbox BOTTOM-CENTRE ((x1+x2)/2, y2); p95 is nearest-rank over per-track consecutive footpoint steps, normalised by the probed source_height 1080.

PER-GAME PROXY TABLE (post-prereg; n = 2 of 7 predeclared route runs completed):
| game | arm | status | wall s | person rows | frames w/rows (den.) | ids | median track len | ball det/total | p95 norm step | step pairs (den.) |
|---|---|---|---|---|---|---|---|---|---|---|
| wnba_01_1080p | P (640) | COMPLETE | 1668.4 | 1433 | 458 | 10 | 158.0 | 414/500 | 0.3315 | 1423 |
| wnba_01_1080p | N (1920) | COMPLETE | 2193.4 | 2940 | 469 | 10 | 267.5 | 173/500 | 0.9010 | 2930 |
| ncaa_basketball_IB-_u4gW3ds_1080p | P, N | NOT RUN (source deleted) | -- | -- | -- | -- | -- | -- | -- | -- |
| ncaa_basketball_mRkuGgeECak | P, N | NOT RUN (source deleted) | -- | -- | -- | -- | -- | -- | -- | -- |

`person_rows_per_evaluated_frame` is EMPTY BY CONSTRUCTION: the route's own `evaluated_frame_count.json` reports `"evaluated_frames": null`, `"reason": "max_frames_is_detector_dependent_in_this_route"`. No denominator was substituted; `frames_with_rows` is reported separately and is NOT that denominator.

SIGN CONVENTION: higher person-rows-per-frame, higher distinct ids, higher median track length and higher detected ball rows would each be consistent with more detection; a LOWER p95 normalised step would be consistent with steadier association. CONSISTENCY IS NOT EVIDENCE. On the one game that ran, ARM N is higher on person rows (2940 vs 1433) and median track length (267.5 vs 158.0), EQUAL on ids (10 vs 10, the route's roster-slot count), LOWER on detected ball rows (173 vs 414), and HIGHER on p95 step (0.9010 vs 0.3315). The directions DISAGREE; this row cannot say which arm is better.

SCREENING LABEL: this is a SCREENING ROW. There is NO ground truth here, so every number is a proxy and none is a quality measure. More rows per frame can mean more players found OR more false boxes, and this row cannot tell those apart; G303, which scores recall against the G296 frames, is the row that can. No claim of recall, precision, accuracy, registration or a harness pass is made; the ledger `passed` field was not touched. Eye check: NONE -- no labels, no blind judging, only arithmetic over route output.

WHY CLOSED AT LIMIT: one post-prereg pass completed both wnba arms; then `track_daemon` restarted (to `--workers 8`) and swept the lane job at frame 369 of IB- ARM P. The relaunch stopped at `G310: no eligible 1920x1080 source for wnba_01_1080p`. Measured cause: the restarted daemon had deleted every 1920x1080 source -- the corpus then held 118 sources, 63 at 640x360 and 55 at 1280x720, ZERO at 1920x1080, and a pod-wide `find` located no copy of the three. 720p is INELIGIBLE per the spec, so NO substitute was used and the budget was NOT extended. Unblock path for a future row: the workstation's `data/videos/bridge/` still holds `ncaa_basketball_IB-_u4gW3ds.mp4` and `wnba_01.f137.mp4`, which would need re-upload and are not byte-identical to the deleted corpus files.

GATES (verbatim; operational, not evidentiary): `--query-gpu=memory.used,memory.total` -> `3939 MiB, 24576 MiB` (free 20637 >= 8192, PASSED; each arm's own lease also passed). `--query-compute-apps` -> `2048580, 482 MiB / 2051123, 482 MiB / 2051102, 462 MiB / 2055297, 476 MiB / 2056583, 482 MiB` (daemon workers; never stopped, signalled or interrupted). `du -sm /workspace` returned EMPTY under its 60 s timeout -> UNKNOWN, never 0 and never a stop; the `dd conv=fsync` 1 MiB probe succeeded (11.0 MB/s), so the row did not stop on disk. Bytes added: 2,316 MB of `pod_run` job roots plus 26 MB of pilot output under `/workspace/wt/a1`; bytes freed: 0 (this row deleted nothing). Writes stayed in `/workspace/wt/a1`; the deployed tree, `data/tracking/`, the ledger and `yolov8n.pt` were untouched. `resources/` and the panos were SHIPPED into the job root (without them the route aborts in `_build_court` on a missing `2d_map.png`), so both arms saw the same warm cache.

NOT VERIFIED:
- No ground truth; every number is a proxy. One game is not a sample; 2 of 7 predeclared runs completed. The spec's bar (3/3 games, both arms, inside budget) is NOT MET.
- The predeclared evaluated-frames denominator does not exist in this route. Nothing was substituted.
- A PILOT pass of all 7 runs ran BEFORE the prereg commit; it is archived at `docs/evidence/tracking/g310_pilot_pre_prereg/` and is NOT quoted as this row's result.
- The route is unstable across identical runs: the pilot's two ARM P runs on wnba_01_1080p at identical settings gave 2116 and 2185 person rows; post-prereg ARM P gave 1433. Every arm here is ONE DRAW. The predeclared ARM P repeat did NOT run post-prereg (its source was deleted).
- Timing shared the card with a live daemon and other lanes; contention varied ~5x within this row, so wall seconds MAY NOT be quoted as a throughput figure.
- All three per-video panorama caches on the pod are BYTE-IDENTICAL (md5 408aca74842f9cd4a1be094d0610230d): the panorama was not video-specific. It is shared by both arms, so not an arm difference, but nothing here speaks to homography quality.
- G298's attribution rests on one shot in frames 19599-23399, a span G278 measured friendlier than its own clip (0.836 vs 0.656, p = 0.0078); nothing here may be quoted clip-wide or programme-wide.
- Nothing adopted or proposed; no production default, threshold or filter moved. Calibration language only -- this row measures no boundary in price terms and makes no such claim.

TIME SPENT: ~9 h wall from lane pickup to memo; ~7 h pod compute (one pilot pass of 7 runs, one swept post-prereg pass, one aborted relaunch) and ~2 h local analysis, harness repair and writing.

ARTIFACT SHA-256: prereg 764e0a374c13a2471f1395029970677f2e40e2e9159700f5fcc38d8aa0f1d069 | harness bbc96f3f2257c22dd0351ab9a5f49567086f00b5255f800a3a46cb7b1500828b | test f1befe2d34e56c616ceb63919e3665585db371f7673a45ad9a94238c2df5fa58 | postprereg CSV 5fb2d480be1ca5e77ede804578907f76a7de2c99971b4192686635688416e388 | postprereg JSON 2d37834dcfb08370b4714bf558e24c4ff2a7f2ec0842fd5b346e1437ff03f0f0 | pilot CSV 6bbda50a1a43c6e092ee930d25624892edf56b96c5d2ebc40d7cf89e2f8a885b | pilot JSON 0ba88940fed9299d15ebd6fc66331a2e8f5e5b2bfe26c2db7aa7ca4040db4d15

TEST: `python -m pytest scripts/platformkit/tracking/test_g310_native_input_arm.py -q -p no:cacheprovider` -> 5 passed. It pins the proxy computation on a hand-computed synthetic construct (rows per frame, distinct ids, median track length, nearest-rank p95 normalised displacement) and the bottom-centre footpoint convention.
