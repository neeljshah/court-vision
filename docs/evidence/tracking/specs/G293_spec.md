GAP G293 | sport soccer + tennis | worktree a7 | log g293_cross_sport_footpoint_content
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**RATER NOTE, DO NOT CHANGE IT: THIS ROW IS DISPATCHED ON `gpt-5.6-terra` ON PURPOSE**, because its whole
comparison is against G287's landed WNBA baseline, which that model labelled. **A rater change would
confound a cross-sport difference with labeller variance.** **State your model in the memo**; if you are
not `gpt-5.6-terra`, **say so in the first line and report the comparison as rater-confounded.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **RUN SELECTION, FRAME EXTRACTION AND CROP RENDERING ARE ON THE POD** -- the tracking outputs and the
    source videos are there. Use **`~/bin/pod_run a7 --ship <harness> --fetch <crops and manifest> --
    <cmd>`**. A missing `/workspace` locally is NOT a failure; it means the step belongs inside `pod_run`.
  - **THE BLIND CLASSIFICATION AND ALL ARITHMETIC ARE LOCAL**, on crops fetched back.
  - **GATE: THIS ROW NEEDS CPU DECODE, NOT THE GPU.** Other rows hold the GPU and are also decoding.
    **Your gate is the `dd conv=fsync` probe on `/workspace` and load15 below `nproc` -- NOT a lane count
    and NOT `nvidia-smi`.** **Do NOT hold for a free lane and do NOT interrupt a running row.** Report the
    gate measurement you used. **This is an OPERATIONAL gate, not an evidentiary bar.**
  - **DISK GUARD:** `du -sm /workspace` is a MooseFS NETWORK walk -- **empty output means UNKNOWN, NEVER
    0, and you must NEVER stop on UNKNOWN.** **The only stopping condition is a FAILED `dd conv=fsync`
    probe on the pod.** You write ~96 small JPEGs, negligible. **DOWNLOAD NOTHING. Use only footage
    already on the pod.** **Delete no corpus source and neither bridge partial download.**

**READ FIRST:** the G277 memo and its `g277_per_run_summary.csv`, the G287 memo and its committed verdicts,
the G273 memo, and the G288 memo.

**WHY THIS ROW EXISTS -- THE PROGRAMME'S GOAL IS ANY GAME, ANY SPORT, ANY VIDEO, AND EVERY PRECISION
NUMBER IT HAS COMES FROM ONE WNBA CLIP.**
G286/G287 measured on that clip that only **0.208 of unconditioned footpoints sit on a player's feet** and
about **0.44 sit on a player at all**, with **0.181 on broadcast overlay furniture** (G288, 13/13).
**Nobody has measured whether that is a property of THIS BROADCAST or of THE DETECTOR.** G277 profiled 42
landed runs across 8 sports in image space, but **image-space profiling cannot say what the footpoint is
ON.** **If precision is far better on other sports, the WNBA figure is not the system's ceiling and the
any-video programme is in better shape than it looks. If it is the same or worse everywhere, the detector
is the bottleneck for arbitrary footage and that is the headline for the whole programme.**

THE QUESTION: **does the unconditioned footpoint-content profile replicate outside basketball?**

METHOD:
  1. **CHOOSE ONE SOCCER RUN AND ONE TENNIS RUN** from `g277_per_run_summary.csv` (4 runs each are
     listed). **Require `analysis_status` comparable, no `schema_missing_fields`, and a source video
     PRESENT ON THE POD -- verify presence and say how you verified it.** **If a chosen sport has no
     usable run, say so plainly and report the row for whichever sports DO have one; a one-sport result is
     an honest partial success.** **State the selection rule BEFORE you look at any crop, and name the
     runs you rejected and why.**
  2. **SAMPLE 48 RETAINED DETECTIONS PER RUN, UNCONDITIONED**, by the same one-per-time-bin rule G273 and
     G280 used. **Report frame and id coverage per run.** **48, not 72: say plainly that the smaller
     denominator gives WIDER intervals than G287's 72 and do not compare precision of estimates as if
     they were equal.**
  3. **RENDER CROPS WITH GEOMETRY IDENTICAL TO G273's**: 512x640 native pixels centred on the footpoint,
     same small red centre cross. **If a source is not 1920x1080, an identical ABSOLUTE crop covers a
     different FRACTION of the frame and IS NOT AN IDENTICAL TASK** -- that confound already bit G280b.
     **Report each run's native resolution and the crop's frame fraction, and ALSO render at the size
     covering the same FRACTION as 512x640 does at 1080p. Report both and say which you treat as primary
     and why.**
  4. **CLASSIFY ALL ARMS BLIND IN ONE POOLED RANDOMISED ORDER so you cannot tell which sport a crop came
     from. Commit the order and verdicts in their OWN commit BEFORE un-blinding or joining anything.**
  5. **CATEGORIES ARE G287's, JUDGED AT THE CENTRE CROSS, GENERALISED ONLY IN WORDING, NEVER IN MEANING**:
     (a) a PLAYER'S FEET; (b) a PLAYER'S BODY but not feet; (c) the BARE PLAYING SURFACE (court, pitch,
     grass, clay, dirt); (d) a BROADCAST GRAPHIC OR SCORE TICKER; (e) a PERSON who is not a player in play
     (official, coach, ball kid, crowd); (f) SOMETHING ELSE, free text; (g) CANNOT JUDGE, kept separate.
     **FREE TEXT IS MANDATORY ON EVERY ROW.** **State the wording generalisation explicitly and confirm
     you did not change any category's meaning.**
  6. **REPORT THE SEVEN COUNTS PER SPORT, AND COMPARE EACH SPORT'S "ON A PLAYER AT ALL" RATE -- (a)+(b) --
     TO G287's LANDED WNBA BASELINE** (read its committed verdicts, do NOT quote from memory).
     **Two-proportion test per comparison: pooled p, SE, z, NOMINAL two-sided p.** **You are making
     MULTIPLE comparisons: say that every p is nominal, that NO multiplicity correction is applied, and
     do NOT declare a best or worst sport.** **Overlapping confidence intervals are NOT a test.**
  7. **REPORT THE (d) GRAPHIC SHARE PER SPORT.** WNBA was 0.181. **A broadcast-furniture failure should
     appear wherever there is broadcast furniture; if it does not, say so.**
  8. **ANSWER IN ONE SENTENCE WITH NUMBERS: does the WNBA footpoint-content profile replicate outside
     basketball?** **REPLICATES means the detector, not the broadcast, is the bottleneck for arbitrary
     footage -- the headline for the whole programme. DOES NOT REPLICATE means the WNBA figure is
     clip-specific and must never again be quoted as a system-wide property. TOO NOISY AT 48 PER SPORT is
     an honest result. ALL are full successes and I want whichever is true stated bluntly.**
  9. **Propose NO filter, threshold, gate, retrain or production change. Do NOT touch `src/`. Do NOT move
     any bar. Do NOT change any landed verdict, count or artifact. DOWNLOAD NO FOOTAGE.**

**HONEST LIMITATIONS to state, not discover:** ONE run per sport, ONE labeller, and the runs are ONE draw
each of a route that is **non-deterministic on the research path (G241: 808 of 1,201 records differed)** --
**state which route each run used and whether it is the deterministic stride-3 production route or the
every-frame research route, because they are not the same measurement.** **A single run is not a sport**:
camera work, resolution, competition level and broadcast style vary enormously within any sport, so a
difference between two runs is **a difference between two videos**, not a proven difference between
sports. **Say that in those words.** **G278 showed a studied span can be measurably friendlier than its own
clip (0.836 against 0.656, p = 0.0078), so per-run results may not even represent their own run** unless
you sample across it -- say how you sampled. **A footpoint is a POINT: this row says what is AT it, never
what a bounding box contained.** The population is detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the stated selection rule with rejected runs named; per-run native resolution, crop
                  fraction and route; per-run sampling with frame and id coverage; the committed pooled
                  blind order and verdicts; the seven counts per sport at BOTH crop sizes; each sport's
                  (a)+(b) rate against G287's WNBA baseline with a two-proportion test and nominal p; the
                  (d) graphic share per sport; and the one-sentence replication answer
  before        = every footpoint-content figure in the programme (0.208 feet, ~0.44 player, 0.181
                  graphic) comes from ONE WNBA clip, with no measurement of whether it is a property of
                  that broadcast or of the detector
  bar           = **NO pass bar.** **Replication makes the detector the programme-wide bottleneck for
                  arbitrary footage. Non-replication makes the WNBA figure clip-specific and it must never
                  again be quoted as system-wide. Too noisy at 48 per sport is honest. ALL are full
                  successes.**
  n             = 1 soccer run, 1 tennis run, 48 detections each, 1 labeller, 1 draw per run, compared to
                  G287's 72 WNBA detections -- name every denominator in the verdict line, name the
                  detector-box population, and never say "players" unqualified
  eye check     = the blind classification IS the measurement. A COARSE categorical judgement at the
                  centre cross, not a geometric one. **Say that distinction.**
  must not move = G287's, G273's, G288's and G277's verdicts, counts and category definitions; every
                  threshold and verdict; `src/` and `domains/` (READ and IMPORT ONLY); the corpus, every
                  source video, and both bridge partial downloads
EVIDENCE: `docs/evidence/tracking/g293_cross_sport_footpoint_content_2026-09-04.md` with the selection
rule and rejections, per-run resolution, crop fraction and route, the sampling, the sealed order sha, the
per-sport counts at both crop sizes, the tests with nominal p and the multiplicity statement, the graphic
shares, the one-sentence answer, every disk-guard probe verbatim, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted -- **pin the one-per-time-bin sampler and the 512x640
crop geometry.** **NEVER a full pytest.** **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
