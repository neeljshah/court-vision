GAP G292 | sport wnba | worktree a6 | log g292_jump_endpoint_content
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**RATER NOTE, READ IT FIRST AND DO NOT CHANGE IT: THIS ROW MUST RUN ON THE SAME MODEL THAT LABELLED G287
(`gpt-5.6-terra`), AND IT IS DISPATCHED THAT WAY DELIBERATELY.** Its whole comparison is against G287's
landed unconditioned baseline, and **a rater change would confound the comparison with labeller
variance.** **State your model in the memo.** If you are NOT `gpt-5.6-terra`, **say so in the first line of
the memo and report the comparison as rater-confounded.**

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **FRAME EXTRACTION AND CROP RENDERING ARE ON THE POD** -- the source video is there. Use
    **`~/bin/pod_run a6 --ship <harness> --fetch <crops and manifest> -- <cmd>`**. A missing `/workspace`
    locally is NOT a failure; it means the step belongs inside `pod_run`.
  - **THE BLIND CLASSIFICATION AND ALL ARITHMETIC ARE LOCAL**, on crops fetched back.
  - **GATE: THIS ROW NEEDS CPU DECODE, NOT THE GPU.** Another row holds the GPU. **Your gate is the
    `dd conv=fsync` probe on `/workspace` and load15 below `nproc` -- NOT a lane count, and NOT
    `nvidia-smi`.** **Do NOT hold for a free lane and do NOT interrupt a running row.** Report the gate
    measurement you used. **This is an OPERATIONAL gate, not an evidentiary bar; nothing in this spec's
    acceptance rule may move.**
  - **DISK GUARD:** `du -sm /workspace` is a MooseFS NETWORK walk -- **empty output means UNKNOWN, NEVER 0,
    and you must NEVER stop on UNKNOWN** (a lane that parsed empty `du` as 0 lost a completed 3,801-frame
    pass). **The only stopping condition is a FAILED `dd conv=fsync` probe on the pod.** You write ~72
    small JPEGs, so the footprint is negligible. **Delete no corpus source and neither bridge partial
    download.** **Never put the guard in the write path of a completed result.**

**READ FIRST:** the G289 memo and ledger row (landed 3f2000f20), the G287 memo and its verdicts, the G273
memo, and the G288 memo.

**WHY THIS ROW EXISTS -- 84.6 PCT OF THE PROGRAMME'S LARGEST ANOMALY IS NOW KNOWN TO BE A REAL IMAGE JUMP,
AND NOBODY HAS LOOKED AT WHAT IS AT EITHER END OF ONE.**
G289 landed the exhaustive partition: of 4,090 implausible steps, **only 630 = 0.154 moved 20 px or less
in the image, so projective amplification is refuted as the mechanism**, and **3,460 = 0.846 are genuinely
large image displacements, 1,897 of them beyond 150 px.** Their cause is **unexplained**. Bimodal ids
account for 0.045 and alternation is refuted at 0.876 non-returning.

**Meanwhile G286/G287 measured what unconditioned footpoints actually sit on: only 0.208 on a player's
feet, about 0.44 on a player at all, and 0.181 on a broadcast graphic (G288 confirmed 13/13 of those are
overlay furniture).** **So the obvious untested candidate is that a large jump is a track id RE-ANCHORING
between a real person and non-player content -- which would make the anomaly a DETECTION defect, matching
the programme's other evidence, rather than an identity defect, which G281 already measured as healthy
(purity 0.935 at 1 s).**

THE QUESTION: **at the two ends of a large image jump, what is actually there -- and is it less often a
player than at a randomly chosen detection?**

METHOD:
  1. **RE-DERIVE THE JUMP POPULATION FROM THE LANDED G289 ARTIFACT**, not from a fresh pass:
     `docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv`. **Select steps that
     are implausible AND have image displacement above 150 px** -- G289 reports 1,897 of them. **Confirm
     you get 1,897 and report your count; if it differs, STOP and report that as the finding.**
  2. **CONFIRM THE SAMPLES ARE COMPARABLE BEFORE COMPARING THEM.** G287's baseline was judged on G273's 72
     crops. **Establish and state plainly whether G273's crops were drawn from the SAME retained-record
     set that G267/G289 use.** **If they are NOT the same draw, say so and report the whole comparison as
     cross-draw** -- the route is non-deterministic (G241: 808 of 1,201 records differed), and this check
     decides what the comparison means. **Do not assume it; verify it and quote what you checked.**
  3. **SAMPLE 36 JUMP STEPS, UNCONDITIONED, one per time bin** across the span by the same one-per-bin
     rule G273 and G280 used. **Report frame and id coverage.** **Do not select on track id, location or
     speed beyond the displacement cut in step 1.**
  4. **RENDER A CROP AT BOTH ENDPOINTS OF EACH SAMPLED STEP -- 72 crops -- WITH GEOMETRY IDENTICAL TO
     G273's**: 512x640 native pixels centred on the footpoint, with the same small red centre cross.
     **State the render settings and confirm they match G273's; if you cannot confirm it, say so.**
  5. **CLASSIFY BLIND IN ONE POOLED RANDOMISED ORDER so you cannot tell a BEFORE endpoint from an AFTER
     endpoint or one step's two ends from each other. Commit the order and verdicts in their OWN commit
     BEFORE un-blinding or joining anything.**
  6. **CATEGORIES ARE G287's, UNCHANGED AND NOT REDEFINED, JUDGED AT THE CENTRE CROSS**: (a) a PLAYER'S
     FEET; (b) a PLAYER'S BODY but not feet; (c) BARE COURT OR FLOOR; (d) a BROADCAST GRAPHIC OR SCORE
     TICKER; (e) a PERSON who is not a player in play; (f) SOMETHING ELSE, free text; (g) CANNOT JUDGE,
     kept separate. **FREE TEXT IS MANDATORY ON EVERY ROW.** **Judge WHAT IS UNDER THE CROSS, not what is
     in the crop -- that is G287's rule and mixing it with G273's crop-level rule would make the
     comparison meaningless.**
  7. **REPORT THE SEVEN COUNTS OVER ALL 72 ENDPOINTS, AND COMPARE EACH TO G287's LANDED BASELINE** (72
     unconditioned detections: 0.208 feet, 0.181 graphic, and its other categories -- read them from the
     committed verdicts, do not quote from memory). **Two-proportion test on the "on a player at all"
     rate, meaning (a)+(b): pooled p, SE, z, NOMINAL two-sided p, said to be nominal with no multiplicity
     correction. Overlapping confidence intervals are NOT a test.** **These are two independent samples of
     detections, so an unpaired test is correct here -- say why, because a sibling row uses McNemar for a
     PAIRED design and the two must not be confused.**
  8. **THEN un-blind the endpoint pairing and REPORT THE JOINT DISTRIBUTION OVER THE 36 STEPS**: for each
     step, the pair of categories at its two ends. **Report the fraction of jumps with at least one
     non-player endpoint, the fraction with BOTH ends non-player, and the fraction with both ends on a
     player.** **Name the 36 denominator every time.**
  9. **REPORT DIRECTION**: among mixed pairs, is the non-player end more often the BEFORE or the AFTER
     endpoint? **Binomial test against 0.5, nominal p.** **A direction would say whether ids drift ONTO
     furniture or OFF it; no direction is equally informative and must be stated as such.**
 10. **ANSWER IN ONE SENTENCE WITH NUMBERS: are the ends of a large jump less often a player than a
     randomly chosen detection?** **YES relocates the anomaly onto DETECTION, consistent with 0.208 on
     feet and with identity being the healthy axis. NO means large jumps happen between things that ARE
     players, which would point back at identity and would CONTRADICT G281's 0.935 purity -- and I want
     that contradiction stated plainly rather than smoothed over. A result too noisy to call at n = 36
     steps is an honest outcome. ALL are full successes.**
 11. **Propose NO filter, threshold, gate, retrain or production change. Do NOT touch `src/`. Do NOT move
     any bar. Do NOT change any G287, G273 or G289 verdict, count or artifact.**

**HONEST LIMITATIONS to state, not discover:** **This row cannot separate "implausible" from "large image
jump" -- at the measured scales a jump beyond 150 px in one frame IS implausible, so the two are very
nearly the same set and there is no matched plausible control available.** **Say that in those words and
do NOT claim to have isolated implausibility.** The comparison baseline is a HISTORICAL landed sample
(G287), not a freshly drawn concurrent control. ONE clip, ONE span, ONE draw of a non-deterministic route,
ONE labeller -- and **agreement with G287 is rater-matched repeatability, NEVER independent validation.**
**Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078), so nothing
here may be quoted clip-wide.** **A footpoint is a POINT: this row says what is AT it, never what a
bounding box contained.** The population is detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the confirmed 1,897 jump population; the same-draw check with what you checked quoted;
                  the 36-step sample with frame and id coverage; the render-settings match to G273; the
                  committed blind order and verdicts; the seven counts over 72 endpoints against G287's
                  landed baseline with the unpaired two-proportion test and nominal p; the joint
                  distribution over the 36 pairs; the direction binomial; and the one-sentence answer
  before        = 3,460/4,090 = 0.846 of implausible steps are genuinely large image displacements with NO
                  established mechanism, and nobody has looked at what is at either end of one
  bar           = **NO pass bar.** **Endpoints less often on a player than baseline relocates the anomaly
                  onto DETECTION. Endpoints as often on a player points back at IDENTITY and contradicts
                  G281's 0.935 purity, which must be stated plainly. Too noisy to call at 36 steps is an
                  honest result. ALL are full successes.**
  n             = 1,897 eligible jump steps, 36 sampled, 72 endpoint crops, 1 clip, 1 span, 1 draw, 1
                  labeller -- name every denominator in the verdict line and name the detector-box
                  population
  eye check     = the blind classification IS the measurement. A COARSE categorical judgement at the
                  centre cross, not a geometric one. **Say that distinction.**
  must not move = G289's steps.csv, partition and counts; G287's and G273's verdicts, crops and category
                  definitions; G281's purity; G267's retained records and span; the 40 ft/s bar; every
                  threshold and verdict; `src/` and `domains/` (READ and IMPORT ONLY); the corpus and both
                  bridge partials
EVIDENCE: `docs/evidence/tracking/g292_jump_endpoint_content_2026-09-04.md` with the population check, the
same-draw check, the sampling, the render settings, the sealed order sha, the endpoint counts and test,
the joint distribution, the direction test, the one-sentence answer, every disk-guard probe verbatim, and
a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted -- **pin the 1,897 selection from the committed
steps.csv and pin the 512x640 crop geometry.** **NEVER a full pytest.** **If a commit grows an allowlisted
file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
