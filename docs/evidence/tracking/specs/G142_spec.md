GAP G142 | sport tennis | worktree a2 | log cx_g142_tennis_eligibility_drivers
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is where the evidence now points the whole programme. Read the REACH row in
TRACKING_GAPS_2026-09-01.md and g131_jump_statistic_policy_attempt2_2026-09-02.md first.
WHY TENNIS AND ONLY TENNIS. Five reachability censuses and eleven basketball rows closed the others:
soccer unreachable (>=4 landmarks in 0/100 frames, never more than two independent directions),
football unreachable (a third direction in 0/60, an absolute-yard reference in 0/60), baseball 1/80
= 1.3 pct overhead-only, and basketball has the geometry on screen in 46.2 pct of frames but neither
detection route recovers it (line route 1 of 84 roles available and 0 of 84 assigned correctly;
naive corner detector recall 0/68, precision 0/1,700). Tennis is the sole sport reaching court_feet
(G47: 0 of 15 coordinate-contract rejections).
WHY THIS SPECIFIC QUESTION. The harness cannot settle its own gating statistic: G107 refused at 6
jump-gate-eligible tables, G109 counted 8 of 196, and G131 counted **8 of 203** and confirmed that
G127's five salvage paths all overlap those eight and add nothing. The bar is 10. Tennis is the only
live route to more, and G133 measured tennis tracking at about 1.0 game/hour with 2 of 2 recent
games becoming eligible -- but refused to forecast from n=2, correctly.
THE QUESTION: what distinguishes a tennis game that REACHES the jump gate from one that does not,
and can acquisition be steered toward the first kind?
  (a) ENUMERATE every tennis tracking table on the pod and classify each by its FIRST blocker, using
      G109's bucket vocabulary: reaches the gate, coordinate-contract rejection, INSUFFICIENT_DATA
      (under MIN_FRAMES_FOR_METRICS = 30), empty or header-only, other. State the count you read --
      the corpus is growing while you work, so name your census moment.
  (b) For the eligible ones versus the rest, compare whatever the artefacts actually let you compare:
      source duration, resolution, frame count, rows, coverage, and which acquisition queue or
      search term produced them. Report differences with denominators, not impressions.
  (c) NAME THE DRIVER, if there is one, in one sentence. "Nothing distinguishes them, it is luck" is
      a legitimate and useful answer -- it would mean acquisition cannot be steered and the only
      lever is volume.
  (d) If a driver exists, say concretely what acquisition should prefer and what that would cost.
      Do NOT edit any queue file, change queue_expander, or alter the duration floors; recommend.
  (e) FORECAST, or refuse again with a reason. Given the observed tennis rate and conversion, when
      does the eligible count reach 10? G133 refused at n=2; if you now have more data points say
      so and give the arithmetic with its assumptions, and if you still do not, refuse plainly.
DO NOT change any threshold, the 10-table bar, the coordinate contract, any queue file, the bridge,
or the cookie jar. NEVER KILL ANYTHING ON THE POD -- the track daemon is live and seven bridge lane
workers run under scripts/platformkit/bridge_keeper.
ACCEPTANCE RULE:
  metric        = per-tennis-table first-blocker classification, and the eligible-versus-rest
                  comparison on source and quality attributes
  before        = 8 eligible tables system-wide across three censuses (6, 8, 8); tennis drivers
                  unexamined
  bar           = NO pass bar. Success is every tennis table classified, the comparison reported
                  with denominators, and a one-sentence driver answer. "No driver, only volume" is
                  a full success.
  n             = every tennis table at your census moment; state it, and state the eligible count
                  separately from the total
  eye check     = not required for the classification, but OPEN at least 2 non-eligible tables and
                  confirm the bucket label matches the file. G100 found three "thin" outputs
                  header-only by looking, and labels here have been wrong before.
  must not move = every threshold, MIN_FRAMES_FOR_METRICS, the coordinate contract, every verdict,
                  every queue file, and the bridge
EVIDENCE: docs/evidence/tracking/g142_tennis_eligibility_drivers_2026-09-0X.md with the
classification table, the comparison, the driver sentence, the forecast or its refusal, and a NOT
VERIFIED list. Commit derived tables under docs/evidence/tracking/g142_drivers/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
