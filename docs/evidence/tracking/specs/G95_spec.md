GAP G95 | sport football | worktree a5 | log cx_g95_football_calibration_survey
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A SURVEY plus a feasibility measurement. Read
docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md and
docs/evidence/tracking/g47_contract_rejection_census_2026-09-02.md first.
WHY FOOTBALL AND WHY NOW. The G47 census measured 119 of 187 pod harness reports failing on
coordinate_contract and nothing else, and football is the LARGEST single block at **30 of 42** --
larger than baseball (66/93 of a bigger denominator), larger than soccer (15/25), larger than
basketball (8/12). Nine football clips sit in the pod corpus. Football has NEVER been quality
scored: every one of its reports dies at the coordinate contract before any quality metric is
reached, so its tracking could be excellent or worthless and no artefact in this repo would show
the difference. That is the gap.
FOOTBALL GEOMETRY IS THE FRIENDLIEST IN SPORT AND ALSO THE MOST DECEPTIVE, and the memo must say
both. Friendly: yard lines every 5 yards across the full width, hash marks, sidelines, goal lines
and end lines, all high-contrast white on a uniform field, far denser than any other sport here.
Deceptive: yard lines are PERIODIC. Every 5-yard stripe looks like every other one, so a solve keyed
on stripes alone can land a whole number of yards off with every internal residual looking perfect.
That is aliasing, it is silent, and it is the specific way this sport fails. The painted NUMBERS and
the asymmetric hash-mark spacing are what break the periodicity. Any landmark scheme you propose
must say how it resolves WHICH yard line it is looking at, or say plainly that it cannot yet.
DO THIS, IN ORDER, AND STOP WHEREVER THE ANSWER ARRIVES:
  1. SURVEY what already exists. scripts/platformkit/tracking/football_fieldview.py and
     football_snap.py are in the tree, and scripts/platformkit/calibration/keypoint_calib.py has a
     CANONICAL_LANDMARKS registry. Report whether football has a canonical landmark set at all,
     whether any detector emits one, and where the chain breaks. Soccer is the cautionary case: it
     has a complete validated solve stack that can never run, because its detector emits 1 landmark
     against a MIN_LANDMARKS of 5. Check for the same shape of dead end here before assuming
     anything is missing or anything is usable.
  2. MEASURE landmark visibility on a seeded sample of >= 100 frames spread across ALL nine
     football clips. For each frame record which named landmark families are visible: sideline,
     goal line, end line, yard-line stripes and how many, hash marks, painted numbers, and whether
     any number is legible enough to identify the yard line. Report the distribution. State the
     seed and the per-clip counts, and commit the labels.
  3. ANSWER ONE QUESTION in one sentence: is football calibration-limited in the same way soccer
     is (the geometry is on screen and no detector emits it), or is it limited by something else
     you can name? If the numbers are rarely legible in broadcast framing, that is a decisive
     finding about aliasing and it belongs in the answer.
DO NOT build a solver, do not promote any football clip to court_feet, do not declare a coordinate
space, and do not touch any harness threshold. This row buys the information that a solver row
would otherwise have to guess at.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-family landmark visibility share across the nine clips, plus the share of
                  frames with at least one LEGIBLE yard number
  before        = football never quality scored; 30 of 42 reports contract-only rejections
  bar           = there is NO pass bar. Success is the survey being complete, the visibility
                  distribution measured, and the one-sentence answer given. "Football broadcast
                  framing rarely shows a legible number" is a fully successful outcome and it
                  changes what the next row builds.
  n             = >= 100 seeded frames across all nine clips; state the seed and per-clip counts
  eye check     = REQUIRED, and it is most of the work. Legibility of a painted number is an eye
                  judgement and cannot be inferred from a detector score. Commit the renders.
  must not move = every harness threshold, the coordinate contract, every existing verdict, and
                  every file under the human-gated trees
EVIDENCE: docs/evidence/tracking/g95_football_calibration_survey_2026-09-0X.md with the existing
stack survey, the visibility distribution, the aliasing answer, the renders, and a NOT VERIFIED
list. Commit labels and renders under docs/evidence/tracking/g95_football_survey/ BEFORE reporting
(A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the tracking daemon and seven footage
bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
