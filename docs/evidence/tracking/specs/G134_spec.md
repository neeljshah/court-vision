GAP G134 | sport basketball | worktree a3 | log cx_g134_grouping_stability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. Three rejected attempts have converged on ONE stage. Read
docs/evidence/tracking/g132_additive_candidate_union_2026-09-02.md and the G129 memo first.
WHAT THREE ROWS ESTABLISHED, each preregistered and none tuned after the fact:
  - G115 baseline: paint-line detection recall 25/68 visible lines = 36.76 pct, reproduced TWICE, so
    the pipeline is deterministic.
  - G120 fragment merging: REJECT, recall fell to 24/68.
  - G123 CLAHE contrast: REJECT, recall fell to 23/68, recovering NONE of the 17 low-contrast misses.
  - G129 traced the losses: 70 pct to CLAHE changing the upstream proposal set, 30 pct to merge
    group geometry, and 0 pct to greedy correspondence, top-N eviction or non-determinism.
  - G132 unioned the original and enhanced segment sets so nothing could be removed. Recall ROSE for
    the first time, 25/68 to 28/68 = 41.18 pct, but **only 24 of the 25 baseline matches survived**,
    so the union is NOT additive and it was rejected on that ground.
That last result is the important one. Every original segment was still present, and a previously
matched line still stopped matching. The only stage that can do that is GROUPING:
`candidate_line_group_details` re-partitions over whatever segment set it is handed, so adding
segments elsewhere in the frame can change which group a true line's segments end up in, or change
that group's fitted geometry until it falls outside the correspondence tolerance.
THE QUESTION: how unstable is grouping, and can it be made stable without changing what it accepts?
  (a) MEASURE THE INSTABILITY FIRST, before proposing anything. For the 30 frozen G84 frames, run
      grouping on the baseline segment set and on the G132 union set, and for each true line that
      matched in the baseline, report whether its matching group SURVIVED, MOVED (same segments,
      different fitted geometry), ABSORBED (its segments joined a larger group) or FRAGMENTED. Give
      the distribution. Name the single line G132 lost and classify it.
  (b) IDENTIFY THE SENSITIVE PARAMETER. Grouping is called as
      `candidate_line_group_details(..., 5.0, 10.0)`. Establish what those two arguments control by
      reading the code, and report which of the four outcomes above each governs. Quote the code;
      do not infer from the call site.
  (c) PROPOSE STABILITY, do not tune acceptance. The aim is that a group which matched a true line
      keeps matching when unrelated segments are added elsewhere -- for example by grouping
      locally rather than globally, or by seeding groups deterministically. State your proposal in
      one paragraph and PRE-REGISTER it before measuring. Do NOT change 5.0 or 10.0 to make recall
      go up: that is tuning acceptance, it is B8 self-fit against the frozen sample, and it would
      invalidate every comparison back to G115.
  (d) RE-MEASURE under the frozen protocol at 98b7d6974 on the SAME 30 frames and 68 visible lines.
      Report recall AND paired precision before and after, plus the baseline-match survival count,
      which is the number that decides whether stability was achieved. **Survival must be 25 of 25.**
  (e) IF STABILITY IS ACHIEVED, re-run the G132 union on top of it and report recall and precision.
      That is the combination the whole chain has been building toward: a union that cannot lose a
      line because grouping no longer moves under it. If stability is NOT achieved, say so and stop.
DO NOT change 28.0 / 5.0 / 10.0, line_calibration.py, the frozen protocol, the G84 sample or seed,
the G115 visibility labels, any harness threshold, or the coordinate contract. Do not touch src/,
kernel/, api/, scripts/team_system/ or intel/.
CONTEXT, and do not overstate it: G111's 66.8 pct basketball reachability was RETRACTED after the
G126 audit measured its labels at 22/45 = 48.9 pct agreement with source frames; the working
estimate is 33.8 pct and G130 is re-censusing. Basketball is still the only sport where detector
work is a lever that exists, but do NOT cite 66.8 pct anywhere.
ACCEPTANCE RULE:
  metric        = the group-outcome distribution for baseline-matched lines under an enlarged
                  segment set; then recall, paired precision, and BASELINE-MATCH SURVIVAL out of 25
  before        = union recall 28/68 with survival 24/25, rejected for non-additivity
  bar           = NO pass bar on recall. Success is the instability measured and classified, the
                  proposal preregistered, and survival re-measured. Survival of 25/25 is what makes
                  a recall gain adoptable; anything less is another honest REJECT and is a full
                  success.
  n             = the same 30 frames, 68 visible lines and 25 baseline matches; state all three
  eye check     = REQUIRED for the lost and moved groups. Render the baseline grouping and the
                  enlarged-set grouping side by side for at least 5 affected lines.
  must not move = every detector and grouping parameter, line_calibration.py, the frozen protocol,
                  the G84 sample and seed, the G115 labels, every harness threshold, and the
                  coordinate contract
EVIDENCE: docs/evidence/tracking/g134_grouping_stability_2026-09-0X.md with the instability
distribution first, the quoted parameter semantics, the preregistered proposal, before/after recall
and precision, the survival count, the renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g134_grouping/ BEFORE reporting (A7).
CAUTION: another session is committing into the main checkout concurrently. Work inside your
worktree and commit there with explicit pathspecs only.
TEST: exactly one new per-file test; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
