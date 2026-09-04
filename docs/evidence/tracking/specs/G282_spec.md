GAP G282 | sport wnba | worktree a5 or a6 (whichever frees) | log g282_defect_rate_across_detector_draws
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** You may
IMPORT and RUN them; you may NOT edit them. Build any new harness in `scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **ALL OF IT IS ON THE POD.** The full-resolution source and the GPU are both there. Use
    **`~/bin/pod_run <aN> --ship <harness> --fetch <the per-run measurement JSONs and summaries> --
    <cmd>`**. **Fetch back only the measurement artifacts, never raw frames.**
  - **The disk guard belongs INSIDE the `pod_run` command.** A missing `/workspace` locally is NOT a disk
    failure; it means that step belongs in `pod_run`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** One lane routinely shows TWO python PIDs
sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). **Reduce to the SET of distinct
`/workspace/wt/a*` directories and compare THAT to 2.** Exclude your own process, your checker and its
parent. **Report the SET you observed**, and record `nvidia-smi` utilisation and each occupant's ARGS as
**evidence only -- do NOT act on them and do NOT propose a new N.** **This row needs the GPU, so it MUST
hold for a free lane. Do NOT interrupt a running row.**

**READ THE LANDED G241, G267, G270 AND G279 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE HEADLINE DEFECT FIGURE HAS NEVER BEEN REPRODUCED ON A SECOND DETECTOR DRAW.**
The programme's most-quoted tracking numbers are **13.6 pct of all finite same-ID steps and 10.5 pct of
both-endpoints-on-court steps above 40 ft/s** (G267/G270, recomputed exactly by G279 as
`4,090 / 29,973 = 0.136456` and `2,507 / 23,783 = 0.105411`).

**Three robustness questions have now been asked and two answered.** G279 showed the figure is robust to
the **cut point**. G278 showed the **span** is measurably friendlier than the clip. G274 showed it cannot
be replicated in a **second shot** because no map exists there. **The remaining one is the detector
itself: G241 established the detector is NON-DETERMINISTIC -- 808 of 1,201 records differed on an exact
re-run -- and every figure in the chain comes from a SINGLE DRAW.**

**Nobody knows whether 10.5 pct is a property of the system or of one draw.**

THE QUESTION: **how much does the implausible-step rate move across independent detector draws on the same
span with the same map?**

METHOD:
  1. **HOLD THE MAP AND THE SPAN FIXED. VARY ONLY THE DETECTOR DRAW.** Use **G233d's published homography
     anchored at seed frame 19599** and the **same source-frame span 19599-23399**, exactly as G267 did.
     **Do not re-fit, re-seed or re-label the map** -- the point is to isolate detector variability, and a
     new map would confound the two.
  2. **RUN THE G267 ROUTE THREE TIMES, UNCHANGED.** G267's `route_sha256` names
     `scripts/platformkit/tracking/g267_court_space_physical_plausibility.py`,
     `g196_homography_from_labelled_corners.py`, `g215_temporal_homography_propagation.py`,
     `src/tracking/player_detection.py` and `domains/basketball/tracking/adapter.py`. **Change no
     parameter, no threshold, no weight and no seed.** **Report each run's route sha256 and confirm they
     match G267's**; a mismatch means you are not measuring what this row asks and you must say so.
  3. **FOR EACH RUN report the same quantities G267 and G270 published**: total detections, eligible
     finite same-ID steps, both-endpoints-on-court steps, the count and fraction above 40 ft/s for both
     denominators, and the p99 and max step speed.
  4. **THEN REPORT THE SPREAD ACROSS THE THREE RUNS, AND G267's LANDED VALUES AS A FOURTH POINT.** Give
     min, max and range for each fraction. **State plainly in one sentence whether 10.5 pct is stable
     across draws.**
  5. **THREE RUNS BOUND A RANGE; THEY DO NOT ESTIMATE A VARIANCE.** Say so. **Do NOT compute a standard
     deviation from three points and present it as precision**, and **do NOT average the runs into a new
     headline** -- G267's published figure stands as the reference and this row reports how far draws move
     around it.
  6. **ALSO REPORT DETECTION-LEVEL CHURN**, to connect this to G241: across the three runs, the detection
     count per run and, if cheaply available, the fraction of records that differ between two runs.
     **Do not re-derive G241's 808/1,201 figure and do not restate it as this row's result.**
  7. **IF A SINGLE RUN EXCEEDS A REASONABLE TIME BUDGET, REPORT WHAT COMPLETED AND SAY SO.** **Two runs
     plus G267's landed values is a usable result; one run is not.** **NEVER PARK** -- report partial
     progress rather than waiting silently.
  8. **Do NOT touch `src/`, do NOT propose a production change, filter, gate or threshold, and do NOT
     move the 40 ft/s bar.** Contract B10.
  9. **The population is detector boxes, not authenticated players** (G273: only 0.597 of retained
     detections are a player on the court of play). **Name every denominator; never say "players"
     unqualified.**

**DISK GUARD, POD SIDE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- about
**39,011 MB at 2026-09-04 14:04**, roughly **11 GB free** against the 50 GB quota, and **a peer session
writes under `/workspace/wt`.** **Re-measure yourself.** **`dd conv=fsync` probe before writing, STOP and
report if it fails ON THE POD.** **Three full runs are the bulk -- keep per-run artifacts to the
measurement JSONs, write no frames or crops, and report committed bytes.** **Do NOT delete any corpus
source, and do NOT delete the two abandoned bridge partials (`baseball__npb_05.mp4.part` 2.4 GB,
`football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable acquisitions and the football one is
the only football footage in the programme.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **three draws on ONE span of ONE shot of ONE clip with ONE
map.** This bounds detector variability **only under that fixed map**; map error is held constant by
design and is therefore NOT included -- the homography was measured at 5 px median / 19 px p90 on the
**seed frame only** (G252). **Per G278 the span is measurably friendlier than the clip (0.836 against
0.656 court-bearing, p = 0.0078), so nothing here may be quoted clip-wide.** **A stable rate across draws
does NOT mean the rate is correct** -- it would mean the defect is reproducible, which is a different and
weaker claim, and G273's 0.208 non-person rate still applies to every draw.

ACCEPTANCE RULE:
  metric        = the three runs' route sha256 values checked against G267's; per-run detections, eligible
                  step counts for both denominators, the above-40-ft/s counts and fractions, p99 and max;
                  the min/max/range across the three runs with G267's landed values as a fourth point; the
                  one-sentence stability statement; and the per-run detection counts for the churn note
  before        = 13.6 pct all-steps and 10.5 pct both-endpoints-on-court, from a SINGLE draw of a
                  detector that G241 showed is non-deterministic
  bar           = **NO pass bar.** **"The rate is stable across draws" would materially strengthen every
                  downstream row.** **"The rate moves substantially" is the more valuable finding and
                  would mean the published figure must always carry a range.** **"Only two runs
                  completed" is a usable result.** Do not tune, do not average into a new headline, do not
                  move the bar.
  n             = 1 clip, 1 shot, 1 map, 3 detector draws plus G267's landed draw, the step counts you
                  state -- name every denominator in the verdict line, and name the detector-box
                  population
  eye check     = none; this row makes no visual judgement
  must not move = the 40 ft/s definition, G267's and G270's published figures and their landed artifact,
                  G233d's published map and labels, the seed frame and span, the court model, the
                  coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY -- run them, never edit
                  them), the pod daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g282_defect_rate_across_detector_draws_2026-09-04.md with the route
sha256 check, the per-run table, the spread table including G267 as a fourth point, the stability
sentence, the churn note, every disk-guard probe with the `du -sm /workspace` figure, bytes freed and
committed, and a NOT VERIFIED list. **The per-run summary must be committed as a machine-readable file.**
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
