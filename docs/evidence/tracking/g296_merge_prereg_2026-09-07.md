# G296 merge -- PREREGISTRATION (sealed before any matching)

Row: G296 merge/adjudication. Worktree a10. Adjudicator: Claude Opus 5 (`claude-opus-5[1m]`),
a MODEL, not a human. Both located passes were MODEL locators too (pass A `gpt-5.6-terra`,
pass B `gpt-6-astra`). This prereg is sealed BEFORE any distance, match or agreement number
is computed. Nothing below was chosen after seeing a distance distribution.

## Precondition already established (frame identity, NOT a matching result)

Pass A frames were extracted locally from `data/videos/bridge/wnba_01.f137.mp4`
(2,841,750,689 bytes, sha256 `f2421bc2...`); pass B frames from the pod file
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` (2,931,985,407 bytes,
sha256 `f361ad7a...`). The 24 JPEGs are NOT byte-identical (different ffmpeg builds and
JPEG encodes). Identity was therefore established on decoded pixels: mean absolute
difference per channel-pixel on the paired index, against an adjacent-index control.
The measured result is reported in the merge memo; the merge proceeds only if every
paired MAD is at least an order of magnitude below the adjacent-index control MAD.

## Sealed rules

R1 SCOPE. The merged ground-truth set contains ONLY `role=player_on_court` rows.
   `official` rows are matched and reported SEPARATELY and are not in the set.
   `bench_or_coach`, `spectator_or_media` and `other` rows are excluded from both and
   reported as counts only.

R2 ELIGIBLE LABEL. A label is matchable iff `feet_visible=true` AND both `foot_x_px` and
   `foot_y_px` parse as numbers. Rows with `feet_visible=false` (no coordinate) CANNOT be
   matched, are EXCLUDED from every agreement denominator, and are reported as counts.

R3 MATCH RADIUS = 50.0 px (Euclidean, native 1920x1080 pixels). Chosen a priori as the
   middle of G285b's published 25/50/100 px ladder and about 2x the "20 px defensible"
   scale both pass specs name for an `approximate` point. Counts at 25.0 px and 100.0 px
   are reported as a declared sensitivity, computed by re-running the identical procedure;
   the 50.0 px run is the only one that produces the ground-truth set.

R4 ONE-TO-ONE MATCHING. Per frame, per role class, build the full A x B Euclidean distance
   matrix (A rows in ascending `person_index`, B columns in ascending `person_index`) and
   solve `scipy.optimize.linear_sum_assignment`. After assignment, any assigned pair with
   distance > the radius is BROKEN: both members become unmatched. No label appears in more
   than one pair. Empty A side or empty B side yields zero pairs.

R5 AGREEMENT. A matched pair is an AGREEMENT at the sealed radius. Reported both ways:
   `matched / eligible A labels` and `matched / eligible B labels`, per frame and overall,
   with both denominators printed. Median and p90 of matched distances are reported.
   No kappa is computed: there is no shared category set and no chance model here.

R6 ADJUDICATION THRESHOLD = 4.0 px. Every matched pair with distance > 4.0 px is
   adjudicated. A pair at distance <= 4.0 px is recorded `source=agreed` with the
   coordinate-wise mean of A and B, rounded to the nearest integer pixel.

R7 ADJUDICATION PROCEDURE. Native-resolution crops (no resize of source pixels) centred on
   the A/B midpoint, sized to contain both marks with margin, upscaled with INTER_NEAREST
   for viewing only, marked with an open A circle and an open B cross so the marked pixel
   itself stays visible, tiled into per-frame contact sheets, written to disk and read back
   (headless; never `cv2.imshow`). The adjudicator picks the mark that better sits at the
   player's floor-contact point.

R8 SOURCE VOCABULARY, exhaustive: `agreed` (R6), `adjudicated_A`, `adjudicated_B`,
   `dropped`. Every A-only and B-only label is also adjudicated by render: kept as
   `adjudicated_A` / `adjudicated_B` if the crop shows a genuine on-court player's floor
   contact at that mark, else `dropped`. Dropped rows are WRITTEN to the CSV with the reason
   in `note` so the bookkeeping is complete and auditable; they are not part of the set.

R9 TIE-BREAK. If the two marks of an adjudicated pair are indistinguishable at the crop's
   resolution, the pair is recorded `adjudicated_A` with note `indistinguishable`, a
   deterministic tie-break to the alphabetically first pass. The count of these is reported
   separately and is a limitation, not an agreement.

R10 OUTPUT. `docs/evidence/tracking/g296_ground_truth_2026-09-07.csv`, header exactly
   `frame_id,player_ordinal,x,y,source,distance_px,note`. `player_ordinal` is assigned per
   frame 1..k over the accepted (non-dropped) rows sorted by ascending x then ascending y;
   dropped rows are appended after them with ordinal 0. `distance_px` is the A-B distance
   for matched pairs (3 decimals) and empty for unmatched labels. A manifest carries the
   SHA-256 of the CSV and of both input CSVs.

R11 NO BAR MOVED. Both pass specs state `bar = NO pass bar. This row builds an INPUT, not a
   result.` The merge inherits that: it declares NO pass/fail bar on agreement. No threshold
   in any other artifact is read, moved or reinterpreted. No recall number is computed here.

R12 HONEST FRAME. This is MODEL-MODEL agreement measuring REPRODUCIBILITY, never
   CORRECTNESS, and both passes can be wrong in the same way. The adjudicator is a third
   MODEL and its adjudications carry the same limit. G291 measured two model raters at
   Cohen's kappa 0.283439 (47/72 raw) on an easier four-category task; that is the
   rater-sensitivity caveat this merge inherits. No human has checked these frames.

--- SEAL ---
sha256(LF-normalized bytes above the seal line) = dcfa4d4be8f735dd1832bbe499991d88e3c34ef25654ae7819d96439c321b5d5
