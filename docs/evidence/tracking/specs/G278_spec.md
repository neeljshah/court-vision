GAP G278 | sport wnba | worktree a5 | log g278_census_stratified_followup
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):**
  - **PART B is LOCAL.** It re-judges frames G275 already extracted and committed under
    `docs/evidence/tracking/g275_map_eligible_footage_census_artifact/`. **No decode, no pod.**
  - **PART A needs the POD**, because it extracts NEW frames from the full-resolution source. Use
    **`~/bin/pod_run a5 --ship <harness> --fetch <the new frames and summaries> -- <cmd>`**. **The disk
    guard belongs INSIDE that command.** A missing `/workspace` in the local checkout is NOT a disk
    failure; it means that step belongs in `pod_run`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** One lane routinely shows TWO python PIDs
sharing one `cwd` (G274 verified this for `/workspace/wt/a17`). **Reduce to the SET of distinct
`/workspace/wt/a*` directories and compare THAT to 2.** Exclude your own process, your checker and its
parent. **Report the SET you observed.** Do NOT interrupt a running row.

**READ THE LANDED G275 MEMO AND THE G275-DESIGN-LIMITS LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- TWO DESIGN FLAWS IN MY G275 SPEC, BOTH REPORTED BY THE LANE, NEITHER ITS FAULT.**
G275 found **118 / 180 = 0.656** of uniformly sampled frames show two or more painted lines and a visible
intersection. **The counts and the sealed blind protocol are sound and are NOT under review.** But:

  - **I asked whether the studied span 19599-23399 is unusually court-bearing while specifying a uniform
    969.06-frame stride**, so that 3,801-frame span could receive at most `3801 / 969.06 = 3.92` samples.
    **It received four. The question is unanswered.**
  - **I required a 40-frame re-judge but did not require it to be STRATIFIED.** The draw contained 29 (a)
    and 11 (c) and **no (b) at all**, so the reported **40/40 agreement tests only (a) against (c)** --
    painted lines against crowd or graphic, a visually trivial call. **The boundary that actually sets
    0.656, (a) against (b), is untested**, which is why that figure currently has a ceiling of
    `(118+11+1)/180 = 0.722` and **no measured floor.**

THE QUESTION, IN TWO PARTS: **(A) is the studied span more court-bearing than the clip as a whole, and
(B) is the (a)/(b) call repeatable?**

PART A -- STRATIFIED RE-SAMPLE OF THE STUDIED SPAN (pod):
  1. **Sample at least 60 NEW frames uniformly WITHIN source frames 19599-23399** (stride about 63).
     **State the stride and the sampled indices.** **Do not reuse G275's four frames from that span as the
     sample**; you may report them separately.
  2. **Extract each with an independent `ffmpeg -ss` seek. NEVER decode the clip in one pass.**
  3. **Classify blind in a randomised order, committing the order and verdicts in their own commit BEFORE
     un-blinding**, using **exactly G275's four categories, unchanged**:
     **(a) two or more distinct painted court lines visible AND at least one intersection of painted lines
     visible; (b) painted court surface visible but not that; (c) no painted court surface at all;
     (d) cannot judge.** **Keep (d) separate.** **Do not redefine or refine any category** -- comparability
     with G275 is the entire point.
  4. **Compare the span's (a) fraction against G275's clip-wide 118 / 180 with a two-proportion test**:
     report pooled p, SE, z and the two-sided p. **Overlapping confidence intervals are NOT a test -- do
     not reason from interval overlap.** **State the p as NOMINAL, with no correction for the many
     comparisons in this programme.**
  5. **Answer in one plain sentence whether the chain was measured on unusually court-bearing footage.**

PART B -- STRATIFIED RE-JUDGE OF THE (a)/(b) BOUNDARY (local):
  6. **Build the re-judge set from G275's OWN committed 180 frames, stratified by first-pass category:**
     **ALL 11 first-pass (b) frames**, plus a random **20 (a)** and **9 (c)**, and the single **(d)** if it
     helps -- **state the exact composition.** **All 11 (b) frames must be included; that category is the
     whole point and there are only 11.**
  7. **Re-judge blind in a fresh randomised order, committed before un-blinding.** **Report the full 4x4
     confusion, and the (a)-versus-(b) cell counts specifically.**
  8. **THIS MEASURES REPEATABILITY, NOT CORRECTNESS -- say so in those words.** Same labeller, same
     criteria. **A LOW agreement would falsify the precision of 0.656, because a call that cannot be
     repeated cannot be right. A HIGH agreement would NOT validate it**, because both passes can be
     consistently wrong in the same way. **Do not claim the figure is confirmed.**
  9. **Recompute the implied bound on 0.656 using the measured (a)/(b) confusion**, and **state a floor if
     the data support one.** If they do not, **say the figure still has no measured floor.**
 10. **Do NOT re-extract, re-crop or alter G275's frames**, and **do NOT change any category definition,
     threshold or verdict.** **Do not touch `src/`.**

**DISK GUARD, POD SIDE (Part A only):** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** --
about **40,600 MB at 2026-09-04 13:00**, roughly **9.2 GB free** against the 50 GB quota, and **a peer
session writes under `/workspace/wt`.** **Re-measure yourself.** **`dd conv=fsync` probe before writing,
STOP and report if it fails ON THE POD.** **60 JPEGs are the bulk -- keep them modest and report committed
bytes.** **Do NOT delete any corpus source, and do NOT delete the two abandoned bridge partials
(`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable
acquisitions and the football one is the only football footage in the programme.** Report bytes freed.

**THE SOURCE:** `wnba__wnba_01.mp4` in the corpus directory under the pod repo's gitignored footage store,
2,796 MB, 174,430 frames, 1920x1080 at 30 fps, sha256 beginning `f361ad7a32ccc6d98ae8e98e`. **Verify
before decoding.**

**HONEST LIMITATIONS to state, not discover:** ONE clip, ONE broadcast, ONE arena, **ONE labeller** for
both passes and both parts. **Part B is repeatability only** (step 8). **Category (a) remains NECESSARY,
NOT SUFFICIENT** -- it says painted geometry is visible, never that a map would fit or be correct, and
G274 produced 0.569 px RMS on a frame with no court in it. **Uniform frame sampling weights long views by
runtime and is not a count of shots.** Part A's 60 frames within one span is a small sample; **give the
interval and do not present the fraction as exact.**

ACCEPTANCE RULE:
  metric        = Part A: the stride, indices, committed blind order and verdicts, the four counts, the
                  two-proportion test against 118/180 with pooled p, SE, z and nominal two-sided p, and
                  the one-sentence answer. Part B: the stratified composition including all 11 (b) frames,
                  the committed fresh blind order, the full 4x4 confusion with the (a)/(b) cells called
                  out, the repeatability-not-correctness statement, and the recomputed bound on 0.656
  before        = the studied span received 3.92 expected samples under G275's stride and got four, so the
                  question is unanswered; the 40/40 agreement drew no (b) frames, so the (a)/(b) boundary
                  that sets 0.656 is untested and the figure has a 0.722 ceiling and no floor
  bar           = **NO pass bar.** **"The span is NOT unusual" would strengthen the existing chain.**
                  **"The span IS unusually court-bearing" would mean the chain was measured on the
                  friendliest footage in the clip and is the more valuable finding.** **A LOW (a)/(b)
                  repeatability is a FULL SUCCESS** and would mean 0.656 must be quoted far more loosely.
                  Do not tune, do not redefine a category, do not move a verdict.
  n             = 1 clip, 1 labeller; Part A the 60+ frames you state within a 3,801-frame span; Part B
                  the 40-ish stratified frames including all 11 (b) -- **name every denominator in the
                  verdict line**
  eye check     = the blind classification IS the measurement, a COARSE categorical judgement, not the
                  sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = every threshold, bar and verdict, G275's 180 frames, its committed order, its counts and
                  its category definitions, G233d's published map, G267's retained records, the court
                  model, the coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY), the pod
                  daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g278_census_stratified_followup_2026-09-04.md with both parts fully
reported, every committed blind order, the two-proportion test, the 4x4 confusion, the recomputed bound,
every disk-guard probe with the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED
list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
