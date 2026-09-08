# G323 PREREG -- non-player content in player boxes (sealed 2026-09-07)

ATTEMPT 2 -- re-sealed after a Q6 vocabulary defect in the attempt-1 prereg (cef6020a3); sample rule, seed, categories, statistics and thresholds UNCHANGED

Sealed BEFORE the first frame was cut, before the first panel was rendered and before the first
label was written. Spec: `docs/evidence/tracking/specs/G323_spec.md` (master `649ce1c50`).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`.
Q6 declaration: `border` and `boundary` are the geometric words for a box side in every G323
artifact; this lane's prose is calibration language only and carries no prohibited Q6 vocabulary.

## 1. CONSUMED INPUT (G322, worktree a21, commit a5056025e, NOT YET LANDED ON MASTER)
Census file: `docs/evidence/tracking/g322_oversized_boxes_census_2026-09-07.csv`
SHA-256:     `73bc654a90bd28effeceacd031ecc290633d063edc4bc56c8973574a60dfe4bd`
If G322 is corrected, this row re-seals and every number below is recomputed.

## 2. GAME SELECTION RULE (fixed now)
One game per source resolution, the **nearest-rank median `share_gt50` game of that resolution** in
the G322 census: order that resolution's games by `share_gt50` ascending, ties by `game_id`
ascending, take rank `ceil(0.5 * n)` (1-based). Expected result, to be RECOMPUTED and any
disagreement reported rather than copied:
  1920x1080 -> `wnba_06`            (rank 4 of 7,  share_gt50 0.0862)
  1280x720  -> `wnba_04`            (rank 7 of 13, share_gt50 0.0643)
  640x360   -> `0022500575_s7200`   (rank 26 of 51, share_gt50 0.1878)
G322's own panel games differ (`bos_mia_playoffs`, `0022500594_s7200`) under a different median
convention. That is noted, not reconciled, and the rule above is the one that binds here.

## 3. STRATIFICATION (fixed now)
All coordinates are the tracker's POST-TOPCUT image space, `TOPCUT = 60`
(`src/tracking/video_handler.py:11`). Let `H = source_height - 60` from the table's own
`source_height` column.
  ratio  = (bbox_y2 - bbox_y1) / H
  region = UPPER if (bbox_y1 + bbox_y2) / 2 < 0.5 * H else LOWER
  tercile T1/T2/T3 = ratio below the game's OWN 1/3 percentile, between, at or above its OWN 2/3
                     percentile. Percentiles are nearest-rank on that game's own ratio values.
Cells = 3 terciles x 2 regions = 6. Each cell holds exactly 10 boxes. Total = 60.
Every row of every game's table is a candidate; no row is filtered out for any reason, including
off-frame boxes and boxes with `bbox_y2 > source_height`.

## 4. SELECTION INSIDE A CELL (seeded, fixed now)
Seed string: `G323`. For each candidate row compute
  key = sha256("G323|" + game_id + "|" + str(frame) + "|" + str(player_id)).hexdigest()
Order the cell's rows by `key` ascending. Fill the cell by ROUND-ROBIN over the three games in the
fixed order (`wnba_06`, `wnba_04`, `0022500575_s7200`), taking each game's lowest-key unused row in
turn, until the cell holds 10 -- so a full cell is 4/3/3. If a game has no unused row left in that
cell, the slot passes to the next game in the order and the shortfall IS NAMED in the memo with its
count. This is neither a head slice nor a top tail (contract A3/B7).
n per cell per game is printed in the sample CSV and in the memo.

## 5. RENDERING (fixed now)
One panel per box, headless PIL, never `cv2.imshow`: a context tile (the whole frame with the box
drawn) beside a crop of the box. Both readings are drawn, as G322 did -- the post-TOPCUT reading
(`y + TOPCUT`, solid) and the no-offset reading (thin) -- so the rendering assumption is visible.
Panels carry an OPAQUE panel id (`P01`..`P60`) and NOTHING else: no game id, no frame, no ratio, no
region, no tercile, no player id. At most 4 contact sheets, at most 500 KB each, 15 panels per
sheet. Panel id order is the sealed cell order (T1-UPPER, T1-LOWER, T2-UPPER, T2-LOWER, T3-UPPER,
T3-LOWER), 10 per cell, so the sheets themselves reveal no per-panel metadata to either rater.

## 6. CATEGORIES (fixed now, stated before any panel is viewed)
Exactly one per panel, from this closed list:
  player_on_court | player_bench_or_courtside | crowd | referee_or_staff | broadcast_graphic |
  off_frame_or_empty | two_or_more_players | unreadable
NON_PLAYER (sealed set) = crowd + referee_or_staff + broadcast_graphic + off_frame_or_empty +
                          player_bench_or_courtside
`two_or_more_players` is NOT in NON_PLAYER. `player_on_court` and `unreadable` are NOT in it.

## 7. RATERS AND BLINDING (fixed now)
Rater A = Claude Opus 5, model id `claude-opus-5[1m]`, declared. Rater A labels all 60 panels and
its labels are COMMITTED BEFORE rater B is dispatched.
Rater B = a codex lane, model `gpt-5.6-sol`, worktree a20, log `cx_r323b_rateB.log`. Its prompt
carries the contact sheets, the panel ids and section 6 of this prereg, and NEVER rater A's labels
and never any panel metadata. Its sheet is landed with `lane_commit.py`.
HUMAN LABELS ARE THE LIMIT. G315 measured two model raters agreeing on 14 of 30 panels. No content
statement in this row is a ground truth and none may be quoted as one.

## 8. AGREEMENT STATISTICS (formulas fixed now)
  po     = (number of panels where A and B give the same category) / 60
  pe     = sum over categories c of (n_A(c) / 60) * (n_B(c) / 60)
  kappa  = (po - pe) / (1 - pe)          -- Cohen's kappa, unweighted
  SE     = sqrt( po * (1 - po) / (N * (1 - pe)^2) ),  N = 60   -- the standard asymptotic SE under
           the null of independence (Fleiss/Cohen large-sample form). Reported with a 95 pct
           interval kappa +/- 1.96 * SE, labelled ASYMPTOTIC and NOT a small-sample guarantee at
           N = 60.
  If pe == 1 exactly, kappa is UNDEFINED and is reported as such, never as 0 or 1.
The confusion counts over the categories actually used are printed in full.

## 9. GATE CHECK PROCEDURE (fixed now)
SURVIVORSHIP, declared before measuring: every sampled row was WRITTEN to `tracking_data.csv`, so it
already passed every gate in the write route. The gate-rejection count is therefore 0 A PRIORI and
is NOT the measurement. Step 5 is a REPRODUCTION check.
  (a) TEAM-COLOUR GATE, re-run standalone, CPU only, no YOLO, no GPU:
      import `_adaptive_colors`, `COLORS`, `PAD` from `src/tracking/player_detection.py` (import
      only, no edit), call `_adaptive_colors(frame)` on the extracted POST-TOPCUT frame, take the
      UNPADDED clamped crop (the writer adds `PAD = 15` per border AFTER the gate sees the box, so
      subtract 15 from each border and clamp to the frame), convert its upper 70 pct to HSV, run
      `cv2.inRange` for each of the three ranges, take the argmax of the nonzero counts, and treat
      an all-zero result as REJECT -- the same argmax and the same `if not team: continue` as
      `src/tracking/advanced_tracker.py:1341-1356`.
      Report per rated category: PASS count, which range matched, and the matched-pixel count.
  (b) COURT-REGION GATE: the row asserts a court mask in `src/pipeline/unified_pipeline.py`. The
      author's S2 check found none. Whatever the premise step finds is reported verbatim. If the
      only region reject is the projected-footpoint map-bounds test at
      `src/tracking/advanced_tracker.py:1429-1431`, it is declared NOT RE-RUNNABLE standalone
      (it needs the per-game homography `M`/`M1` built from a panorama at run time) and is pinned
      by `file:line` instead. It is never simulated and never omitted.

## 10. VERDICT RULES (bars FIXED NOW, never moved)
  PREMISE HOLDS   iff EITHER rater marks >= 10 of the 60 panels NON_PLAYER. Otherwise PREMISE FALSE.
  GATE MISSING    iff the gates reject < 50 pct of the both-rater-agreed NON_PLAYER boxes.
                  Then, and only then, a PROPOSED gate is written under
                  `docs/research/organization-sprint/`. Otherwise GATES SUFFICIENT.
  Nothing under `src/`, `domains/`, `api/`, `kernel/`, `intel/` is edited either way.
  If the both-rater-agreed NON_PLAYER set is EMPTY, the GATE MISSING rule has no denominator: it is
  reported UNDEFINED, never as GATES SUFFICIENT.

## 11. MUST NOT MOVE
The pod tree and the running `track_daemon`; `data/registry/`; `src/`, `domains/`, `api/`,
`kernel/`, `intel/`; `scripts/platformkit/tracking_harness.py`; every threshold, every feature flag,
every historical ledger row; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`; and every number
sealed above -- the seed, the eight categories, the NON_PLAYER set, the 10/60 bar and the 50 pct
bar.

## SEAL
The seal is the SHA-256 of the LF-normalized bytes of this file ABOVE this `## SEAL` line.
SEAL SHA-256: 45c59cccf63e63abf539ff57b13f8ca8b11ec9c7fec9738b616eaf982b525b02
