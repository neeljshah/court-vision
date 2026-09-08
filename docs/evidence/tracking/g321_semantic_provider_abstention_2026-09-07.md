CAUSE NOT UNIQUE, NOT REPAIRABLE THROUGH THE G304 MAP -- per-frame FIRST-zero distribution across the funnel: `_ordered_quad` convexity/400 px^2 at `domains/basketball/tracking/keypoints.py:36` and `:41` is first zero on 3/24, the `0.006*w*h` area floor at `domains/basketball/tracking/keypoints.py:82` (the constant),
applied with side at `:87`, is first zero on 10/24, and the minimum-side floor `float(side_lengths.min()) < 0.15 * height` (162 px at 1080p) at `keypoints.py:87` -- the condition line, not the `:93` return statement -- is first zero on 11/24; no single stage reaches the spec's 20/24 cause bar. Cumulative survivors 0 on 24/24 at the minimum-side stage; 13 of those frames were already zero upstream. No single relaxation R1-R9 reaches the bar -- best cells R6 6/24 and R4 4/24 frames with any emission, max 5 distinct names over 2 marking structures, ready 0/24 in every cell against the >= 6-names / >= 3-structures / >= 12-of-24 / <= 12-false bar; n = 24 frames (CONSTRUCT), 113 adjudicated points over 16 of them, 10 cells, 240 cell-frame observations, 1 broadcast, 1 arena (`wnba_01`, TRANSCRIBED Gateway Center).
G321, worktree a6, LOCAL CPU ONLY -- no pod, no GPU, no `pod_run`. `domains/`, `src/`, `kernel/`
imported, never edited (`git status` clean on all three). Measures NO registration, NO calibration,
NO tracking quality; states no boundary claim. cv2 4.11.0, ffmpeg 8.1. PREREG
`g321_prereg_2026-09-07.md` ALONE at `f53a04d5f`, seal `50e09b04b907a735...46f9034e`, sealed before
any measurement. Spec `specs/G321_spec.md` at master `969bf0efb`.
SOURCE `data/videos/bridge/wnba_01.f137.mp4`, 1920x1080, 2,841,750,689 B, sha256
`f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3` -- byte-identical to the file
`g296_merge_2026-09-07.md` section 1 names, so NO POD EXTRACTION WAS NEEDED. 24 frames at the sealed
G296 formula, decoded by `g296a_extract_frames.py:extract` unmodified, all confirmed 1080x1920x3;
every decode SHA-256 is in the prereg.
## PREMISES
P1 CONFIRMED -- the shipped `detect()` at its default `min_edge_support=0.16` returns **0 keys on
24 of 24** frames; the G304 abstention (0 on 63/63) reproduces on an independent frame set.
P2 CONFIRMED, and it changes what the 8 px number means. Verbatim, as the spec requires: *"The 113
G296 points are adjudicated player foot-contact positions, not named court markings; a court-landmark
proposal within 8 px of one of them is a proposal sitting on a PLAYER, so the 8 px count is a DEFECT
count, never a hit count, and this row therefore establishes NO landmark recall for any provider."*
Schema `frame_id,player_ordinal,x,y,source,distance_px,note`. Five evenly spaced notes
(`g296_ground_truth_2026-09-07.csv` rows 0, 46, 92, 139, 185 of 186): frame 0 `A on lower leg; B
at shoe-floor contact`; frame 37919 `B at the sole; A on the shoe body`; frame 75839 `base of the
green shoe`; frame 98590 `about 40 px left of the yellow shoe on open floor`; frame 151677 `both
marks on the seated crowd; no floor contact`.
**`n_on_player` is 0 in all 10 cells** -- the absence of one defect, not the presence of a landmark.
P3 CONFIRMED -- `g304_proposals.py:SEMANTIC_MAP` = 6 keys -> **5 distinct names** (`FT_LINE_L/R`,
`KEY_TOP`, `LANE_BASE_L/R`) over **2 structures**. 5 < 6 and 2 < 3, so PROVIDER REPAIRABLE is
**UNREACHABLE BY ARITHMETIC** through this map whatever the gate does: the ceiling is the MAP as well
as the GATE, and both are reported.
FIDELITY PIN -- R0 equals the SHIPPED provider EXACTLY on **24 of 24** frames (same keys, coords
within 1e-6): `g321_artifact/fidelity.json`. The shadow re-implements only `_candidate_quads` and the
`_paint` filter chain and imports `_line_support`, `_name_paint`, `_circle_landmarks` unchanged.
## R0 FUNNEL, frames with 0 survivors / first zero (per-frame stage_* columns in `cells.csv`)
contours 0/24 (0) | perimeter 0/24 (0) | vertices 0/24 (0) | quad_ok `:36`,`:41` 3/24 (3) |
area `domains/basketball/tracking/keypoints.py:82`,`:87` 12,442 px^2 13/24 (10) | side `:87` 162 px 24/24 (11) | support `:62` 0.16
24/24 (0 -- zero downstream of `side`, never independently observed). No single stage reaches
the spec's 20/24 cause bar -- CAUSE NOT UNIQUE.
## RELAXATION GRID (all 10 cells x all 24 frames; no frame dropped from any cell)
Reported per cell as frames-with-keys / raw keys / max names / max structures / on_player / ready:
  **R4 side_frac 0.05 -> 4/24, 18, 5, 2, 0, 0/24** and **R6 vertex_max 6 -> 6/24, 27, 5, 2, 0, 0/24**
  are the only cells that emit anything. R0 (shipped), R1 support 0.08, R2 support 0.02,
  R3 area_frac 0.002, R5 approx_eps 0.050, R7 perimeter 60.0, R8 convexity off and R9 contours from
  the G304 marking mask are all **0/24, 0, 0, 0, 0, 0/24**. No cell reaches ready >= 12/24.
## EYE CHECK -- 6 overlays, EVENLY SPACED at i = 0, 4, 9, 13, 18, 23, never a head slice
`g321_artifact/overlays/`, 1280x720 q80, R0 red and best cell R6 green. Two of the six carry an R6
emission and **BOTH ARE WRONG**: `frame 98590` names four lane corners on the ATLANTA floor-logo
boundary while the real painted key stands unmarked across the frame, and `frame 174429` is a player
CLOSE-UP with **no court visible at all** and still receives four named lane corners. n = 2 emitting
frames of 6 -- an eye check, not a rate. Relaxing a floor restores emission by removing the graphics rejection the provider's own docstring promises.
PROPOSED, NOT APPLIED: `docs/research/organization-sprint/PROPOSED-g321-semantic-gate-min-side-floor-2026-09-07.md`
-- the one-line `0.15 -> 0.05` change, its numbers and why it is not recommended alone. That tree is
LOCAL-ONLY by contract (`.gitignore:489`, untracked at `ea05dd9b1`), so the file is NOT in this
commit; sha256 of its LF-normalized bytes `bfb8e8996179c6e0cbcc508e5d40df1b53ac749bd0dd94be2a45055fc7d8ea1e`. Human-gated; no
`domains/`/`src/` file touched, no flag flipped, nothing deployed to the pod (B5).
## FIX 1B (VERIFIER CORRECTIONS)
- Cause attribution corrected from CAUSE NAMED (minimum-side floor, mis-cited `:93`) to CAUSE NOT
  UNIQUE: per-frame FIRST-zero is `_ordered_quad` 3/24 (`keypoints.py:36`, `:41`), area floor
  10/24, minimum-side floor 11/24 (`keypoints.py:87`, the condition line -- `:93` is the return
  statement); no stage reaches the spec's 20/24 cause bar.
- Five ground-truth notes added at evenly spaced indices of `g296_ground_truth_2026-09-07.csv`
  (see the P2 premise above), satisfying the premise procedure's request for more than one example.
- OpenCV version pinned: `cv2.__version__` used throughout this row is `4.11.0`. NEW GAP: under
  cv2 4.13.0 the funnel shifts -- cumulative area zeroes 13/24 -> 12/24, first-zero area/side
  10/11 -> 9/12 -- while the REJECT verdict is unchanged.
- NEW GAP addressed: `tests/platformkit/tracking/test_g321_semantic_gate.py` now computes the
  per-frame first-zero stage from the committed `cells.csv` and asserts the 3/10/11-of-24
  distribution and that no single stage reaches the 20/24 cause bar.
- LOC corrected 270 -> 278 for `g321_semantic_gate.py` (verifier recount; both files stay under
  the 300 LOC rail).
## NOT VERIFIED
- ONE broadcast, ONE arena (TRANSCRIBED, not confirmed by eye), 24 frames; nothing generalises to `wnba_04`, Climate Pledge, another sport or 720p.
- The 113 G296 points are PLAYER FEET, so **no landmark recall is established for any provider**;
  the 6-named-landmarks bar was scored on EMISSION (distinct mapped names), never on correctness.
- The shadow is a re-implementation, pinned equal to the shipped provider on these 24 frames only.
- The two wrong emissions were judged by ONE model (Claude Opus 5, this lane) on 2 frames, no second rater and no adjudication. G304 stays CLOSED AT LIMIT; G306-G308 stay BLOCKED.
TIME about 70 min including the spec. BYTES added 969,377 under `g321_artifact/`; the 24 decoded
frames stay local and uncommitted. SHA-256 `cells.csv` `32522f29d9ae7bce...46cb1335`, `fidelity.json`
`be1a714488...6baeed17d`, `grid.json` `f8c85e9871...4eb6ce7a2`, `g321_semantic_gate.py`
`6abb6a2582...b8a2e9b5df` (278 LOC, under the 300 rail; LF-normalized, recomputed at landing
after the two comment-citation fixes -- the pre-landing value was `25672a56e9...6feb3b2219`). TESTS, per-file only:
`tests/platformkit/tracking/test_g321_semantic_gate.py` -> 7 passed 1.66 s;
`tests/platformkit/test_loc_rail_scope.py` -> 1 passed 0.61 s (landing run on master).
## CORRECTIONS APPLIED AT LANDING (verifier codex-sol, `G321_VERIFY_2026-09-07.md`)
Verdict ACCEPT WITH CORRECTIONS on fix 1b `fc5d83a1d`; no measured number changed by any of these.
- CITATION (`VERIFY:5`, `:31`): the area-floor cite `:88`-`:92` was wrong. Replaced on both memo
  lines with `domains/basketball/tracking/keypoints.py:82` (where `minimum_area = 0.006*width*height`
  is defined) and `:87` (the `if area < minimum_area or float(side_lengths.min()) < 0.15*height`
  line that applies it together with the minimum-side floor).
- NEW GAP (`VERIFY:34`): the shadow parameter comments in `g321_semantic_gate.py:44-45` still cited
  `keypoints.py:88`/`:93`; both updated to `:82`/`:87`. Comments only, no code path touched --
  `tests/platformkit/tracking/test_g321_semantic_gate.py` re-run after the edit, 7 passed.
- NEW GAP (`VERIFY:33`): memo test count was stale at 6 versus the 7 the verifier and this landing
  both reproduce; corrected, with the landing-run timings substituted for the pre-fix ones.
- NEW GAP (`VERIFY:33`): artifact bytes were stale at 969,365, the pre-`versions.txt` figure.
  Corrected to 969,377. METHOD: sum of the on-disk sizes of the ten files under `g321_artifact/`
  as checked out on Windows (CRLF), which is what the original 969,365 measured; the equivalent
  sum of the committed LF blob bytes (`git ls-tree -r -l`) is 968,868, the difference being the
  509 CRLF bytes across `cells.csv`, `grid.json` and `fidelity.json`.
- NEW GAP (`VERIFY:33`), NOT FIXED: the row body of this memo (everything above this section) is
  82 lines against the spec's requested 60; it was 80 before the two citation rewraps here.
  No content was cut at landing -- trimming would drop premise, limitation or citation text that
  the contract requires -- so the overage stands as a disclosed defect of this row.
- The `:39`/`:44` comments on `quad_area_floor`/`require_convex` (`g321_semantic_gate.py:42-43`) are
  stale the same way against the current `_ordered_quad` at `keypoints.py:36`/`:41`. Left as found:
  outside the corrections the verifier listed. Recorded here, not fixed.
