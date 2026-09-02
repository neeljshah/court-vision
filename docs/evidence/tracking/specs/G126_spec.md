GAP G126 | sport basketball | worktree a7 | log cx_g126_g111_label_audit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This AUDITS a headline number that the orchestrator promoted aggressively. Read
docs/evidence/tracking/g121_corner_pixel_targets_2026-09-02.md and
g111_basketball_reachability_2026-09-02.md first.
WHAT IS AT STAKE, stated plainly so this row is taken seriously. G111 reported basketball court_feet
as geometrically reachable in **147 of 220 seeded frames = 66.8 pct** through four visible
paint-corner points. The orchestrator promoted that into the consolidated four-sport REACH verdict
and used it to REPRIORITISE THE ENTIRE CALIBRATION PROGRAMME -- basketball became the one sport
where detector work is worth doing, and soccer and football were retired. Three lanes (G119, G120,
G123) were dispatched off the back of it.
G121 then tried to label pixel targets for those corners and REFUSED, reporting that **G111's
retained "visible" labels conflict with its committed source renders**: it names a mid-court view
where neither paint rectangle is in the image, and a player close-up with no paint rectangle, both
of which carry visible-corner labels. It fabricated nothing (0 targets) and said so.
G121 IS EXPLICIT THAT IT DOES NOT KNOW WHICH OF THESE IS TRUE, and distinguishing them is the whole
job of this row, because they have opposite consequences:
  (a) **G111's LABELS are wrong** -- someone marked corners visible on frames that do not show them.
      Then 66.8 pct is inflated, the REACH verdict is wrong, and the programme reprioritisation was
      built on a bad number.
  (b) **The LABEL-TO-RENDER ASSOCIATION is wrong** -- the labels are correct for the frames they
      describe, but the committed renders are indexed or named such that G121 compared a label
      against the wrong picture. Then 66.8 pct STANDS and only the artefact wiring is broken.
  (c) **G121 misread** the manifest or the role vocabulary. Then nothing is wrong but this row.
METHOD, and it must be blind to avoid confirming whichever answer is convenient:
  1. Take a SEEDED sample of >= 40 of the 220 G111 frames, stratified so it includes frames labelled
     with 4 visible corners, with some, and with none. State the seed.
  2. WITHOUT reading the G111 label for a frame, decode that frame FROM THE SOURCE CLIP by its
     manifest index and judge by eye how many paint corners are visible. Record your judgement
     first. Reading the label first is the anchoring that would simply reproduce it -- this is the
     same discipline G85 used for tennis and G102 used on its second attempt.
  3. ONLY THEN open the G111 labels and compare, three ways: your judgement versus the G111 label,
     your judgement versus what the committed RENDER for that frame shows, and the G111 label versus
     the render. Those three comparisons are what separate (a) from (b): if your source-decoded
     judgement agrees with the LABEL but not the RENDER, the association is broken and the number
     stands.
  4. REPORT the agreement rate with a Wilson 95 pct interval and a plain verdict naming (a), (b) or
     (c). If it is (a), report your best estimate of the corrected reachability rate on your sample
     and say clearly that the REACH verdict needs revising.
PRECEDENT, so you do not assume high agreement: G76 measured a basketball paint criterion at only
68.6 pct raw agreement, and G85 measured a tennis one at 75.0 pct. Visibility criteria in this repo
have repeatedly been less reliable than they look. Measure it; do not defend it.
DO NOT relabel the G111 set wholesale, do not change its seed or manifest, do not change any
threshold or the coordinate contract, and do not adjust the REACH verdict yourself -- report, and
the orchestrator adjudicates.
ACCEPTANCE RULE:
  metric        = three-way agreement (your blind source-decoded judgement, the G111 label, the
                  committed render) on >= 40 seeded frames, with a Wilson 95 pct interval
  before        = G111 reports 147/220 = 66.8 pct; G121 reports its labels conflict with its renders
                  on at least two named frames; cause unknown
  bar           = NO pass bar. Success is the blind judgement made before the labels are opened, the
                  three-way comparison reported, and a clear verdict of (a), (b) or (c). Any of the
                  three is a full success -- (b) would VINDICATE G111 entirely.
  n             = >= 40 seeded frames stratified across label counts; state the seed and the strata
  eye check     = this row IS the eye check, and it must be done on frames decoded from the SOURCE,
                  not on the committed renders, because the renders are one of the things under
                  suspicion.
  must not move = the G111 sample, seed, manifest and labels, the G121 finding, every threshold, the
                  coordinate contract, and the REACH verdict
EVIDENCE: docs/evidence/tracking/g126_g111_label_audit_2026-09-0X.md with the seed, the blind
judgements committed before the comparison, the three-way agreement table, the verdict, and a NOT
VERIFIED list. Commit under docs/evidence/tracking/g126_label_audit/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
