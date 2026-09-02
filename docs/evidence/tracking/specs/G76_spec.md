GAP G76 | sport basketball | worktree a4 | log cx_g76_paint_criterion_audit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row AUDITS A CRITERION, not a number.
WHY THIS ROW EXISTS: the G68 census reports pooled PAINT_SOLVABLE = 1,029/1,650 = 0.6236
[0.6000, 0.6467]. Before that becomes a verdict and before a solver lane (G75) is built on it, an
orchestrator spot-check cropped tiles at native resolution and found a **verified mislabel**:
`wnba__wnba_02` frame **f192** is labelled PAINT_SOLVABLE and contains NO PAINT AT ALL -- it is
midcourt perimeter action with neither basket in shot, showing only a three-point arc and the
centre-court logo. A second tile (f2112) was arguable but defensible, and a third (f1152,
COURT_NO_PAINT) was correct. See docs/evidence/tracking/g68_criterion_audit/ for the three cropped
tiles and the write-up. So the labelling looks PERMISSIVE AT THE MARGIN, not random.
WHY THE EXISTING RE-READ DOES NOT SETTLE IT, and you must not cite it as if it does: both G68A and
G68D reported a seeded 20-tile re-read with **0 flips**. That measures RELIABILITY, not VALIDITY. A
criterion that is uniformly too permissive reproduces itself perfectly on re-read. Repeating the
same judgement cannot detect a systematically wrong judgement.
TASK:
  (a) WRITE THE DEFINITION FIRST, before re-labelling anything. One paragraph, sharp enough that
      two people would agree: PAINT_SOLVABLE means all FOUR lane lines of ONE paint -- the
      baseline, the free-throw line, and both lane side lines -- are individually discernible with
      enough continuous extent to fit a line to each. Say explicitly what does NOT qualify: a
      three-point arc alone, a centre-court logo, a visible basket with the lane lines out of
      frame, a paint whose far side is occluded by players such that no line can be fitted.
      Commit the definition BEFORE the labels (it is the thing being tested).
  (b) Render ONE clear POSITIVE and ONE clear NEGATIVE example at full tile resolution, annotate
      which four lines you can see in the positive, and commit both. f192 is a known negative and
      is already committed -- use it, and say whether you agree it is a negative.
  (c) RE-LABEL a seeded random sample of >= 120 tiles drawn across all 11 clips, against that
      written definition, WITHOUT looking at the existing label first. State the seed. Looking at
      the prior label before judging is the anchoring that would reproduce the original error.
  (d) Report the DISAGREEMENT RATE against the existing labels, broken down by direction:
      how many the census called PAINT_SOLVABLE that you call otherwise (the permissive error, the
      one that inflates the share), and how many the reverse.
  (e) Give a CORRECTED pooled share estimate with a Wilson interval, derived from the disagreement
      rate applied to the census. State the derivation. Do NOT hand-adjust the number by eye.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = directional disagreement rate against the census labels, and the corrected share
  before        = 0.6236 [0.6000, 0.6467] under the criterion as applied, with one verified
                  mislabel found in three tiles spot-checked
  bar           = THERE IS NO PASS BAR. Success is a written definition, two rendered examples, a
                  blind re-label of >= 120 seeded tiles, and a directional disagreement rate.
                  "The criterion was sound and the disagreement rate is low" is an excellent
                  outcome and would release G68D's verdict and G75.
  n             = >= 120 tiles, seeded, spread across all 11 clips; state per-clip counts
  eye check     = this row IS the eye check, at full tile resolution. The contact sheets downscale
                  each tile; a 2x crop is what made the f192 error visible at all.
  must not move = the existing labels (do NOT edit them -- write yours to a separate file), every
                  harness threshold, and the pre-registered 0.10 decision rule.
WHAT HAPPENS NEXT depends on your number, and it is stated here so it cannot be moved afterwards:
if the corrected share still clears 0.10 comfortably, G68D's verdict is released and G75 proceeds;
if it falls near or below 0.10, the per-frame paint route is a limit result and G75 is cancelled.
Either way the soccer comparison (0.0480 [0.0383, 0.0600]) should be restated against the
corrected number, not the original.
DURABILITY (A7): the definition, both example renders, the blind re-labels and the seed all go
under docs/evidence/tracking/g68_criterion_audit/ BEFORE you report.
EVIDENCE: docs/evidence/tracking/g76_paint_criterion_audit_2026-09-0X.md with the definition, the
two examples, the per-direction disagreement rate, the corrected share with its derivation, an
explicit statement on whether you agree f192 is a negative, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. No scp, no deploy, never kill anything -- another session has live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
