GAP G189 | sport wnba | worktree a6 | log g189_route_determinism
**MEASUREMENT ONLY. Change NO code.** No bar, threshold, gate, seed, crop, detector setting,
coordinate contract or verdict. `src/` is HUMAN-GATED: run it, never edit it. If you find a fix,
report it as a finding and STOP.
**RUN EVERYTHING ON THE POD.** The local box is 16 GB with other lanes live and two RAM guards have
already fired on this gap's predecessor. The pod has an idle RTX 3090 and 24 GB.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full. Self-check section B.

WHY, and this is the only reason the row exists:
  - **G187** ran `scripts/run_clip.py --video data/footage_corpus/wnba__wnba_01.mp4 --frames 1200
    --no-show --skip-features` on the pod and got **1,104 player rows over 394 player-row frames**.
  - **G188 v2** ran the IDENTICAL command on the IDENTICAL file (2,931,985,407 bytes, 1920x1080) and
    got **1,549 rows over 400 frames** -- a 40 pct difference -- with neither premise frame matching
    (frame 474: 3 survivors vs 2; frame 1377: 4 vs 6).
  - Both ran after the same code deploy; `src/` was never deployed and is constant. The orchestrator
    checked and DISPROVED the mid-flight-deploy explanation on timing (deploy 14:44:47, G187 run
    14:53:28-14:55:40). **The cause is unknown.**

THE QUESTION: **is this route deterministic?** Everything measured through `run_clip.py` depends on
the answer, so it is worth more than any further quality study until it is settled.

METHOD:
  1. Run the SAME command on the SAME file **three times**, back to back, each into its own
     `--data-dir`. Use `--frames 1200` so each run is about two minutes.
  2. Report for each run: player row count, distinct player-row frames, distinct attempted gameplay
     frames, and the survivor boxes at frames 474 and 1377. Put G187's and G188 v2's committed
     numbers in the same table as runs 0 and 0b.
  3. **State whether the three fresh runs agree with EACH OTHER.** That is the deliverable.
     - All three identical -> the route IS deterministic, and the G187/G188 difference has an
       uncontrolled cause still to find. Say so; do NOT guess at it.
     - Three different -> the route is NON-DETERMINISTIC and every measurement taken through it,
       including G187's landed numbers, is one sample of a distribution.
     Either answer is a FULL SUCCESS. **Do not tune, seed, or pin anything to force agreement** --
     that would destroy the measurement.
  4. If and only if they disagree, spend ONE bounded step locating where the variation enters:
     compare the raw detector output at frame 474 across runs. Detector-level variation and
     tracker-level variation are different findings. Report which, or that you could not tell.

MANDATORY:
  - Record the pod GPU state at each run start (`nvidia-smi --query-gpu=utilization.gpu,memory.used`)
    and whether inference ran on GPU or CPU. G187 measured 0-2 pct utilization with up to 964 MiB
    allocated, which is itself unexplained and may bear on determinism.
  - Name the ELIGIBLE denominator on every row (attempted gameplay frames), never the sample size.
  - **Store PER-RUN records in the artifact**, not just a summary table.
  - Quote the exact command and the full source path, byte size and resolution in the memo. Two
    different videos answer to `wnba_01`; the 1080p POD file above is the authoritative one and the
    1280x720 `g130_recensus/` copy is NOT it.

ACCEPTANCE RULE:
  metric        = per-run row/frame counts and the two premise frames' survivor sets, across three
                  fresh runs plus the two committed historical ones
  before        = two runs of one command on one file differ by 40 pct; cause unknown
  bar           = NO pass bar. "The route is deterministic and something else differed" and "the
                  route is non-deterministic" are both FULL SUCCESSES.
  n             = 3 fresh runs (EXISTENCE of variation, not a rate); state the cap and the file
  eye check     = not required; this is a reproduction row, and renders would not add to counts
  must not move = every threshold, seed, crop, backend default, bar, verdict, `src/`, the pod daemon
                  and keeper
EVIDENCE: docs/evidence/tracking/g189_route_determinism_2026-09-03.md with the per-run table, the GPU
states, the verdict, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: only if you add a harness; then a per-file test, pasted. NEVER a full pytest.
POD: run your three jobs there. Never kill, restart or deploy over the daemon or keeper, and do not
wait on the daemon -- it is slow by a known defect (G186) and irrelevant to this row.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
