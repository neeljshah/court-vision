GAP G276 | sport wnba | worktree a5 | log g276_unconditioned_step_endpoint_baseline
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** N=2 is the measured optimum (G200/G216).
**One lane routinely shows TWO python PIDs sharing one `cwd`** -- G274 verified `/workspace/wt/a17` held
PIDs 3084857 and 3085457, which is ONE lane, and a sibling row deadlocked on that miscount. **Collect the
`cwd` of every python process under `/workspace/wt/a*`, reduce to the SET of distinct worktree
directories, and compare THAT count to 2.** Exclude your own process, your checker and its parent.
**Report the distinct-worktree SET you observed.** Do NOT interrupt a running row.

**READ THE LANDED G272b MEMO, THE G272b-CATEGORY-A-CORRECTION ROW, THE G273 MEMO AND THE
G273-BASELINE-BRACKET ROW FIRST.**

**WHY THIS ROW EXISTS -- I PUBLISHED A BRACKET AND THIS IS THE MEASUREMENT THAT COLLAPSES IT.**
G272b found **24 / 48 = 0.500** of jump-conditioned steps had no person in **one or both** footpoint
crops. G273 found **15 / 72 = 0.208** of single unconditioned detections were not a person. **Those two
numbers are in DIFFERENT UNITS -- a two-endpoint step against a single detection -- and pairing them
invites a 2.40x reading that is not supported.**

My G273-BASELINE-BRACKET row states the honest position: the baseline for an UNCONDITIONED step showing a
non-person at one or both endpoints lies in **[0.208, 0.373]** -- 0.208 if the two endpoints were
perfectly correlated, `1 - (1 - 0.208)^2 = 0.373` if independent -- so G272b's 0.500 exceeds the top of
the range and the concentration survives, **but the ratio is somewhere between 1.34x and 2.40x.**

**That bracket exists only because nobody has measured the endpoint correlation. G273 sampled single
detections, so it cannot supply it, however large it grows. This row measures it directly.**

THE QUESTION: **for UNCONDITIONED same-id steps, how often does one or both endpoint show a non-person,
and how correlated are the two endpoints?**

METHOD:
  1. **BUILD THE SAMPLE TO MATCH G272b's POPULATION IN EVERY RESPECT EXCEPT THE SPEED CONDITION.** G272b
     sampled retained **both-endpoints-on-court, same-ID steps** from G267's records and then required
     **strictly over 40 ft/s**. **Take the SAME population and DROP ONLY the 40 ft/s condition.**
     **State the resulting eligible-step count explicitly** -- that is the denominator, and it is not
     G272b's 2,507 (which was already speed-conditioned). **If any other filter differs from G272b's,
     name it; an unstated difference would make the comparison meaningless.**
  2. **Reuse G267's retained records. Do NOT re-detect and do NOT re-associate.** G241 established the
     detector is non-deterministic (808 of 1,201 records differed on an exact re-run), so a fresh pass
     breaks comparability with G267 and the whole chain.
  3. **SAMPLE AT LEAST 60 STEPS**, spread across the span and across distinct ids, **not a head slice.**
     Report id and frame coverage. **The sample must NOT be conditioned on speed, displacement, jumps, or
     anything downstream** -- that is the entire point of the row.
  4. **RENDER BOTH ENDPOINTS AS SEPARATE, INDEPENDENT CROPS** using G272b's technique: **footpoint-centred
     at full resolution, NO bounding box drawn or inferred** (G267 retained no box extents). State the
     crop size and why.
  5. **THIS IS THE CRITICAL DESIGN POINT -- THE TWO ENDPOINTS OF A STEP MUST BE PRESENTED AS UNRELATED
     ITEMS.** Pool **all 120+ crops into ONE randomised blind order** so the labeller **never knows which
     two crops belong to the same step.** **If the pairing is visible, the labeller's judgement of the
     second endpoint is contaminated by the first and the measured correlation is an artifact of the
     presentation, not of the tracker.** **Commit the order and the verdicts in their own commit BEFORE
     un-blinding**, as G255, G257, G260, G272b and G273 did. **Say in the memo that the pairing was hidden
     and how.**
  6. **Categories are exactly G273's, applied to each crop independently:**
     **(a) PLAYER on the court of play; (b) PERSON, not a player in play -- official, coach, bench,
     photographer, spectator; (c) NOT A PERSON -- floor marking, equipment, scoreboard, graphic, shadow,
     artifact; (d) CANNOT JUDGE.** **Keep (d) separate and never merge it.**
  7. **AFTER UN-BLINDING, REPORT THE JOINT DISTRIBUTION OVER STEPS**, not just the marginals: the 2x2
     counts for non-person at endpoint 1 against endpoint 2 (treating (c) as non-person; **state exactly
     how (d) is handled and report the figures both including and excluding (d)**). From it report:
     **(i) the observed per-crop non-person rate, for comparison with G273's 0.208;
     (ii) the observed ONE-OR-BOTH rate -- this is the number the bracket was standing in for;
     (iii) the endpoint correlation, and where the observed one-or-both rate falls inside
          [per-crop rate, 1 - (1 - per-crop rate)^2].**
  8. **THEN RESTATE THE G272b COMPARISON WITH THE MEASURED BASELINE INSTEAD OF THE BRACKET**, and give the
     ratio as a single measured figure with its uncertainty acknowledged. **If the measured baseline
     reaches or exceeds 0.500, say plainly that G272b's jump steps are NOT enriched in non-people and
     that my bracket row's conclusion was wrong** -- that is a full success and I want it stated bluntly.
  9. **Do NOT assert causation in either direction** (G271 and G267 both correctly refused, and a
     correction on 2026-09-04 came from a category that fused observation with inference). **Do NOT
     propose a production change, filter, gate or threshold; do NOT touch `src/`.**
 10. **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
     people). **Name the denominator; never say "players" unqualified.**

**DISK GUARD:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- the scope the 50 GB quota
is enforced on, **about 40,074 MB at 2026-09-04 12:35, roughly 9.7 GB free**, and **a peer session writes
under `/workspace/wt`, which a subtree measurement cannot see.** **Re-measure yourself.** **`dd
conv=fsync` probe before writing, STOP and report if it fails.** **120+ crops are the bulk -- keep them
modest and report committed bytes.** **Do NOT delete any corpus source, and do NOT delete the two
abandoned bridge partials (`baseball__npb_05.mp4.part` 2.4 GB, `football__football_m8UWuQoflJo.mp4.part`
4.7 GB): they are resumable acquisitions and the football one is the only football footage in the
programme.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one labeller**, one draw
of a non-deterministic detector. **60 steps of the eligible population is a sample** -- give its size and
spread and do not present rates as exact. **A footpoint-centred crop is not the detector's box**: it shows
the neighbourhood the detection claimed, not the extent it claimed. **G273's 0.208 came from a different
sample of the same span**, so a difference between this row's per-crop rate and 0.208 is expected sampling
variation and **must not be reported as a change in the detector.** Eye-label reliability in this
programme has never cleared 80 pct blind agreement on four measured criteria.

ACCEPTANCE RULE:
  metric        = the eligible-step denominator and how it matches G272b's population minus the speed
                  condition; sample size with id and frame coverage; the committed pooled randomised order
                  with the statement that pairing was hidden; the 2x2 joint counts with (d) handled
                  explicitly both ways; the per-crop rate, the one-or-both rate, the endpoint correlation,
                  and where the observed rate falls inside the bracket; and the restated G272b comparison
  before        = the baseline for an unconditioned step is UNMEASURED and stands as the bracket
                  [0.208, 0.373]; G272b's jump-step rate is 0.500; the implied ratio is anywhere from
                  1.34x to 2.40x
  bar           = **NO pass bar.** **A measured baseline that leaves 0.500 clearly enriched confirms the
                  concentration and sharpens it to one number.** **A measured baseline at or above 0.500
                  REFUTES my bracket row's conclusion and is an equally full success -- say so bluntly.**
                  Do not tune, do not filter, do not move a threshold, and do not assert causation.
  n             = 1 clip, 1 shot, the eligible-step count and sample size you state, 1 labeller -- name
                  every denominator in the verdict line, and name the detector-box population
  eye check     = the blind classification IS the measurement; it is a COARSE categorical judgement, not
                  the sub-pixel geometric one G257 bounded at 20 px. **Say that distinction.**
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained records and
                  span, G272b's counts and sealed order, G273's counts and sealed order, the 40 ft/s and
                  83 px definitions, the court model, the coordinate contract, `src/` and `domains/`
                  (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g276_unconditioned_step_endpoint_baseline_2026-09-04.md with the
population match, the sampling description, the committed pooled blind order and verdicts, every crop, the
2x2 joint table, the three reported quantities, the restated G272b comparison, every disk-guard probe with
the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
