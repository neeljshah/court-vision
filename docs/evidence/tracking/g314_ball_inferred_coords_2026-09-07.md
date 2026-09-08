VERDICT: PREMISE FALSE (contract Q8). `ball_inferred` rows DO carry a coordinate -- 310 of 311 in `wnba_05` and 267 of 273 in `wnba_02` hold a finite `ball_x2d` AND `ball_y2d`. The spec's step 0 stops the row on a nonzero count: no fix, no adoption, no threshold moved, no PROPOSED diff against `src/`.

# G314 -- do inferred ball rows carry a coordinate? (2026-09-07, LOCAL)

PREREG sealed and committed ALONE before any count existed (Q1): `g314_prereg_2026-09-07.md`, seal `47bc38d36a4c5612fc6c5473983893a58fdcd04a6cbe08c6decb564efa1ee81e`, commit `4c91a1307`.
INPUTS (A9), fetched read-only by `scp` from `/workspace/nba-ai-system/data/tracking/<game>/`, byte sizes asserted against the pod listing before counting -- raw SHA-256:
`wnba_05/ball_tracking.csv` 24,473 B `805c6479e6988dbb0958d8b15c2b2f35f8a1ee4a51a626be5361b1d24f60ca1d` | `wnba_02/ball_tracking.csv` 23,410 B `79537a95f1d8ca4f0f609b27e07c19aa1f1d66e6bdfb3926558e942d273b8510`
`wnba_05/tracking_data.csv` 1,759,850 B `07077b311c50b1c9482ded969f4e9f736cf05f0b0d130c288cbd5cd407f59413` | `wnba_02/tracking_data.csv` 2,398,304 B `5c7d174bda1503d5cf5b2f0af6085c8052692a9337d2bbde3cb1552c0fab8d43`
Nothing on the pod was written and `track_daemon` pid 25560 was never signalled. No GPU, no GPU lease, no frame decoded.

PREMISE (every row of each file, head to tail, no sampling, no exclusion):
| game | ball_rows | ball_detected | ball_inferred | inferred WITH a finite pair | WITHOUT |
|---|---|---|---|---|---|
| wnba_05 | 1,000 | 907 | 311 | **310** | 1 |
| wnba_02 | 1,000 | 803 | 273 | **267** | 6 |

The spec asserts that fifth column is 0 on both games. It is 310 and 267. PREMISE FALSE.

WHY G309's IDENTITY HELD ANYWAY. `ball_detected` and `ball_inferred` are NOT disjoint buckets.
Cross-tab, `wnba_05`: both=310, detected-only=597, inferred-only=1, neither=92; `wnba_02`:
267 / 536 / 6 / 191. So `ball_detected + ball_inferred + ball_none` EXCEEDS `ball_rows` in both
games. `ball_valid_share == ball_detected / ball_rows` is an identity about the WRITER, not about
inference: `src/pipeline/unified_pipeline.py:1985-1987` writes `ball_x2d`/`ball_y2d` from
`ball_pos` and sets `detected = int(ball_pos is not None)` in the same dict literal, so a row
carries a coordinate exactly when it is detected, whatever the flag says. The flag is written
independently at `unified_pipeline.py:1991` from `self.ball_det.ball_inferred`, which
`src/tracking/ball_detect_track.py:796` sets True only after the dribble predictor has already
produced a bbox. Read-only trace; nothing edited.

ALSO MEASURED. `tracking_data.csv` (73 columns) has NO `ball_inferred` column, so the spec's
instruction to read the premise from that file could not have answered it; the G309 census read
the ball columns from `ball_tracking.csv` (`g309_multigame_census.py:181`), which is the file
measured here and the one the acceptance rule binds. For completeness, 4,668 of 4,736 `wnba_05`
and 5,122 of 6,287 `wnba_02` `tracking_data.csv` rows carry a finite pair.

NEW GAP (cause NOT verified): 1 row in `wnba_05` and 6 in `wnba_02` -- 7 of 2,000 -- carry
`ball_inferred = 1` with `detected = 0` and no coordinate. Candidate sites READ but not measured:
the negative-projection reject at `src/tracking/ball_detect_track.py:919` and the 1,200 px
possessor-drift reject at `:951`. No claim which, or how often.

CONSTRUCT: `tests/platformkit/test_g314_ball_inferred_coords.py`, **2 passed** via
`python -m pytest tests/platformkit/test_g314_ball_inferred_coords.py -q -p no:cacheprovider`.
`n = 1 (CONSTRUCT)`: all 8 detected x inferred x coordinate-present combinations plus the four
non-finite spellings, so the classifier's input space is covered exhaustively and Q7's sampling
rail does not bind. `tests/platformkit/test_loc_rail_scope.py` 1 passed (A12); the two new files
are 153 and 87 LOC, under the 300 cap. ARTIFACT SHA-256 (LF-normalized): prereg `380b544c4f59b7f1b2ee638021faa66194b3582c0a49484b6ba0761c1fe824b3` | reader `scripts/platformkit/tracking/g314_ball_inferred_coords.py` `711dc94eccaa637624e0559c6d764b41489bf30d1e522303003dc7d52f45f827` | test `6fc435f03e63ac753ed1323ce6db5ff19aed21dcea59c3e2dec2c894cd0841ff`.

NOT VERIFIED:
- **A coordinate is not a correct coordinate.** Nothing here is recall, precision, accuracy or
  registration. No position counted here was ever checked against an image; no frame decoded, no
  render produced. EYE CHECK: NONE. Image space only (`coordinate_space = image_px`): no court,
  foot, metre or registration claim is made, implied, or may be read into these numbers.
- The 7 inferred-without-coordinate rows were COUNTED, not explained.
- 2 games, both WNBA, both `passed = false`, as are all 13 adjudicated games. Nothing generalises
  past these four files, read while the pod tree was mutating.
- The `ball_inferred` staleness question -- the flag is read by `getattr` at
  `unified_pipeline.py:1991` even on frames where `ball_tracker` was not called -- was NOT
  measured; no count of stale-flag rows exists. The other 13 census games were not re-measured.

TIME SPENT: 35 minutes wall (2026-09-07 18:40-19:15 CDT), no GPU.
