GAP G136 | sport basketball | worktree a7 | log cx_g136_recensus_second_pass
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This CONTINUES an unfinished census. Read
docs/evidence/tracking/g130_recensus/review_protocol.md and README.md first -- and NOTHING ELSE from
that directory until step 3 below.
WHAT EXISTS ALREADY, committed at d2b8d999b. G130 ran a source-first 210-frame basketball
reachability census and completed:
  - `g130_recensus/first_pass_source_judgements.csv` -- 210 first-pass judgements,
  - `g130_recensus/first_pass_decision_matrix.csv` -- the per-clip matrix,
  - `g130_recensus/rejudge_selection_manifest.json` -- the blind re-judge subset, already fixed at
    seed 13020260903, a seeded shuffled exact 20 pct subset,
  - `g130_recensus/review_protocol.md`, the contact sheets, and a partially empty
    `second_pass_decision_matrix.csv`.
G130 then stopped and said plainly that it could not honestly report a reachability number without
the blind re-judgement. That refusal was correct and this row finishes the job.
**THE BLINDNESS RULE IS THE WHOLE POINT AND IT IS EASY TO BREAK.** Do the steps in this order:
  1. Read ONLY `review_protocol.md`, `README.md` and `rejudge_selection_manifest.json`. Do NOT open
     `first_pass_source_judgements.csv` or `first_pass_decision_matrix.csv`, and do not print or
     grep them. They contain the answers you are about to independently reproduce.
  2. Judge every frame named in the re-judge manifest, decoded FROM THE SOURCE clip by index, under
     the criterion in `review_protocol.md`. Count visible paint corners per frame. Write your
     judgements to `second_pass_source_judgements.csv` and COMMIT that file before step 3.
  3. ONLY THEN open the first pass, join on audit_id, and compute raw agreement with a Wilson 95 pct
     interval.
  If you open the first pass before committing step 2, the re-judgement is contaminated and this
  row is void -- say so and stop rather than reporting an anchored number. The first G102 attempt
  disqualified itself for exactly this and that was the right call.
THEN REPORT, in this order in the memo:
  (a) The blind self-agreement rate with its interval, FIRST, before any headline.
  (b) The reachability figure -- share of the 210 frames with >= 4 visible paint corners -- with a
      Wilson 95 pct interval, computed from the FIRST pass over all 210 frames.
  (c) A comparison against G111's retracted 66.8 pct and G126's 45-frame reweighted estimate of
      33.8 pct.
  (d) If agreement is below roughly 80 pct, say plainly that the census cannot support a precise
      reachability claim and attach that caveat to the figure rather than presenting it clean.
WHY THIS MATTERS AND WHAT NOT TO PROTECT. G111 reported 66.8 pct, the orchestrator promoted it into
the consolidated REACH verdict and reprioritised the whole calibration programme on it, and the G126
audit then measured G111's labels at 22/45 = 48.9 pct agreement with source frames and retracted it.
This is the replacement number and it must be produced without regard for what would be convenient.
Three rows now show eye labels in this repo less reliable than assumed -- G76 68.6 pct, G85 75.0
pct, G111 48.9 pct -- so a low agreement here is an expected and fully successful outcome, not a
failure of this row.
DO NOT change any threshold, the coordinate contract, the rung ladder or any verdict, do not declare
court_feet for any clip, do not re-draw the sample or change the seed, and do not adjust the REACH
row yourself -- report, and the orchestrator adjudicates.
ACCEPTANCE RULE:
  metric        = blind second-pass agreement against the first pass on the manifest subset, with a
                  Wilson 95 pct interval, reported BEFORE the reachability figure
  before        = G111's 66.8 pct retracted; G126's 45-frame estimate 33.8 pct; G130's first pass
                  complete but unvalidated
  bar           = NO pass bar on either number. Success is the second pass judged and committed
                  before the first pass is opened, the agreement reported first, and the
                  reachability figure given with its interval and any warranted caveat.
  n             = the manifest subset for agreement, and all 210 frames for reachability; state both
  eye check     = this row IS the eye check, from source-decoded frames, not from the contact sheets
  must not move = the G130 first pass, its seed, its manifest and its protocol, every threshold, the
                  coordinate contract, and the REACH verdict
EVIDENCE: docs/evidence/tracking/g136_recensus_second_pass_2026-09-0X.md with the ordering evidence
(the second-pass commit sha, made before the join), the agreement, the reachability figure, the
comparison, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g130_recensus/ alongside
the first pass BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report BOTH shas -- the second-pass commit and the
final evidence commit -- so the ordering is auditable.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
