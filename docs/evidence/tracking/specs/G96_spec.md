GAP G96 | sport tennis | worktree a2 | log cx_g96_jump_flip_adjudication
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row ADJUDICATES a retraction. It decides whether a
rejected change was actually right. Read the G88 row in TRACKING_GAPS_2026-09-01.md first.
WHAT HAPPENED. G88 replaced the harness gating statistic `jump_p95` with a modal-stride-adjacent
`jump_max`. It was accepted on a re-measured verdict impact of 0 PASS-to-FAIL / 0 FAIL-to-PASS.
Deployed to the pod and re-measured over 26 REAL pod tables it is **2 PASS-to-FAIL, 0 FAIL-to-PASS**,
and both flips are the ONLY two passing tables in that corpus:
  - data/tracking/g89_tennis_10/tracking_data.csv          PASS -> FAIL  `jump_max 45.21 > 8.00`
  - data/tracking/g89_tennis_nyYk2nPZAwY_720p/...          PASS -> FAIL  `jump_max 56.39 > 8.00`
Its own spec pre-registered that a non-zero impact is a REJECT, so G88 is retracted and the pod is
rolled back to f2a4ac0c2 (G80 and G81 kept). The original 0/0 was near-vacuous: 10 of the 12
replayed tables are coordinate-contract FAILs that never reach the jump gate and one more is a full
FAIL, so the eligible denominator was ONE.
THE QUESTION THIS ROW ANSWERS, and it is the only one: are those two flips TRUE POSITIVES?
A tennis court is 78 ft long. A 45.21 ft or 56.39 ft step between MODAL-STRIDE-ADJACENT frames is
physically impossible for a human. So either the tables contain real tracker teleports and their
PASS was false -- exactly the blindness G82 measured, where 16 of 16 real oversized steps sat above
p95 -- or the modal-stride pairing in the G88 implementation is picking pairs that are not actually
adjacent, and the number is an artefact of the new code.
YOU MUST NOT DECIDE THIS BY PREFERENCE. Both outcomes are good outcomes. "G88 was right and those
two PASSes were false" restores a rejected change on evidence. "G88 has an implementation bug"
protects the corpus from a bad gate. Report whichever the measurement gives.
METHOD:
  (a) On BOTH flipped tables, compute the full distribution of modal-stride-adjacent step lengths.
      Report the modal stride found, the eligible pair count, and the step-length quantiles up to
      the max. ONE 45 ft step among tens of thousands is a very different object from hundreds of
      them, and the fix differs: an isolated outlier argues for a max being brittle, a heavy tail
      argues the table is genuinely broken.
  (b) For the largest handful of steps on each table, print the actual rows: track_id, both frame
      numbers, both coordinates, the frame delta, and the declared coordinate_space. Verify by hand
      that the two frames really are modal-stride apart. If the pair spans a gap, the G88 pairing
      is wrong and that is the answer.
  (c) EYE CHECK, and this is what actually settles it: render the two frames of the largest step on
      each table, side by side, with the track marked. Look at them. Either the tracked box jumps
      across the court between two adjacent frames -- a real teleport, and the PASS was false -- or
      it does not, and the coordinates are lying about something the pixels do not show. Commit
      the renders. No amount of quantile arithmetic substitutes for this.
  (d) State whether the same signature exists on tables that were ALREADY failing. If real
      teleports are everywhere and only these two tables happened to pass, that is a statement
      about the corpus, not about these two clips.
DELIVER A RECOMMENDATION IN ONE SENTENCE: reinstate G88, reinstate it with a named implementation
fix, or leave it retracted. The orchestrator adjudicates; you supply the measurement and the
recommendation.
DO NOT change tracking_harness.py, do not re-deploy anything to the pod, do not move any bar, and
do not re-land G88. If you conclude G88 was right, say so and stop -- reinstating it is a separate
decision that belongs to the orchestrator.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = modal-stride-adjacent step-length distribution on both flipped tables, plus a
                  hand-verified row dump of the largest steps, plus the rendered frame pairs
  before        = two PASS tables flipped to FAIL on 45.21 ft and 56.39 ft, cause undetermined
  bar           = there is NO pass bar. Success is the distribution measured, the largest steps
                  hand-verified as genuinely adjacent or not, the frames looked at, and a
                  one-sentence recommendation. Either recommendation is a full success.
  n             = both flipped tables in full; at least the top 5 steps per table dumped and at
                  least the top 1 per table rendered
  eye check     = REQUIRED and decisive. A verdict reached without looking at the two frames is
                  NOT VALIDATED under A7 no matter how clean the arithmetic is.
  must not move = tracking_harness.py, every bar, the pod, every verdict, and the coordinate
                  contract
EVIDENCE: docs/evidence/tracking/g96_jump_flip_adjudication_2026-09-0X.md with the distributions,
the row dumps, the renders, the recommendation, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g96_jump_flips/ BEFORE reporting (A7). Note that G93 was blocked today
because the G84 renders it needed had not survived, so durability here is not a formality.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull the two tables. Never kill anything -- the track daemon and seven footage
bridge lanes are live. Do NOT deploy.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none, and do not take the token. This row measures; it does not change the harness.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
