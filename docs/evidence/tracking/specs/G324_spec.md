GAP G324 | sport all | worktree a2 | log cx_g324_apache_arm_rebudget
**SCREENING ROW, RE-RUN UNDER A RE-REGISTERED INSTALL PREMISE. `src/`, `domains/`, `api/`,
`kernel/` and `intel/` are READ and IMPORT only -- `src/tracking/player_detection.py` is
HUMAN-GATED. You may IMPORT and RUN it; you may NOT edit it. Build in
`scripts/platformkit/tracking/`. This row MEASURES an alternative detector; it ADOPTS NOTHING,
moves no production default and proposes no cutover.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check against every
line of section B before you report.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **BOTH DETECTION ARMS RUN ON THE POD** -- the source video, the GPU and the weights are there.
    Use `~/bin/pod_run a2 --ship <harness + constraints> --fetch <per-arm CSVs and summaries> -- python -m ...`.
  - **THE ARITHMETIC AND THE MEMO ARE LOCAL**, on the fetched summaries.
  - **GPU LEASE, SERIALIZED WITH THE RUNNING DAEMON.** `track_daemon` (16 workers) owns the card and
    **must never be stopped, signalled or interrupted.** Read
    `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` and
    `--query-compute-apps=pid,used_memory --format=csv,noheader` YOURSELF, **report both verbatim, and
    PROCEED ONLY WHEN FREE VRAM IS >= 8192 MiB.** Below that, WAIT and re-probe. **This row stays
    under 4 GB. OPERATIONAL gate, not an evidentiary bar.**
  - **WALL BUDGET: 3,600 s PER GAME (both arms together)**, separate from and additional to the
    install premise below. A game that exceeds it is a BUDGET LIMIT for that game, reported as such;
    the row continues with the games that finished.
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** Stop only on a failed
    `dd conv=fsync` probe. Write into `/workspace/wt/a2` and `--target /workspace/mmlab_env` ONLY --
    **never the deployed `/workspace/nba-ai-system` tree, never the daemon's system site-packages,
    never `data/tracking/`, and never overwrite `yolov8n.pt`.**

**WHY THIS ROW EXISTS.** G311 closed at its sealed 1,800 s install premise (`G311_VERIFY_2026-09-07.md`)
while the mmcv 2.1.0 CUDA ops were still compiling: the measured build+install is **2,921 s**
(wheel 1,898 s + install 1,023 s, `TORCH_CUDA_ARCH_LIST=8.6`, sm_86 only), so the 1,800 s bar was
**unmeetable by 1,121 s** and every arm number G311 produced is an out-of-contract diagnostic. The
licence problem is unchanged and unmeasured in contract: production detection is AGPL-3.0 `yolov8n`
(`scripts/platformkit/detection/MODEL_LICENSES.md`), the shim's only non-AGPL backend is
`YoloxOnnxBackend`, and **no Apache-2.0 detector has ever been screened on this corpus inside a
premise that could be met.** Four NEW GAPs from the G311 verifier -- RAW-BOX-DURABILITY,
EVIDENCE-NAME, PROVENANCE, MASTER-TEST -- are this row's requirements, not reopened G311 budget.

**PREMISE (step 0, BINDING before-condition, 3,600 s WALL CLOCK, SEALED BEFORE ANY BUILD):** on the
pod, an Apache-2.0-licensed RTMDet person-detector artifact is **obtainable AND runnable** under
`--target /workspace/mmlab_env` against the pod's `torch 2.8.0+cu128` / Python 3.12. **The 3,600 s
limit is a NEW bar, sealed in the prereg BEFORE any build or install command runs, and IS NEVER
LENGTHENED AGAIN (VERIFIER_CONTRACT Q3): if the clock elapses before the import gate clears, the row
is CLOSED AT LIMIT with the elapsed time, which is a VALID RESULT and not a failure of the row.**
**WHEEL REUSE, the only permitted shortcut:** the mmcv wheel already built on the pod
(`/workspace/mmlab_wheels/mmcv-2.1.0-cp312-cp312-linux_x86_64.whl`) may be REUSED **only if its
SHA-256 and byte size are recorded IN THE PREREG before the clock starts** and the import gate
`import mmcv, mmdet; from mmcv.ops import batched_nms` clears against it. **The
rebuild-from-source time is reported SEPARATELY** -- either re-measured this row, or carried from
G311's `route_i5_mmcv210_build.txt` with that citation and the word INHERITED -- and **counts toward
the 3,600 s ONLY IF THE REUSE FAILS**, in which case the row builds from source inside the same
sealed clock. Print the exact resolved versions of everything imported, the checkpoint download URL,
its SHA-256 and byte size, and every licence URL. **Pin `opencv-python-headless<5` / `opencv-python<5`
in the constraints (cv2 5 silently empties every tracking table -- 2026-09-02 rebuild landmine) and
print the runtime `cv2.__version__`.** **`torch.load` keeps `weights_only=True` with the 7 named
safe-globals; the checkpoint SHA-256 is verified before load.** **The mmyolo RTMDet copy is GPL-3.0
and is FORBIDDEN; use mmdetection ONLY. TVCalib, Sportlight and KaliCalib are BLOCKED. No new AGPL
dependency may be installed.** **Pin every licence with its URL; do not infer a weight licence from
an architecture name.**

METHOD:
  1. **THREE GAMES, ffprobe-CONFIRMED NATIVE 1920x1080 AND ALREADY TRACKED:** `wnba_01_1080p`,
     `ncaa_basketball_IB-_u4gW3ds_1080p`, `wnba_06`. **Print full pod path, BYTE SIZE, width, height,
     fps and duration per source (contract A9); a 1280x720 source is INELIGIBLE by measurement, not
     by filename.**
  2. **TWO ARMS ON IDENTICAL FRAME SETS. ARM Y = PRODUCTION ROUTE** -- import the gated
     `player_detection.py` path unedited (`yolov8n`, its own `_infer_imgsz`, `classes=[0]`,
     `conf=0.3`); **if you cannot import it, replicate those exact settings and SAY you replicated.**
     **ARM R = the Apache RTMDet arm**, person class only. **Both arms decode the SAME frame list
     (40 evenly spaced indices spanning 0 .. the LAST DECODABLE index, that anchor MEASURED per clip
     by binary search on the real cv2 seek path -- G311 AMENDMENT 1's readable-anchor rule, carried
     verbatim because ffprobe overcounts the seekable range by up to 132 frames on this corpus; no
     head slice) and see byte-identical decoded frames. A failed read is FATAL, never dropped. Print
     the frame list length and the anchor. Add NO third difference beyond the detector itself, and
     state that the arms differ in model AND input size, so this is a DETECTOR-STACK comparison, not
     a single-variable ablation -- say that in those words.**
  3. **PROXIES, PER GAME PER ARM, EVERY ONE WITH ITS DENOMINATOR (decoded frames):** person boxes per
     frame; **box agreement BOTH WAYS** -- share of ARM Y boxes with an ARM R box at IoU >= 0.5 and
     share of ARM R boxes with an ARM Y box at IoU >= 0.5, **greedy one-to-one matching, stated**;
     distinct track ids after **the same tracker on both arms**; median track length in rows;
     **inference ms/frame SINGLE-IMAGE** (detector call only, warm-up excluded and said to be
     excluded) **AND BATCHED ms/frame at batch size 8, reported side by side, both arms, same
     frames** -- G311's 2,141-2,513 ms/frame ARM R figure is single-image and unbatched and must not
     stand alone; and **peak VRAM per arm**.
  4. **RAW SAMPLED BOX ROWS ARE COMMITTED (G311-RAW-BOX-DURABILITY).** Write, under
     `docs/evidence/tracking/g324_artifact/`, one CSV per game per arm carrying **>= 200 box rows**
     with `frame_index`, `x1`, `y1`, `x2`, `y2`, `score`, `class` -- enough that a verifier can
     recompute the greedy IoU matching from coordinates alone. **State the row count per file and
     whether it is the full set or a declared subset with its selection rule.**
  5. **PROVENANCE IS PRINTED AT MEASUREMENT TIME (G311-PROVENANCE, contract A9/A11):** the byte size
     of each source opened, and the **SHA-256 of every harness route file AS DEPLOYED ON THE POD**
     (`g324_*` modules and any G311 helper they import), computed on the pod inside the run, not
     reconstructed afterwards.
  6. **STATE THE SIGN CONVENTION EXPLICITLY, PER PROXY, IN THE VERDICT LINE**: which direction of
     boxes/frame, agreement in each direction, median track length, distinct ids, ms/frame and peak
     VRAM is consistent with more detection, and say plainly that **consistency is not evidence**.
  7. **LABEL THE WHOLE ROW SCREENING. THERE IS NO GROUND TRUTH.** More boxes can mean more players
     found OR more false boxes and **this row cannot tell them apart**; low agreement says the two
     stacks disagree and **says nothing about which is right**. **G303 and G296 are the rows that
     score recall against labelled frames.** **Say that in those words. Make NO recall, precision,
     registration, accuracy or pass claim, and no claim that either detector is better.**
  8. **THE PRODUCTION ROUTE MUST BE UNTOUCHED:** report **SHA-256 of `src/tracking/player_detection.py`
     and of the pod `yolov8n.pt` BEFORE and AFTER**, and show they are identical.

**HONEST LIMITATIONS to state, not discover:** ONE corpus, three clips, no labels, one seed. The arms
differ in more than one variable. Agreement is symmetric ignorance: it cannot rank the arms. A newly
installed stack has had no tuning at all, so **a poor ARM R showing is as likely to be an unconfigured
default as a property of RTMDet** -- say so. Timing is measured on a card shared with a running daemon
and is therefore an UPPER bound on ms/frame, not a benchmark. **A reused wheel measures INSTALLABILITY,
not buildability; the build cost is the separately reported rebuild-from-source figure.**

ACCEPTANCE RULE:
  metric        = premise output (elapsed seconds against the sealed 3,600 s wall; reused-wheel
                  SHA-256 + byte size + import gate; rebuild-from-source seconds reported separately;
                  resolved versions; checkpoint URL + SHA-256 + byte size + licence URLs); per game
                  per arm: person boxes per frame, both-way IoU >= 0.5 agreement shares, distinct ids,
                  median track length, single-image ms/frame, batch-8 ms/frame, peak VRAM -- each with
                  its decoded-frame denominator; the per-proxy sign rule in the verdict line; the
                  committed raw box CSVs (>= 200 rows per arm per game); source byte sizes and pod
                  harness route SHA-256s; the SCREENING statement
  before        = G311 CLOSED AT LIMIT at a sealed 1,800 s install premise against a measured 2,921 s
                  build+install; no in-contract arm-frame exists; the repo still has NO RTMDet backend,
                  the only shipped non-AGPL backend is `YoloxOnnxBackend`, and production is AGPL
                  `yolov8n` (`MODEL_LICENSES.md`); no raw box rows and no route provenance are committed
  bar           = **INSTALL PREMISE ONLY: the import gate clears within 3,600 s of wall clock, sealed
                  before any build. THAT BAR IS NEVER MOVED AGAIN -- exceeding it is CLOSED AT LIMIT
                  with the elapsed time, a VALID RESULT.** **NO pass bar on any proxy. A run in which
                  the arms disagree strongly is a FULL SUCCESS. Neither arm may be declared better.**
                  The only failure is an unmeasured or unlabelled number.
  n             = 3 games x 40 evenly spaced decoded frames x 2 arms = 240 arm-frames; >= 200 raw box
                  rows per arm per game; 1 corpus, 1 seed -- name every denominator in the verdict line
  eye check     = NONE. No renders and no eye labels; this row is arithmetic over box coordinates.
                  **Say that rather than implying validation.**
  must not move = `src/`, `domains/`, `api/`, `kernel/`, `intel/` (READ/IMPORT ONLY;
                  `player_detection.py` HUMAN-GATED and SHA-256-pinned before/after); production
                  defaults; `data/registry/`; the pod `yolov8n.pt`; the deployed
                  `/workspace/nba-ai-system` tree; the daemon's system site-packages; `data/tracking/`;
                  IoU 0.5, IoU link 0.3, detector conf 0.3, 40 frames; every existing threshold
NON-TAUTOLOGY: the proxies cover every decoded frame in the declared list, including frames where an
arm emits zero boxes -- **a zero-box frame counts in the denominator and is NOT dropped.** State the
zero-box frame count per arm. The raw CSVs carry every box behind the reported counts, or name the
selection rule for the subset they carry.
EVIDENCE: `docs/evidence/tracking/g324_apache_arm_rebudget_2026-09-07.md` (<= 60 lines) -- **the memo
MUST live at exactly this path (G311-EVIDENCE-NAME)** -- with line 1 the verdict, the premise output
and elapsed clock, the per-game per-arm proxy table with both ms/frame columns, the per-proxy sign
rule, the SCREENING statement, every GPU and disk probe verbatim, the pod log tail, the before/after
SHA-256 pair, source byte sizes, pod harness route SHA-256s, artifact SHA-256s, and a NOT VERIFIED
list. **Copy the per-arm summary JSON and the raw box CSVs under
`docs/evidence/tracking/g324_artifact/` for durability.**
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO (one append only, `>>`, never a rewrite
of any historical row -- G311-LEDGER-HISTORY).**
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test on the batching/raw-row code this row adds, over SYNTHETIC boxes
-- pin that batch-8 and single-image paths yield identical box sets, that the raw-row writer emits
frame index + xyxy + score + class for every box, and that a zero-box frame stays in the denominator.
Reuse `tests/platformkit/test_g311_proxies.py`'s coverage of IoU >= 0.5, greedy one-to-one matching
and both-way agreement asymmetry rather than duplicating it. **The test must pass ON MASTER after
landing (G311-MASTER-TEST).** Run only that file. **NEVER a full pytest.**
COMMIT: explicit pathspec, in the worktree. **Sealed PREREG committed ALONE before any build or
measurement**, then harness + tests, then artifacts + memo + ledger row. No forced git operation of
any kind. **Commit BEFORE reporting (A7).** ASCII stdout.
**NEVER PARK:** poll your own pod job in a blocking loop; never end waiting.
