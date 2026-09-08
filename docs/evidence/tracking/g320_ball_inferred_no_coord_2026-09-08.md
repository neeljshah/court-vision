VERDICT: DONE. The 7 rows reproduce exactly -- 1 in `wnba_05`, 6 in `wnba_02`, n = 2,000 ball rows -- and the cause is NAMED at the writer: `src/pipeline/unified_pipeline.py:1985-1991` builds one row dict from two independent attributes that are never reconciled, the coordinate and `detected` from `ball_det.last_2d_pos` and the flag from `ball_det.ball_inferred`, so any branch that nulls the projection after the dribble predictor has set the flag emits a flagged row with no coordinate. WHICH nulling branch fired on a given frame is UNATTRIBUTED; the candidates with the evidence for and against each are below.

# G320 -- ball rows flagged inferred with no coordinate (2026-09-08, LOCAL)

PREREG sealed and committed ALONE before any measurement existed (Q1): `g320_prereg_2026-09-08.md`, seal `30b530367c7a019a8c8f3d803b1ba4b06bc708b596d6621e028426836fafc634`, commit `789ced987`.
INPUTS. The two ball tables are committed NOWHERE (see the census), so both were fetched read-only from the pod with `ssh ... cat`. Nothing on the pod was written, no daemon or guard signalled, pids 1168432 / 1039858 / 1201700 untouched. No GPU, no frame decoded. Byte size AND raw SHA-256 are IDENTICAL to what G314 asserted, so this is a recount of the same bytes, not of a newer table:
`wnba_05/ball_tracking.csv` 24473 B `805c6479e6988dbb0958d8b15c2b2f35f8a1ee4a51a626be5361b1d24f60ca1d` | `wnba_02/ball_tracking.csv` 23410 B `79537a95f1d8ca4f0f609b27e07c19aa1f1d66e6bdfb3926558e942d273b8510`

## PREMISE -- TRUE. Every row of both tables, head to tail, no sampling, no head slice.
| game | ball_rows (n) | detected | inferred | inferred_no_coord |
|---|---|---|---|---|
| wnba_05 | 1,000 | 907 | 311 | **1** |
| wnba_02 | 1,000 | 803 | 273 | **6** |
| both | 2,000 | 1,710 | 584 | **7** |

The 7 rows, by game and frame id (zero-padded), each with `detected = 0`, `ball_inferred = 1` and both `ball_x2d` and `ball_y2d` empty: `wnba_05` 000444; `wnba_02` 000540, 000750, 001746, 002064, 002100, 002823. G314's count of 7 is reproduced exactly, n = 2,000.

## TRACE (read-only; `src/` not edited)
`ball_detect_track.py:793-796` -- when `bbox is None` the dribble predictor supplies one and sets `self.ball_inferred = True`; control then falls through `:816` (update state) to `:908`. The coordinate attribute `last_2d_pos` is assigned at only four sites -- `:156` (init), `:919`, `:951`, `:956` -- and is never reset per frame. `unified_pipeline.py:1942-1947` calls the tracker only when `_apply_yolo` (`:3086`) left `_last_ball_2d` None, and copies `last_2d_pos` into it; `:1985-1987` writes the coordinate and `detected` from that value and `:1991` writes the flag from the other attribute. Because all 7 rows have `detected = 0`, the tracker DID run on them, so the flag is fresh on these rows and the staleness path (`getattr` at `:1991` on frames where the tracker never ran) is ruled out for them, n = 7.

WHICH BRANCH nulled the coordinate -- UNATTRIBUTED from code alone. Candidates:
- A, negative-projection reject, `ball_detect_track.py:919`. FOR: unconditional, fires on a stale `M`/`M1`. AGAINST: leaves no distinguishing trace in the table.
- B, possessor-drift reject at more than 1200 px, `ball_detect_track.py:951`. FOR/AGAINST: as A; A and B write the identical value and are not separable from the table.
- C, projection block skipped because `:908` is false (`check_track` reached 0; `MAX_TRACK = 150` at `:110`), retaining the previous value. AGAINST, on all 7: the immediately preceding row carries a finite coordinate in 7 of 7 cases, so a retained value would have been finite, not None -- decisive only where that preceding coordinate came from `ball_det` rather than from the YOLO path at `:3086`, which the table cannot separate, so C is disfavoured, not excluded. FOR the branch existing at all, though not on these 7: consecutive rows repeat one pair exactly (`wnba_02` 000537 / 000543 / 000546 all `91,449`), which is equally what a stationary ball looks like.

HOW IT WOULD BE CONFIRMED, NOT DONE HERE: print the frame id at `:919`, at `:951` and at the `:908` skip, then re-run exactly the 7 frame ids above. This row performs no re-run.

## PROPOSED DIFF (local-only, gitignored; `src/` NOT edited)
`docs/research/organization-sprint/G320_PROPOSED_ball_inferred_coord.md`, 40 lines, sha256 `1fc07bd285fd0d9bfc906ea053d9aecd139e64f586e6c9535bc84f7eac707a86`. It replaces the single line `unified_pipeline.py:1991` with a 7-line form that writes the flag as true only when this row has a coordinate. It writes the flag DOWN rather than writing the predictor's point IN, because the predictor's output is a pixel bbox while the column is the projected map point, and branches A and B null that point precisely because the projection was rejected as wrong; writing it would put a known-rejected point in the table. The same line also closes the staleness path.

## READER HARDENING (additive, B2) AND CENSUS
`scripts/platformkit/tracking/g314_ball_inferred_coords.py` (179 lines): `count_ball_table` now RAISES `MissingBallInferredHeader` when the `ball_inferred` header is absent, instead of reporting its flag counts as zero, and counts `inferred_no_coord` (plus `inferred_no_coord_frames`) as its own class, folded into neither `ball_detected` nor `ball_inferred`. Every pre-existing output field keeps its name and meaning; `inferred_no_coord` is equal by construction to the retained `inferred_without_coords` and the test asserts the two cannot drift.

CENSUS, exhaustive (B7): all 423 git-tracked `.csv` files under `docs/evidence/tracking/` were header-scanned; a ball table is one carrying BOTH `ball_x2d` and `ball_y2d`. n = 2 are ball tables; n = 1 more carries a `ball_inferred` column but is a per-game aggregate with no per-row coordinate column (`g309_multigame_census_2026-09-07.csv`, listed out of scope); n = 420 neither. BOTH ball tables STOP the hardened reader, so **0 of 423 committed files carry a per-row `ball_inferred` header** and the pre-hardening reader would have reported 0 flagged rows for each -- the silent miscount the hardening removes. Cells in `g320_ball_inferred_no_coord_2026-09-08/census.csv` (integers zero-padded to six digits there):
| scope | table | rows (n) | detected | inferred | inferred_no_coord | status |
|---|---|---|---|---|---|---|
| committed | g82_jump_statistic/eye_check_selection.csv | 6 | - | - | - | STOP_MISSING_BALL_INFERRED_HEADER |
| committed | g82_jump_statistic/oversized_steps_above_p95.csv | 16 | - | - | - | STOP_MISSING_BALL_INFERRED_HEADER |
| pod_read_only | wnba_05_ball_tracking.csv | 1,000 | 907 | 311 | 1 | OK |
| pod_read_only | wnba_02_ball_tracking.csv | 1,000 | 803 | 273 | 6 | OK |

TESTS. `tests/platformkit/test_g320_ball_inferred_no_coord.py` **3 passed**, n = 20 rows (CONSTRUCT) in the seven-row case; `tests/platformkit/test_g314_ball_inferred_coords.py` **2 passed** (unchanged by the hardening); `tests/platformkit/test_loc_rail_scope.py` **1 passed**. Touched files are 179, 116 and 102 lines, all under the 300 cap.

## NOT VERIFIED
- The cause is named at the WRITER, not at the branch. A, B and C are not separated, and no named cause is confirmed until a re-run with the proposed change reproduces those 7 frame ids with a coordinate. No re-run happened, nothing was deployed, `src/` was not edited.
- Nothing here is recall, precision, accuracy or registration. No coordinate counted here was ever checked against an image; no frame was decoded and no render produced. EYE CHECK: NONE. Image space only (`coordinate_space = image_px`): no court, foot, metre or registration reading may be taken from these numbers.
- The census is a census of what was ARCHIVED, not of the pod fleet: 0 committed ball tables carry the flag header, so the only tables actually classified are the 2 pod games, both WNBA, both `passed = false`. Nothing generalises past them; the other pod games were not measured.
- `inferred_no_coord` for the 2 stopped committed tables is not zero, it does not exist. Reading a blank cell as a zero reintroduces exactly the miscount this row removed.

TIME SPENT: 25 minutes wall (2026-09-08 06:55-07:20 CDT), no GPU, nothing written on the pod.
SHA-256 (LF-normalised): prereg `fd855b32809734d59aa9defee3671823fbe2610de91c291d2f9497c65e08832f` | reader `a186a13b1e3d7c0f35325a8accec8c86ae3a2e67359ce35431446e25df43d12c` | census script `2c0594abdd7bab4bc4f28e1b10c5cb2dcb170c7812ec992f73a893d03de574f6` | test `f1c84216c1f4de1adfceb7e1346b0b7a3d92f56d3c84933ba5d1e582083922cf` | census.csv `c2d73f0bb8672565ef8eff4e40f1c16acceb968de9fca833e2ba383c548d58c8`
