GAP G146 | sport all | worktree a7 | log cx_g146_pod_throughput_headroom
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A THROUGHPUT question, now that the supply side finally works.
WHAT CHANGED TONIGHT. The footage bridge was repaired twice on 2026-09-02. First a stale yt-dlp
(2026.07.04 against a current 2026.08.19) capped every download at about 10.4 MB with a mid-stream
403 -- proven not to be a cookie problem because a no-cookie run failed identically at 10.37 MB.
Second, and this was the real stall, the attempt ladder planned a 16-minute SECTION for any video
over about 20 minutes and burned all eight section attempts before any full-file attempt; both
routes to a section are dead (default client 403s under ffmpeg, player_client=web now returns zero
media formats). With sections disabled, staging grew 51 MB in 6 s against 0 KB in 100 s before.
So full games are landing again -- one KBO game tracked at 162,557 rows.
THE QUESTION: with supply restored, is the POD now the bottleneck, and where is its headroom?
  (a) MEASURE pod GPU utilisation over at least 20 minutes with several samples, alongside the
      number of concurrently running tracking jobs. One instantaneous nvidia-smi reading is
      meaningless here: jobs are bursty and the GPU sat at 0 pct for a day while the queue was full.
      Report the sample times.
  (b) MEASURE the queue depth at the pod: how many complete .mp4 files sit in data/footage_bridge
      waiting, and how that changes over the window. A stage that keeps growing means the daemon is
      the constraint; a stage that keeps emptying means acquisition still is.
  (c) The daemon runs with --workers 10 (pid 4035, started long before tonight). Establish from the
      ledger how many jobs it actually runs CONCURRENTLY in practice, and whether that approaches
      10. Note that track_daemon.py documents two very different timeout budgets -- 12,000 s for the
      adapter path and 5,400 s for the clip path, the latter sized around a checkpoint cliff -- so
      long-running jobs can occupy slots for a long time.
  (d) STATE THE BOTTLENECK in one sentence: acquisition, upload bandwidth, GPU, or daemon
      concurrency. Support it with the numbers, not with an impression.
  (e) RECOMMEND, do not apply. If the daemon should run more workers, say so with the evidence and
      the risk. Do NOT restart or reconfigure the daemon: it is long-running, other work depends on
      it, and there is a standing never-kill rule for the pod.
DO NOT kill, restart or reconfigure ANY pod process. Do not change the daemon, its worker count, any
timeout, any threshold, or the coordinate contract. READ-ONLY on the pod throughout.
ACCEPTANCE RULE:
  metric        = GPU utilisation samples over >= 20 minutes, concurrent job counts, and pod stage
                  depth over the same window
  before        = supply was broken all day; pod utilisation under working supply never measured
  bar           = NO pass bar. Success is a sampled utilisation series with times, the stage-depth
                  trend, the observed concurrency, and a one-sentence bottleneck call. "Acquisition
                  is still the bottleneck" is a full success.
  n             = >= 6 samples across >= 20 minutes; state each sample time
  eye check     = n/a. Reproduction = the sampled series with timestamps.
  must not move = every pod process, the daemon and its worker count, every timeout, every
                  threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g146_pod_throughput_headroom_2026-09-0X.md with the sampled series,
the stage-depth trend, the concurrency finding, the bottleneck sentence, the recommendation, and a
NOT VERIFIED list. Commit derived tables under docs/evidence/tracking/g146_throughput/ BEFORE
reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly. Never kill anything.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token -- READ it, do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
