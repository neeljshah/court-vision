GAP G118 | sport tennis | worktree a6 | log cx_g118_temporal_agreement_power
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This row RESOLVES an inconclusive result by adding the one thing it lacked: n.
Read docs/evidence/tracking/g102_ball_label_temporal_2026-09-02.md first.
WHAT G102 FOUND, and it did the procedure correctly on its second attempt (attempt 1 disqualified
itself for reading prior labels before the blind pass, which was the right call). Blind labels were
committed BEFORE the G85 join, in the required order. Result on the overlap:
  **24/29 = 82.8 pct, Wilson 95 pct [65.5, 92.4]**, against the still-frame baseline of
  **45/60 = 75.0 pct [62.8, 84.2]**.
That is +7.8 percentage points, and G102 was explicitly honest that the intervals overlap heavily,
so no improvement is proven. It is a directional hint, not a result. The chain behind it is worth
remembering: G65 refused to label invisible balls, G78A/B/C disagreed 96.7 / 84.4 / 27.7, G85
measured 75 pct blind agreement, G92 wrote an exemplar card, and G98 step 0 measured that the card
changed 0 of 109 labels. Writing the criterion down more carefully has already been measured and
does not work. MOTION is the remaining untested input, and it now has a hint but not an answer.
THE ONLY THING MISSING IS SAMPLE SIZE. 29 overlapping rows cannot separate 75 pct from 83 pct.
  (a) EXTEND the blind strip-labelling to a substantially larger overlap with the G85 blind set --
      target every row where an overlap is possible, and state how many that is. If the achievable
      overlap is still small, say so up front and state what precision it can buy BEFORE labelling,
      so nobody discovers afterwards that the row could not have answered its own question.
  (b) FOLLOW THE SAME ORDER G102 FOLLOWED, which is what made its result trustworthy: derive frame
      identifiers without reading any ball_visible value, render the 3-frame strips, label blind,
      COMMIT the labels, and only then open prior labels and join. Reuse the committed G102 strips
      where they exist rather than re-rendering them; do NOT re-label a row G102 already labelled
      blind -- pool it.
  (c) REPORT pooled agreement with a Wilson interval and state plainly whether it now separates from
      the 75.0 pct baseline. The decision rule is pre-registered here: the strip method is judged
      BETTER only if its interval's lower bound exceeds the still-frame point estimate of 75.0 pct.
      Write that rule in the memo before the number.
  (d) IF IT STILL DOES NOT SEPARATE, say so and stop. That closes the labelling branch: neither a
      written criterion nor temporal context moves agreement, which would mean the ball is not
      reliably recoverable from this footage and the effort belongs in acquisition. That is a full
      and valuable result, not a failure.
DO NOT relabel the chunk labels, the G85 blind labels, the G92 card or the G102 blind labels, do not
change any harness threshold, and do not touch the y-gate or the coordinate contract.
ACCEPTANCE RULE:
  metric        = pooled blind strip-versus-G85 agreement with a Wilson 95 pct interval
  before        = 24/29 = 82.8 pct [65.5, 92.4] versus still-frame 45/60 = 75.0 pct [62.8, 84.2];
                  intervals overlap, nothing proven
  bar           = the PRE-REGISTERED rule above: better only if the lower bound exceeds 75.0 pct.
                  Failing that bar is a full success and closes the branch.
  n             = state the achievable overlap BEFORE labelling and the final pooled n after; both
                  numbers go in the memo
  eye check     = this row IS the eye check. Commit every strip you labelled from.
  must not move = every prior label set, the G85 seed, the pooled 110/150 count, every harness
                  threshold, the y-gate, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g118_temporal_agreement_power_2026-09-0X.md with the achievable
overlap stated first, the pre-registered rule stated before the number, the pooled agreement and
interval, the separation verdict, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g118_temporal_power/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a6, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
