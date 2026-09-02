GAP G100 | sport all | worktree a11 | log cx_g100_pod_job_outcome_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A THROUGHPUT census. The pod is the scarce resource and most
of what it produces is currently discarded.
THE NUMBERS, read by the orchestrator from the live pod ledger
(/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl, 397 rows, 184 distinct games):
  tracked  179
  thin     165
  timeout   50
  corrupt    3
So **215 of 397 job outcomes are thin or timeout** -- 54 pct. More than half of every GPU-hour the
pod has spent produced a result the pipeline itself classifies as too little or unfinished. Nobody
has ever explained the `thin` bucket, and it is the largest failure class in the system.
WHY NOW: the footage bridge was dead from 2026-09-01 until 21:40 today (a hardcoded SSH port that
had drifted; fixed at 03a34eef8), so the pod is about to receive a sustained multi-sport backlog.
Whatever makes 54 pct of jobs unusable is about to be applied to a lot of new footage. Measuring it
before the backlog lands is worth far more than measuring it after.
ANSWER THESE, IN ORDER:
  (a) What EXACTLY does `thin` mean? Find where the daemon writes it and quote the condition. Do not
      infer it from the name. track_daemon.py and track_daemon_done.py are the places to look; the
      adjudication lives in `adjudicate` / `retain`.
  (b) Break `thin` down by SPORT and by ADAPTER PATH. track_daemon.py routes CLIP_SPORTS (wnba,
      basketball, ncaa_basketball, nba) through run_clip.py and everything else through the adapter
      registry, and those two paths have different timeouts (5,400 s versus 12,000 s) for reasons
      the file documents at length. If thin is concentrated on one path or one sport, the fix is
      specific and cheap.
  (c) Break `timeout` down the same way, and check the documented quantisation hazard: the comment
      at track_daemon.py explains that unified_pipeline checkpoints every 2,000 frames and never
      flushes the residual, so a basketball job killed at frame 1,999 yields four rows. Measure how
      many of the 50 timeouts died before their first checkpoint and therefore returned nothing.
      That is recoverable GPU time and it is countable.
  (d) Report the ROW COUNT distribution for thin jobs. A job with 4 rows and a job with 4,000 rows
      should not share a label, and if they do that is itself the finding.
  (e) Name the single largest recoverable bucket and estimate the GPU-hours it represents, from the
      `seconds` field already in the ledger. Estimate, clearly labelled as an estimate.
DO NOT change the daemon, any timeout, any threshold, or anything on the pod. Do not re-run any
job. This row counts what already happened; changing the budget is a separate adjudicated decision
that needs this census as its input.
NEVER KILL ANYTHING ON THE POD. The track daemon (pid 4035) and its keeper are running, seven
footage bridge lanes are uploading, and other long-running processes belong to another session.
Read the ledger and the logs; touch no process.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = thin and timeout counts broken down by sport and adapter path, the row-count
                  distribution within thin, and the pre-first-checkpoint timeout count
  before        = 179 tracked / 165 thin / 50 timeout / 3 corrupt over 397 rows, unexplained
  bar           = there is NO pass bar. Success is the `thin` condition quoted from the code, the
                  breakdowns measured, and the largest recoverable bucket named with an hours
                  estimate. "Thin is correct and those jobs really were worthless" is a fully
                  successful outcome and it closes a large open question.
  n             = all 397 ledger rows; state the count you actually read, since the daemon is
                  writing new rows while you work
  eye check     = not the primary evidence, but spot-check at least 3 thin jobs by opening their
                  tracking output and confirming it really is thin. A label believed without one
                  look is how 165 rows went unexamined this long.
  must not move = the daemon, every timeout budget, every threshold, every pod process, the
                  coordinate contract, and the ledger itself
EVIDENCE: docs/evidence/tracking/g100_pod_job_outcome_census_2026-09-0X.md with the quoted
condition, every breakdown, the spot checks, the recoverable estimate, and a NOT VERIFIED list.
Commit any derived tables under docs/evidence/tracking/g100_pod_census/ BEFORE reporting (A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, and that is strict here. Never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a11,
no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token, and this row does NOT need to edit it. Read it,
do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
