GAP G228 | sport all | worktree a7 | log g228_degraded_handler_reachability
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: **READ and IMPORT only** -- you
may import and CALL production code from your own process, and you may monkey-patch WITHIN YOUR OWN
PROCESS to force a failure, but **write no file into `src/`.** Build in `scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- G211 is measuring per-frame cost there and G220b is
uploading to it. **LOCAL LOAD GUARD: this box has crashed twice from concurrent unbounded load**
(`footage_bridge.py:95`). Two other lanes are running locally. **Bound every decode to a few thousand
frames, run one at a time, keep temporary files in the scratch area and delete them, reporting bytes
freed.**

**WHY THIS ROW EXISTS -- G218 FOUND 19 DEGRADED-SUBSTITUTE HANDLERS AND ONLY TWO HAVE BEEN TESTED.**
G218 classified them by STATIC reading and said plainly it obtained no runtime evidence for any.
**G221 then tested exactly two and got one of each answer, which is why this method is worth
extending:**
  - **Defect A (`unified_pipeline.py:283-286`, G218 rank 1) CONFIRMED**: a hand-truncated clip emitted
    322 frames then the ordinary EOF sentinel, **indistinguishable at the consumer API from a clean
    control** -- both `(False, None, -1)`. Only process stderr differed.
  - **Defect B (`unified_pipeline.py:1505-1521`, rank 11) REFUTED as reachable**: `cv2` returns a
    nonzero frame count first and short-circuits the file-size guess. The counterfactual stands (the
    guess would have flipped the stride) but the branch is not taken.
**So "static classification" and "runtime reachability" genuinely diverge, and only measurement tells
them apart.**

**ALREADY SETTLED -- DO NOT RE-TEST THESE THREE:**
  - ranks 1/2 (decoder EOF) -- CONFIRMED by G221.
  - rank 11 (file-size frame estimate) -- REFUTED by G221.
  - **rank 6 (`advanced_tracker.py:286`, configured player detector reverting to base `yolov8n`) --
    the orchestrator has already shown this is UNREACHABLE in current configuration**: the upgrade
    branch runs only when `_yolo_stem != "yolov8n"` (`:276`), `_yolo_stem = _cfg.get("yolo_model",
    "yolov8n")` (`:260`), and **a repo-wide search found nothing that ever sets `yolo_model`**. Record
    that as settled and move on.

**THE HANDLERS THIS ROW TESTS, in G218's blast-radius order.** For each, the question is the same:
**does the branch actually execute at runtime on real input, and if it does, is anything observable?**
  1. **rank 3 -- `unified_pipeline.py:1171`**: a failed M1 sanity check leaves validation true, so **an
     unvalidated recovered homography can be installed.** **This is the one that matters most**, because
     calibration is the gate in front of 91 pct of the ledger and an unvalidated homography would be a
     silent coordinate-integrity defect.
  2. **rank 4 -- `advanced_tracker.py:500`**: a failed ByteTrack per-game reset **retains the previous
     game's tracker object and association state.** **First establish whether one process ever handles
     more than one game** -- if every `adapter_run`/`run_clip` invocation is a fresh process handling a
     single clip, this branch cannot fire in production and that is the finding. **Say which.**
  3. **rank 5 -- `advanced_tracker.py:490`**: the same question for the per-game colour tracker.
  4. **rank 9 -- `unified_pipeline.py:609`**: failed detector inference returns a **plausible empty
     detection list**, which is indistinguishable from an ordinary no-player frame.
  5. **rank 10 -- `unified_pipeline.py:1283`**: a failed learned Kornia/LoFTR homography route silently
     falls back to SIFT. **Establish first whether the learned route is even installed and attempted** --
     if Kornia is absent, the fallback is the only path and "silently falls back" means something
     different. **Say which.**

METHOD:
  1. **For each handler, answer REACHED / NOT REACHED / UNDETERMINED at runtime**, and state the
     evidence. **"Not reached because the guarding branch never executes in current configuration" is a
     first-class answer** and is worth more than a forced synthetic failure, so **check reachability
     BEFORE trying to force anything.**
  2. Where a branch is reachable, **force the failure from your own process** (monkey-patch the callee
     to raise, or supply input that genuinely fails) and record: what the caller returned, whether any
     status field, log line, column or timing change betrayed it, and **whether a caller could tell the
     difference from success.** **Run a matched clean control for every forced failure** -- G221's
     truncation result was only meaningful because it had one.
  3. **Do NOT count a `try` that never runs as a defect, and do NOT count a monkey-patched failure as
     evidence the branch fires in production.** State the distinction explicitly for every handler.
  4. **Report the observable-signal answer precisely.** G218's remedy shape is "keep the fallback, make
     it say so", so the decisive fact per handler is **whether ANY durable output would reveal the
     degradation** -- not merely whether a Python exception existed somewhere.
  5. **PROPOSALS ONLY for anything in `src/`, clearly marked human-gated. Apply nothing.** G218 already
     proposed a durable per-run degradation status; **do not re-propose it, just say which handlers it
     would cover.**

**HONEST LIMITATIONS to state, not discover:** forcing a failure by monkey-patching shows what the
handler DOES, never that it fires in production; only reachability analysis plus real input speaks to
that, and you must keep the two claims separate in every line you write. Local files are not the pod
corpus and came from a different acquisition path, so a branch unreached here may be reached there --
**do not generalise to the pod.** This row tests five handlers of nineteen; the rest remain static-only.

ACCEPTANCE RULE:
  metric        = per handler: REACHED / NOT REACHED / UNDETERMINED with its evidence; if reached, what
                  the caller observed under a forced failure beside a matched clean control; and whether
                  any durable output reveals the degradation
  before        = 19 handlers classified statically by G218; 2 tested by G221 (one confirmed, one
                  refuted); 1 shown unreachable by the orchestrator; the other 16 have no runtime
                  evidence at all
  bar           = NO pass bar. **"All five are unreachable in current configuration" is a FULL SUCCESS**
                  and would substantially downgrade a set of findings I currently treat as serious.
                  **"The unvalidated-homography branch is reachable and silent" is the other full
                  success** and would be a coordinate-integrity defect worth acting on. Do not prefer
                  the alarming outcome, and do not inflate a monkey-patched result into a production
                  claim.
  n             = 5 named handlers (CONSTRUCT, exhaustive for this row); name every one you could not
                  reach and why
  eye check     = none; this row is runtime behaviour and code reading
  must not move = every threshold, `_FRAME_STRIDE`, `_FRAME_STRIDE_THRESH`, every bar and verdict, the
                  coordinate contract, `src/` (READ and IMPORT only -- no writes, no fixes), the pod
                  (DO NOT USE IT), the corpus, and every landed ledger row
EVIDENCE: docs/evidence/tracking/g228_degraded_handler_reachability_2026-09-04.md with the per-handler
verdict table, the reachability evidence, the forced-failure results with their matched controls, an
explicit separation of "reachable in production" from "does this when forced", bytes freed on cleanup,
and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
