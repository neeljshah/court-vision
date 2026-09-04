GAP G230 | sport tennis | worktree a4 | log g230_physical_plausibility_audit
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- rows are running there. **Every input is already
committed in this repo**, so this row needs no network at all:
  - `docs/evidence/tracking/g219_inputs/tennis_ref01_tracking_data.csv` (1,861 rows, SHA-256
    `77accc8cd83dee040601605a19bd7db592a703b2dd2bdf066fb0f2a8245f567b`)
  - `docs/evidence/tracking/g219b_inputs/tennis_01_tracking_data.csv` (19,437 rows, SHA-256
    `4e0def5dd2a53570d3aba4c5893f9761a8d695e62c16da5d0b60b12ab87c3929`)
  - `docs/evidence/tracking/g219b_inputs/tennis_02_tracking_data.csv` (1,637 rows, SHA-256
    `a2f8147401f85044fa8d0a120d1bf316a497db959b845b520eaad5a58dc2d2cd`)
**Verify each SHA-256 before use and report it.**

**WHY THIS ROW EXISTS -- THE PROGRAMME HAS NEVER ASKED WHETHER THE EMITTED NUMBERS DESCRIBE REALITY.**
Every tracking row to date measures a GATE (coverage, `jump_max`, `median_track_len`, duplicates,
`coordinate_contract`) or a CALIBRATION construct. **Not one asks whether the coordinates that DO come
out are physically possible.** These three tennis tables are the only emitted tables in the whole ledger
that declare `coordinate_space=court_feet`, so **they are the only place this question can currently be
asked at all.**

**AND THERE IS ALREADY EVIDENCE THE ANSWER IS NOT "yes".** G219b diagnosed `tennis_01`'s `jump_max`
incident: track 159 moved **108.390727 ft across 6 frames**, which at the declared **59.94 fps** is about
**0.1001 s** -- an implied speed on the order of a thousand feet per second -- while the other player sat
on track 160 moving **0.404160 ft** over the same frames. **G219b also recorded that the prior x was
below 0 and the next x and y exceeded 78 and 36, i.e. OUTSIDE the adapter's own declared 78 x 36 ft court
plane (`domains/tennis/tracking/adapter.py:21,124-126`).** **That is one incident found because a gate
happened to catch it. This row asks how common such rows are.**

THE QUESTION: **what fraction of emitted court-feet rows is physically impossible, and how is that
spread across the three tables?**

**THIS ROW INTRODUCES NO GATE AND NO THRESHOLD. Say so explicitly and repeatedly.** Physical reference
values are used to DESCRIBE a distribution, never to pass or fail a row. **Report distributions first
and counts against a reference second; if you ever write a number as "N failed", rewrite it as "N rows
lie beyond <reference>, which is a descriptive count, not a gate."** **Do NOT propose adding any of this
to the harness** -- that is a separate decision with its own id, and inventing a gate here would be B10
territory.

METHOD:
  1. **Confirm the three SHA-256 values and row counts (1,861 / 19,437 / 1,637), and confirm each table
     declares `coordinate_space=court_feet`.** If a table does not, exclude it and say so. **Name the
     ELIGIBLE DENOMINATOR per table as its player rows**, and state separately how many rows are `ball`
     -- G219 found the historical ball id collides with player epoch ids, so **treat `cls` explicitly
     rather than assuming all rows are players.**
  2. **OUT-OF-BOUNDS.** The tennis court plane is **78 x 36 ft** per the adapter. Report, per table, the
     fraction of player rows with x outside [0, 78] or y outside [0, 36], **and the distribution of how
     far outside** (a row 0.3 ft past a line is a different thing from one 40 ft past it, and players
     legitimately run beyond the baseline, so **report the magnitude distribution, do not treat every
     out-of-bounds row as an error**). Say plainly what a reasonable run-off margin would be and how
     many rows exceed even that.
  3. **IMPLAUSIBLE SPEED.** For each track, compute frame-to-frame displacement divided by elapsed time
     using the table's own declared `source_fps` and the ACTUAL frame gap between consecutive rows of
     that track -- **not an assumed stride; G219b showed the modal gap is 6 frames.** Report the speed
     distribution (median, p90, p99, max) per table. **As a REFERENCE only: elite tennis sprint speed is
     on the order of 20 mph, about 29 ft/s.** Report what fraction lies beyond that reference and beyond
     a generous multiple of it. **State that the reference is a descriptive yardstick, not a bar.**
  4. **PLAYER COUNT PER FRAME.** Singles tennis has two players on court. Report the distribution of
     distinct player track ids per frame. **Frames with more than two are physically impossible for
     singles**; frames with fewer are ordinary (occlusion, detection miss). **Establish whether these
     clips are singles or doubles before drawing any conclusion** -- if you cannot establish it from the
     committed evidence, say UNDETERMINED and report the distribution without the verdict.
  5. **CO-OCCURRENCE.** Do the implausible rows cluster in the same tracks, the same frames, or the same
     epochs? G219b found 189 one-frame identity epochs in `tennis_02` created by the
     `source_frame - last_player_emission > 3 * stride` reset. **If implausible speeds sit mostly at
     EPOCH BOUNDARIES, that is a very different finding from them being spread through steady tracking**
     -- the first would be an artefact of identity re-numbering rather than bad positions. **Test that
     explicitly; it is the most decision-relevant question in this row.**
  6. **Then state what the emitted output is worth**, honestly and without overclaiming in either
     direction. **"The overwhelming majority of rows are physically plausible and the impossible ones
     concentrate at epoch boundaries" is a GOOD result and would say the positions are broadly sound
     while identity is not. "A large share is impossible throughout" is also a full success** and would
     be the most important negative in the ledger.

**HONEST LIMITATIONS to state, not discover:** physical plausibility is a NECESSARY condition, never a
sufficient one -- **a completely wrong position can be perfectly plausible, so nothing here shows the
coordinates are CORRECT.** Say that in the verdict. These are three clips of one sport, produced by a
NON-DETERMINISTIC route (G190/G195/G198/G203), so you are describing THESE tables and not a stable
population. The 78 x 36 ft plane is the adapter's declared model; if the real court differs, bounds
statistics inherit that. There is no ground truth here and none is claimed.

ACCEPTANCE RULE:
  metric        = per table: out-of-bounds fraction with its magnitude distribution; frame-to-frame speed
                  distribution (median/p90/p99/max) using real frame gaps; distinct player ids per frame;
                  and whether implausible rows concentrate at identity-epoch boundaries
  before        = no row has ever asked whether emitted coordinates are physically possible; one
                  impossible incident is known (G219b: 108.390727 ft in 6 frames at 59.94 fps, ending
                  outside the 78 x 36 ft plane) and it was found only because a gate caught it
  bar           = NO pass bar and NO new threshold. **Describing the distribution IS the deliverable.**
                  Do not invent a gate, do not propose one, and do not report any count as a pass/fail.
  n             = 3 committed tables, 22,935 rows total (CONSTRUCT, exhaustive for coordinate-valid
                  ledger rows)
  eye check     = none; this row is table analysis
  must not move = every threshold, `jump_max`'s 8.00 bar, every bar and verdict, the coordinate contract,
                  the harness, `src/` (READ ONLY), the pod (DO NOT USE IT), the committed input tables
EVIDENCE: docs/evidence/tracking/g230_physical_plausibility_audit_2026-09-04.md with the SHA-256
confirmations, per-table denominators split by `cls`, the out-of-bounds magnitude distribution, the speed
distribution with its frame-gap basis, the per-frame id-count distribution, the epoch-boundary
co-occurrence test, an explicit statement that plausibility is necessary and not sufficient, an explicit
statement that no gate or threshold was introduced, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
