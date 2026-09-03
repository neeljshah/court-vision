GAP G187 | sport wnba, ncaa_basketball | worktree a5 | log g187_basketball_end_to_end
**MEASUREMENT ONLY. Change NO production code.** No bar, threshold, gate, coordinate contract or
verdict. `src/` is HUMAN-GATED: you may RUN it, never edit it. If a fix seems needed, report it as a
finding and STOP.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full. Self-check section B before
reporting. Q8 premise-first.

WHY (landed today, do not re-derive):
  - **G181**: five thin attempts on `wnba_01` and `ncaa_basketball_IB-_u4gW3ds` all died with the
    same ledger tail -- `_build_court` calls `cv2.resize(map_img, ...)` and OpenCV raises
    `!ssize.empty()`. 0 rows, no verdict.
  - **G186b**: the cause was a MISSING `resources/2d_map.png` on the pod (3 files under `resources/`
    against 93 locally; `cv2.imread` returns None for a missing file, so it failed 45 lines later).
    The asset is now deployed and `imread` returns (695,1241,3) with the resize succeeding.
  - **G186c**: the pod is not a git repo and was running the bootstrap snapshot. 4,327 `.py` files
    under the two non-gated trees are now deployed at hash parity with master.
  - **NOTHING DOWNSTREAM IS MEASURED.** G186b explicitly refused to claim these games now track.
    That is this row's job.

THE QUESTION: does a basketball clip now produce tracking rows end to end, and if not, where does it
stop NOW?

METHOD:
  1. Q8 first: re-confirm on the pod that `resources/2d_map.png` loads and that both corpus files are
     present. If either is false, STOP and say so.
  2. Run ONE bounded clip through the same route the ledger tail came from (`_build_court` is in
     `src/pipeline/unified_pipeline.py`; find the runner that reaches it -- `scripts/run_clip.py` is
     the likely entry). **Bound it with a frame cap** -- prior timing on this box is ~10 fps steady
     state, so a 6,000-frame run is ~10-15 min and a full clip is 30-45 min. Pick a cap you justify.
  3. Report exactly ONE of: rows produced (with counts), or the NEW failure point with its traceback.
     **A new failure is a FULL SUCCESS for this row** -- the deliverable is where it stops now, not a
     working pipeline.
  4. **Measure GPU utilization WHILE it runs.** Sample `nvidia-smi --query-gpu=utilization.gpu,
     memory.used --format=csv,noheader` at least 10 times across the run and report the series. The
     orchestrator measured the 3090 at 0 pct / 1 MiB with the daemon idle; whether inference actually
     reaches the GPU is unknown and matters for every future throughput decision.
  5. If rows ARE produced, report `coordinate_space`, row count, and frames covered -- name the
     ELIGIBLE denominator (frames the run attempted), never the sample size. Do NOT adjudicate; do
     not write a ledger row; the orchestrator owns verdicts.

DO NOT kill, restart or deploy over the pod daemon or keeper. The daemon is currently stuck in an
`ffprobe -count_frames` (a known issue being fixed in G186) and has zero `adapter_run` children --
**do not wait on the daemon and do not try to unstick it.** Run your clip as your own process.
Do not delete any footage; retention is unimplemented and 10 reader-required sources were already
lost to premature deletion (G183).

ACCEPTANCE RULE:
  metric        = rows produced with counts and coordinate_space, OR the new failure point with its
                  traceback; plus the GPU utilization series
  before        = 5 attempts, 0 rows, all dying at cv2.resize on a missing asset now restored
  bar           = NO pass bar. "It now fails later, at X" is a FULL SUCCESS and is the most likely
                  outcome. Do not tune anything to force rows.
  n             = 1 clip, bounded (EXISTENCE, not a rate); name the clip and the frame cap
  eye check     = if rows are produced, render 5 evenly spaced frames with overlaid positions and say
                  whether the players are on the court where the rows claim
  must not move = every bar, the coordinate contract, every verdict, `src/` (human-gated), the pod
                  daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g187_basketball_end_to_end_2026-09-03.md with the outcome, the GPU
series, the frame cap and its justification, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: if you add any harness under scripts/platformkit/, a per-file test for it, pasted. NEVER a full
pytest.
POD: this row RUNS a job on the pod, which is expected. Everything else stays read-only and batched.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
