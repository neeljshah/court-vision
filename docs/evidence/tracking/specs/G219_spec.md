GAP G219 | sport tennis | worktree a8 | log g219_tennis_failure_head_diagnosis
**MEASUREMENT AND PROPOSAL ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build
in `scripts/platformkit/tracking/`.

**S1 MACHINE: ANALYSE LOCALLY. The pod is BUSY with a throughput measurement (G216) and you must not
add load to it.** The ONLY pod action permitted by this spec is copying **three small emitted CSVs**
(a few MB in total) to your worktree with `scp`. **FORBIDDEN: any route run, `run_clip.py`, model
inference, GPU work, `ffmpeg`, `ffprobe`, video decode, and touching the daemon, keeper or bridge.
Delete NOTHING on the pod, write NOTHING to the pod.** If your approach needs more than three file
copies, STOP and say so rather than proceeding.

**WHY THIS ROW EXISTS -- THESE THREE ROWS ARE THE ONLY WINDOW IN THE ENTIRE LEDGER PAST CALIBRATION
INTO ACTUAL TRACKING QUALITY.** G207 rescored the whole pod body: 34 complete canonical tables, 32
scorable, **zero pass**, and **29 of 32 exit first at `coordinate_contract`** -- they die before any
tracking-quality gate is ever evaluated. **Only three rows get past it, all tennis, and each fails at a
DIFFERENT head:**

    | row | emitted rows | first failure head |
    |---|---:|---|
    | `tennis_01`   | 19,437 | **`jump_max` 108.39 > 8.00** |
    | `tennis_02`   |  1,637 | **`median_track_len` 1.00 < 3.00** |
    | `tennis_ref01`|  1,861 | **duplicate frame-track rows = 4** |

(Source: `docs/evidence/tracking/g207_pod_ledger_rescore_census_2026-09-03.md:137-139` and the
companion `g207_pod_ledger_rescore_rows_2026-09-03.csv`. A fourth, `tennis_smoke`, is UNSCORABLE for
lack of a durable denominator -- exclude it and say you did.)

**READ WHAT THOSE THREE NUMBERS ACTUALLY MEAN, because they are worse than they look:**
  - **`median_track_len 1.00` means the MEDIAN TRACK LIVES EXACTLY ONE FRAME.** More than half of all
    tracks are never associated to a second frame. **That is not weak tracking; it is a tracker
    producing detections with no temporal association at all.**
  - **`jump_max 108.39` against a bar of 8.00** means some track moves 13x the permitted per-frame
    distance -- an identity switch, a coordinate-unit error, or an association to something that is
    not the same object.
  - **duplicate `(frame, track_id)` rows is a LOGICAL IMPOSSIBILITY for a tracker.** One track cannot
    occupy two positions in one frame. **This one needs no model judgement to call a defect**, which
    makes it the cheapest and most certain finding available.

THE QUESTION: **for each of the three heads, what specifically produces it?**

METHOD:
  1. Copy the three emitted CSVs from the pod and **record each path, byte size and SHA-256** so a
     later reader can confirm you analysed the same tables G207 scored. **Name the ELIGIBLE DENOMINATOR
     as the rows in each table**, and reconcile your row counts against G207's (19,437 / 1,637 / 1,861).
     **A mismatch means the tables changed under us and is itself a finding -- report it and stop
     rather than analysing a different artifact than the one that was scored.**
  2. **Reuse the harness's OWN metric definitions** (`tracking_harness.py`) for `jump_max`,
     `median_track_len` and the duplicate check rather than reimplementing them, so your numbers are
     commensurable with G207's. **If you must reimplement, reproduce G207's exact values first as a
     control and say so.**
  3. **`median_track_len`:** report the FULL distribution of track lengths, not the median -- how many
     tracks live 1 frame, 2, 3-5, 6+; what fraction of all emitted rows belongs to one-frame tracks.
     **Then answer WHY**: read the association code and state which condition rejects the match. Is it
     a distance gate, a missing embedding, an appearance threshold, an age/hit requirement, or is
     association simply not being invoked on this path? **Cite `file:line`.**
  4. **`jump_max`:** find the specific offending track and frame pair. Report the coordinates, the
     units, and the frame gap between the two rows. **Distinguish these three explanations explicitly:
     a genuine identity switch; a coordinate-unit or scale error; or a large frame GAP that makes a
     legitimate displacement look like a jump** (a track absent for 40 frames and reacquired is not
     the same defect as a track teleporting between consecutive frames). **Say which, with the numbers
     that decide it.**
  5. **Duplicate `(frame, track_id)`:** identify all 4 duplicate pairs, show the differing columns, and
     **trace the emission path to say how one track produced two rows in one frame** -- two detectors
     writing to one table, a re-emission after a re-ID merge, a retry, an append without dedupe.
     **Cite `file:line`. If you cannot determine it from the code, say UNDETERMINED rather than
     guessing.**
  6. **Say whether these are TENNIS-SPECIFIC or GENERAL.** The other 29 rows die at
     `coordinate_contract` before these gates ever run, **so the same defects could be sitting
     unmeasured behind every other sport.** State clearly which of your findings are properties of the
     shared tracking code (and therefore affect every sport) and which are tennis-path specific. **Do
     NOT claim the general case is broken without naming the shared code that carries it.**
  7. **PROPOSALS ONLY for anything in `src/`, clearly marked human-gated.** State the expected effect
     and what could regress. **Apply nothing.**

**HONEST LIMITATIONS to state, not discover:** these are three clips of one sport and the tables were
produced by a NON-DETERMINISTIC route (G189/G195/G198/G203), so a re-run would not reproduce them row
for row -- **you are diagnosing THESE tables, not a stable population.** You cannot conclude a rate from
three rows. Tennis has 2-4 players against basketball's 10, so association difficulty differs by sport
and a tennis finding does not transfer by default.

ACCEPTANCE RULE:
  metric        = per-row reconciliation against G207's counts; the full track-length distribution; the
                  identified `jump_max` incident with its cause classified among the three named
                  explanations; the 4 duplicate pairs with an emission-path explanation or an explicit
                  UNDETERMINED; a shared-code-versus-tennis-path judgement for each finding
  before        = three failure heads are NAMED by G207 and NONE is explained; they are the only
                  tracking-quality signals in the ledger that are not blocked by `coordinate_contract`
  bar           = NO pass bar. **"The cause is X at file:line" is the success for each head, and
                  "UNDETERMINED from static reading" is an acceptable honest outcome for any head you
                  cannot settle** -- provided you say what evidence would settle it. Do not repair
                  anything; do not move a gate value to make a row pass.
  n             = 3 emitted tables (CONSTRUCT, exhaustive for coordinate-valid pod rows), 22,935 rows
  eye check     = none required; this row is table and code analysis
  must not move = every threshold, `jump_max`'s 8.00 bar, `median_track_len`'s 3.00 bar, every verdict,
                  the coordinate contract, `src/` (READ ONLY -- apply no fix), the pod (THREE FILE
                  COPIES ONLY -- no route runs, no writes, no deletions), the daemon, keeper and bridge
EVIDENCE: docs/evidence/tracking/g219_tennis_failure_head_diagnosis_2026-09-04.md with the SHA-256 of
each analysed table, the reconciliation against G207, the track-length distribution, the three
diagnoses with `file:line` citations, the shared-versus-tennis-path judgement, the human-gated
proposals, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
