GAP G269 | sport wnba | worktree a6 | log g269_physical_reassociation_headroom
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` is HUMAN-GATED and must not be edited or proposed for edit.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G268 may be running on a5; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G267 MEMO FIRST.**

**WHY THIS ROW EXISTS -- G267 REORDERED THE PROGRAMME AND THIS IS THE FIRST ROW ON THE NEW PRIORITY.**
G267 projected detector boxes through **G233d's validated map** and found **4,090 of 29,973 same-ID
court-space steps exceed 40 ft/s -- 13.6 pct** -- with p99 **700 ft/s** and max **100,457 ft/s**, plus a
max inter-detection distance of **3,269 ft on a 94-ft court**. **Physics needs no eye gate**, which matters
because the eye resolves only 20 px (G257) and no hand-built signal beats it (G260).

**And it is not the geometry: 48.0 pct of implausible steps coincide with an association-ID discontinuity
and 53.9 pct with a >100 px image jump.** The calibration was validated and good, and the output is still
13.6 pct impossible. **Association, not calibration, is now the binding defect.**

THE QUESTION: **how much of that 13.6 pct is removable by re-associating the SAME detections under a
physical speed constraint -- measured post-hoc, changing nothing in production?**

**THE TRAP, AND IT IS FATAL IF UNGUARDED: THE METRIC IS TRIVIALLY GAMEABLE.** **Give every detection its
own track id and the implausible-step fraction is EXACTLY ZERO, with zero value delivered.** Any
re-association that fragments tracks improves this metric while making tracking worse. **So the fraction
may NEVER be reported alone.**

METHOD:
  1. **Reuse G267's exact inputs and span** -- G233d's published map, source frames 19599-23399, the same
     detector boxes. **Do not re-detect, do not re-fit, do not relabel.** Recompute G267's baseline
     figures first and **confirm they match**; if they do not, say so (G241 established the detector is
     non-deterministic, so a fresh detection pass would NOT be comparable -- reuse the retained boxes).
  2. **PRE-DECLARE THE CONSTRAINT AND SEAL IT BEFORE SCORING**, in its own commit with its SHA-256, as
     G258 and G260 did. **Use 40 ft/s, the same figure G267 reported against** -- do NOT choose a limit
     after seeing results, and do NOT sweep it to find a favourable one.
  3. **Re-associate post-hoc in court space under that constraint**, in `scripts/platformkit/tracking/`.
     State the algorithm plainly. **This is a measurement of headroom, not a proposed tracker.**
  4. **REPORT THE FULL SET, NEVER THE FRACTION ALONE:**
     **(a)** implausible-step fraction before and after;
     **(b)** **the number of track ids before and after** -- G267 had 98 emitted ids;
     **(c)** **the track-length distribution before and after** (median, p90, max);
     **(d)** the number of detections left unassociated, if any.
     **A large drop in (a) accompanied by a large rise in (b) or a collapse in (c) is FRAGMENTATION, not
     improvement, and must be reported as such in the verdict line.**
  5. **STATE THE HEADROOM IN WORDS.** If the fraction falls substantially **without** fragmenting tracks,
     that quantifies a real, available improvement and is the most useful outcome. **If it only falls by
     fragmenting, the defect is in DETECTION rather than association, which is an equally full success and
     redirects the next row.**
  6. **Do NOT propose a production change, a threshold, or an edit to any tracker.** **Do NOT touch
     `src/`.** This row measures what is available; deciding to build it is not yours.
  7. **The population is detector boxes, not authenticated players** -- officials, bench, spectators and
     duplicates included (G225: 19 boxes, 2 visibly on-court people). **Name that denominator and never say
     "players" unqualified.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`**, the scope the
50 GB quota is enforced on, last measured about **36,400 MB** with roughly 13.6 GB free. **`dd conv=fsync`
probe before writing, STOP and report if it fails.** **Do NOT delete any corpus source or the two abandoned
partials in the bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one arena, **one draw of a
non-deterministic detector** (G241: 808 of 1,201 records differed on an exact re-run) -- report to three
decimals. **There is NO identity ground truth anywhere in this programme**, so a re-association cannot be
shown correct, only more or less physically possible. **A physically plausible association can still be
the wrong person**, which is precisely why (b), (c) and (d) are mandatory. The map is certified only to
about 20 px (G257), so speeds computed through it inherit that. **40 ft/s is a generous reference chosen to
be uncontroversial, not a performance bar.**

ACCEPTANCE RULE:
  metric        = the sealed pre-declared constraint with its commit sha; the reproduced G267 baseline;
                  then implausible-step fraction, track-id count, track-length distribution and
                  unassociated-detection count, ALL of them, before and after; and a worded statement of
                  whether any improvement is real or fragmentation
  before       = G267 measured 13.6 pct of same-ID steps physically impossible through a validated map,
                 with 48 pct coinciding with an association discontinuity, and nothing has tested how much
                 is removable
  bar          = NO pass bar. **"A large drop without fragmentation" quantifies real available headroom
                 and is the most useful outcome.** **"It only drops by fragmenting tracks" is an equally
                 full success** and would move the defect to detection. **"No drop at all" is a third.**
                 Do not sweep the constraint, do not report the fraction alone, and do not propose a
                 production change.
  n            = 1 clip, 1 shot, 1 map, the box and step counts you state -- name every denominator in the
                 verdict line, and name the box population, not "players"
  eye check    = none required; this row is deliberately eye-free
  must not move = every threshold, bar and verdict, G233d's published map, G267's retained boxes and span,
                  the court model, the coordinate contract, **`src/` and `domains/` (READ and IMPORT ONLY,
                  and `advanced_tracker.py` is human-gated)**, the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g269_physical_reassociation_headroom_2026-09-04.md with the sealed
constraint and its sha, the reproduced baseline, the full before/after table including id counts and track
lengths, the fragmentation judgement, every disk-guard probe with the `du -sm /workspace` figure, bytes
freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit
BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
