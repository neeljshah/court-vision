# Tracking architecture: consolidated diagnosis and the plan that follows from it

Written by the orchestrator 2026-09-03 after a day of measurement rows and an
external survey of the published state of the art. **Nothing here is a result.**
Every number cited is a landed row named in the text; the architecture section is
a plan and is labelled as such.

---

## 1. What we measured today, consolidated

| # | Finding | Row | Status |
|---|---|---|---|
| 1 | 0 of 40 pod ledger rows pass. Unchanged all day. | live ledger | measured |
| 2 | 29 of 40 fail `coordinate_contract`, and it is BY DESIGN: `adapter_run.py:47` sets `IMAGE_SPACE = {baseball, football, soccer}` and `:102-105` applies `image_space=True` unconditionally. Those adapters emit pixel rows and `continue` before their calibration branch. | G185 | measured |
| 3 | Calibration on real pod footage: **0 of 120** adapter-evaluated frames for baseball, football and soccer each. | G185 | measured |
| 4 | Tennis corner detection loses **26,113 / 28,773 = 90.755 pct** of frames. | G182 | measured |
| 5 | That loss is dominated by footage with no court visible (modal gates, eye-confirmed), not by a detector defect. One genuine full-court miss exists at `horizontal_roles`. | G184, G182b | measured |
| 6 | Basketball's crash was a missing 51 KB `resources/2d_map.png`, not a footage limit. | G186b | measured, fixed |
| 7 | `decoded_frame_count` decoded whole files to count frames: 22+ min at 99 pct CPU on one 3.37 GB clip. Now metadata-first: same value in **0.21 s**, 6/6 equality. | G186 | measured, fixed, deployed |
| 8 | **The `run_clip.py` route is NON-DETERMINISTIC**: five identical runs gave 1,104 / 1,246 / 1,247 / 1,360 / 1,549 player rows, a **40 pct spread**. FP16 on GPU device 0; raw detector emits 15 boxes each time but not byte-identical ones. | G189 | measured |
| 9 | Player selection emits spectators and bench while missing on-court players. | G187, G18 | observed, single-run |
| 10 | Some survivor tuples fall outside the frame (x1=2979 on a 1920-wide frame; y1=-35). | G189 | observed, unresolved |

---

## 2. The architectural diagnosis, against the published state of the art

Surveyed 2026-09-03. **Our stack is roughly a generation behind on all three
components, and findings 4, 5, 9 and 10 above are the EXPECTED symptoms of that
gap rather than mysterious bugs.**

| Component | What we do | What the field does | Consequence for us |
|---|---|---|---|
| **Detection** | stock `yolov8n.pt` -- the NANO model, COCO-pretrained, generic `person` class, `conf=0.22` | fine-tuned sports detectors: YOLOX, YOLOv8/v11, RF-DETR, trained on sports data | A COCO person detector has no concept of "on-court player". **Emitting spectators is correct behaviour for the model we are running.** Finding 9 is not a bug in our selection code so much as the absence of a sports-trained detector. |
| **Association** | hand-rolled per-half box heuristics (`detect_players` picking a per-half box) | tracking-by-detection with Deep-EIoU or BoT-SORT; Deep-EIoU reports HOTA 77.2 on SportsMOT and 85.4 on SoccerNet | Our heuristic has no appearance model and no principled association, so identity and selection both degrade. |
| **Calibration** | hand-rolled Hough lines plus hand-written 5/4/4 role templates, cross-ratio checks, `TOPHAT_CONTRASTS` | learned keypoint + line detection then point-line optimisation: PnLCalib, TVCalib; KaliCalib is basketball-specific | The literature states plainly that traditional search-based methods struggle on broadcast angles and occlusion. **Finding 4's 90.755 pct is that statement, measured on our footage.** |
| **Determinism** | FP16 inference, no fixed seed, stateful tracker | measurement runs pin determinism or report distributions | Finding 8. Near-threshold boxes flip and the stateful tracker amplifies one flip across the clip. |

### The keystone

**Calibration is the single highest-leverage component, because it collapses
three failure classes into one fix.** A working field homography gives:

1. **`court_feet` coordinates** -> satisfies the coordinate contract that
   currently accounts for 29 of 40 ledger failures (finding 2).
2. **A field polygon** -> project detections and drop everything off-field. That
   removes spectators and bench without any new detector (finding 9), and bounds
   coordinates (finding 10).
3. **A scorable quantity at all** -> without it these sports emit preservation
   data that was never eligible to pass.

Fixing detection alone leaves us with better boxes in pixel space, still
unscorable. Fixing calibration alone makes the existing boxes both scorable and
filterable. **Calibration first is not a preference; it is the dependency order.**

### Licensing constraint, which is real and binds the choice

The public origin is recruiter/buyer-facing. Ultralytics is AGPL and
`scripts/platformkit/detection/shim.py` already carries a standing note to
replace it with Apache-2.0 YOLOX. **PnLCalib is GPL-2.0 and soccer-only**, so it
cannot be vendored into this repo either. What transfers is the METHOD -- a
learned keypoint detector plus point-line optimisation -- not the code. Any
adoption must state its licence in the row before a line is written.

### An asset we already own and are not using

The reachability record notes that G140 left **68 committed pixel targets and a
measured 11.39 px precision floor** as reusable basketball ground truth. That is
a training and evaluation set for a learned court-keypoint model that already
exists in this repo. No new labelling is needed to start.

---

## 3. Sequencing, in dependency order

Each step is a gap row with its own spec. **No step begins before the one above
it has landed**, because each depends on the previous being trustworthy.

| Order | Row | Why it must come first |
|---|---|---|
| **0** | **Determinism control** | Nothing measured through `run_clip.py` means anything until a run repeats (finding 8). Either a `--deterministic` measurement mode (fixed seed, FP32 or deterministic cuDNN) or a mandatory 3-run distribution. **Every quality row after this depends on it.** |
| 1 | Off-field filter using the EXISTING tennis homography | Tennis already produces a homography on 9.245 pct of frames. On exactly those frames we can test the polygon filter cheaply and measure whether it removes non-players -- before building anything new. |
| 2 | Learned court-keypoint model for basketball, using G140's 68 targets | The ground truth exists. Basketball is the core sport. KaliCalib is the published precedent. |
| 3 | Detector upgrade, licence-clean | Only after calibration, because a better detector in pixel space still fails the coordinate contract. |
| 4 | Association upgrade (Deep-EIoU class method) | Last, because it improves identity given good detections and a filtered field. |

**Explicitly NOT on this list:** more measurement rows about denominators, more
tennis funnels, and any new sport. Those are finished or blocked.

---

## 4. Why the process failed today, and the rules that follow

Four defective specs (G174 wrong premise, G178 a mechanism present in 1 of 21
jobs, G185 a baseball calibrated path that does not exist, G188 no machine
named), three near-destructive worktree frees, one silent lane death holding an
uncommitted fix, 2.94 GB of reader-required footage deleted before the survey
that said what was needed, and quality measurement built on an unverified
reproducibility assumption.

Every one of those is a rule that did not exist. Proposed additions are in
section 5 and are written as contract clauses, not advice.

---

## 5. Proposed VERIFIER_CONTRACT v2 clauses

Each clause names the failure that produced it. **A rule with no incident behind
it is not proposed here** -- the contract earns its length or it does not grow.

### A. Verifier duties (additions)

**A8 REPRODUCE BEFORE YOU MEASURE.** Before any quality, recall, coverage or
selection claim is made through a processing route, that route must be shown to
repeat: run it at least 3 times on one fixed input and report the spread. If it
does not repeat, every claim through it reports a DISTRIBUTION over >= 3 runs, or
the row uses a pinned deterministic mode and says so. *(G189: five identical runs
of `run_clip.py` spread 1,104-1,549 rows, 40 pct, and three quality rows had
already been landed on it.)*

**A9 NAME THE EXACT SOURCE.** Every artifact and memo states the full path, byte
size and resolution of each input opened -- never a `game_id` alone. *(Two
different videos answer to `wnba_01`: a 1920x1080 pod file and a 1280x720
`g130_recensus/` derivative. The same code gives materially different answers on
them, and only G187 naming its byte size made the mismatch catchable.)*

**A10 STATE THE LICENCE BEFORE THE LINE.** Any row proposing external code names
its licence and whether that licence is compatible with a public
recruiter-facing origin, BEFORE any is written or vendored. *(Ultralytics is
AGPL and carries a standing replacement note; PnLCalib is GPL-2.0.)*

### B. Automatic rejects (additions)

**B11 SINGLE-RUN CLAIM ON AN UNREPRODUCED ROUTE.** Quoting n=1 through a route
whose repeatability is unestablished as a property of the system. The run is a
record of itself and nothing more. This binds EYE CHECKS equally: rendered
overlays come from one run. *(G187's counts and my own eye check on its renders,
both withdrawn as system properties by G189.)*

**B12 UNVERIFIED SPEC PREMISE.** A spec asserting a mechanism, path, count or
file that its author did not verify against the code or the live system. The
LANE is not at fault for stopping; the SPEC AUTHOR owns the wasted cycle and the
row records it. *(G174 asserted a 19-table denominator that was 0. G178 named
`frame_manifest.csv` as persisted per job; it existed for 1 of 21. G185 asserted
a calibrated baseball emit path that does not exist.)*

**B13 AGGREGATE-ONLY ARTIFACT.** An artifact storing summary counts without the
per-unit records the summary was computed from. The verifier cannot recompute it,
so A2 cannot be satisfied and the row is downgraded. *(G182b's artifact held
aggregates only and its counts were not independently reproducible; G182's
per-frame records reproduced exactly.)*

### S. Spec-authoring duties (new section -- these bind the ORCHESTRATOR)

**S1 NAME THE MACHINE.** Every spec that runs anything states where it runs, in
its own line, with the reason. "Pod is read-only" plus "do not wait on the
daemon" reads as "work locally" unless the machine is named. *(G188 ran
`run_clip.py` on the 16 GB local box and hit two RAM guards at 95 and 96 pct with
other lanes live; its sibling G187, written an hour earlier, did name the pod.)*

**S2 VERIFY THE PREMISE BEFORE DISPATCH, NOT AFTER.** The orchestrator checks
each premise against the code or the live system before the spec is sent. Q8
makes the LANE re-measure; S2 makes the AUTHOR measure first. Four defective
specs in one day is a spec-authoring failure rate, not bad luck.

**S3 STATE THE DEPENDENCY.** A spec whose question only makes sense if an earlier
row holds names that row and its verdict. A quality spec dispatched before
determinism is established is void on arrival.

### D. Destructive-action duties (new section -- these bind the ORCHESTRATOR)

**D1 CONTENT, NOT PATHS, BEFORE FREEING A WORKTREE.** Never free on
dispatched-vs-exited or on path existence. Compare blob hashes of every unlanded
commit's files against master; a differing path that exists is UNLANDED. *(G175's
finished memo and renders were destroyed and recovered only from the reflog. A
second lane wrote a distinct implementation at a path that already existed on
master, which a path-existence check called "safe to free".)*

**D2 SURVEY READERS BEFORE DELETING ANY DATA.** Run the A5 reader survey FIRST.
A durable derived artifact is NOT evidence its source is spent: readers that
re-measure from source frames need the original, and a reader that tests
non-reproducibility makes its sources irreplaceable by construction. Write a
per-file deletion manifest BEFORE deleting. *(23 sources deleted on a durability
test alone; 10 of them, 2.94 GB, are named by four readers, none re-fetchable and
none recoverable. The ledger recorded counts but no filenames, so six further
missing files cannot be attributed at all.)*

**D3 A LANE THAT STOPS SPEAKING IS NOT A LANE THAT FINISHED.** A never-exited
lane silent past 10 minutes is presumed dead; check its worktree for uncommitted
work and commit that work BEFORE any cleanup. *(G186's process vanished with its
log frozen; the fix sat uncommitted for 18 minutes while the status check read
"running", one `git clean` from gone.)*

**D4 MATCH PROCESSES BY EXECUTABLE AND ARGUMENT, NEVER BY SUBSTRING.** A
substring match on a command line catches the tools doing the matching. *(Twice
in one day: a broad match killed an ssh client and a PowerShell wrapper, then a
second killed my own monitor, because each merely mentioned the target name.)*

---

## 6. What "automatic at the highest level" requires, and what it does not

**It does not mean more lanes in parallel.** Today ran 5-6 lanes and moved the
passing-row count by zero. Throughput was never the constraint; correctness of
premises and ordering was.

The automation that is worth building, in order:

1. **A pre-dispatch premise check** the orchestrator must pass before a spec is
   sent -- S2 as a script, not a habit. Each spec declares its premises as
   assertions; the script runs them; a failing assertion blocks dispatch.
2. **A reproducibility gate** -- A8 as a script. A route used by a quality spec
   must have a determinism record no older than its last code change.
3. **Lane liveness with salvage** -- D3, already partly built into
   `lane_status.py`, extended to auto-commit a dead lane's uncommitted work to a
   WIP branch rather than leaving it exposed.
4. **A dependency graph over gap rows** -- S3 as data, so a spec cannot be
   dispatched while the row it depends on is OPEN.

Those four remove every process failure recorded in section 4. None of them is
about running more work at once.
