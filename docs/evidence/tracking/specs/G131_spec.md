GAP G131 | sport all | worktree a5 | log cx_g131_jump_statistic_policy_attempt2
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is G107 attempt 2, and it may still be too early. Read
docs/evidence/tracking/g107_jump_statistic_policy_2026-09-02.md,
g127_partial_table_salvage_2026-09-02.md and g109_eligible_table_census_2026-09-02.md first.
WHY G107 REFUSED, and it was right to. It set out to choose a replacement for the harness jump
statistic and stopped because the live pod had 193 tables and **only 6 reached the jump gate**,
below the >= 10 eligible reports its spec required. That refusal is the reason this whole
eligible-denominator discipline exists: the retracted G88 change was accepted on a "0 of 12" impact
that was really 0 of 1.
WHAT MAY HAVE CHANGED. G109 later counted 8 eligible of 196. G114 observed 8 while measuring
something else, noting tennis_07 had grown into eligibility on its own as the live pipeline ran.
G127 then found that of the 68 salvageable partial tables, **7 outcome entries are jump-gate
eligible across 5 distinct current paths** -- but it explicitly did NOT establish whether those 5
are ADDITIONAL to the 8 or already among them. That is the first thing you must settle, and you must
settle it by measurement rather than by adding the numbers together.
STEP 1, THE GATE ON THIS ROW: count the CURRENT distinct jump-gate-eligible tables on the pod. A
table is eligible only if it actually reaches the jump statistic -- not a coordinate-contract
rejection, not INSUFFICIENT_DATA, not empty, not short-circuited earlier. Report the count and list
the tables by path.
  - If the count is **< 10, STOP AND REPORT IT.** Do not measure a policy on fewer. Say what the
    count is and what would raise it. A second honest refusal is a full success and is far better
    than a policy chosen on eight tables.
  - Only if it is >= 10 do you proceed to step 2.
STEP 2, THE MEASUREMENT (only if the gate opens). Choose between candidate jump statistics, with the
rule written down BEFORE any number:
  - The problem, restated from measurement: `jump_p95` is too BLIND (G82: 16 of 16 real oversized
    steps sat above p95, at 0.0455 pct prevalence, while a p95 only trips near 6 pct), and
    `jump_max` is too BRITTLE (G96: both flipped tables run smoothly to 2.79 and 3.21 ft, then a
    single isolated 45.21 / 56.39 ft outlier, so one bad pair in 4,436 condemns a table).
  - G107 preregistered candidate C5 -- max as a WARNING plus a rate-based verdict at 0.50 pct -- as
    the one to re-measure when the denominator allows. Start there, and say if you add others.
  - Score every candidate against BOTH known-real defects: the nyYk 56.39 ft coordinate move that
    G96 confirmed by eye on a static wide shot where no player crossed the court, and the G82
    basketball case where 16 of 16 oversized steps sat above p95. A candidate that misses either is
    disqualified; say so.
  - Report verdict impact against the ELIGIBLE denominator, stated separately from the total pulled.
DO NOT implement, deploy, change tracking_harness.py, move any bar, or touch the pod. The
orchestrator adjudicates and lands. Do not reinstate G88.
ACCEPTANCE RULE:
  metric        = the current eligible-table count; and only if >= 10, per-candidate verdict impact
                  against that eligible denominator plus detection of the two known-real defects
  before        = G107 refused at 6 eligible; G109 counted 8; G127 found 5 eligible paths of unknown
                  overlap
  bar           = NO pass bar. Success is the eligible count established by measurement, and either
                  an honest stop below 10 or a candidate table with one recommendation above it.
  n             = every pod table; state the total read and the eligible count separately, and list
                  the eligible tables
  eye check     = n/a; G96 already did the decisive one. Do not redo it and do not attempt to render
                  tennis_10, whose source is pruned and where three retrieval paths already failed.
  must not move = tracking_harness.py, every bar, every verdict, the pod, the G96 findings, and the
                  coordinate contract
EVIDENCE: docs/evidence/tracking/g131_jump_statistic_policy_attempt2_2026-09-0X.md with the eligible
count and table list first, then either the stop or the candidate table, and a NOT VERIFIED list.
Commit under docs/evidence/tracking/g131_policy2/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live and the corpus is
still growing, so state the moment you took your census.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: none, and do not take the token.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
