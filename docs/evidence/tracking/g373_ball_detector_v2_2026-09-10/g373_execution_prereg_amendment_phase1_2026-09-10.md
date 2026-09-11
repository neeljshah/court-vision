# G373 execution preregistration -- AMENDMENT 1 (phase 1 protocol)

Spec: docs/evidence/tracking/specs/G373_spec.md. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q1, Q6.
Amends (never edits) docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/g373_execution_prereg_2026-09-10.md, whose SEAL sha256 8f504e3712db5e7d4f408383061a67e4ac912b6388a8b8e2f367a6cfbea5b0cb was recomputed over its LF-normalised bytes above its seal line and MATCHES.

Why this amendment exists: the base prereg names a blind full-frame native pass, optional 256-pixel crops, native diameter max(box_w, box_h), and per-frame/p90/missingness reporting, but it does NOT state the numeric reference usability bar, the >= 30 pair minimum, the consequence of failing that bar, the extra-frame sample sizing/spacing/deduplication rule, the rater identities and emission schema, or the phase split. Q1 requires the protocol sealed before the first phase-1 metric. No metric, rating, inference, fetch, decode, hash, or pod command precedes this commit.

## Phase split

PHASE 1 (this commit onward): binding premise replay, decode-cache identity verification, reference v2 construction over the sealed keys, the sealed extra-frame sample, and the development label set. NO ARM IS SCORED IN PHASE 1.
PHASE 2 (a later commit, only after phase 1 is committed and its usability bar is read): arms A8/A9/A10 under the base prereg, and exactly one held-out candidate run. Phase 2 does not score at all if the reference usability bar below is unmet.

## Reference v2 rating protocol

Sheets. One sheet per frame key. Each sheet is the NATIVE 1920x1080 decoded frame, JPEG, at most 200000 bytes, quality stepped down only as needed to meet that cap; the pixel dimensions are never reduced. A sheet carries no candidate box, no detector score, no arm name, no previous centre, no v1 rating, no burned-in text, and no causal strip. The v1 sheet builder (960-pixel panel plus a 320-pixel causal strip) is NOT reused.

Raters. Two independent primary raters, terra and sol, run as separate codex lanes on the PC under distinct CODEX_HOME values, each seeing only the sheet and the fixed instruction. Neither rater sees the other's output, the v1 ratings, or any detector output. Batches are at most 40 sheets. Ratings are appended to ratings_v2.csv and committed after every batch.

Emission schema. ratings_v2.csv fields: frame_key, rater, label, box_x, box_y, box_w, box_h, cx, cy, pass, reason. label is exactly one of VISIBLE, ABSENT, UNKNOWN. A VISIBLE rating MUST carry an integer box in NATIVE pixels with box_w >= 1, box_h >= 1, and the box inside 0 <= x, x+w <= 1920, 0 <= y, y+h <= 1080; cx = box_x + box_w/2 and cy = box_y + box_h/2 are derived, never rated directly. ABSENT and UNKNOWN ratings carry an empty box and MUST NOT fabricate one; their frames are retained. pass is full_frame or crop_refine.

Crop pass. After the full-frame pass only, a rater may be shown a 256-pixel crop centred on THAT RATER'S OWN full-frame box, for refinement of that same box. A rater is never shown a crop derived from the other rater's box, from an adjudicated box, from a v1 centre, or from any detector output. A crop pass may move a box; it may not create a box on a frame the same rater called ABSENT or UNKNOWN, and it may not change a label. Both the full-frame and any crop_refine row are archived.

Adjudication. The finisher adjudicates blind from the sheets alone, without the detector, without v1 labels, and without knowing which rater produced which row. A frame is adjudicated when the two raters disagree on label, or both call VISIBLE and their centres differ by more than the native matching tolerance for that frame. The adjudicated result is written to reference_v2.csv with the adjudicator recorded; unadjudicated disagreements are reported as missingness, never dropped.

Geometry. diameter = max(box_w, box_h) in native pixels. Centre disagreement is the Euclidean distance between the two raters' derived native centres. Every median and p90 names its population explicitly and separately.

Labels. The v1 ratings.csv, ratings_terra.csv, ratings_sol.csv and every other sealed G363 artifact are READ ONLY and are never edited. reference_v2.csv is a separate census archived beside the v1 census; the two are reported side by side and no v1 row is silently repaired.

## Reference usability bar (FIXED; never moved)

Over the both-VISIBLE pairs, median centre disagreement <= 0.5 x median native diameter, with at least 30 such pairs. Both medians name their populations separately. Reported alongside and never in place of the median: per-frame disagreement, p90, and missingness over ALL scheduled keys.

Consequence, fixed here: if the bar is unmet, or reference completeness fails, the reference v2 is reported LIMIT and PHASE 2 DOES NOT SCORE ANY ARM. The bar is not lowered, and no substitute bar is introduced. A LIMIT reference is an honest result, not a failure.

## Extra-frame sample (sealed as a fixed list BEFORE any rating)

Population: the decoded frames of DEVELOPMENT sections only, as named by the development rows of the sealed frames.csv and re-fetched with the G361 pinned recipe at the format_id recorded per section in the sealed sources.csv. No held-out game and no held-out section contributes a single frame. A game that appears in the held-out split is excluded from the extra sample entirely, even if it also appears in development.

Sizing: from the supply math, roughly 733 extra frames are needed in expectation at the observed 156/332 visibility rate to reach 500 usable development boxes. The sealed sample size is that expectation rounded to the number of frames the even sampler actually yields under the deduplication rule below; the realised size is reported against the expected size. This is an expectation, not a quota guarantee, and the sample is NEVER replenished after any detector score is seen.

Spacing: evenly spaced indices over each section's complete decoded frame sequence, never a head slice, computed by the sealed even sampler over the whole set.

Deduplication: two selected frames from the same section must be at least 30 decoded frame indices apart, and no selected frame may equal or be a causal neighbour (t-1, t-2) of any sealed reference key.

Retention: ABSENT and UNKNOWN outcomes on extra frames are retained in the census and reported; only VISIBLE adjudicated boxes count toward the box quota.

Provenance: dev_boxes.csv records, per box, the frame_key, section, game, format_id, section sha256, section bytes, decoded frame index, native width and height, both rater rows, the adjudicated box, and the sheet sha256.

## Development label set quota

At least 500 unique adjudicated development boxes drawn from at least 5 distinct development games. Uniqueness is by frame_key; two boxes on causal-neighbour frames of one another do not both count. If the quota is unmet the development label set is reported LIMIT, A8 is LIMIT, and A10 is unavailable, exactly as the base prereg states.

## Execution accounting

This commit computes and quotes no metric. It authorises no arm score, no evaluator call, no ledger charge, and no candidate selection. Nothing under src/, kernel/, api/, intel/, data/registry/, /workspace/deploy, /workspace/data, /workspace/nba-ai-system or /workspace/wt/a7 is written by phase 1; /workspace/wt/a7/data/g363_cache is read only. The daemon is never touched. Every phase-1 artifact is committed by explicit pathspec in the lane worktree.
SEAL sha256 c48de409cb5d708bc28a9ba3c90cc7220b27af75632566aa5fb0000a81e5ff22
