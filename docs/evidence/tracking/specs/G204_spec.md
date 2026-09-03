GAP G204 | sport all | worktree a7 | log g204_evaluated_denominator_direct_path
**This makes scoring HARDER and is additive (B2). No threshold, bar or verdict may change by a single
digit.** `src/` is HUMAN-GATED: READ only. Build in `scripts/platformkit/`.

**S1 MACHINE: LOCAL, and no pod.** Arithmetic over committed artifacts plus per-file tests. The pod is
running G203, which measures byte identity and must not share the machine.

**S3 DEPENDENCY, and this row exists because G199 returned a NEGATIVE that closed the easy route.**
  - **G197** (landed) gated coverage on `attempted_frames` and made it `None` when no honest count
    exists, so every committed table now fails closed.
  - **G199** (landed) tested the obvious source and **rejected it**: `ball_tracking.csv` is NOT a
    superset of the tracking table -- 852 tracking frames were absent from its ball set -- so it
    correctly returned `None` rather than clamping. **No artifact-derived count is available.**
  - **G179** established the honest quantity for the DAEMON path: EVALUATED frames, computed from
    `decoded_frames` and stride BEFORE any tracking runs.
  - **G177-ADJ** fixed the principle in one line: **"EVALUATED is decided before tracking; EMITTED is
    decided by tracking."**

**THE FINDING THAT MAKES THIS URGENT, verified by the orchestrator this session by reading the code:**
`unified_pipeline.py:992` `_is_gameplay` documents itself as *"Return True when YOLO detects enough
players"*, and it is **sticky** -- `_gameplay_cache_until` trusts a positive verdict for about three
seconds and `_no_gameplay_until` suppresses re-checking after a negative. **So the route's own notion
of an ATTEMPTED frame is selected by the detector succeeding.** That is B1 circularity in the
PRODUCER, one layer upstream of the harness defect G197 fixed. **Any denominator derived from gameplay
frames is contaminated and must not be used**, which is the deeper reason G199's candidate failed.

THE CHANGE:
  (a) Supply the direct harness path with an EVALUATED-frame count computed the G179 way: from the
      source frame count and the stride, **decided before tracking**. Derive the stride the way the
      pipeline does rather than assuming it -- read it from the code and SAY where you got it.
  (b) **Honour truncation.** G178 measured that `adapter_run.py:81` defaults `--max-frames` to 30000
      and that at least one job (`mlb_...10893dca`, 39,035 decoded) EXCEEDS it, so a naive
      `ceil(decoded / stride)` overstates the denominator for capped jobs. G179 pinned the semantics:
      `adapter.py:198` counts the STRIDE-SELECTED frame, so the cap limits EVALUATED frames. Your
      count must be correct for capped and uncapped jobs, and you must show a worked capped case.
  (c) **If the inputs for an honest evaluated count are unavailable for a table, return `None`.**
      Never fall back to anything tracking-derived. `None` is a correct answer.
  (d) Change no existing field name and no threshold.

MANDATORY EVIDENCE:
  - Per-table before/after for the four committed tables G197 scored: which now receive a real
    evaluated count, which stay `None`, and the resulting verdict. **`None` -> FAIL is the EXPECTED
    direction; anything -> PASS must be justified frame-by-frame, not accepted.**
  - A worked capped case and a worked uncapped case, with the arithmetic shown.
  - A per-file test that fails without the change, plus `test_tracking_harness.py`,
    `test_tracking_harness_g197.py` and `test_attempted_frame_count_source.py` -- paste all four.
  - A `git diff` over `CONFIG_VERSIONS` proving every threshold byte-identical.

ACCEPTANCE RULE:
  metric        = per-table evaluated count or `None`; resulting verdicts; the capped and uncapped
                  worked cases
  before        = the corrected gate is `None` on every committed table and the one artifact-derived
                  candidate was rejected by G199, so nothing can currently be scored at all
  bar           = NO pass bar. **"The evaluated count cannot be computed honestly for these tables
                  either" is a FULL SUCCESS** and would mean the ROUTE must emit the count, which is a
                  different and larger row. Do not manufacture a number to make the gate feedable.
  n             = the four committed tables plus any capped daemon row you can reach (CONSTRUCT); name
                  every exclusion and why
  eye check     = replaced by REPRODUCTION (Q7): recomputed from committed artifacts
  must not move = every threshold, every bar and verdict, existing field NAMES, the eligibility
                  definition, the coordinate contract, `src/` (READ ONLY), the daemon path, the pod
                  daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g204_evaluated_denominator_direct_path_2026-09-03.md with the
per-table table, both worked cases, the unchanged-threshold diff, an explicit statement of why no
gameplay-derived quantity was used, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: the four named above, all pasted. NEVER a full pytest. **If a commit grows an allowlisted file,
raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
