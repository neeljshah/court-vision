GAP G311 | sport all | worktree a2 | log g311_apache_detector_arm
**SCREENING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only --
`src/tracking/player_detection.py` is HUMAN-GATED. You may IMPORT and RUN it; you may NOT edit it.
Build in `scripts/platformkit/tracking/`. This row MEASURES an alternative detector; it ADOPTS
NOTHING, moves no production default and proposes no cutover.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **BOTH DETECTION ARMS RUN ON THE POD** -- the source video, the GPU and the weights are there.
    Use `~/bin/pod_run a2 --ship <harness + constraints> --fetch <per-arm CSVs and summaries> -- python -m ...`.
  - **THE ARITHMETIC AND THE MEMO ARE LOCAL**, on the fetched summaries.
  - **GPU LEASE, SERIALIZED WITH THE RUNNING DAEMON.** `track_daemon` (4-8 workers) owns the card and
    **must never be stopped, signalled or interrupted.** Read
    `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` and
    `--query-compute-apps=pid,used_memory --format=csv,noheader` YOURSELF, **report both verbatim, and
    PROCEED ONLY WHEN FREE VRAM IS >= 8192 MiB.** Below that, WAIT and re-probe. **OPERATIONAL gate,
    not an evidentiary bar.**
  - **WALL BUDGET: 3,600 s PER GAME (both arms together).** A game that exceeds it is a BUDGET LIMIT
    for that game, reported as such; the row continues with the games that finished.
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** Stop only on a failed
    `dd conv=fsync` probe. Write into `/workspace/wt/a2` ONLY -- **never the deployed
    `/workspace/nba-ai-system` tree, never `data/tracking/`, and never overwrite `yolov8n.pt`.**
  - **WORKTREE a2 IS ON A FOREIGN BRANCH at allocation** (`codex/synthcal-basketball`, 2 commits ahead
    of master). **Archive those commits outside the repo, then `git checkout -B track-a2 master`,
    BEFORE any work.**

**WHY THIS ROW EXISTS.** The programme's production detector is `yolov8n` from Ultralytics, which is
**AGPL-3.0 and whose author asserts that weights and fine-tunes inherit that licence**
(`scripts/platformkit/detection/MODEL_LICENSES.md`: "yolov8n.pt is not approved for commercial
use"). The 2026-08-31 decision was to replace it with **RTMDet (mmdetection), Apache-2.0 code AND
weights**. The seam exists -- `scripts/platformkit/detection/shim.py`, `CV_DETECTOR` -- but **its only
non-AGPL backend today is `YoloxOnnxBackend`; there is no RTMDet backend and no RTMDet artifact has
ever been run in this repo.** **Nobody has measured what the Apache arm actually detects on this
corpus.** A licence decision that has never been executed is not a migration.

**PREMISE (step 0, BINDING before-condition, 30-MINUTE CLOCK):** on the pod, (a) **the shim imports**
and (b) **an Apache-2.0-licensed RTMDet person-detector artifact is obtainable AND runnable**. Attempt
in this order and **print the exact resolved versions of everything installed and the exact download
URL and SHA-256 of the checkpoint**: **(i)** `mmdet` / `mmengine` / `mmcv` under
`--break-system-packages` with a **constraints file pinning `opencv-python-headless<5`** (cv2 5
silently empties every tracking table -- pod rebuild landmine 2026-09-02), against the pod's
`torch 2.8.0+cu128` / Python 3.12; **(ii)** an **ONNX RTMDet export served by onnxruntime**, if and
only if the artifact and its serving library are Apache-2.0 or MIT. **Start the clock and report it.
If neither route yields a running Apache-2.0 RTMDet within 30 minutes, the row is PREMISE FALSE --
STOP, write the memo naming the exact failing versions and error, commit, and report PREMISE FALSE,
which is a VALID RESULT with its own register row and is NOT a failure of the row.** **The mmyolo
RTMDet copy is GPL-3.0 and is FORBIDDEN; use mmdetection ONLY. TVCalib, Sportlight and KaliCalib are
BLOCKED. No new AGPL dependency may be installed.** **Pin every licence with its URL in the memo; do
not infer a weight licence from an architecture name.**

METHOD:
  1. **THREE GAMES, ffprobe-CONFIRMED NATIVE 1920x1080 AND ALREADY TRACKED:** `wnba_01_1080p`,
     `ncaa_basketball_IB-_u4gW3ds_1080p`, `wnba_06`. **Print width, height, fps and duration per
     source; a 1280x720 source is INELIGIBLE by measurement, not by filename.**
  2. **TWO ARMS ON IDENTICAL FRAME SETS. ARM Y = PRODUCTION ROUTE** -- import the gated
     `player_detection.py` path unedited (`yolov8n`, its own `_infer_imgsz`, `classes=[0]`,
     `conf=0.3`); **if you cannot import it, replicate those exact settings and SAY you replicated.**
     **ARM R = the Apache RTMDet arm** through the shim seam, person class only. **Both arms decode
     the SAME frame list (same start, same stride, same cap; >= 30 frames per game, EVENLY spaced over
     the clip, no head slice) and see byte-identical decoded frames. Print the frame list length and
     the stride. Add NO third difference beyond the detector itself, and state that the arms differ in
     model AND input size, so this is a DETECTOR-STACK comparison, not a single-variable ablation --
     say that in those words.**
  3. **PROXIES, PER GAME PER ARM, EVERY ONE WITH ITS DENOMINATOR (decoded frames):** person boxes per
     frame; **box agreement BOTH WAYS** -- share of ARM Y boxes with an ARM R box at IoU >= 0.5 and
     share of ARM R boxes with an ARM Y box at IoU >= 0.5, **greedy one-to-one matching, stated**;
     distinct track ids after **the same tracker on both arms**; median track length in rows;
     **inference ms/frame** (detector call only, warm-up excluded and said to be excluded) and **peak
     VRAM per arm**.
  4. **STATE THE SIGN CONVENTION EXPLICITLY**: which direction of each proxy is consistent with more
     detection, and say plainly that **consistency is not evidence**.
  5. **LABEL THE WHOLE ROW SCREENING. THERE IS NO GROUND TRUTH.** More boxes can mean more players
     found OR more false boxes and **this row cannot tell them apart**; low agreement says the two
     stacks disagree and **says nothing about which is right**. **G303 and G296 are the rows that score
     recall against labelled frames.** **Say that in those words. Make NO recall, precision,
     registration, accuracy or pass claim, and no claim that either detector is better.**
  6. **THE PRODUCTION ROUTE MUST BE UNTOUCHED:** report **SHA-256 of `src/tracking/player_detection.py`
     and of the pod `yolov8n.pt` BEFORE and AFTER**, and show they are identical.

**HONEST LIMITATIONS to state, not discover:** ONE corpus, three clips, no labels, one seed. The arms
differ in more than one variable. Agreement is symmetric ignorance: it cannot rank the arms. A newly
installed stack has had no tuning at all, so **a poor ARM R showing is as likely to be an unconfigured
default as a property of RTMDet** -- say so. Timing is measured on a card shared with a running daemon
and is therefore an UPPER bound on ms/frame, not a benchmark.

ACCEPTANCE RULE:
  metric        = premise output (resolved versions, checkpoint URL + SHA-256 + licence URL, minutes
                  elapsed); per game per arm: person boxes per frame, both-way IoU >= 0.5 agreement
                  shares, distinct ids, median track length, ms/frame, peak VRAM -- each with its
                  decoded-frame denominator; the stated sign convention; the SCREENING statement
  before        = the repo has NO RTMDet backend and has never run an Apache-2.0 detector on this
                  corpus; the only shipped non-AGPL backend is `YoloxOnnxBackend`; production is
                  AGPL `yolov8n` (`MODEL_LICENSES.md`)
  bar           = **NO pass bar.** **PREMISE FALSE with named versions and the exact error is a FULL
                  SUCCESS. A run in which the arms disagree strongly is a FULL SUCCESS. Neither arm
                  may be declared better.** The only failure is an unmeasured or unlabelled number.
  n             = 3 games, >= 30 evenly spaced decoded frames per game, 2 arms, 1 corpus, 1 seed --
                  name every denominator in the verdict line
  eye check     = NONE. No renders and no eye labels; this row is arithmetic over box coordinates.
                  **Say that rather than implying validation.**
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/` (READ/IMPORT ONLY;
                  `player_detection.py` HUMAN-GATED and SHA-256-pinned before/after); production
                  defaults; `data/registry/`; the pod `yolov8n.pt`; the deployed
                  `/workspace/nba-ai-system` tree; `data/tracking/`; every existing threshold
NON-TAUTOLOGY: the proxies cover every decoded frame in the declared list, including frames where an
arm emits zero boxes -- **a zero-box frame counts in the denominator and is NOT dropped.** State the
zero-box frame count per arm.
EVIDENCE: `docs/evidence/tracking/g311_apache_detector_arm_2026-09-07.md` (<= 60 lines) with the
premise output, the per-game per-arm proxy table, ms/frame and VRAM, the SCREENING statement, every
GPU and disk probe verbatim, the pod log tail, the before/after SHA-256 pair, and a NOT VERIFIED list.
**Copy the per-arm summary JSON and the sampled box rows under `docs/evidence/` for durability.**
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO** (one append only).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test on the proxy/matching computation using SYNTHETIC boxes -- pin the
IoU >= 0.5 threshold, the greedy one-to-one matching, both-way agreement asymmetry, and that a
zero-box frame stays in the denominator. Run only that file. **NEVER a full pytest.**
COMMIT: explicit pathspec, in the worktree, no push, no forced git operation of any kind.
**Commit BEFORE reporting (A7).** ASCII stdout.
**NEVER PARK:** poll your own pod job in a blocking loop; never end waiting.
