# G304 adjudication batch 1 -- PREREGISTRATION (sealed before any adjudication)

Row: G304 (E1 sealed held-out packet). Batch 1 = the 23 ELIGIBLE rows of the original
60-row sealed inventory. Worktree `C:/Users/neelj/nba-track-a4` (branch `track-a4`).

## 0. Who is adjudicating

- Adjudicator: **claude-opus-5 (MODEL adjudicator, not a human)**, named here as required by the spec.
- Locator pass 1: `gpt-5.6-sol` -- **MODEL**, not a human.
- Locator pass 2: `gpt-5.6-terra` -- **MODEL**, not a human.
- All three raters are models. G280b/G291 measured crop judgements to be rater-sensitive.
  Agreement alone never establishes correctness, and a model adjudicator does not convert two
  model annotations into truth.

## 1. Read-only inputs (not modified by this batch)

- Sealed manifest: `docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json`,
  canonical payload SHA-256 `5806527e2d50c9830a12774e690e440dcda6a4e56fe04b933c676fd48aed14c1`.
- Renders: `C:/Users/neelj/nba-track-a4/g304_local_renders/` (native 1920x1080 JPEG).
- Eligibility: `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv`
  (60 rows; 23 ELIGIBLE, 35 NEGATIVE, 2 UNRESOLVABLE).
- Locator pass 1: `C:/Users/neelj/nba-track-a7/docs/evidence/tracking/g304_locator_pass1_sol_2026-09-07.csv`
  (`visible` is the text TRUE/FALSE).
- Locator pass 2: `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g304_locator_pass2_terra_2026-09-07.csv`
  (`visible` is 1/0).

## 2. Matching rule

Two annotations are the SAME item iff they share **`row_id` AND `landmark_name`** after
whitespace stripping. Column-name differences between the two CSVs are normalized onto that
pair; no positional, nearest-neighbour or fuzzy matching is used, ever. Only rows whose
`row_id` is ELIGIBLE in the eligibility CSV and whose `visible` flag is true in that pass
enter the table. The vocabulary is the shared 15 names: CORNER_NEAR_L/R, CORNER_FAR_L/R,
LANE_BASE_L/R, FT_LINE_L/R, KEY_TOP, THREE_PT_BASE_L/R, CENTER_SIDELINE_NEAR/FAR,
CENTER_CIRCLE_TOP/BOTTOM.

## 3. Agreement threshold

**4 px Euclidean distance in original 1920x1080 pixels** (spec value, quoted verbatim, not
moved). `distance_px = hypot(x1-x2, y1-y2)`.

## 4. What counts as a disagreement (adjudication is MANDATORY for each)

- **DISTANCE**: the item is visible in both passes and `distance_px > 4`.
- **PRESENCE**: the item is visible in exactly one pass (pass1-only or pass2-only).

An item visible in both passes with `distance_px <= 4` is AGREED and is not adjudicated.

## 5. Adjudication procedure (sealed, headless)

For every disagreeing item, renders are produced under `g304_adjudication_batch1/`,
one PNG per frame, containing for that frame:
- the full native frame at half scale with every pass-1 point and every pass-2 point marked
  and labelled, for orientation only;
- per adjudicated item, a **native (1:1, no resampling) 96x96 crop centred on each locator's
  point** and a **256 px context crop centred on each locator's point**; a presence-only item
  renders the one point it has.
The adjudicator judges, from those crops, **which point sits on the named landmark**, or marks
the item both-wrong / not-identifiable. No projection, homography, detector, fitted corner or
prediction of any kind is opened or run; none exists for this packet.

## 6. Per-item outcome vocabulary and the final coordinate

| outcome | meaning | final coordinate |
|---|---|---|
| `agreed` | visible in both, `distance_px <= 4` | **mean of the two points**, rounded to integer px |
| `pass1` | adjudicated: pass 1's point sits on the named landmark | **pass 1's x,y** |
| `pass2` | adjudicated: pass 2's point sits on the named landmark | **pass 2's x,y** |
| `both_wrong` | the landmark is identifiable in the frame but neither point sits on it | **none; label UNRESOLVED** |
| `unidentifiable` | the named landmark is not identifiable in this frame | **none; label UNRESOLVED** |

A `both_wrong` or `unidentifiable` item is RESOLVED-AS-UNRESOLVED: it is counted, never
omitted, and it counts against the instrument. Each item records a one-line reason confined to
the named landmark itself; the reason may not describe or lean on the position of any other
landmark in the frame.

## 7. Structures

Structure of each name, fixed here before adjudication:

- `court_boundary_corner`: CORNER_NEAR_L, CORNER_NEAR_R, CORNER_FAR_L, CORNER_FAR_R
- `lane_boundary`: LANE_BASE_L, LANE_BASE_R
- `free_throw_line`: FT_LINE_L, FT_LINE_R
- `free_throw_circle`: KEY_TOP
- `three_point_arc`: THREE_PT_BASE_L, THREE_PT_BASE_R
- `sideline`: CENTER_SIDELINE_NEAR, CENTER_SIDELINE_FAR
- `center_circle`: CENTER_CIRCLE_TOP, CENTER_CIRCLE_BOTTOM

## 8. Frame-level outcome

A frame is **E1-ready** iff it has **>= 6 resolved landmarks** (outcome in
{`agreed`, `pass1`, `pass2`}) spanning **>= 3 distinct structures** from section 7.
Otherwise the frame is **short**, and the frame row records its resolved count and its
structure count. A short frame is not dropped: it stays in the batch output.

## 9. Bars NOT moved by this batch

The frame-good rule (`p90 <= 12 px AND max <= 24 px` on the six held-out landmarks), the
4 px adjudication threshold, the >= 6 landmarks / >= 3 structures rule and the primary
acceptance bars are quoted from `docs/evidence/tracking/specs/G304_spec.md` and the sealed
manifest byte-identically. Nothing here lowers a bar. Unresolved labels mean **INSTRUMENT NOT
VALIDATED** -- they are NOT omitted frames and NOT successful abstentions.

## 10. Outputs of this batch

- `docs/evidence/tracking/g304_e1_landmarks_batch1_2026-09-07.csv`
- `docs/evidence/tracking/g304_e1_frames_batch1_2026-09-07.csv`
- `docs/evidence/tracking/g304_adjudication_batch1_2026-09-07.md`
- `scripts/platformkit/tracking/g304_adjudicate.py`, `tests/platformkit/test_g304_adjudication.py`
- renders under `g304_adjudication_batch1/` (local; the numbers behind them are in the CSVs)

## 11. Honesty note on ordering (disclosed, not hidden)

Before writing this prereg the adjudicator computed the pairwise distance table -- a
deterministic function of the two read-only locator CSVs with no free parameter, no threshold
chosen from the data and no bar derived from it. Every threshold and rule above is quoted from
the spec and the sealed manifest, not fitted. **No adjudication decision, no per-item outcome
and no frame verdict was formed before this seal.** The seal below predates the first
adjudication render and every outcome in section 6.

## 12. Scope

This batch measures NO registration, NO calibration and NO tracking quality whatsoever. It is
annotation adjudication only. It does not translate into any ledger `passed` field.

<!-- SEAL LINE -- SHA-256 below is over the LF-normalized bytes of everything above this line -->
SEAL_SHA256: 6c091d189c2721807a97b600d99087a3572277d2c52d72a50d0ac605eeff9892
