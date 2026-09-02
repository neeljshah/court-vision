GAP G130 | sport basketball | worktree a7 | log cx_g130_basketball_recensus
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This REPLACES a retracted number. Read
docs/evidence/tracking/g126_g111_label_audit_2026-09-02.md and
g111_basketball_reachability_2026-09-02.md first.
WHAT WENT WRONG. G111 reported basketball court_feet as geometrically reachable in 147/220 = 66.8
pct of frames through four visible paint-corner points. The orchestrator promoted that into the
consolidated REACH verdict and reprioritised the whole calibration programme on it. G126 then
audited it blind from the SOURCE clips and found:
  - source versus committed render: **45/45**, so the renders are faithful and the label-to-render
    association is NOT the problem;
  - source versus G111 label: **22/45 = 48.9 pct, Wilson [35.0, 63.0]**.
G111's visibility labels are wrong more often than they are right. Its 66.8 pct is retracted and
G126's reweighted estimate is 33.8 pct -- but that is an ESTIMATE from a 45-frame audit, not a
census, and it must not be quoted as if it were one. This row produces the replacement number.
THE PATTERN THIS ROW MUST NOT REPEAT, and it is now three for three: G76 measured a basketball paint
criterion at 68.6 pct raw agreement, G85 measured a tennis ball criterion at 75.0 pct, and G111's
corner labels came in at 48.9 pct. Eye labels in this repo have never yet been as reliable as the
row using them assumed. So:
  **BUILD THE AGREEMENT MEASUREMENT INTO THE CENSUS, DO NOT BOLT IT ON AFTERWARDS.** A census whose
  own reliability is unknown is not evidence, and discovering that later costs a retraction.
METHOD:
  (a) Draw a fresh SEEDED stratified sample of >= 150 frames across all basketball pod clips. State
      the seed and per-clip counts. Do NOT reuse the G111 labels for anything. You may reuse its
      frame manifest if that helps comparability, but say so explicitly.
  (b) Judge every frame from the SOURCE clip, decoded by index -- not from a pre-rendered image.
      G126 established the renders are faithful, but the source is the ground truth and this row
      should not inherit a dependency it does not need.
  (c) WRITE DOWN THE CRITERION FIRST, as a short operational rule for when a paint corner counts as
      visible, and include at least 3 worked boundary cases. G92 measured that writing a criterion
      down does NOT by itself change decisions, so this is not offered as a fix -- it is offered so
      that the SECOND pass in (d) is judging the same question.
  (d) SELF-AGREEMENT, seeded and blind: re-judge a seeded 20 pct of the frames without seeing the
      first pass, and report raw agreement with a Wilson 95 pct interval. **Report this number
      BEFORE the reachability number in the memo.** If agreement is below roughly 80 pct, say
      plainly that the census cannot support a precise reachability claim and give the reachability
      figure with that caveat attached rather than as a clean result.
  (e) REPORT reachability -- the share of frames with >= 4 visible corners -- with a Wilson 95 pct
      interval, and state it beside G126's 33.8 pct estimate and G111's retracted 66.8 pct.
WHAT THE ANSWER CHANGES, so you know the stakes but do not bend to them: at 33.8 pct basketball is
still far above soccer (0/100), football (a third direction in 0/60) and baseball (1/80 = 1.3 pct),
so it remains the only sport where detector work is a lever that exists. A LOWER number does not
overturn that direction and must not be softened to protect it. A number near zero WOULD overturn
it, and that would be a valuable and fully successful result.
DO NOT change any threshold, the coordinate contract, the rung ladder or any verdict, do not declare
court_feet for any clip, and do not adjust the REACH row yourself -- report, and the orchestrator
adjudicates.
ACCEPTANCE RULE:
  metric        = share of frames with >= 4 visible paint corners, Wilson 95 pct interval; AND the
                  blind self-agreement rate with its own interval, reported first
  before        = G111's 66.8 pct retracted; G126's 45-frame reweighted estimate 33.8 pct
  bar           = NO pass bar on the reachability value. Success is the self-agreement measured and
                  reported BEFORE the headline, the criterion written before judging, and the census
                  reported with its interval. Low agreement honestly reported is a full success.
  n             = >= 150 seeded frames; the re-judged subset is a seeded 20 pct; state both seeds
  eye check     = this row IS the eye check, from source-decoded frames. Commit what you judged.
  must not move = every threshold, the coordinate contract, the rung ladder, every verdict, the G126
                  audit, and the G84/G115 line-recall evidence, which never depended on G111
EVIDENCE: docs/evidence/tracking/g130_basketball_recensus_2026-09-0X.md with the criterion stated
first, the self-agreement reported before the headline, the reachability figure with its interval,
the comparison to 33.8 and 66.8 pct, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g130_recensus/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
