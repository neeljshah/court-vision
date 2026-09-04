GAP G280b | sport basketball | worktree a5 | log g280b_amateur_blind_precision
**READ `docs/evidence/tracking/specs/G280_spec.md` FIRST for context, then follow THIS file.** G280's
Part A is DONE AND LANDED. **This row is Part B only, and Part B is now a smaller, cleaner job than it
was, because the blind packet is already sealed in git.**

**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY): ENTIRELY LOCAL. THERE IS NO POD STEP AND NO DISK GUARD.**
Everything you need is committed in this worktree under
`docs/evidence/tracking/g280_amateur_footage_trackability_artifact/blind_packet/`:
**72 crops in `blind_renders/`, the presentation order in `blind_presentation_order.csv`, an EMPTY
`blind_verdicts.csv`, and `blind_order_commitment.json`** which already records
`sample_size 72`, `sample_seed 28020260904`, `blind_seed 28020904`, the crop policy, and
**`unblind_map_sha256 = 4bb76cd6da4c094fcd7a903671cb0006b6c60c20cebabc00a96270a7330e8a32`.**
**Do NOT call `pod_run`. Do NOT decode video. Do NOT run `du -sm /workspace`** -- its absence locally is
NOT a failure. **NO HOLD RULE APPLIES; start immediately.**

**WHY THIS RE-ISSUE EXISTS.** G280's lane completed three byte-identical tracker runs and prepared the
blind packet, then **ran out of budget and committed nothing.** I committed its work. **The packet is now
sealed in git history with EMPTY verdicts and a committed unblind-map hash, which is a stronger protocol
than the original single-lane design: the seal provably predates every verdict.**

THE QUESTION: **what fraction of the amateur clip's retained detections are actually people, and how does
that compare with broadcast?**

METHOD:
  1. **VERIFY THE SEAL BEFORE JUDGING ANYTHING.** Confirm `blind_renders/` holds 72 crops, that
     `blind_presentation_order.csv` has 72 rows, that `blind_verdicts.csv` is empty of verdicts, and
     **that the committed `unblind_map_sha256` matches the unblind map you will later use.** **If the hash
     does not match, STOP and report it** -- that would mean the seal is broken and no verdict from this
     packet could be trusted.
  2. **CLASSIFY ALL 72 CROPS BLIND, IN THE COMMITTED PRESENTATION ORDER**, using **G273's four categories,
     UNCHANGED**: **(a) PLAYER on the court of play; (b) PERSON, not a player in play -- official, coach,
     bench, photographer, spectator; (c) NOT A PERSON -- floor marking, equipment, scoreboard, graphic,
     shadow, artifact; (d) CANNOT JUDGE.** **Keep (d) separate and never merge it.** **Do not redefine or
     refine a category** -- comparability with G273 is the entire point of the row.
  3. **COMMIT THE FILLED `blind_verdicts.csv` IN ITS OWN COMMIT BEFORE UN-BLINDING.** Then un-blind and
     report.
  4. **REPORT THE FOUR COUNTS AND FRACTIONS**, with (a) as the detector's useful yield and **(b)+(c)
     reported together as the boxes that arguably should never enter tracking**, exactly as G273 did.
  5. **COMPARE AGAINST G273's BROADCAST BASELINE WITH A TWO-PROPORTION TEST.** G273 measured
     **43/72 = 0.597 PLAYER** and **15/72 = 0.208 NOT A PERSON** on broadcast. Report pooled p, SE, z and
     the **nominal** two-sided p **for the (a) rate and for the (c) rate separately.**
     **OVERLAPPING CONFIDENCE INTERVALS ARE NOT A TEST -- do not reason from interval overlap.** **State
     that the p is nominal, with no correction for the many comparisons in this programme.**
  6. **ALSO REPORT WHERE EACH CLASS SITS in image coordinates**, descriptively. **Do NOT propose a spatial
     filter, threshold or gate** -- G269 showed how easily a filter fakes an improvement.
  7. **PUT THE BOX-DENSITY OBSERVATION IN CONTEXT, CAREFULLY.** G280 recorded **24,078 detections over
     about 1,243 processed frames, roughly 19.4 boxes per processed frame**, on footage where at most a
     dozen people are on court. **Your classification is what makes that interpretable.** **Do not assert
     causation and do not call it a false-positive rate** -- it is a box count, and your four categories
     are what turn it into a precision statement.
  8. **Make NO court-space, calibration, speed or track-length claim.** There is no map for this clip, and
     `step_count = 0` because the production tracker emits every third frame -- **that is settled and is
     not this row's subject.**
  9. **The population is detector boxes, not authenticated players**, and `cls=player` is the DETECTOR'S
     label, not a verified identity. **Name every denominator; never say "players" unqualified.**

**HONEST LIMITATIONS to state, not discover:** **ONE amateur clip, 120 seconds, ONE camera, ONE labeller,
and -- unusually for this programme -- ONE DETERMINISTIC draw**, since G280 showed three runs are
byte-identical, so re-running would add nothing. **72 of 24,078 retained detections is a sample**: give
its spread and do not present fractions as exact. **A footpoint-centred crop is not the detector's box**;
it shows the neighbourhood the detection claimed, not the extent, so "not a person" means nothing
person-like is at that location. **Category (b) is a judgement about role, not identity**, and courtside
people in amateur footage are often ambiguous -- **expect (d) to be non-trivial and do not suppress it.**
**This cannot support any claim about amateur footage as a class.** Eye-label reliability in this
programme has never cleared 80 pct blind agreement on four measured criteria.

ACCEPTANCE RULE:
  metric        = the seal verification including the unblind-map hash check; the committed filled
                  verdicts; counts and fractions for (a)-(d) with (d) separate and the (b)+(c) grouping;
                  the two-proportion tests against 0.597 and 0.208 with pooled p, SE, z and nominal p; and
                  the positional breakdown by class
  before        = the amateur clip has 24,078 retained detections at about 19.4 boxes per processed frame
                  and NO precision measurement of any kind; broadcast precision is G273's 0.597 PLAYER and
                  0.208 NOT A PERSON
  bar           = **NO pass bar.** **"Amateur precision is much worse than broadcast" would be a major
                  finding for the any-video goal.** **"It is comparable" would be the first evidence that
                  the detector transfers, and is equally valuable.** **A large (d) share is ALSO a full
                  success** and would mean amateur crops are simply harder to judge. Do not tune, filter,
                  or propose a threshold.
  n             = 1 clip, 1 deterministic draw, 72 classified detections of 24,078 retained, 1 labeller --
                  name every denominator in the verdict line, and name the detector-box population
  eye check     = the blind classification IS the measurement; it is a COARSE categorical judgement, not
                  the sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = the sealed packet, its presentation order, its commitment JSON and its unblind-map hash;
                  G273's four categories, counts and sealed order; G280's three runs and their sha256;
                  every other threshold, bar and verdict; `src/` and `domains/` (READ and IMPORT ONLY);
                  the pod daemon and keeper; the corpus; the bridge partials
EVIDENCE: docs/evidence/tracking/g280b_amateur_blind_precision_2026-09-04.md with the seal verification,
the committed verdicts, the four counts with groupings, the two-proportion tests, the positional
breakdown, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit
BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish -- G280 ended with all its
work uncommitted and I had to commit it for the lane.** Report the sha.
NEVER PARK.
