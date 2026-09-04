GAP G225 | sport wnba | worktree a6 | log g225_detector_capacity_sweep
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and IMPORT only. Build in
`scripts/platformkit/tracking/`. **You need NO `src/` edit to do this row** -- `yolo_model` is already a
config key read at `src/tracking/advanced_tracker.py:260`, so pass it from YOUR OWN process.

**HOLD LIFTED 2026-09-04: G211 and G211b have both reported (both NOT VALIDATED -- the disjoint wrapper
is built and correct, but the route emitted no instrumented sample). Check the pod for other measurement
rows before starting and say that you checked.**

**AMENDMENT 2026-09-04 -- USE THE ADAPTER, NOT `run_clip`, AND YOU NOW HAVE TWO BASELINES.**
The legacy route is a poor vehicle for this row and tonight measured why: `run_clip --frames 1200`
made 400 detector calls and emitted **ZERO rows** (G211b); **9 of 9** historical basketball daemon jobs
died with `cv2.error` in `_build_court` (G234, G234-COMPLETE), though that crash is INTERMITTENT (G235);
and a 40-frame probe never reached `cv2.findHomography` at all. **The basketball ADAPTER works: use
`adapter_run basketball ... --max-frames 6000`, which is how both baselines below were produced.**

**BASELINE A -- professional broadcast (G226c / G226c-OUTPUT / G226c-IDENTITY), `wnba__wnba_01.mp4`:**
6,000 evaluated frames, **64,171 rows**, 5,972 frames with players, players/frame min 1 / **median 11.0**
/ p90 16 / max 27, 207 track ids, track length min 1 / **median 205** / p90 730 / max 2,270, one
one-frame track, zero duplicate `(frame, track_id)`, 100.00 pct of rows inside 1920x1080, harness SCORED
failing `coordinate_contract` on `image_px`.

**BASELINE B -- fixed-camera amateur (G239), `g220c__jh3fnwMi7dM.mp4`:** same invocation, players/frame
**6 / 20.0 / 24 / 34**, track length **1 / 500 / 1,729.2 / 4,029**, 50 fewer distinct ids.

**REPORT YOUR ARMS AGAINST BASELINE A** (same clip, same invocation) so the capacity comparison is
clean. **A second pass on the amateur clip is a bonus, not a requirement.**

**AND CARRY G239's WARNING: a median of 20 detections per frame against TEN players on court means the
adapter is very likely counting the bleacher crowd. A larger model detecting MORE people is NOT
automatically better** -- it may simply find more spectators. **The eye check in this spec is what
separates those, and it is mandatory.**

**This row is deliberately heavy, so check the pod for other measurement rows before starting and say in
your memo that you checked and when you began.** The `track_daemon`, `keep_track_daemon.sh`,
`adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT residents and are the
load floor, **not** a reason to wait; never kill or restart them. Harness and test writing may proceed
immediately.

**S1 MACHINE: RUN ON THE POD.** RTX 3090. **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE here (it
reports the whole cluster filesystem against a 50 GB volume cap, which caused a `Disk quota exceeded`
incident). **Do a real `dd` write probe before writing, record `du -sm /workspace/nba-ai-system/data`
(baseline ~30,900 MB of 50,000), and STOP and report if the probe fails -- do not delete to make room.**
Model weights are a few tens of MB each; **delete any you download and report bytes freed.**

**WHY THIS ROW EXISTS -- THE DETECTOR IS THE SMALLEST YOLOv8 VARIANT AND THE GPU IS IDLE.**

**Premises the orchestrator verified in master, so do not re-derive them:**
  - **`src/tracking/advanced_tracker.py:260`**: `_yolo_stem = _cfg.get("yolo_model", "yolov8n")`, and the
    upgrade branch at `:276` runs **only** when the stem differs from `yolov8n`. **A repo-wide search
    found NOTHING that ever sets `yolo_model` to another value.** So **player detection always runs
    YOLOv8-NANO**, and G218's rank-6 concern -- that a configured detector silently reverts to base
    `yolov8n` on exception (`:286 except Exception: pass`) -- **is UNREACHABLE in the current
    configuration, because the branch guarding it never executes.** Record that as a small negative.
  - **`resources/` contains only nano artefacts**: `yolov8n.pt`, `yolov8n.engine`, `yolov8n-pose.engine`,
    `yolov8n_ball.engine`, `osnet_x025.engine`. No `s`/`m`/`l`/`x` weights exist locally.
  - **`unified_pipeline.py:1007`** records that players are about **25 px at imgsz 640**, and that 480
    gives about 19 px, which it calls "below reliable detection". **Detection is operating near its own
    stated resolution floor with the weakest model in the family.**
  - **The GPU is idle.** Measured repeatedly: **0 pct utilisation under EIGHT concurrent route jobs**
    with 5,956 MiB of 24,576 MiB used, and 2 pct at 723 MiB when quiet. G216 eliminated storage as the
    constraint; per-frame profiling puts detection at `yolo=0.095 s` of a ~5.3 s frame.
  - **G200/G216**: N=2 is the best tested schedule and N=8 yields less throughput than N=1, so
    **more concurrency is NOT the way to use the idle GPU. A bigger model is.**

THE QUESTION: **what does detector capacity buy, and what does it cost, on this route?**

METHOD:
  1. **Baseline first, unchanged**, at the production configuration (`yolov8n`, `imgsz` as production
     sets it). **Do not change `imgsz` anywhere in this row** -- G202 owns the resolution axis and
     changing two things at once makes neither attributable.
  2. Sweep **`yolov8n` -> `yolov8s` -> `yolov8m`** by passing `yolo_model` through config **from your own
     process**. Confirm for each arm **which weight file was actually loaded** and its SHA-256 -- note
     that `_best_yolo_model` (`src/tracking/player_detection.py:50-66`) prefers a `.engine` if TensorRT
     imports and otherwise returns `f"{stem}.pt"`, which **ultralytics auto-downloads**. **A silently
     auto-downloaded weight is fine but must be RECORDED, not assumed.** If an arm falls back to nano,
     that arm is void -- say so rather than reporting it.
  3. **Report per arm**: raw detector box count per frame (distribution, not a mean), survivors reaching
     the emitted table, **wall time per frame**, **GPU utilisation and GPU memory**, and aggregate CPU.
     **The GPU numbers are a first-class deliverable of this row**, because the question is whether
     capacity converts idle GPU into detection quality.
  4. **n=3 per arm and report DISTRIBUTIONS.** The route is NON-DETERMINISTIC and no deterministic mode
     exists -- G190, G195, G198, G199 and G203 exhausted every enumerated candidate, and G203 showed
     decode is byte-identical yet output still differs. **Never report a single number as an arm's
     result.** If the spread between identical runs is comparable to the spread between arms, **say that
     the sweep cannot resolve the difference** -- that is a legitimate and important outcome.
  5. **MORE BOXES IS NOT BETTER. This is the trap in this row.** A larger model will detect more people,
     including spectators, coaches and bench players; a person detector is SUPPOSED to emit every person
     (that framing was withdrawn once already and must not return). **So report raw boxes and survivors
     SEPARATELY, and do the eye check**: on 3 evenly spaced frames per arm, render the raw boxes and
     state how many are on-court players. **An arm that raises raw boxes without raising on-court
     survivors is a NEGATIVE result and must be reported as one.**
  6. **State the throughput consequence honestly.** A bigger model costs time per frame. Given a full
     pass of `wnba__wnba_01` is 58,143 evaluated frames at stride 3, **report what each arm does to the
     projected full-clip wall time.** A quality gain that makes breadth measurement impossible is a
     trade-off to state, not a win to claim.

**LICENCE NOTE, so nobody reads this row as introducing an obligation:** the repo ALREADY depends on
ultralytics YOLOv8, which is **AGPL-3.0**, and already ships `yolov8n`. **Using `yolov8s`/`yolov8m`
changes NOTHING about the licence position** -- same package, same licence, different weights. **Do not
add any new third-party dependency, and do not vendor anything.** If an arm would require a new package,
skip it and say so.

**HONEST LIMITATIONS to state, not discover:** one clip, bounded runs, on a SHARED pod whose daemon and
keeper are always running -- record the load and do not present these as clean-machine figures. Survivor
counts depend on the whole selection path, not detection alone, so an unchanged survivor count does not
by itself prove the detector is not the constraint. The eye check is a single-labeller judgement.

**DO NOT** change `imgsz`, `conf`, `min_players`, any threshold, the coordinate contract, or any gate.
**DO NOT deploy a different model into the pod checkout or into production** -- run it in your own
process only, and leave the pod's configuration exactly as you found it. **DO NOT** propose a production
default change in this row; measure first.

ACCEPTANCE RULE:
  metric        = per arm (`yolov8n`/`yolov8s`/`yolov8m`), n=3: raw box distribution, survivors, wall
                  time per frame, GPU utilisation and memory, aggregate CPU, and the projected
                  full-clip time; plus the loaded weight path and SHA-256 for each arm
  before        = player detection has always run YOLOv8-nano because nothing sets `yolo_model`; the GPU
                  measures 0-2 pct utilised; detection is ~0.095 s of a ~5.3 s frame; capacity has never
                  been varied
  bar           = NO pass bar. **"A larger model does not raise on-court survivors" is a FULL SUCCESS**
                  and would redirect effort to the selector, which G202 owns. **"It raises survivors but
                  triples per-frame cost" is also a full success** -- it is a stated trade-off. Do not
                  tune, and do not report an arm whose weights did not actually load.
  n             = 3 runs x 3 arms on one clip, bounded, distributions reported
  eye check     = raw boxes rendered on 3 evenly spaced frames per arm, with a count of how many are
                  on-court players; commit the renders
  must not move = `imgsz`, `conf`, `min_players`, every threshold, bar and verdict, the coordinate
                  contract, `src/` (READ and IMPORT only), the pod daemon, keeper and its configuration,
                  the corpus (delete NOTHING), production defaults
EVIDENCE: docs/evidence/tracking/g225_detector_capacity_sweep_2026-09-04.md with the per-arm table, the
loaded-weight SHA-256s, the n=3 distributions, the GPU numbers, the renders and on-court counts, the
projected full-clip times, every disk-guard probe result, bytes freed, the load context for every
timing, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
POD: run there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
