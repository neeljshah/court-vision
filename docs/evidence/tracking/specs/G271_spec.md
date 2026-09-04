GAP G271 | sport wnba | worktree a5 | log g271_implausibility_concentration_and_image_displacement
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` is HUMAN-GATED.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal). **Check first, do NOT interrupt a running row, and
EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G267, G269 AND G270 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- THE DEFECT IS LOCATED BUT NOT CHARACTERISED, AND THE FIX DEPENDS ENTIRELY ON WHICH
SHAPE IT HAS.**
G267 found **13.6 pct** of same-ID court-space steps physically impossible through a validated map. G269
showed association cannot repair it -- constraining merely fragmented tracks (98 to 139 ids, p90 length
841.7 to 526.4). G270 then conditioned on position: **both endpoints on court is 10.5 pct (2,507 / 23,783)
and 61.3 pct of all impossible steps are fully on court**, so it is not an off-court projection artifact.

**Two questions now decide what to do next, and both are answerable from G267's retained records without
any new detection or fitting.**

**QUESTION 1 -- IS IT CONCENTRATED OR SYSTEMIC?** If a handful of the 98 emitted ids produce most of the
impossible steps, those tracks are probably spurious -- duplicates, crowd or bench that happen to project
on court -- and **the rest of the tracking may be sound.** If it is spread evenly across tracks, the defect
is systemic. **These imply completely different next steps and the difference is cheap to measure.**

**QUESTION 2 -- DID THE BOX MOVE, OR ONLY ITS PROJECTION?** G267's Jacobian gives 0.016-0.079 ft/px on
court, so **an on-court step of 40 ft/s at 30 fps needs roughly 17-83 px of IMAGE displacement.** If the
impossible in-court steps carry large image displacement, **the box genuinely jumped -- a detection or
association failure.** If they carry small image displacement, **the projection amplified ordinary noise**,
which is a geometry-conditioning problem instead. **G269 pointed upstream to detection; this is the test
of that claim rather than an assumption of it.**

METHOD:
  1. **Reuse G267's retained boxes, map and span exactly** (frames 19599-23399). **Do not re-detect** --
     G241 established the detector is non-deterministic, so a fresh pass is not comparable. **Reproduce the
     0.136 and the 0.105 on-court figures first and confirm they match**; say so if they do not.
  2. **PER-TRACK CONCENTRATION.** For each emitted id: step count, impossible-step count, and fraction.
     **Report how many ids have zero impossible steps, and what share of ALL impossible steps comes from
     the worst 5 and worst 10 ids.** Also report **track length against impossible fraction** -- are short
     tracks worse? **Restrict the headline to the on-court partition (G270's 23,783 steps) and say so.**
  3. **IMAGE-DISPLACEMENT DECOMPOSITION.** For every on-court impossible step, report the **image-space
     displacement of the box bottom-centre in px** alongside its court-space speed. **Give the joint
     distribution, not two marginals** -- median, p90 and max image px for impossible steps, and the same
     for plausible steps as the contrast. **State how many impossible steps have image displacement below
     17 px**, the lower end of what the Jacobian says 40 ft/s requires; those are projection-amplified
     rather than box-jumped.
  4. **NAME THE SPLIT PLAINLY**: what fraction of on-court impossible steps are box-jumps versus
     projection-amplified versus indeterminate. **Do NOT assign a single cause you have not evidenced** --
     G267 refused to and several corrections tonight came from exactly that failure.
  5. **Do NOT propose a production change, filter, gate or threshold; do NOT touch `src/`; do NOT
     re-associate** (G269 already showed where that leads).
  6. **The population is detector boxes, not authenticated players** -- officials, bench, spectators and
     duplicates included (G225: 19 boxes, 2 visibly on-court people). **Name that denominator; never say
     "players" unqualified.** **A concentrated result would NOT prove the concentrated tracks are
     spurious** -- identity is unvalidated everywhere in this programme.

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** (last about
**36,400 MB**, roughly 13.6 GB free). **`dd conv=fsync` probe before writing, STOP and report if it
fails.** **Do NOT delete any corpus source or the two abandoned partials in the bridge directory.** Report
bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one draw of a
non-deterministic detector** -- report to three decimals. The map is certified only to about 20 px (G257),
and the Jacobian bounds are sampled at four court points, so the 17-83 px figure is **indicative, not a
threshold**. **Image displacement and court speed are not independent** -- they are related by the very map
under test -- so the decomposition is descriptive. **This row explains where impossible steps live; it does
not show any track is correct.**

ACCEPTANCE RULE:
  metric        = the reproduced 0.136 and 0.105 baselines; per-id step and impossible counts with the
                  zero-impossible id count and the worst-5 and worst-10 share; track length against
                  impossible fraction; the joint image-px against court-speed distribution for impossible
                  and plausible steps; the count below 17 px; and the named box-jump / projection-amplified
                  / indeterminate split
  before       = the defect is located on court (10.5 pct, 61.3 pct of impossible steps fully on court) and
                 shown unrepairable by association, but it is not known whether it is concentrated or
                 systemic, nor whether boxes actually jump
  bar          = NO pass bar. **"A few ids produce most of it" and "it is systemic" are both full
                 successes and imply opposite next steps.** **"Boxes genuinely jump" confirms G269's
                 upstream redirect; "projection amplifies small moves" would overturn it.** Do not filter,
                 tune, or propose a change.
  n            = 1 clip, 1 shot, 1 map, 98 emitted ids, the step counts you state -- name every denominator
                 in the verdict line, and name the box population, not "players"
  eye check    = none required; commit a per-track scatter if it aids a reader
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained boxes and span,
                  the court model, the coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY),
                  the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g271_implausibility_concentration_and_image_displacement_2026-09-04.md
with the reproduced baselines, the per-id table and concentration shares, the length-against-implausibility
relation, the joint image-px/court-speed distributions, the sub-17-px count, the named split, every
disk-guard probe with the `du -sm /workspace` figure, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
