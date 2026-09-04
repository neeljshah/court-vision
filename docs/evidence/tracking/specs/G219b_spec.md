GAP G219b | sport tennis | worktree a8 | log g219b_tennis_heads_refetch
**MEASUREMENT AND PROPOSAL ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build
in `scripts/platformkit/tracking/`.

**READ `docs/evidence/tracking/specs/G219_spec.md` AND
`docs/evidence/tracking/g219_tennis_failure_head_diagnosis_2026-09-04.md` FIRST. This row inherits
G219's method, limitations and honesty requirements unchanged and completes the two heads it could not
reach.** Do not redo the `tennis_ref01` duplicate diagnosis: it is CONFIRMED, its citations were
re-verified in master by the orchestrator, and repeating it wastes the row.

**WHY THIS ROW EXISTS -- G219 FAILED ON A SPEC ERROR THAT WAS MINE.** All three pod sources are named
`tracking_data.csv`. G219's spec permitted exactly three copies into one directory, so `scp` used each
source basename and **the third transfer overwrote the first two.** The lane then correctly refused a
fourth copy because the spec forbade it, and returned NOT VALIDATED rather than analysing one table and
implying three. **That refusal was right. The constraint was wrong, and this row fixes the constraint.**

**COPY INSTRUCTION, AND THIS IS THE WHOLE POINT OF THE ROW: give each transfer a DISTINCT destination
filename.** Copy to `<dir>/tennis_01_tracking_data.csv` and `<dir>/tennis_02_tracking_data.csv`, or
`scp` each into its own subdirectory. **Verify after each copy that the previous file still exists and
that the byte sizes differ as expected**, and say in the memo that you checked.

**S1 MACHINE: ANALYSE LOCALLY.** The pod may still be busy with G216 or G222. **Your ONLY permitted pod
actions are TWO small CSV copies (a few MB total).** **FORBIDDEN: any route run, `run_clip.py`, model
inference, GPU work, `ffmpeg`, `ffprobe`, video decode, writes to the pod, deletions on the pod, and
touching the daemon, keeper or bridge.**

THE TWO REMAINING HEADS, from `g207_pod_ledger_rescore_census_2026-09-03.md:137-138`:
    | row | pod path | G207 rows | first failure head |
    |---|---|---:|---|
    | `tennis_01` | `/workspace/nba-ai-system/data/tracking/tennis_01/tracking_data.csv` | 19,437 | **`jump_max` 108.39 > 8.00** |
    | `tennis_02` | `/workspace/nba-ai-system/data/tracking/tennis_02/tracking_data.csv` |  1,637 | **`median_track_len` 1.00 < 3.00** |

**If either table is GONE from the pod or its row count no longer matches G207's, say so and stop on
that head.** The tables were produced by a non-deterministic route and may have been overwritten by the
daemon; **a changed table is a finding, not something to analyse as if it were the scored one.**

**CARRY FORWARD G219's HARNESS-IDENTITY CAUTION.** G219 established that the local harness SHA-256
`c5a86154...` DIFFERS from the pod harness SHA-256 `59f60428...` that G207 recorded. **So do not present
a local recomputation as a reproduction of G207's score.** Reproduce the metric on the retained table,
report your value beside G207's, and **if they differ, report the difference rather than reconciling it
away.** Reuse the harness's own definitions -- `jump_max` and player track length at
`scripts/platformkit/tracking_harness.py:322-329` and its neighbourhood -- and cite the lines you used.

METHOD:
  1. Copy both tables under distinct names. Record path, byte size and SHA-256 for each, and reconcile
     row counts against G207's 19,437 and 1,637. **Name the ELIGIBLE DENOMINATOR for each table.**
  2. **`tennis_02`, `median_track_len` 1.00.** Report the FULL distribution of track lengths -- how many
     tracks live 1 frame, 2, 3-5, 6+ -- and **what fraction of all emitted rows belongs to one-frame
     tracks.** A median of exactly 1.00 means more than half of all tracks are never associated to a
     second frame. **Then answer WHY**: read the association path and name the condition that rejects
     the match -- a distance gate, a missing embedding, an appearance threshold, an age/hit requirement,
     or association simply not being invoked. **Cite `file:line`.** **UNDETERMINED is acceptable if the
     code does not settle it, provided you say what evidence would.**
  3. **`tennis_01`, `jump_max` 108.39 against a bar of 8.00.** Identify the offending track and frame
     pair; report coordinates, units, and **the frame GAP between the two rows.** **Distinguish three
     explanations explicitly: a genuine identity switch; a coordinate-unit or scale error; or a large
     frame gap making a legitimate displacement look like a teleport.** A track absent for 40 frames and
     reacquired is NOT the same defect as one jumping between consecutive frames. **Say which, with the
     numbers that decide it.** Note that `tennis_ref01` declared `coordinate_space=court_feet` at 360p
     source height, so **check what `tennis_01` declares rather than assuming it matches.**
  4. **Say for each head whether it is TENNIS-SPECIFIC or SHARED.** The other 29 pod rows die at
     `coordinate_contract` before these gates ever run, **so the same defects could sit unmeasured
     behind every other sport.** Name the shared code that would carry a general defect; **do not claim
     the general case is broken without naming it.** G219 found the duplicate head to be tennis-path
     specific -- do not assume these two are.
  5. **PROPOSALS ONLY, clearly marked human-gated. Apply nothing.**

**HONEST LIMITATIONS to state, not discover:** two clips of one sport, produced by a NON-DETERMINISTIC
route, so you are diagnosing THESE tables and not a stable population; a re-run would not reproduce them
row for row. Tennis has 2-4 players against basketball's 10, so association difficulty differs by sport
and a tennis finding does not transfer by default.

ACCEPTANCE RULE:
  metric        = per-table SHA-256 and row reconciliation against G207; the full track-length
                  distribution for `tennis_02`; the identified `jump_max` incident for `tennis_01` with
                  its cause classified among the three named explanations; a shared-versus-tennis-path
                  judgement for each head
  before        = both heads are NAMED by G207 and NEITHER is explained; G219 lost both tables to an
                  `scp` basename collision and honestly returned NOT VALIDATED
  bar           = NO pass bar. **"The cause is X at file:line" is the success for each head, and an
                  honest UNDETERMINED is acceptable** provided you say what would settle it. **"The
                  table no longer matches G207 and cannot be diagnosed" is also a legitimate outcome.**
                  Repair nothing; move no gate value to make a row pass.
  n             = 2 emitted tables, 21,074 rows by G207's counts
  eye check     = none; this row is table and code analysis
  must not move = every threshold, the 8.00 `jump_max` bar, the 3.00 `median_track_len` bar, every
                  verdict, the coordinate contract, `src/` (READ ONLY -- apply no fix), the pod (TWO
                  FILE COPIES ONLY), the daemon, keeper and bridge
EVIDENCE: docs/evidence/tracking/g219b_tennis_heads_refetch_2026-09-04.md with the per-table SHA-256 and
reconciliation, the copy-verification statement, the track-length distribution, the two diagnoses with
`file:line` citations, the shared-versus-tennis judgement, human-gated proposals, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
