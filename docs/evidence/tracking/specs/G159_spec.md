GAP G159 | sport all | worktree a5 | log cx_g159_supply_not_workers
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A7 and Q8; self-check
section B before reporting. This is a MEASUREMENT of a live system. Move nothing, start nothing, kill
nothing, and do NOT change the worker count.

THE CLAIM TO TEST, which is the orchestrator's and may well be wrong. The instinct after acquiring a
256-core, 1 TiB, RTX 3090 pod is to raise the daemon's worker count and "push it hard". The
orchestrator's reading of the live system on 2026-09-03 is that this would achieve **nothing**,
because the binding constraint is SUPPLY, not pod capacity:

  - the daemon runs `--workers 10` and was observed with exactly ONE active job and one staged file;
  - the footage bridge runs seven local lanes, and downloads are FULL broadcasts of roughly 1.7-2.2 GB;
  - a rough local reading was ~1.5 MB/s per lane, ~10.7 MB/s aggregate, i.e. one lane's 2 GB game
    takes about twenty minutes to arrive;
  - downloads run LOCALLY on purpose. See the datacenter-block history: fetching from the pod is not
    a lever that exists.

**Falsify or confirm this properly.** If supply really is binding, "raise workers" is a non-fix and
saying so plainly is the deliverable. If it is NOT binding, the orchestrator is wrong and that is the
better result.

MEASURE over a stated window of at least 30 minutes, all read-only:
  (a) Local download throughput: sample the bridge staging directory repeatedly and report per-lane
      and aggregate MB/s, with the sampling interval stated. Do not infer it from two points.
  (b) Pod-side occupancy over the same window: how many tracking jobs are live at each sample, out of
      the configured worker count. Report the distribution, not just a mean. Use
      `ps -eo pid,etimes,args` and NOT `pgrep -f`, which matches the ssh command line running the
      check itself and reports phantoms.
  (c) Per-job service time from the ledger: `seconds` per completed job, and games completed per hour.
      Name the ELIGIBLE DENOMINATOR (completed jobs in the window). Never a bare sample size.
  (d) Put (a) and (c) together into the one number that settles it: **games arriving per hour versus
      games the pod can complete per hour at the current worker count.** If arrival is the smaller
      number, supply binds and raising workers cannot help. Say which it is.
  (e) THE CONFOUND YOU MUST HANDLE, and the row is weak without it: a separate defect is known to
      stall the daemon. `_finish` calls `adjudicate` calls `decoded_frame_count` calls
      `ffprobe -count_frames`, synchronously, inside the poll loop, so the daemon claims nothing while
      a finished job is being counted (this is G156's row -- read it and do not duplicate its fix).
      That stall depresses pod occupancy for a reason that has nothing to do with supply. Separate the
      two: report occupancy with the stall time excluded as well as included, or if you cannot
      separate them, say so and label the occupancy figure CONFOUNDED rather than quoting it clean.
  (f) Quota, because it bounds the whole plan: `MAX_POD_BACKLOG` is 24 and games are ~2 GB, so a full
      backlog alone is ~48 GB against a ~50 GB quota. Measure current usage with `du`, not `df` (df
      reports the cluster and showed 372,096 GB free while the volume was FULL). Report how many
      games fit before the quota binds, counting the corpus that retained sources accumulate in.
      RECOMMEND only. Do not change MAX_POD_BACKLOG or delete anything.

DO NOT change the worker count, MAX_POD_BACKLOG, any threshold, the coordinate contract, or any
verdict. Do not delete a single pod file. Do not restart or kill the daemon, the keeper or the bridge.

ACCEPTANCE RULE:
  metric        = local aggregate MB/s; pod job-occupancy distribution; per-job seconds and games/hour
                  completed; arrival rate versus completion rate; games-until-quota
  before        = "raise the workers" is an untested instinct; supply and capacity have never been
                  compared on the same clock
  bar           = NO pass bar. Success is the comparison made over a stated window with the ffprobe
                  stall handled honestly. "Supply binds, raising workers is a non-fix" and "capacity
                  binds, here is the headroom" are both full successes.
  n             = >= 30 minutes of samples at a stated interval; state the completed-job count
  eye check     = replaced by REPRODUCTION (Q7): every command quoted with its raw output and its
                  timestamp
  must not move = the worker count, MAX_POD_BACKLOG, every threshold, the coordinate contract, every
                  verdict, and every pod file and process
EVIDENCE: docs/evidence/tracking/g159_supply_not_workers_2026-09-03.md with the sample series, the
two rates, the confound treatment, the quota arithmetic, and a NOT VERIFIED list. Commit the raw
samples under docs/evidence/tracking/g159_supply/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: STRICTLY READ-ONLY. Everything on it is LIVE. Never kill or restart anything.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
NEVER PARK: sample on a schedule you control and then STOP. Do not sit in a blocking wait, and never
end your turn waiting for the window to pass -- take the samples you have and report them.
