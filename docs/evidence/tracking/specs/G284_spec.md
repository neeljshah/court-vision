GAP G284 | sport wnba | worktree a5 | log g284_detector_recall_bound
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY): ENTIRELY LOCAL. NO POD STEP, NO DISK GUARD, NO HOLD RULE.**
Everything is already committed in this worktree:
  - **61 full frames** at
    `docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/frames/part_a_0NN.jpg`
    with `blind_manifest.json` giving `span_inclusive [19599, 23399]` and
    `sampled_indices_chronological`.
  - **G267's per-frame detections** at
    `docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`
    (3,801 frame records, 30,071 detections, fields `track_id, source_frame, foot_x_px, foot_y_px,
    court_x_ft, court_y_ft, finite, nearest_previous_track_id, nearest_previous_id_changed`).
**Do NOT call `pod_run`. Do NOT decode video. Do NOT run `du -sm /workspace`** -- its absence locally is
NOT a failure. **The pod is currently occupied by five or more peer lanes; this row is deliberately built
to need none of it. START IMMEDIATELY.**

**READ THE LANDED G273, G280b AND G278 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- PRECISION IS MEASURED, RECALL HAS NEVER BEEN, AND THE ARITHMETIC SAYS IT MAY BE
THE BIGGER PROBLEM.**
G273 measured detector **precision** on broadcast: only **43/72 = 0.597** of retained detections are a
player on the court of play. **Recall is explicitly in G273's own NOT VERIFIED list and no row has
touched it.**

Here is why it matters. Across G267's 3,801 frames the mean is **7.91 finite detections per frame**
(max 21). At G273's 0.597 player rate that implies roughly **4.7 player-boxes per frame -- for a sport
with ten players on court.** **If that holds, the detector is missing more than half the players while
simultaneously emitting non-person boxes, and recall is a defect at least the size of precision.**
**That arithmetic is suggestive, not a measurement. This row measures it.**

**Also settled in advance so nobody re-proposes it: DUPLICATE DETECTIONS ARE NOT THE EXPLANATION.** Across
121,926 same-frame detection pairs, only **0.33 pct are within 1 ft** and **0.74 pct within 2 ft** in
court space, and **0.21 pct within 20 px** in image space. **Over-counting by duplicates is ruled out; do
not spend the row on it.**

THE QUESTION: **how many of the people actually on court does the detector find?**

METHOD:
  1. **PASS 1, BLIND AND SEALED: COUNT PEOPLE, WITH NO DETECTIONS SHOWN.** For each of the 61 committed
     frames, in a randomised order, **count separately: (i) PLAYERS on the court of play, and
     (ii) any OTHER people on the court surface (officials especially).** **Show no detection markers,
     no overlays and no counts from the records** -- if the labeller can see the detections, the count is
     contaminated and the row is worthless. **Commit the order and the counts in their own commit BEFORE
     joining anything.**
  2. **DEFINE "ON THE COURT OF PLAY" ONCE, VISUALLY, AND STATE IT**: inside the painted boundary lines.
     Bench, sideline, crowd and anyone off the painted surface are excluded from both counts. **If a frame
     does not show enough court to judge, record it as CANNOT COUNT and keep that category separate** --
     do not force a number.
  3. **THEN JOIN TO G267's RECORDS** for the same `source_frame`: the count of finite detections, and the
     count whose footpoint projects **on court** under G270's unchanged definition.
  4. **REPORT THE RATIO PER FRAME AND IN AGGREGATE**: on-court detections against counted on-court people.
     Give the median and the distribution, not just a mean. **Report players and players-plus-officials
     separately**, since the detector cannot be expected to distinguish them.
  5. **THIS BOUNDS RECALL, IT DOES NOT MEASURE IT -- SAY SO IN THOSE WORDS.** **No per-person matching is
     performed**, so a frame with 10 people and 5 detections is consistent with 5 people detected once
     each, or with 3 people detected twice and 2 missed. **A count ratio is an upper bound on the fraction
     of people found only if there are no duplicates, and duplicates are rare (0.33 pct within 1 ft) but
     not zero.** State that chain explicitly.
  6. **COMBINE WITH G273's PRECISION TO GIVE A RECALL ESTIMATE WITH ITS ASSUMPTIONS NAMED.** Expected
     player-boxes per frame is roughly `on-court detections x 0.597`; compare against counted players.
     **Name every assumption: that G273's precision applies to the on-court subset, that duplicates are
     negligible, and that the 61 frames are representative of the span.** **If any assumption looks
     shaky, say so rather than smoothing it.**
  7. **MEASURE COUNT AGREEMENT.** **Re-count at least 20 of the 61 frames blind, in a fresh randomised
     order, after Pass 1 is committed**, and report exact-agreement and within-one agreement. **A count
     the labeller cannot reproduce is not a measurement.**
  8. **REPORT BY G278's COMMITTED CATEGORY, DESCRIPTIVELY.** Those frames already carry a court-geometry
     label. **Do NOT condition the sample on it** -- report the ratio broken down by category so a reader
     can see whether recall differs where less court is visible.
  9. **Do NOT re-detect, re-render, or touch `src/`. Do NOT propose a production change, filter, gate,
     threshold or retrain.** **Do NOT move any bar.**
 10. **The population is detector boxes, not authenticated players.** **Name every denominator; never say
     "players" unqualified when you mean boxes.**

**HONEST LIMITATIONS to state, not discover:** **61 frames of ONE camera shot of ONE clip, ONE labeller.**
**Per G278 this span is measurably friendlier than the clip (0.836 against 0.656 court-bearing,
p = 0.0078), so nothing here may be quoted clip-wide.** **Occluded people cannot be counted** -- a player
fully behind another is invisible to the labeller and to the detector alike, so the denominator is
"people visibly on court", **not "people on court", and that inflates apparent recall.** Say so. **The
detector's own class label is `player`, which is its label and not a verified identity.** **G267's
detections are ONE non-deterministic draw** (G241: 808 of 1,201 records differed on an exact re-run).

ACCEPTANCE RULE:
  metric        = the committed blind counts with their randomised order; the per-frame join to G267's
                  detection and on-court detection counts; the ratio distribution with median, reported
                  for players and for players-plus-officials; the bounds-not-measures statement in step
                  5's words; the recall estimate with every assumption named; the re-count agreement
                  (exact and within-one); and the breakdown by G278 category
  before        = precision is 0.597 (G273) and recall has never been measured; the mean is 7.91 finite
                  detections per frame, implying about 4.7 player-boxes for ten on-court players
  bar           = **NO pass bar.** **"Recall is poor" would make detection the dominant defect on BOTH
                  axes and would reframe the programme's priorities.** **"Recall is good and the boxes are
                  simply mislabelled" is equally valuable and points somewhere completely different.**
                  **"Counts are not reproducible" is ALSO a full success** and would mean the method needs
                  per-person matching instead. Do not tune, filter, or propose a threshold.
  n             = 1 clip, 1 shot, 61 frames, 1 labeller, the people and detection counts you state -- name
                  every denominator in the verdict line, and name the detector-box population
  eye check     = the blind count IS the measurement; it is a COARSE counting judgement, not the sub-pixel
                  geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = G267's retained records and span, G270's on-court definition, G273's counts and
                  categories, G278's committed frames, manifest and labels, G233d's published map, the
                  court model, the coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY), the
                  pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g284_detector_recall_bound_2026-09-04.md with the committed blind counts,
the join, the ratio distribution, the bounds statement, the assumption-named estimate, the agreement
figures, the category breakdown, and a NOT VERIFIED list. **The per-frame table must be committed as a
machine-readable file.** **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** Report the sha.
NEVER PARK.
