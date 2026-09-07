GAP G302 | sport wnba + amateur basketball | worktree a5 | log g302_amateur_vs_resolution_attribution
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only --
`src/tracking/player_detection.py` is HUMAN-GATED. You may IMPORT and RUN it; you may NOT edit it.**
Build in `scripts/platformkit/tracking/`. **Propose NO production change; this row ATTRIBUTES an existing
measured gap, it does not adopt, filter or fix anything.**
CONTRACT: `docs/evidence/tracking/VERIFIER_CONTRACT.md` -- read it; self-check against every line of
section B before you report.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **THE DETECTOR RUNS ON THE POD** -- the source videos, the GPU and the weights are there. Use
    **`~/bin/pod_run a5 --ship <harness> --fetch <per-arm detection CSVs, crops and summaries> -- <cmd>`**.
  - **THE CROP RATING AND ALL ARITHMETIC ARE LOCAL**, on what you fetch back.
  - **GATE: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader` EMPTY, or free VRAM
    above what your run needs.** Report your reading verbatim. **Do NOT gate on a lane count, do NOT hold
    for a free lane, do NOT interrupt a running row, and do NOT kill anything on the pod.** This is an
    OPERATIONAL gate, not an evidentiary bar. **If the pod is still being bootstrapped, or `resources/` is
    absent, or `opencv-python-headless` is version 5, STOP and report BLOCKED -- do not work around it.**
  - **DISK GUARD:** `v=$(timeout 60 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN` -- report v
    verbatim; **empty means UNKNOWN, NEVER 0, and NEVER stop on UNKNOWN.** The only stopping condition is
    a FAILED `dd conv=fsync` probe. **Delete no corpus source and neither bridge partial download.**

**READ FIRST:** `g280b_amateur_blind_precision_2026-09-04.md`,
`g273_detector_precision_blind_sample_2026-09-04.md`, the G280b verifier note at `7f1ddfc04`, and the G298
memo `g298_detector_capacity_and_input_resolution_2026-09-04.md` (landed `ace539619`). **Do NOT open any
unblind map or verdict sheet until your own blind verdict sheet is committed.**

**WHY THIS ROW EXISTS -- G298 TURNED A SUSPECTED CONFOUND INTO A MEASURED ONE.**
G280b measured, on a **720p amateur** clip, **25/72 = 0.347 PLAYER** and **37/72 = 0.514 NOT A PERSON**,
against G273's **43/72 = 0.597 PLAYER** and **15/72 = 0.208 NOT A PERSON** on the **1080p broadcast**
(nominal two-sided p = 0.002659 and 0.000135, no multiplicity correction). The G280b verifier note
(`7f1ddfc04`) already said that comparison is **confounded with 720p-vs-1080p**. **G298 then measured that
input resolution is the DOMINANT detector defect (`ace539619`) -- so the confound is no longer a caveat,
it is the leading candidate explanation, and the amateur-vs-broadcast reading may not be quoted until it
is separated.** Nothing in the programme has separated it.

THE QUESTION: **at MATCHED source resolution, how much of the 0.597 -> 0.347 PLAYER gap survives?**

METHOD:
  1. **ONE BLIND POOL, THREE ARMS, ONE RATER.** G291 (kappa 0.283), G295 and G297 measured crop-level
     rating to be **NOT rater-robust**, so a new arm compared against G273's or G280b's OLD verdict sheets
     would be **rater-confounded and would answer nothing.** **You must re-rate all three arms yourself,
     in ONE interleaved blind pool, with ONE rater.** Report your rater identity.
     - **ARM 1 -- BROADCAST NATIVE:** the G273 broadcast source at native **1920x1080**.
     - **ARM 2 -- BROADCAST DOWNSCALED:** the SAME broadcast source, SAME frames, downscaled to
       **1280x720** before the detector sees it. **The ONLY difference from ARM 1 is source resolution.**
     - **ARM 3 -- AMATEUR NATIVE:** the G280 amateur source `basketball__amateur_jh3fnwMi7dM.mp4` at its
       native **720p** (`source_height=720`, confirmed in `g280_per_run_summary.json`).
     **State that design: ARM 1 vs ARM 2 isolates RESOLUTION on identical content; ARM 2 vs ARM 3 isolates
     AMATEUR-vs-BROADCAST at matched resolution. Do not add a fourth difference.**
  2. **DETECTOR SETTINGS IDENTICAL IN ALL THREE ARMS** -- the production settings G298 names (`yolov8n`,
     `imgsz=640`, `classes=[0]`, `conf=0.3`). **Import and run the gated `player_detection.py` path if you
     can do so without editing it; if you cannot, replicate those exact settings and SAY that you
     replicated rather than imported.** **CONFIRM DETERMINISM: run ARM 1 twice and report whether the
     detections are byte-identical; if they are not, say so and treat every arm as ONE draw.**
  3. **SAMPLE 72 CROPS PER ARM BY THE SAME DETERMINISTIC PROCEDURE G273 AND G280b USED** -- one retained
     class-`player` detector-box observation from each of 72 equal-width source-frame bins, conditioned on
     nothing downstream -- and render each as a **512x640 crop in that arm's own source pixels**, centred
     on the claimed footpoint. **Seal the pool BEFORE rating**: commit the crops, a presentation order and
     a blank verdict sheet, plus an order-commitment JSON carrying the pool size and the SHA-256 of the
     unblind map, exactly as G280b did. **Interleave the three arms in the presentation order, and confirm
     that no arm label, filename, path or image dimension leaks which arm a crop came from.**
  4. **RATE ALL 216 CROPS WITH THE FOUR G273 CATEGORIES UNCHANGED AND IN COMMITTED ORDER:** (a) PLAYER on
     the court of play, (b) PERSON NOT PLAYER IN PLAY, (c) NOT A PERSON, (d) CANNOT JUDGE. **Commit the
     completed verdict sheet BY ITSELF, before the unblind map is generated or opened.**
  5. **REPORT PER ARM: all four category counts over 72, and the (b)+(c) grouping.** Then report **two
     two-proportion tests with nominal p and no multiplicity correction, said to be nominal: ARM 1 vs ARM 2
     (the RESOLUTION effect) and ARM 2 vs ARM 3 (the AMATEUR effect at matched resolution).** **Also
     report the total detection count and detections per frame per arm** -- a category share that moves
     because an arm emitted far more boxes is a different finding, and a reader must be able to see which
     happened.
  6. **ANSWER IN ONE SENTENCE WITH NUMBERS: of the 0.597 -> 0.347 PLAYER gap, how much is resolution and
     how much survives at matched resolution?** **A large ARM 1 -> ARM 2 drop means the G280b amateur
     reading was mostly the confound and must be retracted as an amateur-footage claim. A large ARM 2 ->
     ARM 3 drop means amateur footage is genuinely harder beyond resolution. BOTH ARE FULL SUCCESSES, and
     so is a null -- "the gap does not decompose cleanly" is a real answer and must be reported as one.**
  7. **Do NOT edit `src/`, do NOT change any production default, do NOT propose a filter, threshold, gate
     or retrain, do NOT move any bar, and do NOT re-judge G273's or G280b's committed verdicts.** Your
     ARM 1 numbers are a SECOND rater's reading of the same population, not a correction of G273.

**HONEST LIMITATIONS to state, not discover:** **YOU ARE A MODEL RATER, NOT A HUMAN, AND NO HUMAN HAS
CHECKED THESE CROPS.** **Your ARM 1 counts will probably NOT equal G273's 43/72, and that is EXPECTED --
G291 measured two raters at kappa 0.283 on this exact task. Say so in those words, and do NOT present any
difference from G273 as a correction of G273.** **A 512x640 crop in source pixels covers 1.5x more of the
scene at 720p than at 1080p; that is inherent to matching resolution and cannot be removed without adding
a second difference. Name it as a limitation and do NOT rescale the crops to hide it.** **Downscaling a
1080p broadcast to 720p is NOT the same thing as a camera that shot 720p** -- encoder, optics, framing and
motion blur all differ -- so ARM 2 BOUNDS the resolution effect, it does not reproduce amateur capture.
**Two clips, one rater, one draw per arm; nothing here is a claim about amateur video as a class.**

ACCEPTANCE RULE:
  metric        = per-arm counts in all four G273 categories over 72 crops per arm plus the (b)+(c)
                  grouping; the ARM 1 determinism check; the sealed-pool record (pool size, unblind-map
                  SHA-256, blank sheet committed before rating, verdict sheet committed before
                  unblinding); the interleaving confirmation; the two two-proportion tests (ARM 1 vs
                  ARM 2, ARM 2 vs ARM 3) with nominal p and the no-correction statement; per-arm detection
                  counts and detections per frame; and the one-sentence decomposition of the
                  0.597 -> 0.347 gap
  before        = G280b measured 0.347 PLAYER / 0.514 NOT A PERSON on a 720p amateur clip against G273's
                  0.597 / 0.208 on a 1080p broadcast (n = 72 crops each, one rater each), and that
                  comparison is confounded with 720p-vs-1080p (verifier note 7f1ddfc04) -- a confound
                  G298 (ace539619) has since measured to be the DOMINANT detector defect. **NO ROW HAS
                  EVER COMPARED THE TWO SOURCES AT MATCHED RESOLUTION.**
  bar           = **NO pass bar. This is an ATTRIBUTION row.** A large resolution effect, a large residual
                  amateur effect, and a null that refuses to decompose are ALL full successes.
  n             = 216 crops = 3 arms x 72; 2 source clips plus 1 downscale of one of them; 1 rater; 1 draw
                  per arm -- name every denominator in the verdict line and state that the rater is a
                  MODEL, not a human. **If you cannot complete all 216 ratings, STOP and report CLOSED AT
                  LIMIT with the count you completed; NEVER rate one arm more thinly than another.**
  eye check     = the blind rating IS the measurement. Additionally commit 6 EVENLY SPACED crops per arm
                  (18 total, no head slice) alongside their post-unblind verdicts.
  must not move = `src/` and `domains/` (READ and IMPORT ONLY, `player_detection.py` HUMAN-GATED);
                  production defaults; `yolov8n.pt` on the pod; the deployed `/workspace/nba-ai-system`
                  tree; G273's and G280b's committed crops, verdict sheets, counts and verdicts; G298's
                  counts; every threshold and verdict; the corpus and both bridge partial downloads
EVIDENCE: `docs/evidence/tracking/g302_amateur_vs_resolution_attribution_2026-09-07.md` with the
three-arm design statement, the determinism check, the seal and blinding record, the per-arm category
table, both two-proportion tests, the per-arm detection counts, the one-sentence decomposition, every GPU
and disk probe verbatim, bytes added and freed, and a **NOT VERIFIED** list naming at minimum: no human
rating, the crop-field-of-view asymmetry, downscale-is-not-capture, and the one-draw-per-arm limit.
**REQUIRED EVIDENCE DURABILITY:** commit under `docs/evidence/` the crops, the presentation order, the
order-commitment JSON, the verdict sheet, the unblind map and the per-arm summary JSON -- everything a
verifier needs to recompute every number without the pod.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO, by APPENDING one line -- NEVER rewrite that
file.** Commit BEFORE reporting (A7). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: a per-file test for the harness, pasted -- **pin the 72-per-arm denominator, the four category names
in committed order, and that the three arms differ ONLY in source resolution and source clip.** **NEVER a
full pytest.** **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
