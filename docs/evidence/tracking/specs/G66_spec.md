GAP G66 | sport tennis | worktree a8 | log cx_g66_player_candidate_labels
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the A7 clause; self-check
every line of section B before you report. THIS ROW PRODUCES A LABEL SET. Nothing else.
WHY THIS ROW EXISTS: G38B stopped at n=0 and was right to. G38 named its decisive experiment -- join
the oversized-jump endpoints to render-attributed real/not-real player labels -- and the orchestrator
(me) told the lane those labels existed in
docs/evidence/tracking/tennis_player_select_limit_2026-09-04/candidates.csv. **They do not.** The
lane checked the schema and the true columns are: match, range_start, range_stop, source_frame,
local_frame, candidate_index, x1, y1, x2, y2, foot_x, foot_y, confidence, detector_track_id. There
is NO label field. 33,632 candidate rows, zero labels. The 21 committed renders are a viewing sample,
not a label set. That correction is the lane's and it stands.
DELIVERABLE: real/not-real labels attached to a defined subset of those candidate rows.
  (a) The candidate rows cover tennis_09, tennis_10 and tennis_nyYk2nPZAwY_720p. G38's tables were
      tennis_02-05, so state the overlap explicitly. If there is none, label on the clips the
      candidates DO cover and say plainly that a later join to G38's own tables will need either
      new tables or new candidates -- do not paper over the mismatch.
  (b) Sample >= 200 candidate rows SEEDED and stratified so the sample is not dominated by one clip
      or one range. State the seed, the strata and the per-stratum counts. Deliberately over-sample
      candidates that participate in a >8 ft stride-adjacent transition, since those are the ones
      G38's question is about, and record the stratum so the sample can be reweighted later.
  (c) For each sampled candidate, render the source frame with the candidate box drawn, LOOK at it,
      and record one label from exactly this set: `player` (one of the two match players),
      `non_player_person` (ball kid, line judge, chair umpire, coach, spectator),
      `duplicate_of_player` (a second box on a person already detected), `not_a_person`, or
      `uncertain` with a one-clause reason. These five are what G38 needs distinguished, and
      `duplicate_of_player` versus `non_player_person` is the distinction that decides the fix.
  (d) Commit the label file AND the rendered crops under
      docs/evidence/tracking/g66_player_candidate_labels/. Durability IS the deliverable (A7).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = label-set completeness, stratification and independence
  before        = 33,632 candidate rows with no label field; G38's decisive experiment unrunnable
  bar           = >= 200 candidates labelled by eye, every one carrying one of the five labels,
                  stratification and seed stated and reproducible, and the labels NOT derived from
                  the selector's own choice (labelling a candidate `player` because the selector
                  picked it is exactly the circularity this row exists to break -- B7/B8)
  n             = >= 200; state the exact count and the per-clip and per-stratum breakdown
  eye check     = this row IS the eye check. Say what you saw, especially the confusable cases:
                  a ball kid at the baseline looks like a player at low resolution and that is
                  precisely why the earlier rectangle proxy failed.
  must not move = every harness threshold including the 8.0 ft jump bar, the selector, the solver,
                  the camera lock, and the coordinate contract.
DO NOT, in this row: compute the three-way jump split, propose a selector fix, or touch the adapter.
That is G38B's job and it becomes runnable the moment this lands. The labeller must not also be the
person tuning against the labels in the same pass.
ALSO REPORT, in one line each: the share of sampled candidates that are `player`, and the share of
candidates participating in a >8 ft stride-adjacent transition that are NOT `player`. The second
number is the direct answer to G38's question on the sample, and reporting it here is fine because
it is a description of the labels, not a fit.
EVIDENCE: docs/evidence/tracking/g66_player_candidate_labels_2026-09-0X.md with the schema
correction restated, the sampling method, the label distribution with Wilson intervals, the two
reported shares, the confusable cases you saw, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only frame work is fine -- the full corpus is there and listed in
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. No scp, no deploy, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
