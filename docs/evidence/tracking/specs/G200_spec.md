**HOLD LIFTED 2026-09-03 on the user's explicit instruction to push GPU pressure on the pod.**
**G203 IS STILL RUNNING ON THIS MACHINE.** That is a real confound and you must handle it, not ignore
it: **record the concurrent load (`ps`, core count, what the daemon and any G203 job are doing) BEFORE
and AFTER every measurement, and report it beside every timing. A timing without its load context is
not a result.** If G203 has finished by the time you start, say so and note the machine was quieter.

**DISK GUARD, BINDING -- the pod hit `Disk quota exceeded` tonight.** `df` CANNOT see the volume cap;
it reports the whole cluster filesystem. **Before each arm, verify writable headroom with an actual
small write test (`dd` a few MB to a temp path and remove it), and record `du -sm` of
`/workspace/nba-ai-system/data`. If a write test FAILS, STOP IMMEDIATELY, report, and delete nothing.**
Give every concurrent job its own `--data-dir` and **delete your own job outputs when done**; do not
leave N sets of tracking output behind.

**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and wrap in your own
process only. Deploy nothing into the pod checkout (B5). **NEVER kill, restart or deploy over the pod
daemon or the keeper**, and never kill any process you did not start.

**S1 MACHINE: RUN ON THE POD.**

THE MEASURED FACT THIS ROW STARTS FROM, taken by the orchestrator on the pod 2026-09-03:
  - `nproc` = **256 cores**; `free -g` total **1007 GB**, available **934 GB**.
  - GPU at that moment: **2 pct utilisation, 664 MiB used of 24,576 MiB.**
  - One bounded route job (`--frames 1200`) was running at **1288 pct CPU**, i.e. about 13 cores.
  - So a single route job uses roughly **5 pct of the machine's cores and under 3 pct of its VRAM.**

THE QUESTION: **how many route jobs can run CONCURRENTLY on this pod before per-job throughput
degrades, and what binds first -- cores, VRAM, RAM, or video decode?**
This decides whether the tracking programme is throughput-limited by the machine or by our own
sequencing. Every determinism row so far has run jobs one at a time BY DESIGN, and that discipline
has been silently setting the programme's throughput ceiling.

METHOD:
  1. Establish a single-job baseline: run the bounded route once and record wall time, mean CPU pct,
     peak RSS, and peak GPU memory. **Use a DIFFERENT `--data-dir` per job, always.**
  2. Then run N concurrent jobs for **N = 2, 4, 8**, each on its own `--data-dir`. For each N record:
     per-job wall time, total wall time, aggregate CPU pct, peak host RAM, peak GPU memory and
     utilisation.
  3. Report **throughput** as completed jobs per minute at each N, and the **per-job slowdown factor**
     against the N=1 baseline.
  4. **Name what binds.** If per-job time is flat to N=8, say the machine is not the limit at 8 and
     say what the next test would be. If it degrades, attribute it with the recorded resource series,
     not by assertion.

**DO NOT tune anything to make concurrency look better.** No thread-count changes, no batch-size
changes, no `imgsz` changes, no precision changes. This measures the machine as the programme
actually uses it today.

**HONEST LIMITATIONS you must state rather than discover:** the route is NON-DETERMINISTIC (G189,
G193, G195), so per-job row counts will differ between jobs and that is expected and is NOT a
concurrency effect -- report wall time and resources, and do NOT present row-count differences as
evidence about concurrency. The pod also runs a daemon and a keeper you must not disturb; record
their CPU share so your baseline is honest about a shared machine, and if either is mid-job say so.

**A9:** `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes,
1920x1080, 174,430 frames. `--frames 1200 --no-show --skip-features`.
**A11:** record pod SHA-256 for `unified_pipeline.py` and `advanced_tracker.py`.
**B13/Q9:** per-job records in the artifact, not just per-N means.

ACCEPTANCE RULE:
  metric        = jobs per minute and per-job slowdown factor at N = 1, 2, 4, 8, with the resource
                  series that explains it
  before        = one route job uses about 13 of 256 cores and under 3 pct of VRAM; the concurrency
                  ceiling is unmeasured and the programme has been running jobs one at a time
  bar           = NO pass bar. **"Throughput is flat to N=8" and "it degrades sharply at N=2" are both
                  full successes.** The deliverable is a NUMBER we can schedule against.
  n             = 1 + 2 + 4 + 8 = 15 job runs of one clip (throughput, not quality)
  eye check     = none; this row makes no claim about tracking output
  must not move = every threshold, `conf`, `imgsz`, batch sizes, thread counts, the coordinate
                  contract, every bar and verdict, `src/` (READ ONLY), the pod daemon and keeper, the
                  corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g200_pod_concurrency_headroom_2026-09-03.md with the per-job table,
the resource series, the binding-constraint attribution, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest. **If it grows an allowlisted file, raise the entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and run that rail test.**
POD: run there. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
