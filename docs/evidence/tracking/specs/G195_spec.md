GAP G195 | sport wnba | worktree a3 | log g195_cv2_rng_route_determinism
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ, IMPORT and wrap it IN
YOUR OWN MEASUREMENT PROCESS only. Edit nothing; deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD.** RTX 3090, 24 GB. The local box is 16 GB with other lanes live.

**S3 DEPENDENCY.** Three landed rows, all ACCEPT:
  - **G189**: the route is non-deterministic.
  - **G190**: `cudnn.benchmark = False` alone makes the DETECTOR bit-exact; seeds added nothing THERE.
  - **G193**: tuner-off is **NOT** sufficient for the whole route -- 1,246 / 1,348 / 1,268 rows with
    differing survivor sets. Residual variance lives downstream of the detector.

THE QUESTION: **is the residual route variance OpenCV's global RNG?**

PREMISES, ENUMERATED BY THE ORCHESTRATOR OVER THE WHOLE ROUTE (S2), not a single flagged line.
Re-confirm cheaply; if any is false, STOP and report FALSIFIED:

  ALREADY SEEDED, so NOT candidates:
  - `src/tracking/color_reid.py:73` -- `np.random.default_rng(0)`, seeded.
  - `src/tracking/jersey_ocr.py:382` -- `KMeans(..., random_state=0)`, seeded (sklearn).

  UNSEEDED, and ALL SIX share OpenCV's single global RNG:
  - `src/tracking/color_reid.py:77-78` -- `cv2.kmeans(..., cv2.KMEANS_PP_CENTERS)`, randomised
    initialisation, `attempts=1`.
  - `cv2.findHomography(..., cv2.RANSAC, 5.0)` at **five** sites: `src/tracking/rectify_court.py:56`
    and `:90`, `src/tracking/video_handler.py:145`, `src/pipeline/unified_pipeline.py:1228` and
    `:1299`. **RANSAC is a randomised consensus algorithm.**

**Why this is a stronger hypothesis than the k-means alone:** RANSAC decides the HOMOGRAPHY. A
different consensus set gives a different matrix, which moves every projected coordinate. That is
consistent with G189 and G193 both observing survivor coordinates far outside the frame
(x = 2979 and y = -1699 on a 1920x1020 crop). One call, `cv2.setRNGSeed(n)`, seeds all six.

METHOD -- four arms, **3 runs each, fresh process per run**, all on the pod, one at a time:

  | arm | cudnn.benchmark | cv2.setRNGSeed |
  |---|---|---|
  | A control (unchanged route) | on | no |
  | B | off | no |
  | C | on | **yes** |
  | D | off | **yes** |

  Arms A and B reproduce G193 and are the control; C isolates the OpenCV RNG; D is both. Use the same
  in-memory wrapper pattern G193 used (save `UnifiedPipeline.__init__`, call the original, then apply
  the arm's settings). Seed with a FIXED value and state it.

  Report per run: player rows, distinct player-row frames, distinct attempted gameplay frames
  (**the ELIGIBLE DENOMINATOR -- name it, never `--frames`**), and survivor tuples at source frames
  474 and 1377. **Then state per arm: are the three runs identical to each other, yes or no.**

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. `--frames 1200 --no-show --skip-features`.
**A11:** record pod SHA-256 for `unified_pipeline.py`, `advanced_tracker.py`, `color_reid.py`,
`rectify_court.py`.
**B13/Q9:** per-run records in the artifact, not just a summary.

ACCEPTANCE RULE:
  metric        = identical-or-not across the 3 runs of each of the four arms
  before        = the route varies with the tuner on AND off; the residual source is unknown; six
                  unseeded OpenCV RNG call sites are enumerated but untested
  bar           = NO pass bar. **"Seeding OpenCV changes nothing" is a FULL SUCCESS** and would
                  eliminate the leading candidate, which is real progress. "Arm D is deterministic"
                  is the other full success and would unblock quality measurement. Do NOT add FP32,
                  torch seeds, threshold changes or anything else to chase agreement -- G190 measured
                  that torch seeds add nothing and that FP32 CHANGES the values.
  n             = 3 runs x 4 arms (EXISTENCE of variance, not a rate)
  eye check     = none; G189 established single-run renders are not evidence here
  must not move = every threshold, `conf`, `imgsz`, the crop, the coordinate contract, every bar and
                  verdict, `src/` (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g195_cv2_rng_route_determinism_2026-09-03.md with the four-arm
table, per-run records, the per-arm identical-or-not verdict, code hashes, and a NOT VERIFIED list.
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest.
POD: run the twelve jobs there, sequentially. Never kill, restart or deploy over the daemon or
keeper; do not wait on the daemon.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
