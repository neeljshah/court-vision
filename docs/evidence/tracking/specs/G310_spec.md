GAP G310 | sport all | worktree a1 | log g310_native_input_arm
**SCREENING ROW. `src/`, `domains/`, `api/` and `kernel/` are READ and IMPORT only --
`src/tracking/player_detection.py` and `src/pipeline/unified_pipeline.py` are HUMAN-GATED. You may
IMPORT and RUN them; you may NOT edit them. Build in `scripts/platformkit/tracking/`. This row
MEASURES an alternative input size; it ADOPTS NOTHING and proposes NO production change.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **BOTH ARMS RUN ON THE POD** -- the source video, the GPU and the weights are there. Use
    `~/bin/pod_run a1 --ship <your harness> --fetch <per-arm summaries and proxy CSVs> -- <cmd>`.
  - **THE ARITHMETIC AND THE MEMO ARE LOCAL**, on the fetched summaries.
  - **GPU LEASE, SERIALIZED WITH THE RUNNING DAEMON.** `track_daemon` (pid 25560, 4 workers) owns the
    card and **must never be stopped, signalled or interrupted.** Read
    `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` and
    `--query-compute-apps=pid,used_memory --format=csv,noheader` YOURSELF, **report both verbatim, and
    PROCEED ONLY WHEN FREE VRAM IS >= 8192 MiB.** Below that, WAIT and re-probe; do not kill, do not
    queue behind a lane count. **This is an OPERATIONAL gate, not an evidentiary bar.**
  - **WALL BUDGET: 3,600 s PER GAME PER ARM.** A game that exceeds it is a BUDGET LIMIT for that game,
    reported as such, and the row continues with the games that finished. **Report wall seconds per
    arm per game either way.**
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** Stop only on a failed
    `dd conv=fsync` probe. Write into `/workspace/wt/a1`, **NEVER into the deployed
    `/workspace/nba-ai-system` tree, and NEVER into `data/tracking/`.** Report bytes added and freed.
  - **WORKTREE a1 IS DIRTY at allocation** (untracked `docs/evidence/tracking/tracknetv3_a1/` renders).
    **Archive those paths outside the repo, then reset the worktree, BEFORE any work.**

**WHY THIS ROW EXISTS.** G298 (`ace539619`) measured input resolution to be the DOMINANT detector
defect -- but on **ONE shot, 15 frames, 143 single-locator feet**, at the DETECTOR level only. **Nobody
has run the PRODUCTION ROUTE at native resolution on a whole game.** The setting is a source constant,
not a measurement: `src/tracking/player_detection.py:82` sets **`self._infer_imgsz = 640`** and
`src/pipeline/unified_pipeline.py:917` and `:1021` read it back with
`getattr(self.feet_det, "_infer_imgsz", 640)`. **Because the route reads it off the detector INSTANCE,
the native arm is an INSTANCE ATTRIBUTE SET AT RUNTIME -- never a source edit.** Set it and SAY that
is what you did.

**PREMISE (step 0, BINDING before-condition):** instrument the route as the daemon actually calls it
and **PRINT the effective input size the detector receives**. **If that printed value is NOT below
1920, this row is PREMISE FALSE -- STOP, write the memo, commit, and report PREMISE FALSE**, which is a
valid result with its own register row. **Do not infer the value from the source constant: print what
the running route uses**, since a constant read through `getattr` can be overridden anywhere upstream.

METHOD:
  1. **PICK 3 ALREADY-TRACKED GAMES WHOSE SOURCE IS NATIVE 1920x1080** -- confirm with `ffprobe` and
     print width, height, fps and duration per source. **A 1280x720 source is INELIGIBLE and must be
     excluded by measurement, not by filename.** Name the three and say how many candidates you
     rejected and why.
  2. **TWO ARMS, ONE DIFFERENCE.** **ARM P = PRODUCTION DEFAULT** (the effective size printed in step
     0). **ARM N = NATIVE**, the same route with the detector instance's `_infer_imgsz` set to 1920.
     **SAME frames (same start, same stride, same frame cap), SAME weights, SAME conf, SAME classes,
     SAME code path. State that design and add NO third difference.** Print the settings of both arms.
  3. **COMPARE IMAGE-SPACE PROXIES ONLY**, per game per arm, each with its denominator: person rows
     per emitted frame, distinct track ids, median track length in rows, ball rows detected, and the
     p95 per-track consecutive bbox-bottom-centre displacement normalised by `source_height`.
     **State the footpoint convention.** **Report per-arm wall seconds** -- a native arm is SLOWER and
     the reader must see the cost.
  4. **STATE THE SIGN CONVENTION EXPLICITLY**: which direction of each proxy would be consistent with
     more detection, and say plainly that **consistency is not evidence.**
  5. **LABEL THE WHOLE ROW A SCREENING ROW.** **There is NO ground truth here.** More rows per frame
     can mean more players found OR more false boxes, and **this row cannot tell those apart** -- G303
     scores recall against the G296 frames and is the row that can. **Say that in those words. Make NO
     claim of recall, precision, accuracy, registration or a harness pass, and do NOT touch the ledger
     `passed` field.**
  6. **CHANGE NOTHING.** No production default, no threshold, no filter, no adoption, no proposal.
     **Do NOT delete or overwrite `yolov8n.pt` anywhere on the pod.**

**HONEST LIMITATIONS to state, not discover:** **no ground truth, so every number is a proxy and none
is a quality measure.** **3 games is not a sample of anything.** The route is non-deterministic in
places (G241: 808 of 1,201 records differed on a repeat) -- **run ARM P twice on ONE game and report
whether the proxies are stable; if they are not, treat every arm as ONE DRAW and say so.** Timing on a
shared card with a live daemon is contended and **may not be quoted as a throughput figure.** G298's
attribution rests on one shot in frames 19599-23399, a span G278 measured friendlier than its own clip
(0.836 against 0.656, p = 0.0078), **so nothing here may be quoted clip-wide or programme-wide.**

ACCEPTANCE RULE:
  metric        = the step-0 printed effective input size; the three sources' probed dimensions with
                  the rejected candidates counted; both arms' exact settings with the single-difference
                  design stated; per game per arm the five proxies with denominators named and the wall
                  seconds; the ARM P repeat-stability check; the stated sign convention; and the
                  SCREENING label with the no-ground-truth sentence
  before        = the production route feeds the detector an input size below 1920 on 1920x1080 sources
                  (`_infer_imgsz = 640`, `player_detection.py:82`, read back at
                  `unified_pipeline.py:917` and `:1021`) and NO whole-game native-input arm exists
  bar           = **3/3 games complete BOTH arms within 3,600 s each and every proxy is tabulated with
                  its denominator.** **NO quality bar and NO pass bar** -- this row screens, it does not
                  score. **A proxy table showing NO difference is a FULL SUCCESS.** A game that busts
                  the budget is a BUDGET LIMIT reported per game, not a silent drop.
  n             = 3 games x 2 arms + 1 repeat = 7 route runs; name the emitted-frame denominator per
                  run in the verdict line
  eye check     = NONE. This row has no labels and no blind judging; it is arithmetic over route
                  output. **Say that rather than implying validation.**
  must not move = `src/`, `domains/`, `api/`, `kernel/` (READ and IMPORT ONLY; `player_detection.py`
                  and `unified_pipeline.py` HUMAN-GATED); every production default including
                  `_infer_imgsz` ON DISK; `yolov8n.pt` on the pod; the deployed
                  `/workspace/nba-ai-system` tree; `data/tracking/` and the daemon ledger; the running
                  `track_daemon`; G298's and G303's numbers and bars
EVIDENCE: `docs/evidence/tracking/g310_native_input_arm_2026-09-07.md` with the premise print, the
source probes, both arms' settings, the per-game proxy table, the wall seconds, the repeat check, every
GPU and disk probe verbatim, bytes added and freed, and a **NOT VERIFIED** list. Copy the per-arm
summary JSON and proxy CSVs under `docs/evidence/`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT
AS THE MEMO.** Commit BEFORE reporting (A7). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test for the PROXY COMPUTATION on a synthetic construct -- pin rows per
frame, distinct ids, median track length and the p95 normalised displacement against hand-computed
values, and pin the bottom-centre footpoint convention. Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only, no push. ASCII stdout. **NEVER PARK.**
