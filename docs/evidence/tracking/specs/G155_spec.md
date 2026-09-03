GAP G155 | sport all | worktree a5 | log cx_g155_pod_readiness_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a READ-ONLY MEASUREMENT of a machine the orchestrator is bringing
up. Move nothing, start nothing, kill nothing.

THE SITUATION, measured rather than assumed. The pod at 213.192.2.83:40193 died on 2026-09-03 and
took 427 ledger rows, roughly 204 tracking tables and an 18 GB footage corpus with it. A replacement
exists at the `pod` alias in ~/.ssh/config.pod (RTX 3090, 24 GB) and the orchestrator is bootstrapping
it WHILE YOU WORK. So the machine is a moving target: your job is to record what is true at a stated
moment, not to make anything true.

DO THIS, entirely read-only:
  (a) Census the new pod at a stated UTC moment: GPU model and VRAM, CPU count, RAM, Python version,
      and which of the pipeline's required packages are importable. Get the required-package list
      from scripts/setup_pod_optimized.sh rather than guessing it.
  (b) Quota headroom, which df CANNOT tell you. `df -h /workspace` reports the CLUSTER and showed
      372,096 GB free while the volume was completely full on 2026-09-02. Measure the tree with
      `du -sh /workspace/*` and report the breakdown. If you want the decisive answer, write ONE
      small probe file and delete it -- that and nothing else.
  (c) Report what is present under /workspace: repo, model weights, footage corpus, staged videos,
      tracking tables, ledger. Give counts and sizes. The honest expected answer for most of these is
      "absent, the old pod had it" -- say so rather than reaching for a substitute.
  (d) Compare against what the daemon actually NEEDS to run one tennis job end to end. Read
      scripts/platformkit/track_daemon.py build_command and follow it to the adapter. List every
      prerequisite and mark each PRESENT or ABSENT at your census moment. That list is the deliverable.
  (e) State the ELIGIBLE denominator for anything you count, never a bare sample size.

DO NOT install anything. DO NOT start, restart or kill any process on the pod -- the orchestrator owns
the daemon and the keeper, and a race here costs real time. DO NOT delete any pod file except your own
probe. DO NOT deploy code.

THE CATCH. The orchestrator is installing dependencies concurrently, so a package that is absent when
you look may be present minutes later. That is not a defect in your measurement, it is why the census
must carry a TIMESTAMP and be phrased as "at 2026-09-03THH:MM:SSZ", not as a standing claim. Say this
explicitly in the memo. If you re-check anything, report both moments.

ACCEPTANCE RULE:
  metric        = the timestamped hardware/software census, the du-measured quota breakdown, the
                  present/absent inventory, and the PRESENT/ABSENT prerequisite list from (d)
  before        = the new pod is known to be bare; nothing about it is measured
  bar           = NO pass bar. Success is a timestamped census and a complete prerequisite list.
                  "Everything the daemon needs is absent" is a full success.
  n             = every prerequisite on the tennis path (CONSTRUCT, exhaustive -- state that the
                  enumeration is complete)
  eye check     = replaced by REPRODUCTION (Q7): every command you ran, quoted, with its raw output
  must not move = every pod process, every pod file, every threshold, the coordinate contract, and
                  every verdict
EVIDENCE: docs/evidence/tracking/g155_pod_readiness_census_2026-09-03.md with the raw command outputs,
the prerequisite table, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: no code change is expected. If you add a script, exactly one per-file test, run only that file.
NEVER a full pytest.
POD: STRICTLY READ-ONLY plus one probe file you delete. NEVER kill or restart anything.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
NEVER PARK: do not poll the pod in a blocking loop; never end waiting.
