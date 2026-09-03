GAP G207 | sport all | worktree a3 | log g207_pod_ledger_rescore_census
**HELD -- DO NOT DISPATCH UNTIL G203 HAS REPORTED.** G203 is measuring byte identity on the pod and
must not share the machine.

**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only.
**Never kill, restart or deploy over the pod daemon or keeper**, and never delete any corpus source.

**S1 MACHINE: RUN ON THE POD** (the tables live there), but this is file reading and arithmetic, not
inference. Copy nothing large back; commit summaries and a per-row CSV.

**S3 DEPENDENCY.**
  - **G179** (landed) corrected the DAEMON path's coverage denominator to EVALUATED frames, computed
    before tracking. **These pod tables are daemon-produced, so unlike the four committed direct-path
    tables they CAN be scored.**
  - **G176** (landed) surveyed **18** pod ledger rows and found **exactly 1** carried a coverage
    failure head; **14 failed at `coordinate_contract`** because baseball rows declare `image_px`,
    which is not accepted for baseball; 3 carried no failure head. It stated honestly that an 18-row
    ledger dominated by coordinate-contract exits cannot settle whether the coverage gate
    discriminates program-wide.
  - **Orchestrator, this session, measured on the pod:** there are now **35 tracking directories and
    34 `tracking_data.csv` files**, nearly double G176's 18. The corpus holds **11 clips across 7
    sports** (wnba, ncaa_basketball, tennis, soccer, football x2, mlb, kbo x2, npb x2).

THE QUESTION: **on the corrected evaluated-frame denominator, what does the whole pod body of results
actually score, per sport, and what fails FIRST?** This is the programme's honest current state and
nobody has measured it since the denominator was corrected and since the body nearly doubled.

METHOD:
  1. Enumerate every tracking directory on the pod. **Name the ELIGIBLE DENOMINATOR as the count of
     directories that carry a complete canonical table**, and name every exclusion and why. Do not
     silently drop anything.
  2. For each, score with the CURRENT frozen harness on the corrected denominator, exactly as the
     daemon path does. **Do not re-run tracking. Do not re-run the route.** Score committed output.
  3. Report per row: sport, rows, evaluated-frame denominator, gate coverage, ball validity, verdict,
     and **the FIRST failure head** -- which gate fired first, not the whole list.
  4. **Aggregate by sport and by first-failure-head.** The decision-relevant question is whether the
     coverage gate is even REACHED, or whether `coordinate_contract` still exits first as G176 found
     on the smaller body.
  5. Report how many rows PASS. **If the answer is zero, say zero plainly.**

**DO NOT move any threshold, bar, denominator or verdict to make a row pass.** If a gate looks wrong,
that is a finding to report, not to act on -- B10/Q3 make bar changes an orchestrator decision.

**HONEST LIMITATIONS you must state rather than discover:**
  - These tables were produced by a route that is **non-deterministic** (G189, G195, G198), so each
    row is one sample from a distribution, not a fixed property of the clip. Say so; do not present
    per-row numbers as reproducible.
  - They were also produced under the **frame misalignment G198 measured** -- 100 pct of detections
    attributed to the next processed frame -- which is uncorrected. **Every number here is a
    measurement of the CURRENT system including that defect**, and is a baseline to improve against,
    not a statement about what the tracker could do.
  - Do not compare against G176's 18 rows as if it were the same construct; the body has changed.

**A9:** name each table's full pod path and row count.
**B13/Q9:** commit the per-row CSV, not only the aggregate.

ACCEPTANCE RULE:
  metric        = per-row verdict and FIRST failure head on the corrected denominator; aggregates by
                  sport and by first-failure-head; the count of rows passing
  before        = G176 surveyed 18 rows before the denominator was corrected and found coverage
                  reached in exactly 1; the body is now 34 tables and has never been scored on the
                  corrected denominator
  bar           = NO pass bar. **"Zero rows pass and N still exit at coordinate_contract" is a FULL
                  SUCCESS** and is the honest state of the programme. A row that PASSES must be
                  inspected and justified, not celebrated -- given G198's misalignment a pass would be
                  surprising and must be explained.
  n             = every pod tracking directory with a complete canonical table (CONSTRUCT,
                  exhaustive); name exclusions
  eye check     = none; this row is arithmetic over committed tables
  must not move = every threshold, bar, denominator and verdict, the coordinate contract, `src/`
                  (READ ONLY), the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g207_pod_ledger_rescore_census_2026-09-03.md with the per-row table,
both aggregates, the pass count, the exclusions, and a NOT VERIFIED list. Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added under `scripts/platformkit/tracking/`, pasted. NEVER a
full pytest. **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
POD: read there; never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
