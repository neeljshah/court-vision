# G310 Attempt 2 -- Preregistration

Row G310, worktree a1, spec `docs/evidence/tracking/specs/G310_spec.md` VERSION 2026-09-08b
(the ATTEMPT 2 block). Sealed and committed ALONE before any recomputation of this attempt was
written into evidence.

## What already exists, and why none of it is this attempt's headline

Two earlier passes were run on the pod on 2026-09-07 and both are EXPLORATORY here:

1. A PILOT pass of seven route runs that ran BEFORE the attempt-1 preregistration was sealed. It is
   archived, frozen, at `docs/evidence/tracking/g310_pilot_pre_prereg/`. It is not this attempt's
   headline and none of its numbers is quoted as a result of this attempt.
2. The attempt-1 POST-PREREG pass, whose memo is `docs/evidence/tracking/g310_native_input_arm_2026-09-07.md`
   and whose preregistration is `docs/evidence/tracking/g310_prereg_2026-09-07.md`. Candidate
   `195d1c45660924367d46d7eabb16fa9f7d8b5bea` was REJECTED by `docs/evidence/tracking/G310_VERIFY_2026-09-08.md`
   on Q1 (the sealed preregistration said no arm preceded sealing while the memo used the pilot),
   on B9 (`player_id` is a reusable tracker slot 1-10, so the distinct-id, track-length and step
   proxies were keyed on the wrong unit) and on the result bar (1 of 3 games, 2 of 7 runs). Those
   three files are FROZEN and are not edited by this attempt.

Attempt 2 therefore treats BOTH earlier passes as exploratory prior work, re-derives the track
proxies on a corrected key, and claims nothing that rests on the pilot being confirmatory.

## No GPU run

This attempt runs NO route arm and touches NO GPU. It recomputes proxies from row-level outputs that
already exist on the pod. The pod is read-only for this attempt: nothing is written, moved or deleted
there, and `track_daemon` and `vol_guard.py` are never stopped, signalled or restarted.

## Source set, named before any recomputation

Every run whose row-level output survives on the pod, across the two roots that hold them. Root A is
the lane job root `/workspace/wt/a1/g310_out` and carries the PILOT pass. Root B is
`/workspace/wt/a1/jobs/20260907223158_464723_12590/g310_out` and carries the attempt-1 POST-PREREG
pass. Sources are named by the file each run recorded in its own sidecar.

| # | root | run directory | arm | source file | status |
|---|---|---|---|---|---|
| 1 | A | `wnba_01_1080p_armP` | P | `wnba__wnba_01_1080p.mp4` | run_summary.json PRESENT |
| 2 | A | `wnba_01_1080p_armN` | N | `wnba__wnba_01_1080p.mp4` | run_summary.json PRESENT |
| 3 | A | `wnba_01_1080p_armP_repeat` | P | `wnba__wnba_01_1080p.mp4` | run_summary.json PRESENT |
| 4 | A | `ncaa_basketball_IB-_u4gW3ds_1080p_armP` | P | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | run_summary.json PRESENT |
| 5 | A | `ncaa_basketball_IB-_u4gW3ds_1080p_armN` | N | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | run_summary.json PRESENT |
| 6 | A | `ncaa_basketball_mRkuGgeECak_armP` | P | `ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | run_summary.json ABSENT -- BUDGET LIMIT |
| 7 | A | `ncaa_basketball_mRkuGgeECak_armN` | N | `ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | run_summary.json ABSENT -- BUDGET LIMIT |
| 8 | B | `wnba_01_1080p_armP` | P | `wnba__wnba_01_1080p.mp4` | run_summary.json PRESENT |
| 9 | B | `wnba_01_1080p_armN` | N | `wnba__wnba_01_1080p.mp4` | run_summary.json PRESENT |
| 10 | B | `ncaa_basketball_IB-_u4gW3ds_1080p_armP` | P | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | run_summary.json ABSENT -- SWEPT, no tracking CSV written |

Runs 6, 7 and 10 carry no `run_summary.json`; runs 6 and 7 busted the 3,600 s wall and run 10 was
swept mid-run by the daemon restart described in the attempt-1 memo. They are reported with that
status and are never silently dropped.

The three source videos are DELETED from the pod, so they cannot be re-probed. Their probed
dimensions are taken from the frozen attempt-1 memo (all three 1920x1080), and each surviving run's
own `evaluated_frame_count.json` records a `source_size_bytes` that matches that memo's byte size for
the same file, which is the cross-check that these outputs came from those exact files.
`source_height` for normalisation is therefore 1080 for every run.

## Whole-game 1920x1080 census on the pod (2026-09-08, read-only)

`find /workspace/nba-ai-system/data/footage_corpus -name '*.mp4' -size +300M` returned NOTHING.
The corpus holds 85 mp4 files. `ffprobe` over every one of them gives exactly two heights: 63 files
at 360 and 22 files at 720. ZERO files at 1080. The five largest files, probed:

| file | bytes | WxH | fps | frames | duration s |
|---|---|---|---|---|---|
| `nba__0022500081_s6297.mp4` | 37026762 | 1280x720 | 30/1 | 4011 | 133.752 |
| `nba__0022500081_s654.mp4` | 36613721 | 1280x720 | 30/1 | 4001 | 133.412 |
| `nba__0022400909_s60.mp4` | 34319575 | 1280x720 | 30000/1001 | 3982 | 132.912 |
| `nba__0022400909_s3116.mp4` | 34306706 | 1280x720 | 30000/1001 | 3912 | 130.574 |
| `nba__0022400909_s1588.mp4` | 34285160 | 1280x720 | 30000/1001 | 3944 | 131.639 |

(duration rounded to three decimal places from the `ffprobe` value; bytes and dimensions verbatim.)

The largest file is under 40 MB and every file is a section of about 130 s, not a whole game. THERE
ARE ZERO WHOLE-GAME 1920x1080 SOURCES ON THE POD. The bar below requires three of them. THE 3/3 BAR
IS UNREACHABLE, and the verdict of this row is therefore CLOSED AT LIMIT on source availability. No
1280x720 substitute is used, because the spec makes a 1280x720 source INELIGIBLE by measurement.

## Non-recycled track-instance key

`tracking_data.csv` was inspected first. Its columns are `frame`, `timestamp`, `player_id`, `team`,
positions, `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2`, `lineup_id`, `observation` and others. THERE
IS NO PERSISTENT TRACK OR INSTANCE ID COLUMN. `player_id` is the reusable slot: `_build_players` at
`src/pipeline/unified_pipeline.py:821-831` allocates a fixed pool of 5 green slots, 5 white slots and
one referee slot, and a slot is evicted and re-used once `self._lost_ages[slot] >= self._max_lost`
(`src/tracking/advanced_tracker.py:1538`, `:1566`, `:1787`), with `MAX_LOST = 90` at
`src/tracking/advanced_tracker.py:75`.

An INSTANCE is therefore defined as a maximal run of emitted rows for one slot within one run, in
increasing frame order, cut between two consecutive rows whenever EITHER

- the frame-id gap exceeds G, OR
- the Euclidean bbox bottom-centre displacement exceeds J times `source_height`.

FIXED VALUES, derived from the route and not from any outcome:

- G = 270 frame ids. The tracker evicts after `MAX_LOST` = 90 lost updates and the route emits on a
  stride of 3 frame ids, so 90 x 3 = 270 is the largest frame-id gap that a single un-evicted slot
  can span. Any larger gap means the slot was certainly evicted and re-assigned.
- J = 0.20 of `source_height`. A detected player bbox in these sources is about one fifth of the
  frame height, so J is one player body height of apparent bottom-centre motion within one emission
  step. A real player at sprint speed covers roughly half of that in the 0.1 s an emission step
  spans, so J leaves about a factor of two of headroom for camera motion before a step is called an
  identity swap.

SENSITIVITY PAIR, reported alongside and never instead of the fixed values: (G = 90, J = 0.10),
strictly tighter on both axes.

FOOTPOINT convention, unchanged from attempt 1: the image-space bbox BOTTOM-CENTRE,
`((bbox_x1 + bbox_x2) / 2, bbox_y2)`.

The three track proxies are recomputed on this instance key, per run: distinct instances, median
instance length in rows, and the p95 nearest-rank per-instance consecutive normalised footpoint step.
A STEP THAT SPANS A SPLIT BOUNDARY IS EXCLUDED from the p95 sample, since the two rows either side of
a cut are by construction not the same instance. The attempt-1 slot-keyed numbers are reported BESIDE
them for contrast and are labelled as the attempt-1 unit; they are not restated as this attempt's
track proxies.

## Rows-per-frame denominator rule

`person_rows_per_frame` is reported with BOTH candidate denominators printed for every run:

- `evaluated_frames` from the route's own `evaluated_frame_count.json` sidecar, and
- `frames_with_rows`, the count of distinct frame ids present in `tracking_data.csv`.

The RULE: if `evaluated_frames` is non-null it is the denominator; otherwise the denominator is
`frames_with_rows`, and the substitution is stated explicitly at the point of use together with the
sidecar's own `reason` string. Nothing is invented when both are absent; the cell stays empty.

## Bars, byte-identical to the spec

    metric        = the step-0 printed effective input size; the three sources' probed dimensions with
                    the rejected candidates counted; both arms' exact settings with the single-difference
                    design stated; per game per arm the five proxies with denominators named and the wall
                    seconds; the ARM P repeat-stability check; the stated sign convention; and the
                    SCREENING label with the no-ground-truth sentence
    before        = the production route feeds the detector an input size below 1920 on 1920x1080 sources
                    (`_infer_imgsz = 640`, `player_detection.py:82`, read back at
                    `unified_pipeline.py:917` and `:1021`) and NO whole-game native-input arm exists
    bar           = 3/3 games complete BOTH arms within 3,600 s each and every proxy is tabulated with
                    its denominator. NO quality bar and NO pass bar -- this row screens, it does not
                    score. A proxy table showing NO difference is a FULL SUCCESS. A game that busts
                    the budget is a BUDGET LIMIT reported per game, not a silent drop.
    n             = 3 games x 2 arms + 1 repeat = 7 route runs; name the emitted-frame denominator per
                    run in the verdict line
    eye check     = NONE. This row has no labels and no blind judging; it is arithmetic over route
                    output. Say that rather than implying validation.

No bar above is moved, softened or reinterpreted by this attempt. The bar is reported UNMET.

## Sign convention and the screening label

A HIGHER person-rows-per-frame, a HIGHER distinct-instance count, a HIGHER median instance length and
a HIGHER detected-ball-row count would each be consistent with more detection; a LOWER p95 normalised
footpoint step would be consistent with steadier association. CONSISTENCY IS NOT EVIDENCE.

This is a SCREENING ROW. There is NO ground truth here, so every number is a proxy and none is a
quality measure. More rows per frame can mean more players found OR more false boxes, and this row
cannot tell those apart; G303, which scores recall against the G296 frames, is the row that can. No
claim of recall, precision, accuracy, registration or a harness pass is made, and the ledger `passed`
field is not touched.

## Archive

The minimal per-run columns -- frame id, slot, instance id, bbox bottom-centre x and y, and the ball
rows -- are written as gzipped CSV under `docs/evidence/tracking/g310_attempt2/`, each file at most
5 MB and sharded if larger, with a SHA-256 for every archived file, so that every median and every
p95 in the memo is recomputable from committed bytes. Integer CSV cells are zero-padded to six digits.

## Non-targets

No production default is changed and no flag is flipped. Nothing under `src/`, `kernel/`, `api/`,
`intel/` or `scripts/team_system/` is edited; those trees are read-only for this attempt. Nothing is
written under `data/registry/`. `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` is not edited.
The attempt-1 memo, its preregistration, the pilot archive and the verify memo are FROZEN and are not
edited. Nothing is adopted and nothing is proposed. Calibration language only.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A, B and Q, with B2 (additive only;
the attempt-1 JSON schema field names and meanings are preserved and only new fields are added), B9
(the non-recycled instance key) and Q6 (vocabulary) binding.

Seal SHA-256 of the pre-seal content above (LF-normalised bytes): `627DF9217E91D781D7C4DFAFA2071975C6CC0E1D58E2E5DC789A912E9CE38141`.
