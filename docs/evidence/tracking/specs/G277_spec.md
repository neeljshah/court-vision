GAP G277 | sport all | worktree a6 | log g277_cross_sport_image_space_profile
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **The records are ON THE POD**, under the deployed tree's gitignored tracking store,
    `data/tracking/<run>/tracking_data.csv`. **Verified 2026-09-04 12:55: 57 such files exist.**
  - **The ANALYSIS runs ON THE POD too**, because the CSVs total hundreds of MB and must not be shipped
    back. Use **`~/bin/pod_run a6 --ship <your harness> --fetch <your summary outputs> -- <cmd>`**, which
    copies this worktree's code tree to `/workspace/wt/a6`, runs there under nohup, and fetches only the
    listed paths back. **It never writes the deployed tree.**
  - **FETCH BACK ONLY SMALL SUMMARIES** -- per-run summary JSON/CSV of the statistics below. **Do NOT
    fetch raw tracking rows.**
  - **The disk guard is POD-side and belongs inside the `pod_run` command.** A missing `/workspace` in the
    local checkout is NOT a disk failure; it means that step belongs in `pod_run`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** N=2 is the measured optimum. One lane
routinely shows TWO python PIDs sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). **Reduce
to the SET of distinct `/workspace/wt/a*` directories and compare THAT to 2.** Exclude your own process,
your checker and its parent. **Report the SET you observed.** Do NOT interrupt a running row.

**READ THE LANDED G267, G271, G273, G274 MEMOS AND SECTION 7.19 OF CALIBRATION_STATE_2026-09-04.md
FIRST.**

**WHY THIS ROW EXISTS -- EVERY TRACKING NUMBER WE HAVE COMES FROM 2.2 PCT OF ONE CLIP, AND THERE ARE
ALREADY 42 TRACKED RUNS ACROSS 7 SPORTS SITTING ON THE POD.**
The chain (G267, G269, G270, G271, G272b, G273) was measured on frames 19599-23399 of
`wnba__wnba_01.mp4` -- **3,801 of 174,430 frames.** G274 then showed the adjacent shot has no court at
all, so **the court-space route cannot be extended without new hand labels.**

**But the image-space route needs no map, and the records already exist.** Verified schema, uniform across
files: `frame, track_id, cls, x, y, coordinate_space, observation, calibration, source_fps,
source_height, source_duration`, with `coordinate_space=image_px`, `calibration=none`, `cls=player` and
`observation=observed` as the only values present in the file checked. Row counts are large (soccer
240,661; football 258,248; mlb 183,929; npb 119,498).

THE QUESTION: **is the wnba clip's same-id image-displacement and track-length profile unusual among the
tracked runs, or typical?**

METHOD:
  1. **ENUMERATE THE RUNS AND SPLIT THEM PROPERLY. This is the first thing that can go wrong.** Of the 57
     runs, **15 are DETECTOR- OR HASH-VARIANT EXPERIMENTS on the same footage, not footage samples**, and
     **must be excluded from the cross-sport comparison**: the `g172_*`, `g225_yolov8{n,s,m}_r{1,2,3}_*`,
     `g226c_*`, `g239_*` and `g240_*_r{1,2,3}` directories. **That leaves 42 footage runs across 7
     sports** -- football 3, kbo 10, mlb 13, ncaa_basketball 1, npb 4, soccer 4, tennis 4, wnba 3.
     **List every run you included and every run you excluded, with the reason.** **If your count differs
     from 42, say so and go with what you measure, not with this number.**
  2. **NORMALISE, OR THE COMPARISON IS MEANINGLESS. THE RUNS DO NOT SHARE UNITS.** Verified: `source_fps`
     takes at least 30, 29.97 and 59.94, and `source_height` takes at least 1080 and 720. **A per-frame
     pixel displacement is therefore NOT comparable across runs** -- at 59.94 fps a body moves half as far
     per frame, and 100 px means twice as much in a 720-high frame as in a 1080-high one.
     **Use FRAME-HEIGHTS PER SECOND throughout:**
     `speed = sqrt(dx^2 + dy^2) / source_height * source_fps`, computed on **consecutive-frame,
     same-`track_id`** steps. **State the formula in the memo and state that raw pixels are never
     compared across runs.**
  3. **REPORT DISTRIBUTIONS, NOT A THRESHOLD.** For each run give the step count and the **median, p90,
     p99, p99.9 and max** of normalised speed, plus the **track-length distribution** (number of distinct
     `track_id`s, median and p90 track length in frames, and the fraction of tracks shorter than 5
     frames). **Do NOT invent a cross-sport threshold and do NOT reuse the 83 px or 40 ft/s figures** --
     both are specific to the wnba clip's resolution and to a court-space map that does not exist here.
  4. **AGGREGATE BY SPORT AND PLACE WNBA IN THE DISTRIBUTION.** For each statistic, **say where the wnba
     runs sit among all 42** -- rank or percentile. **The question this row exists to answer is whether
     the clip everything rests on is typical. Answer it in one plain sentence.**
  5. **THE CENTRAL HONESTY REQUIREMENT, STATE IT PROMINENTLY, DO NOT BURY IT:** **image-space displacement
     conflates player motion, CAMERA motion and tracking error, and without a map they cannot be
     separated.** Camera regimes differ enormously by sport -- a tennis camera is near-static, a soccer
     camera pans, a baseball broadcast cuts constantly. **So a larger tail in one sport is NOT evidence of
     worse tracking there, and the memo must say exactly that.** **What the row CAN establish is whether
     the wnba profile is an outlier among the runs; that is the claim, and nothing stronger.**
  6. **CHECK PROVENANCE AND FLAG THE CONFOUND.** The run names suggest different dates and pipelines
     (e.g. `mlb_2026-08-30_*` against `mlb_gDv5xF2AA2E`). **Look for any manifest, config or timestamp in
     each run directory and report what you find.** **If the runs were produced by different tracker
     versions, a cross-run difference confounds tracker version with footage, and you must say so.** **If
     you cannot determine provenance, say that plainly rather than assuming a common pipeline.**
  7. **Do NOT re-run the tracker or the detector on anything.** These are landed records; a fresh pass
     would be a different non-deterministic draw (G241: 808 of 1,201 records differed on an exact re-run).
  8. **Do NOT propose a filter, gate, threshold or production change; do NOT touch `src/`.** G269 showed
     how easily a filter fakes an improvement.
  9. **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
     people), and `cls=player` is the DETECTOR'S label, not a verified identity. **Name the denominator;
     never say "players" unqualified.** **Nothing in this row validates identity anywhere.**
 10. **`wnba_01` here is NOT G267's retained record set.** It is a separate landed run over presumably the
     whole clip. **Do not merge, compare row-for-row, or present them as the same data**; if you reference
     G267's figures at all, say they came from a different span and a different draw.

**DISK GUARD, POD SIDE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- about
**40,070 MB at 2026-09-04 12:50**, roughly **9.7 GB free** against the 50 GB quota, and **a peer session
writes under `/workspace/wt`.** **Re-measure yourself.** **`dd conv=fsync` probe before writing, STOP and
report if it fails.** **This row should write almost nothing -- summaries only, no crops, no renders, no
decode.** **Do NOT delete any corpus source, and do NOT delete the two abandoned bridge partials
(`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable
acquisitions and the football one is the only football footage in the programme.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** **this is not a quality ranking of sports** (step 5).
One run per clip, one draw of a non-deterministic detector per run, **unknown and possibly mixed tracker
provenance** (step 6). **`observation=observed` and `cls=player` were the only values in the ONE file
checked** -- **verify that per run and report any run where other values appear**, because a run
containing interpolated or coasted rows is not comparable to one that does not. Track length is measured
in frames, so **it is fps-dependent and must be reported in seconds as well.** Nothing here says anything
about court-space accuracy, calibration, or identity.

ACCEPTANCE RULE:
  metric        = the included and excluded run lists with reasons; the normalisation formula; per-run
                  step counts and the five speed quantiles in frame-heights per second; per-run track
                  counts and length distributions in frames AND seconds; the by-sport aggregation; **the
                  rank or percentile of the wnba runs on each statistic and a one-sentence plain answer to
                  whether wnba is typical**; the provenance findings; and the per-run check of the
                  `observation` and `cls` values
  before        = every tracking-quality number in the programme comes from 3,801 frames of one clip, and
                  nobody has looked at the 42 landed footage runs across 7 sports that already exist
  bar           = **NO pass bar.** **"The wnba clip is typical" would materially strengthen the existing
                  chain.** **"The wnba clip is an outlier" would weaken it and is the more valuable
                  finding.** **"The runs are not comparable because provenance is mixed" is ALSO a full
                  success** and would be an important infrastructure finding. Do not tune, do not filter,
                  do not rank sports by quality.
  n             = the run count you actually measure, the per-run step and track counts you state, 7
                  sports -- **name every denominator in the verdict line, and name the detector-box
                  population**
  eye check     = none; this row touches no images and makes no visual judgement
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained records and
                  span, the 40 ft/s and 83 px definitions (which do NOT apply here), the court model, the
                  coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the bridge partials, every landed tracking run
EVIDENCE: docs/evidence/tracking/g277_cross_sport_image_space_profile_2026-09-04.md with the run lists,
the normalisation statement, the full per-run table, the by-sport aggregation, the wnba placement and its
one-sentence answer, the provenance findings, the conflation statement from step 5 stated prominently,
every disk-guard probe with the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED
list. **The per-run summary table must be committed as a machine-readable file as well as in the memo.**
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
