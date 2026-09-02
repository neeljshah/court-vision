GAP G109 | sport all | worktree a2 | log cx_g109_eligible_table_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row measures the SYSTEM's binding constraint. Read
docs/evidence/tracking/g107_jump_statistic_policy_2026-09-02.md and its
g107_policy/pod_table_snapshot.csv first -- that snapshot is your starting point, do not rebuild it
from scratch if it already answers part of this.
THE NUMBER THAT TRIGGERED THIS. G107 set out to choose a jump statistic and could not, because on
the live pod **193 tracking tables exist and only 6 reach the jump gate.** It refused rather than
measure a policy on six rows, which was correct. But the refusal exposes something larger than the
jump question: the entire quality-gate apparatus of this system -- every threshold, every bar, every
verdict that is not a coordinate rejection -- is currently exercised by SIX tables out of 193.
That means almost every gate in the harness is effectively untested against real data, and no
statistic question can be settled until the eligible population grows.
THE QUESTION: for each of the 193 pod tables, WHY does it not reach the quality gate, bucketed, and
which single change would add the most eligible tables?
  (a) Bucket every table by the FIRST thing that stops it. The buckets to expect, and you should
      confirm rather than assume them: coordinate_contract (rows declare image_px for a sport that
      requires court_feet), INSUFFICIENT_DATA (under MIN_FRAMES_FOR_METRICS = 30, a G80 verdict),
      metric_local scope (scored but PASS_METRIC_LOCAL / FAIL_METRIC_LOCAL, which cannot enter a
      court-feet pass count), empty or header-only output, and unknown-sport routing. Report exact
      counts and the count per sport.
  (b) ORDER MATTERS AND MUST BE STATED. A table can fail several of these at once; bucket it by
      what stops it FIRST, and say what the ordering is. A table counted in two buckets inflates
      both and would make the ranking in (c) wrong.
  (c) RANK THE LEVERS. For each bucket, how many tables would become gate-eligible if that bucket
      alone were fixed? That ranking is the deliverable. Be honest about which levers are
      reachable: G91 and G101 established that soccer court_feet is unreachable from this corpus by
      any point or line method, so "solve soccer calibration" is not a lever that exists today, and
      a ranking that lists it as the top lever would be misleading.
  (d) TENNIS IS THE CONTROL AND DESERVES ITS OWN PARAGRAPH. G47 measured tennis at 0/15
      coordinate-contract rejections -- it is the one sport that reaches court_feet. So why are only
      6 tables gate-eligible in total when tennis alone has had 13 to 15 tables? Find out what
      happened to the tennis tables specifically. If G80's insufficient-data verdict moved a large
      share of them, say so with the count; that would mean the eligible population SHRANK when a
      correct change landed, which is a real and important side effect worth naming plainly rather
      than hiding.
  (e) STATE THE ONE SENTENCE: what is the binding constraint on this system's ability to test its
      own gates, and what is the cheapest thing that relaxes it.
DO NOT change any threshold, any verdict, the coordinate contract, or anything on the pod. Do not
re-track or re-score anything into a durable artifact. This row counts.
NEVER KILL ANYTHING ON THE POD -- the track daemon, its keeper, seven footage bridge lanes and other
sessions' processes are live, and the corpus is growing while you work.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = table counts per first-blocking bucket, per sport, plus the eligible-table gain
                  per lever
  before        = 193 tables, 6 gate-eligible, reasons unbucketed
  bar           = there is NO pass bar. Success is every table bucketed by its FIRST blocker with
                  the ordering stated, the levers ranked by eligible-tables-gained, the tennis
                  question answered with counts, and the one-sentence constraint. A finding that no
                  cheap lever exists is a full success and it redirects the programme to
                  acquisition.
  n             = all pod tables; state the exact count you read, since it is growing -- G107 saw
                  193 and the corpus has been taking new games all evening
  eye check     = n/a; this is a census over verdicts. But do OPEN at least 3 tables from the
                  largest bucket and confirm the bucket label matches what is in the file. G100
                  found three "thin" outputs were header-only by doing exactly that, and a label
                  believed without one look is how 165 rows went unexamined.
  must not move = every threshold, every verdict, the coordinate contract, the pod, and the G107
                  snapshot
EVIDENCE: docs/evidence/tracking/g109_eligible_table_census_2026-09-0X.md with the bucket table, the
stated ordering, the lever ranking, the tennis paragraph, the three opened tables, the one-sentence
answer, and a NOT VERIFIED list. Commit derived tables under
docs/evidence/tracking/g109_eligibility/ BEFORE reporting (A7).
CAUTION FROM TODAY: several lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended, which had to be restored by hand. Work inside your
worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
