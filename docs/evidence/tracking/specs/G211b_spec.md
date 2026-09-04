GAP G211b | sport wnba | worktree a4 | log g211b_per_frame_cost_retry
**MEASUREMENT AND PROPOSAL ONLY. Change NO production code in `src/`** -- human-gated, READ and wrap in
your own process only. Build in `scripts/platformkit/tracking/`.

**READ `docs/evidence/tracking/specs/G211_spec.md` IN FULL FIRST, INCLUDING ALL THREE AMENDMENTS, AND
`docs/evidence/tracking/g211_per_frame_cost_attribution_2026-09-03.md`. This row inherits every one of
G211's requirements unchanged.** It exists only because G211's instrumentation never received a frame.

**WHAT G211 ALREADY DELIVERED -- DO NOT REBUILD IT.** `scripts/platformkit/tracking/g211_per_frame_cost.py`
is landed on master with its per-file test. It wraps `AdvancedFeetDetector.get_players_pos` in a
streamed, additive, off-by-default process-local wrapper with **seven MUTUALLY EXCLUSIVE buckets** --
`pre_yolo`, `yolo`, `post_yolo`, `crops_step3`, `osnet`, `assign_state`, `render` -- and **a reducer that
asserts the total equals their sum and names any remainder.** That is the disjoint decomposition the
amendment demanded, and it replaces the legacy intervals, which cannot be shares because
`assign_render` begins BEFORE OSNet and spans it (they summed to 6.92 s against a stated 5.267 s total).
**Reuse it unchanged unless it is actually broken; if you must change it, say exactly what and why.**

**WHY G211 PRODUCED NOTHING, AND THE ONE THING YOU MUST DO DIFFERENTLY.** Its one-source-frame smoke
route **exited 3 after nine processed source frames, with no tracking rows and ZERO calls reaching the
instrumented collector**; a later 360-frame attempt fixed a wrapper-global binding defect but still
yielded no record. **The leading explanation, from G206: `--frames N` counts DETECTOR-SELECTED GAMEPLAY
frames and FAILS CLOSED, so a small budget can terminate before a single gameplay frame is ever
selected.** **Therefore: use a frame budget known to work. G200 and G216 both ran `--frames 1200
--no-show --skip-features` successfully on this exact clip, many times. Start there.** **Confirm the
collector actually received calls BEFORE reporting anything** -- an empty sample must be reported as an
empty sample, never as a result.

**THE POD IS NEVER QUIET. DO NOT WAIT AND DO NOT PARK.** `track_daemon`, `keep_track_daemon.sh`,
`adapter_run` jobs, `inplay_capture_runner`, `foundry_runner` and a scheduler are PERMANENT residents and
are the LOAD FLOOR, not a conflict. G211 handled this correctly -- it recorded a floor of load 13.02 to
15.84, GPU 0 pct at 354 MiB, tennis `adapter_run` about 69 pct, `foundry_runner` about 17 pct, capture
about 13 pct, scheduler about 6 pct -- **and you should do the same: snapshot the floor immediately
before and after every timing, report each timing beside its own floor, and discard-and-repeat any
timing whose floor shifted materially, saying how many you discarded.** State plainly that these are
SHARED-MACHINE figures, so absolutes are upper bounds and **the PROPORTIONS are the deliverable.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE on this pod (it reports the whole cluster filesystem
against a 50 GB volume cap, which caused a `Disk quota exceeded` incident). **`dd conv=fsync` write
probe before writing, record `du -sm /workspace/nba-ai-system/data`, STOP and report if it fails.**
Delete temporary artifacts and report bytes freed. **Never kill, restart or deploy over the daemon or
keeper. Delete no corpus source.**

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. **A11:** record pod SHA-256 for `run_clip.py`, `unified_pipeline.py` and
`advanced_tracker.py`, as G211 did.

**EVERYTHING BELOW THIS LINE IS G211's ORIGINAL SPEC, INHERITED UNCHANGED.**
--------------------------------------------------------------------------------

**What still stands and is the reason for the row:** detection (`yolo=0.095`) is a small fraction of
per-frame cost and the remainder is CPU-side. That is independently corroborated by the GPU measuring
0-2 pct utilisation in every observation, including under **8 concurrent route jobs** where it used
**5,524 MiB of 24,576 MiB at 0 pct** with load average 63.5 of 256 cores.

**THIRD AMENDMENT 2026-09-04. THE PREVIOUS "QUIET MACHINE" REQUIREMENT WAS MY ERROR AND IT MADE THIS
ROW UNRUNNABLE. An attempt on 2026-09-04 correctly refused to measure and reported that
daemon-launched tennis routing and an active frame-count scan were still consuming CPU. Its reasoning
followed my spec exactly. The spec was wrong.**

**THE POD IS NEVER QUIET AND NEVER WILL BE.** `keep_track_daemon.sh` supervises
`track_daemon --workers 10 --forever`, which keeps `adapter_run` jobs running continuously; an
`inplay_capture_runner`, a `foundry_runner`, a scheduler and periodic `ffprobe -count_frames` scans also
live there permanently. **Waiting for silence is waiting forever. DO NOT WAIT. DO NOT PARK.**

**MEASURE WITH THE FLOOR PRESENT AND RECORD IT -- that is exactly what G200 and G216 did, and both
produced landed, useful results.** The binding requirements are:
  - **Snapshot the load floor immediately BEFORE and immediately AFTER every timing** (`ps` top
    consumers with CPU pct, `uptime` load average, `nvidia-smi`, `free`), and report each timing beside
    its own floor. **A timing without its load context is not a result** -- that rule stands.
  - **State plainly that these are SHARED-MACHINE figures, not clean-machine capacity**, and that the
    ABSOLUTE per-frame cost is therefore an upper bound. **The PROPORTIONS and the DECOMPOSITION are
    what this row is for, and they survive a shared machine far better than absolutes do.**
  - **If the floor changes materially between the before and after snapshot of a timing, DISCARD that
    timing and repeat it**, saying how many you discarded. That is the honest way to handle contention,
    rather than waiting for a silence that never comes.
  - **The ONLY thing you should wait for is another ORCHESTRATOR-DISPATCHED measurement row** (a G-row
    running route jobs on the pod). At dispatch time none is running. **The daemon, keeper, supervisor,
    capture and foundry processes are the FLOOR, not a conflict.** Never kill or restart any of them.

**ONE FINDING FROM TONIGHT THAT SHARPENS THIS ROW: the GPU is idle even under heavy load.** Observed
directly on the pod under EIGHT concurrent route jobs: `nvidia-smi` reported **0 pct utilisation with
5,956 MiB of 24,576 MiB used**, while load average sat near 57 of 256 cores. Separately, **OPS-NVDEC-UNUSED
established that `decord` on the pod is built WITHOUT CUDA, so all video decode runs on CPU and the
3090's hardware decoder is completely unused.** So the CPU-bound conclusion is no longer a hypothesis
from one profile line; it is corroborated from three independent directions. **Your job is to say WHICH
CPU work dominates, precisely enough that someone could act on it.**

**MEASUREMENT AND PROPOSAL ONLY. Change NO production code in `src/`** -- human-gated, READ and wrap in
your own process only. `scripts/run_clip.py` is NOT human-gated and may be changed **only if** the
change is additive and off by default. Deploy nothing into the pod checkout (B5).

**S1 MACHINE: RUN ON THE POD**, and **record what else is running on it** -- see the contention
warning below, which is the whole reason this row exists in this form.

**S3 DEPENDENCY. The orchestrator read a live profile line out of a G203 route log on the pod:**
    `[PROFILE f=780] gameplay=0.003s homog=0.035s players=5.370s ball=0.344s TOTAL=5.751s`
    `[SUBPROFILE]   yolo=0.095  ac_call=0.021  hsv=0.370  warmup=0.568  classify_dyn=0.383`
    `               ctrack_upd=0.314  n_boxes=17.000  crops_step3=1.774  osnet=1.163`
    `               assign_render=2.232  total=5.267`
**Detection is 95 ms and the rest is CPU-side. Read those sub-timings as OVERLAPPING, not as shares:
they sum to 6.92 s against `total=5.267 s` (see the amendment above).** The CPU-bound conclusion is
consistent with G189's 3.5 fps and with the 3090 measured at **2 pct utilisation, 664 MiB of
24,576 MiB**.

**WHY THIS IS THE BINDING CONSTRAINT.** G206 established that a coverage number needs a FULL-LENGTH
run, because `--frames N` counts detector-selected gameplay frames and fails closed. A full pass of
`wnba__wnba_01` is **58,143 evaluated frames at stride 3**. Even at G189's optimistic 0.29 s/frame
that is **4.7 hours for one clip**. The goal is arbitrary-footage tracking across a corpus, so
per-frame cost decides whether breadth measurement is possible at all.

**THE CONTENTION WARNING, and you must not repeat my error:** the numbers above came from a run
sharing the pod with `track_daemon --workers 10`, a supervisor and an in-game capture process.
**The ABSOLUTE 5.75 s is inflated and must not be quoted as the clean cost. Only the PROPORTIONS are
carried forward as prior.** Your first job is to measure the cost **cleanly**.

METHOD:
  1. **Record the machine's concurrent load** (`ps`, core count, what the daemon is doing) BEFORE and
     AFTER each measurement, and report it alongside every timing. **A timing without its load
     context is not a result.**
  2. Measure per-frame cost over a bounded run with the route's existing profile instrumentation.
     Report the **DISTRIBUTION across frames** (median, p90, max), not one frame (S2). One profile
     line is an anecdote; I quoted one and labelled it as such, and you must do better.
  3. **Attribute the cost exhaustively.** The stage times must account for the total; if they do not,
     say how much is unattributed rather than rounding it away.
  4. **Answer what `assign_render` actually spends 2.2 s on.** The orchestrator has already
     established it does NO rendering (zero drawing calls in `advanced_tracker.py:1472-1773`), so do
     not re-check that. It is assignment and tracking-state work: identify WHICH operations dominate,
     and whether any is quadratic in box count or repeated per box where it could be batched.
  5. Do the same for `crops_step3` (1.77 s) and `osnet` (1.16 s): what are they for, and is either
     avoidable for a run whose only purpose is coverage measurement, without changing what the
     coverage number MEANS? **A speedup that changes which players survive is NOT acceptable** -- it
     would alter the metric, which is B10 territory.
  6. **Deliver a PROPOSAL, not an applied optimisation, for anything inside `src/`.** State the
     expected saving and what it would cost in fidelity. Any `run_clip.py` change must be additive
     and **off by default**.

ACCEPTANCE RULE:
  metric        = per-frame cost distribution (median/p90/max) with concurrent load recorded; an
                  exhaustive stage attribution with any unattributed remainder named; a per-stage
                  avoidable/not-avoidable judgement with reasons
  before        = one contended profile line suggests detection is 1.7 pct of cost and CPU
                  post-processing about 98 pct; the clean per-frame cost is unmeasured and the
                  full-clip projection (4.7 h) rests on an old 3.5 fps figure
  bar           = NO pass bar. **"The cost is irreducible without changing what the metric means" is a
                  FULL SUCCESS** -- it would force the concurrency route instead, and that is a real
                  decision. Do NOT tune anything to make a number look better, and do not apply a
                  speedup that changes survivors.
  n             = one bounded run per configuration, cost reported as a distribution over frames
  eye check     = none; this row is about time
  must not move = every threshold, `conf`, `imgsz`, the crop, `min_players`, the coordinate contract,
                  every bar and verdict, WHICH PLAYERS SURVIVE, `src/` (READ ONLY), the pod daemon and
                  keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g211_per_frame_cost_attribution_2026-09-03.md with the cost
distribution, the load context for every timing, the exhaustive attribution, the `assign_render`
answer, the avoidability judgements, any proposal clearly marked as human-gated, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
POD: run there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
