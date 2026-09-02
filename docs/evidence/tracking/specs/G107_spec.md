GAP G107 | sport all | worktree a2 | log cx_g107_jump_statistic_policy
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row settles a POLICY question that three prior rows have
circled. Read docs/evidence/tracking/g96_jump_flip_adjudication_2026-09-02.md,
g88_jump_statistic_impl_2026-09-02.md and g82_jump_statistic_limit_2026-09-02.md first.
THE STORY SO FAR, and it is now well measured on both sides:
  - G82: `jump_p95` is BLIND. On real basketball, 16 of 16 oversized steps sit above p95, at a
    prevalence of 0.0455 pct, while the synthetic sweep showed a p95 only trips at 6 pct
    prevalence. A percentile excludes the tail it exists to catch.
  - G88 replaced it with a modal-stride-adjacent `jump_max`, accepted on a re-measured 0 PASS-to-FAIL
    impact. That 0/0 was near-vacuous: 10 of its 12 replay tables never reach the jump gate and one
    more is a full FAIL, so the ELIGIBLE denominator was ONE.
  - On 26 real pod tables `jump_max` is 2 PASS-to-FAIL, and both flips are the only two passing
    tables in the corpus. G88 was retracted under its own pre-registered rule and the pod rolled
    back to f2a4ac0c2.
  - G96 then adjudicated the flips and produced the fact this row turns on. Both maxima ARE
    genuinely modal-stride-adjacent, so the G88 pairing is sound. And the nyYk eye check is
    unambiguous: source frames 20295 and 20300 are a static wide shot, both players stay in nearly
    the same image locations, nobody crosses the court -- yet the stored court coordinate moves
    **56.39 ft**. That is a REAL defect in the data. It is not a player teleport and it is not a
    pairing artefact; it is a coordinate that is simply wrong, and `jump_p95` hid it.
SO BOTH STATISTICS ARE WRONG IN OPPOSITE DIRECTIONS, and that is the finding to act on:
  - p95 is too blind: it cannot see a defect that occurs a handful of times in thousands of pairs.
  - max is too brittle: G96's quantile tables show BOTH tables run smoothly to about 2.8 and 3.2 ft
    and then jump to a single isolated 45.21 / 56.39 ft outlier. One bad pair in 4,436 currently
    condemns an entire table.
THE QUESTION: what statistic, at what bar, correctly separates a table with a handful of bad
coordinates from a table that is broadly untrustworthy? Candidates worth evaluating, and you may
add others:
  (a) a COUNT or RATE of pairs above a physical bar, which is what the defect actually is,
  (b) a very high quantile such as p99.9, which sees further into the tail than p95 without being
      hostage to one row,
  (c) `jump_max` retained but gating a WARNING rather than a FAIL, with a separate rate gate for
      the verdict,
  (d) max with a small tolerated-exceedance allowance.
PRE-REGISTER YOUR DECISION RULE BEFORE YOU MEASURE, and write it in the memo before any number.
**AND FIX THE DENOMINATOR ERROR THAT LET G88 THROUGH -- this is the single most important
instruction in this spec.** The impact bar is NOT "N existing reports". It is: **at least 10 reports
that actually REACH the jump gate**, meaning they are not coordinate-contract rejections, not
INSUFFICIENT_DATA, and not otherwise short-circuited before the statistic is computed. State the
eligible denominator explicitly and separately from the sample size. A rate measured on a
denominator of one is how this whole loop started.
MEASURE ON THE POD CORPUS, not on local retained tables. The pod holds the tables that reach the
gate; local retained tables are overwhelmingly contract rejections, which is exactly why G88's
replay was uninformative. Pull read-only.
REPORT, for each candidate: the verdict impact with its eligible denominator, whether it flags the
confirmed-real nyYk 56.39 ft defect, and whether it flags the G82 basketball case where 16 of 16
oversized steps sat above p95. A candidate that misses either of those two known-real defects is
disqualified, and say so.
DELIVER ONE RECOMMENDATION with its bar. Do NOT implement it, do not change tracking_harness.py, do
not move any threshold, and do not deploy. The orchestrator adjudicates and lands it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-candidate verdict impact stated against the ELIGIBLE denominator, plus
                  detection of the two known-real defects
  before        = p95 blind to 16 of 16 real oversized steps; max fails 2 of 2 passing tables on a
                  single isolated outlier each
  bar           = there is NO pass bar on any candidate. Success is the rule pre-registered before
                  measuring, the eligible denominator stated separately from the sample size, every
                  candidate scored against both known-real defects, and one recommendation.
                  "No candidate separates them" is a full success and it would say the defect is in
                  the coordinates and not in the gate.
  n             = >= 10 pod reports that REACH the jump gate; state that eligible count explicitly
                  and state the total pulled alongside it
  eye check     = n/a; G96 already did the decisive one. Do not redo it, and do not try to render
                  tennis_10 -- its source is pruned and three retrieval paths already failed.
  must not move = tracking_harness.py, every bar, every verdict, the pod, the G96 findings, and the
                  coordinate contract
EVIDENCE: docs/evidence/tracking/g107_jump_statistic_policy_2026-09-0X.md with the pre-registered
rule stated first, the candidate table, the eligible denominator, the two known-defect checks, the
recommendation, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g107_policy/ BEFORE
reporting (A7).
CAUTION FROM TODAY: several lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the track daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none, and do not take the token. This row recommends; it does not change the harness.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
