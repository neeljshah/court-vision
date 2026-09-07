GAP G312 | sport all | worktree a12 | log g312_coverage_denominator
**ARITHMETIC ROW, ADDITIVE ONLY. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and
IMPORT only. Build in `scripts/platformkit/`. This row ADDS ledger fields and CHANGES NO EXISTING
ONE. It moves no threshold, no verdict, no `passed` value and no production default.**

**WHERE THIS ROW RUNS:** LOCAL. The premise reproduction needs ONE pod `tracking_data.csv` and its
ledger line, fetched READ-ONLY by `scp` into a scratchpad -- **never into `data/` in the repo.**
**NEVER stop, signal or interfere with `track_daemon`.** No GPU, no GPU lease, no disk guard.

**WHY THIS ROW EXISTS.** G309 measured that the ledger's `evaluated_frames` is
`ceil(decoded_frames / stride)` and therefore IGNORES the route's `max_frames = 3000`, which every
one of the 15 censused games carries in its `evaluated_frame_count.json`. Against the frames the
route actually attempted -- `min(ceil(decoded/stride), ceil(max_frames/stride))` -- the attempted
share is **median 0.9790, min 0.7210, max 1.0000 (n = 13)**, not the ledger's `coverage_pct`
median 0.0346. Every coverage figure carried in the register understates the attempted share by
roughly 10x-30x. That is a DENOMINATOR defect, not a tracking result: it says nothing about
whether the tracker is right, only about what it was asked to look at.

**PREMISE (step 0, BINDING before-condition):** pick ONE censused game, fetch its pod
`tracking_data.csv` and its LAST ledger line, and **PRINT BOTH NUMBERS SIDE BY SIDE**: the ledger's
own `evaluated_frames` / `coverage_pct`, and the capped `attempted_frames_capped` /
`coverage_attempted_capped_pct` recomputed for the same game. **If the two are equal, or if the
game's `evaluated_frame_count.json` carries no `max_frames`, the premise is FALSE: STOP, write the
memo, commit, and report PREMISE FALSE.**

METHOD:
  1. **ADDITIVE FIELDS IN THE LEDGER WRITER** (`scripts/platformkit/track_daemon_done.py`). Add
     exactly three keys to the `adjudicate` payload: `route_max_frames` (**the cap recorded
     EXPLICITLY**, read from the game's `evaluated_frame_count.json`), `attempted_frames_capped`
     and `coverage_attempted_capped_pct`. **EVERY PRE-EXISTING KEY KEEPS ITS EXACT VALUE AND
     SPELLING** -- `coverage_pct`, `evaluated_frames`, `stride`, `decoded_frames`, `passed`,
     `failure_heads`, `harness_coverage_pct`, `coordinate_space`, `rung`, `evaluated_at`,
     `csv_fsynced`. Nothing is renamed, nothing is recomputed, nothing is deleted.
  2. **MISSING CAP = NULL, NEVER A GUESS.** No sidecar, an unreadable sidecar, a null or
     non-positive `max_frames`, or an unknown stride -> all three new keys are `null`. **A default
     cap may NOT be invented.**
  3. **RE-ADJUDICATION TABLE** for ALL 13 censused rows with a ledger line, committed as a CSV
     beside the memo: game_id, stride, decoded_frames, ledger `evaluated_frames`, ledger
     `coverage_pct`, `attempted_frames_capped`, `coverage_attempted_capped_pct`, and the ratio of
     the two coverages. Recompute from the COMMITTED G309 census columns, never from a live pod
     read -- **the pod ledger has grown since the census and is a different population.**
  4. **CHANGE NOTHING ELSE.** No harness edit, no threshold, no register edit, no adoption.

**HONEST LIMITATIONS to state, not discover:** **the capped share is a SCHEDULING number, not a
quality one.** A game may attempt 100% of its capped frames and emit rows for all of them while
tracking the wrong objects entirely; this row measures denominators, not recall, precision,
accuracy or registration, and says so in those words. Image space only. All 13 rows are
`passed = false`, so this is a re-adjudication of FAILING runs and none of them becomes a pass.
**The 0.9790 headline is post-hoc arithmetic on committed columns and was NOT in the G309 sealed
metric list; it is re-derived here, not inherited.** The new fields are written by no completed
pod run yet -- **nothing on the pod is re-adjudicated by this row.**

ACCEPTANCE RULE:
  metric        = the premise pair printed for one named game; the three additive payload keys; the
                  13-row re-adjudication CSV
  before        = the ledger's `evaluated_frames` = `ceil(decoded/stride)` for all 13 rows, and NO
                  field anywhere records the route's `max_frames`
  bar           = **13/13 rows recomputed to within 1e-9** of the arithmetic on the committed census
                  columns, AND every pre-existing payload key **byte-identical** to the unmodified
                  writer on the same input (asserted in the test, not by eye)
  n             = 13 ledger-backed census rows (15 census rows, 2 with no ledger line, named)
  eye check     = NONE. No frames, no renders, no labels. Say that rather than implying validation.
  must not move = `data/tracking/` on the pod (READ ONLY -- never write, never delete, never touch
                  the ledger); the running `track_daemon`; `src/`, `domains/`, `api/`, `kernel/`,
                  `intel/`; `tracking_harness.py`; every existing field, threshold and verdict
EVIDENCE: `docs/evidence/tracking/g312_coverage_denominator_2026-09-07.md` (<= 60 lines) with the
premise pair, the re-adjudication summary, every denominator, and a **NOT VERIFIED** list. The CSV
is committed beside it. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: `tests/platformkit/test_g312_coverage_denominator.py` -- a SYNTHETIC construct pinning the
capped arithmetic, the null-on-missing-cap branch, and the byte-identity of the pre-existing keys.
**n = 3 (CONSTRUCT).** Run that ONE file. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**
