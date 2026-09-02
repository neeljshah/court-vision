GAP G70 | sport tennis | worktree a8 | log cx_g70_player_vs_bystander
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report.
THIS IS A NEW ROW, NOT A REOPENING OF G26. G26 is CLOSED AT LIMIT after two attempts under loop
rule 2 and stays closed. This is new work on a new premise -- labels now exist that did not exist
for either G26 attempt -- and it takes a new id, exactly as the G12 lineage note in the register
requires. Do not cite G26's attempts as prior art for the acceptance bar.
PREMISE (step 0, reproduce it): G66 labelled 210 tennis player-candidates BY EYE, 70 per clip
across all 15 range strata. Result: **51 player (24.3 pct), 155 non_player_person (73.8 pct), 4
uncertain (1.9 pct)**. On the subset participating in a >8 ft stride-adjacent transition (n=120):
91 non_player_person (75.8 pct), 25 player (20.8 pct), 4 uncertain.
The decisive fact is an EMPTY branch: **not one candidate was labelled `duplicate_of_player` or
`not_a_person`.** So the unstable per-half selection that drives tennis `jump_p95` is not a
deduplication failure and not a spurious blob -- it is OTHER PEOPLE (ball kids, line judges, chair
umpire, coaches) being chosen as the player. That makes this a person-CLASSIFICATION problem.
Reproduce those counts from docs/evidence/tracking/g66_player_candidate_labels/labels.csv before
writing anything. Read g66_player_candidate_labels_2026-09-02.md first.
TASK: build a classifier that separates `player` from `non_player_person` among candidates, and
MEASURE it honestly. Hard constraints:
  (a) FIT AND SCORE ON DISJOINT DATA. Split by CLIP, not by row: train on some clips, evaluate on a
      held-out clip. A row-wise split leaks, because candidates from the same frame are near
      duplicates of each other and would appear on both sides (B8). State the split.
  (b) Report the MAJORITY-CLASS BASELINE alongside every accuracy number. With 73.8 pct
      non_player_person, a classifier that always says "not a player" scores 0.738 and is useless.
      An accuracy that does not clearly beat that baseline is a REJECT and you say so plainly.
      The G17C soccer role lane closed at limit on exactly this and that was the right outcome.
  (c) Report PER-CLASS recall, not just accuracy. The class that matters is `player` (n=51), and it
      is the minority. A model with high accuracy and low player-recall selects nobody.
  (d) Exclude the 4 `uncertain` rows from training and scoring, and say you did.
  (e) Use features that are defensible and state them. Candidates worth trying: position in court
      coordinates when a homography exists, box size and aspect, motion between sampled frames,
      colour against the local background. Do NOT use the selector's own choice as a feature --
      that is the circularity G66 was built to break.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = held-out `player` recall AND held-out overall accuracy, both with Wilson 95 pct
                  intervals, against the majority-class baseline
  before        = no classifier exists; the selector picks a real player 24.3 pct of the time in
                  the labelled candidate pool
  bar           = held-out accuracy clearly above the majority baseline of 0.738 AND held-out
                  `player` recall materially above chance, with the intervals stated. If either
                  fails, this row CLOSES AT LIMIT and reports the number -- an honest limit is a
                  success and the label set remains valuable regardless.
  n             = 206 labelled candidates after dropping `uncertain`; state train and held-out
                  sizes and the per-class counts in each
  eye check     = MANDATORY. Render >= 10 held-out MISTAKES (both directions) and LOOK at them.
                  Say what the model got wrong and why -- a confusion you cannot explain from the
                  picture means you do not yet understand the failure.
  must not move = the selector in production, every harness threshold, the solver, the camera lock,
                  and the coordinate contract. This row builds and MEASURES a classifier; it does
                  NOT wire it into the adapter. Wiring is a separate row with its own before/after.
SCOPE HONESTY: n=51 positives is small. If the honest conclusion is "not enough positives to
separate these classes", say it and state how many more labels would be needed. That is a better
outcome than a model fitted to 51 examples and quoted as working.
DURABILITY (A7): commit the split definition, per-fold predictions and the mistake renders under
docs/evidence/tracking/g70_classifier/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g70_player_vs_bystander_2026-09-0X.md with the reproduced label
counts, the clip-wise split, held-out accuracy and per-class recall with intervals against the
0.738 baseline, the feature list, the mistake renders and what you saw, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: none. If you find yourself editing the tennis adapter, STOP -- that is the wiring
row, not this one.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
