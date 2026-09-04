GAP G285 | sport wnba | worktree a5 | log g285_per_person_recall
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO DISK GUARD, NO HOLD RULE. START IMMEDIATELY.**
Everything is committed here:
  - 61 frames at `docs/evidence/tracking/g278_census_stratified_followup_artifact/part_a/frames/`
  - **G284's SEALED per-frame player counts** at
    `docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv`
  - G267's footpoints in `g267_court_space_physical_plausibility_artifact/g267_measurement.json`

**READ THE LANDED G284 MEMO AND THE G284-CONSEQUENCE LEDGER ROW FIRST. THIS SPEC IS SHORT ON PURPOSE.**

**WHY THIS ROW EXISTS.** G284 bounded recall at **0.416 expected player-boxes per visible player**
(365 on-court boxes, 524 visible players, 54 judgeable frames) but **performed no per-person matching**,
so it could only bound the fraction found, never measure it. **That single assumption is the row's main
weakness and it can be removed locally.**

THE QUESTION: **for each visible on-court player, is there actually a detector footpoint on them?**

METHOD:
  1. **RENDER EACH OF G284's 54 JUDGEABLE FRAMES WITH EVERY G270-ON-COURT DETECTOR FOOTPOINT MARKED** --
     a small distinct marker at each footpoint, nothing else drawn, no boxes inferred. **State the marker
     style and size.**
  2. **THE DENOMINATOR IS ALREADY SEALED. DO NOT RE-COUNT PEOPLE.** Use G284's committed per-frame
     visible-player counts as-is. **This is the point: the denominator was fixed before any marker was
     ever shown, so it cannot drift to fit the answer.** **Say that in the memo.**
  3. **JUDGE PER PERSON, NOT PER FRAME.** For each visible on-court player in a frame, record
     **MATCHED** (a marker sits on that person's feet, within a radius you state up front) or
     **UNMATCHED**. **Do NOT count markers and subtract** -- that reproduces G284 and answers nothing new.
     **Record the frame order and the per-person verdicts, and commit them BEFORE computing any total.**
  4. **ALSO RECORD UNMATCHED MARKERS**: markers that sit on no visible person. **Report them separately.**
     They are the per-person view of G273's non-person rate and should roughly agree with it -- **say
     whether they do, and treat a disagreement as a finding, not an error to reconcile away.**
  5. **REPORT: matched / visible = RECALL**, with a 95 pct Wilson interval, plus the unmatched-marker
     count and rate. **Compare against G284's 0.416 upper bound and say in one sentence whether the bound
     held.** **If measured recall EXCEEDS 0.416, that is important** -- it would mean one of G284's
     assumptions failed, most likely that G273's precision transfers to the on-court subset. **Say so
     plainly rather than smoothing it.**
  6. **A MARKER RADIUS IS A JUDGEMENT CALL. State it before judging, and report how many verdicts sit
     near the boundary.** Do NOT tune it after seeing results (contract B10).
  7. **Do NOT re-detect, re-count people, or touch `src/`. Propose no filter, threshold, gate or
     retrain.**

**LIMITS to state, not discover:** ONE shot, ONE clip, ONE labeller. **Occluded players are invisible to
labeller and detector alike, so the denominator remains "visible" players and recall stays inflated
relative to true recall** -- this row narrows G284's assumptions, it does not remove that one.
**Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078): NOT
clip-wide.** G267's detections are ONE non-deterministic draw. **A footpoint is not a box**; a marker
landing on a person means a detection claimed that location, not that it bounded them correctly.
**The population is detector-box observations, not authenticated players.**

ACCEPTANCE RULE:
  metric        = the marker radius stated up front; the committed per-person verdicts and frame order;
                  matched / visible with a Wilson interval; the unmatched-marker count and its comparison
                  with G273's non-person rate; the one-sentence verdict on whether G284's 0.416 bound
                  held; and the count of near-boundary judgements
  before        = recall is bounded at 0.416 with no per-person matching, under three named assumptions
  bar           = **NO pass bar.** **A low measured recall confirms detection as the dominant defect on
                  both axes.** **A measured recall above 0.416 would break one of G284's assumptions and
                  is the more interesting outcome.** **"Too many near-boundary calls to be reliable" is
                  ALSO a full success.** Do not tune the radius, do not re-count, do not move a bar.
  n             = 1 clip, 1 shot, 54 frames, 524 sealed visible players, 1 labeller -- name every
                  denominator in the verdict line
  eye check     = the per-person judgement IS the measurement; a COARSE visual judgement, not the
                  sub-pixel geometric one G257 bounded at 20 px
  must not move = G284's sealed counts and its 54 judgeable frames, G267's records, G270's on-court
                  definition, G273's counts, G278's frames, every threshold and verdict, `src/` and
                  `domains/`, the corpus
EVIDENCE: `docs/evidence/tracking/g285_per_person_recall_2026-09-04.md` with the marker policy, the
committed verdicts, the recall figure and interval, the unmatched-marker analysis, the bound verdict, and
a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Commit the verdicts before computing totals; make
EVERY commit before you finish.** ASCII stdout. **NEVER PARK.**
