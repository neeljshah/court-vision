GAP G282c | sport wnba | worktree a6 | log g282c_defect_rate_second_draw
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only -- run them, never edit them.**
Build any harness in `scripts/platformkit/tracking/`.

**THIS IS THE FOURTH ATTEMPT AT ONE QUESTION AND IT IS DELIBERATELY THE SMALLEST POSSIBLE VERSION.
READ THIS WHOLE FILE -- IT IS SHORT ON PURPOSE. Two earlier attempts died on things that were my fault,
and both are fixed below.**

THE QUESTION: **does a SECOND detector draw reproduce G267's implausible-step rate?**

Reference values, recomputed exactly by G279 from the landed artifact:
  - **all finite same-ID steps: 4,090 / 29,973 = 0.136456**
  - **both endpoints on court: 2,507 / 23,783 = 0.105411**

**ONE DRAW IS ENOUGH. Do NOT run three.** One fresh draw against G267's landed draw is a two-point
comparison and answers the question at its minimum useful size. Attempt three completed a full
3,801-frame pass and then **lost it**, which is far worse than a small result.

METHOD, in order, and the ORDER IS THE POINT:
  1. **Census the pod immediately before launching** -- distinct `/workspace/wt/a*` worktrees holding a
     LIVE python process, reduced to one entry per worktree, excluding your own process, checker, parent
     and any waiter you started. **A `(deleted)` cwd with a RUNNING process still counts.** Hold while
     that count is 2 or more, **re-censusing before every attempt, never once.** Report the censuses you
     saw.
  2. **Run the G267 route ONCE** on span 19599-23399 with **G233d's published homography anchored at seed
     frame 19599**. Change no parameter, threshold, weight or seed. Do not re-fit or re-seed the map.
  3. **THE MOMENT THE PASS COMPLETES, WRITE THE RAW MEASUREMENT JSON AND COMMIT IT.** **Nothing may sit
     between a completed pass and its committed artifact -- no disk guard, no parsing, no summary, no
     formatting.** **Attempt three completed a pass and then destroyed it in a `du` output parser; that
     failure mode is forbidden here.**
  4. **Only after that commit**, compute and report: total detections, eligible finite same-ID steps,
     both-endpoints-on-court steps, the count and fraction above 40 ft/s for both denominators, and p99
     and max step speed.
  5. **Compare against the two reference values above** and **state in one sentence whether the rate
     reproduces.**
  6. **Disk: echo the raw `du -sm /workspace` line verbatim into the memo. DO NOT PARSE IT.** Run a
     `dd conv=fsync` probe before writing and stop only if the probe itself fails. Delete no corpus source
     and neither bridge partial.

**BARS AND LIMITS:**
  - **NO pass bar.** **"It reproduces" strengthens every downstream row; "it moves" means the published
    figure must always carry a range.** Both are full successes.
  - **TWO POINTS BOUND NOTHING.** Do not compute a variance, a standard deviation or an interval from two
    draws, and **do not average them into a new headline.** G267's figure stands as the reference.
  - **Do not move the 40 ft/s bar** (contract B10) and do not touch `src/`.
  - The population is **detector boxes, not authenticated players** (G273: 0.597 are a player on the court
    of play). Name every denominator.
  - Map error is held constant by design and is **not** included; the homography was measured at 5 px
    median / 19 px p90 on the **seed frame only**.
  - **Per G278 this span is measurably friendlier than the clip (0.836 against 0.656 court-bearing,
    p = 0.0078), so nothing here may be quoted clip-wide.**
  - A reproducing rate means the defect is **reproducible**, not **correct**.

EVIDENCE: `docs/evidence/tracking/g282c_defect_rate_second_draw_2026-09-04.md` with the censuses, the raw
measurement JSON path, the figures, the one-sentence verdict, the verbatim `du` line, and a NOT VERIFIED
list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Commit the raw artifact the moment it exists
(step 3), then the memo. Make EVERY commit before you finish.** ASCII stdout. **NEVER PARK.**
