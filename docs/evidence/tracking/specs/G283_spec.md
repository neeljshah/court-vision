GAP G283 | sport wnba | worktree a5 | log g283_resolution_control_on_precision
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** You may
IMPORT and RUN them; you may NOT edit them. Build any new harness in `scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **The DOWNSAMPLE and both DETECTION runs are on the POD** -- the source and the GPU are there. Use
    **`~/bin/pod_run a5 --ship <harness> --fetch <crops and summaries> -- <cmd>`**. **The disk guard
    belongs INSIDE that command.** A missing `/workspace` locally is NOT a disk failure; it means the step
    belongs in `pod_run`.
  - **The blind classification and the arithmetic are LOCAL**, on crops fetched back.

**HOLD RULE, REPLACED BY THE VERIFIER 2026-09-04 21:00 -- GATE ON THE GPU, NOT ON A LANE COUNT.**
**The old lane-count gate (hold while more than 2 distinct `/workspace/wt/a*` directories are occupied)
held this row out for five hours and it was gating on the WRONG RESOURCE.** Measured by the verifier at
2026-09-04 20:50: `nvidia-smi` **0 pct utilisation, 1 MiB of 24,576 MiB used, and ZERO compute
processes**; 256 cores at load15 = 107.88; 834 GB of 1,007 GB RAM available; `dd conv=fsync` on
`/workspace` **passed at 28 MB/s**. The five occupied worktrees (a13, a14, a15, a16, a17) are all running
**CPU-only simulation** rows. **THE GATE FOR THIS ROW IS THE GPU: re-run `nvidia-smi
--query-compute-apps=pid,used_memory --format=csv,noheader` yourself and PROCEED IF IT IS EMPTY or free
VRAM exceeds what your run needs.** **Report your own measurement, and report the occupied-worktree SET as
CONTEXT ONLY.** **Do NOT interrupt a running row. Never count python PIDs** -- one lane routinely shows two
PIDs sharing one `cwd` (G274). **THIS IS AN OPERATIONAL GATE, NOT AN EVIDENTIARY BAR: no threshold, no
acceptance bar and no p-value in this spec has moved or may move.**

**READ THE LANDED G273 AND G280b MEMOS AND THE G280b-CONFOUND LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- A CONFOUND I LEFT IN MY OWN SPEC, AND IT DECIDES WHAT THE ANY-VIDEO RESULT MEANS.**
G280b measured, blind and against a verified seal, that on the corpus's one amateur clip **only 25/72 =
0.347 of retained detections are a player on the court of play and 37/72 = 0.514 are NOT A PERSON**,
against G273's broadcast **0.597 and 0.208** (z = -3.005, p = 0.00266; z = 3.817, p = 0.000135).

**But the amateur clip is 1280x720 and the broadcast clip is 1920x1080, so "amateur" and "lower
resolution" are perfectly confounded.** A person subtending the same fraction of frame height carries
**1.5x fewer pixels linearly and 2.25x fewer in area** at 720p, and detector precision degrades on small
objects. **An unknown share of the collapse may be resolution and nothing to do with amateur camerawork.**

**The two answers have completely different consequences: if it is resolution, the fix is capture or
upscaling; if it is amateur-ness, the fix is retraining. This row separates them.**

THE QUESTION: **how much of the precision collapse is explained by resolution alone?**

METHOD:
  1. **DOWNSAMPLE THE BROADCAST CLIP TO EXACTLY 1280x720.** Use `wnba__wnba_01.mp4` (2,796 MB,
     1920x1080, 30 fps, 174,430 frames, sha256 begins `f361ad7a32ccc6d98ae8e98e`). **State the exact
     ffmpeg command, scaler and encoder settings.** **Downsample only the studied span 19599-23399** if
     that keeps disk within budget; say what you did.
  2. **RUN DETECTION AT BOTH RESOLUTIONS IN THIS SAME ROW, ON THE SAME SPAN, WITH THE SAME ROUTE AND THE
     SAME SETTINGS. This is the whole design: the ONLY difference between the two arms must be
     resolution.** **Do NOT compare against G273's landed records as the 1080p arm** -- that would
     reintroduce a different draw and a different date as extra differences. **G273 is CONTEXT, not the
     control arm.** Report both arms' route sha256 and confirm they are the same route.
  3. **SAMPLE 72 RETAINED DETECTIONS FROM EACH ARM, UNCONDITIONED**, by the same one-per-time-bin rule
     G273 and G280 used. **Say how you sampled and report frame and id coverage for each arm.**
  4. **HOLD THE CROP GEOMETRY COMPARABLE, AND SAY WHICH COMPARABILITY YOU CHOSE.** G273 and G280b both
     used a 512x640 native-pixel crop, which covers **26.7 pct x 59.3 pct** of a 1080p frame but
     **40.0 pct x 88.9 pct** of a 720p frame -- so an identical absolute crop is NOT an identical task.
     **Render the 720p arm's crops at a size covering the SAME FRACTION of the frame as 512x640 does at
     1080p (that is 341x427, rounded as you see fit), and ALSO render them at 512x640.** **Report both,
     and state plainly which one you treat as the primary comparison and why.** **This is the second
     confound in G280b and it must not simply be inherited.**
  5. **CLASSIFY BLIND, ALL ARMS POOLED INTO ONE RANDOMISED ORDER so the labeller cannot tell which arm a
     crop came from**, committing the order and verdicts in their own commit BEFORE un-blinding.
     **Categories are G273's four, UNCHANGED**: (a) PLAYER on the court of play; (b) PERSON, not a player
     in play; (c) NOT A PERSON; (d) CANNOT JUDGE. **Keep (d) separate. Do not redefine a category.**
  6. **REPORT THE FOUR COUNTS PER ARM AND THE TWO-PROPORTION TEST BETWEEN ARMS** for the (a) rate and the
     (c) rate: pooled p, SE, z, **nominal** two-sided p. **Overlapping confidence intervals are NOT a
     test.** **State that p is nominal with no multiplicity correction.**
  7. **THEN ANSWER THE ATTRIBUTION QUESTION IN ONE PLAIN SENTENCE**, and quantify it: **what fraction of
     G280b's 0.597 -> 0.347 drop is reproduced by resolution alone on broadcast footage?** **If
     resolution reproduces most of it, say that G280b's result must NOT be attributed to amateur footage.
     If it reproduces little, say that amateur-ness survives as the explanation.** **Both are full
     successes.**
  8. **ALSO REPORT THE CANNOT JUDGE RATE PER ARM.** G273 had 5/72 at 1080p and G280b had 0/72 at 720p
     with an absolute-size crop; **if the (d) rate tracks crop FRACTION rather than resolution, that
     confirms the task-difference reading in the G280b-CONFOUND row.**
  9. **Do NOT propose a production change, filter, gate, threshold, retrain or upscaling rule.** **Do NOT
     touch `src/`.** **Do NOT move any bar.**
 10. **The population is detector boxes, not authenticated players.** **Name every denominator; never say
     "players" unqualified.**

**DISK GUARD, POD SIDE, CORRECTED 2026-09-04 21:00:** `df` is NON-AUTHORITATIVE (it reports the 929T
MooseFS cluster, not the 50 GB quota). **`du -sm /workspace` is a NETWORK filesystem walk: under load it
takes minutes or RETURNS NOTHING, and an EMPTY result means UNKNOWN, NEVER 0.** A lane that parsed empty
`du` output as 0 lost a COMPLETED 3,801-frame pass (G282b), and a monitor that did the same raised a false
"corpus deleted" alarm. **So: `v=$(timeout 90 du -sm /workspace | cut -f1); [ -z "$v" ] && v=UNKNOWN`,
report `v` VERBATIM, and NEVER STOP ON UNKNOWN.** The verifier measured UNKNOWN twice at 2026-09-04 20:52
under peer load; last known good was about **40,060 MB at 14:50**, roughly **10 GB free** of the 50 GB
quota, and **a peer session writes under `/workspace/wt`. THE ONLY STOPPING CONDITION IS A FAILED
`dd conv=fsync` PROBE ON THE POD** -- cheap, decisive, and it PASSED for the verifier at 28 MB/s at 20:52.
**NOTHING MAY SIT BETWEEN A COMPLETED PASS AND ITS COMMITTED ARTIFACT: run the guard BEFORE the pass, never
in the write path of a result.** **A downsampled span plus two detection runs plus crops is the bulk --
downsample ONLY the span you need, delete your own intermediate video when done and report the bytes, and
keep crops modest.** **Do NOT delete any corpus source, and do NOT delete the two abandoned bridge
partials (`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are
resumable acquisitions and the football one is the only football footage in the programme.** Report bytes
freed.

**HONEST LIMITATIONS to state, not discover:** **downsampling a 1080p broadcast is NOT the same thing as
natively capturing at 720p** -- it shares the pixel budget but not the optics, compression history,
framing or camera work, so it isolates resolution **as far as any cheap experiment can** and no further.
**Say that in those words.** ONE clip, ONE span, ONE labeller. **Per G278 the span is measurably friendlier
than the clip (0.836 against 0.656 court-bearing, p = 0.0078), so nothing here may be quoted clip-wide.**
**The research route is non-deterministic (G241: 808 of 1,201 records differed), so each arm is one draw**
-- do not read a small difference as signal. **A footpoint-centred crop is not the detector's box.**

ACCEPTANCE RULE:
  metric        = the exact downsample command; both arms' route sha256 confirmed identical; per-arm
                  sampling with frame and id coverage; the committed pooled blind order and verdicts; the
                  four counts per arm at BOTH crop sizes; the between-arm two-proportion tests with
                  nominal p; the one-sentence attribution answer with the fraction of the drop explained;
                  and the per-arm CANNOT JUDGE rates
  before        = amateur 0.347 PLAYER / 0.514 NOT A PERSON against broadcast 0.597 / 0.208, with
                  "amateur" and "720p" perfectly confounded and the attribution therefore unavailable
  bar           = **NO pass bar.** **"Resolution explains most of it" would retract the amateur
                  attribution and redirect the any-video effort to capture and upscaling.**
                  **"Resolution explains little" would confirm amateur-ness and redirect it to
                  retraining.** **Both are full successes and I want whichever is true stated bluntly.**
                  Do not tune, do not filter, do not move a bar.
  n             = 1 clip, 1 span, 2 resolution arms, 72 classified detections per arm, 1 labeller -- name
                  every denominator in the verdict line, and name the detector-box population
  eye check     = the blind classification IS the measurement; a COARSE categorical judgement, not the
                  sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = G273's and G280b's counts, sealed orders and category definitions; G267's retained
                  records and span; G233d's published map; every threshold, bar and verdict; `src/` and
                  `domains/` (READ and IMPORT ONLY -- run them, never edit them); the pod daemon and
                  keeper; the corpus; the bridge partials
EVIDENCE: docs/evidence/tracking/g283_resolution_control_on_precision_2026-09-04.md with the downsample
command, the route check, per-arm sampling, the committed blind order and verdicts, per-arm counts at both
crop sizes, the between-arm tests, the attribution sentence, the CANNOT JUDGE comparison, every disk-guard
probe with the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** Report the sha.
NEVER PARK.
