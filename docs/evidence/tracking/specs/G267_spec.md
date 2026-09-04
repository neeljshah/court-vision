GAP G267 | sport wnba | worktree a6 | log g267_court_space_physical_plausibility
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO court model and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G266 may be running on a5; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G233d, G241b, G252, G257 AND G260 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- CALIBRATION IS A MEANS, AND NOBODY HAS CHECKED THE END.**
Everything tonight has been about getting a court map. **Nothing has asked whether having one produces
sensible player motion**, which is the only reason the map matters.

**AND IT OFFERS THE ONE THING THIS PROGRAMME LACKS: AN OBJECTIVE CHECK THAT NEEDS NO HUMAN EYE.**
G257 measured the eye gate at **20 px**; G260 then showed **the best hand-built signal needs 40 px and is
therefore worse than the eye**, closing hand-built validity against known ground truth. **But physics is
not an opinion. A player moving at 40 ft/s is wrong whatever any labeller says**, and court-space speed is
computable directly from a map plus detections.

THE QUESTION: **projected through G233d's validated map, is the resulting player motion physically
plausible -- and what does the calibration's measured pixel error mean in FEET?**

METHOD:
  1. **Use G233d's published map on `wnba__wnba_01.mp4` over its validated span** -- the 1,200 post-seed
     frames from **19599**, which G241b confirmed reproduce bit-exactly and which held to distance 4,000
     before a shot cut. **Do not re-fit and do not relabel.** **Stay inside one camera shot** -- G241b's
     cut is at about distance 3,876, so say which span you used and why it contains no cut.
  2. **TRANSLATE THE PIXEL ERROR INTO FEET FIRST, because it conditions everything after.** G252 measured
     the projection at **median 5 px / p90 19 px**. **Report the local pixel-to-feet scale at several court
     positions** -- near sideline, far sideline, near baseline, mid-court -- and give **the 5 px and 19 px
     errors in feet at each.** Perspective means this varies a lot across the image; **a fixed
     px-to-feet number would be wrong and must not be quoted.**
  3. **Project detected feet to court coordinates and build per-track speeds in ft/s** across the span.
     **Report the speed distribution: median, p90, p99, max**, and the fraction above stated physical
     reference points. **State your references and their source** -- an elite human sprint is roughly
     30-33 ft/s and basketball players in play rarely exceed about 25 ft/s, so **anything far above that is
     an error signal, not an athlete.**
  4. **REPORT THE IMPLAUSIBLE FRACTION AS THE HEADLINE.** That number is an objective quality measure of
     the whole chain -- detection, tracking and calibration together -- **and it needs no eye gate.**
  5. **DECOMPOSE WHAT YOU CAN, AND REFUSE WHAT YOU CANNOT.** An implausible speed can come from a detection
     jumping between people, a track-id swap, a projection error, or a genuinely fast player. **Report how
     many implausible steps coincide with a track-id change or a large pixel jump**, and **say plainly
     which portion you cannot attribute.** Do NOT present a single cause you have not evidenced --
     tonight already produced several corrections for exactly that.
  6. **ALSO REPORT TWO CHEAP SANITY DISTRIBUTIONS**: the fraction of projected positions inside the
     94 x 50 ft court, **to three decimals** (G241 showed the detector is non-deterministic, so this is one
     draw), and the distribution of **inter-player distances**, flagging any physically impossible
     coincidences.
  7. **THE POPULATION IS NOT PLAYERS.** G225 found one frame with 19 raw boxes yielding 2 visibly on-court
     players; officials, bench, and spectators are included. **Name that denominator explicitly and do not
     call these "players" without qualification.**
  8. **Do NOT propose a production change, a gate, or a threshold. Do NOT tune. A high implausible fraction
     is a FULL SUCCESS** -- it would quantify how far the current chain is from usable tracking, which is
     exactly what the programme needs to know.

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`**, the scope the
50 GB quota is enforced on, last measured **36,419 MB** with about 13.6 GB free. **`dd conv=fsync` probe
before writing, STOP and report if it fails.** Stream the decode; never write a full decode to disk. **Do
NOT delete any corpus source or the two abandoned partials in the bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one arena, one camera shot. **The
detector is non-deterministic** -- G241 found 808 of 1,201 records differed on an exact re-run while the
geometry reproduced bit-exactly -- so **every count here is one draw**; report to three decimals, not six.
**The map itself is certified only to about 20 px** (G257), so implausibility measured through it inherits
that. **Speeds depend on the track ids being right, and identity is not validated anywhere in this
programme.** A plausible speed distribution would NOT prove the tracking is correct -- **it is necessary,
never sufficient**, exactly like the in-court fraction.

ACCEPTANCE RULE:
  metric        = the pixel-to-feet scale at several named court positions with G252's 5 px and 19 px
                  expressed in feet at each; the court-space speed distribution (median, p90, p99, max)
                  with the implausible fraction against stated references; the attribution of implausible
                  steps to id changes or pixel jumps with the unattributable portion named; the in-court
                  fraction to three decimals; and the inter-player distance distribution
  before       = every calibration result tonight is about obtaining a map; nothing has measured whether
                 the map yields sensible motion, and hand-built validity is closed (best signal 40 px,
                 worse than the eye's 20 px)
  bar          = NO pass bar. **A high implausible fraction is a FULL SUCCESS** and would quantify the gap
                 between the current chain and usable tracking. **A low one would be the first objective,
                 eye-free evidence that the chain produces something physically sensible.** Do not tune and
                 do not propose a threshold.
  n            = 1 clip, 1 map, 1 shot, the frame span and box count you state -- name every denominator in
                 the verdict line, and name the box population, not "players"
  eye check    = none required; this row is deliberately eye-free. Commit a couple of court-space
                 trajectory plots if they aid a reader
  must not move = every threshold, bar and verdict, G233d's published map and labels, the court model, the
                  coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus
EVIDENCE: docs/evidence/tracking/g267_court_space_physical_plausibility_2026-09-04.md with the span and its
no-cut justification, the pixel-to-feet table, the speed distribution and implausible fraction, the
attribution analysis with the unattributable portion, the in-court fraction to three decimals, the
inter-player distances, every disk-guard probe with the `du -sm /workspace` figure, bytes freed, and a NOT
VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
