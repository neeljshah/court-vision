GAP G211 | sport wnba | worktree a6 | log g211_per_frame_cost_attribution
**HELD -- DO NOT DISPATCH UNTIL G203 HAS REPORTED.** G203 holds the pod and this row needs a QUIET
machine to measure cost honestly.

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
**Detection is 95 ms. Everything after it is about 5.7 s: assign_render 2.23 s, crops_step3 1.77 s,
osnet 1.16 s.** That is consistent with G189's 3.5 fps and with the 3090 measured at **2 pct
utilisation, 664 MiB of 24,576 MiB**.

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
  4. **Answer the specific suspicious item: what is `assign_render` doing under `--no-show`, and why
     does it cost about 2.2 s?** Read the code path. **If a headless run is doing rendering work it
     does not need, that is the finding** -- quantify what fraction of the total it is. **If it turns
     out to be legitimate assignment work that is merely named "render", say so plainly; my suspicion
     is a hypothesis, not a premise.**
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
