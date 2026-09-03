GAP G206 | sport all | worktree a7 | log g206_route_emits_evaluated_count
**ADDITIVE ONLY (B2). No threshold, bar, verdict or existing field may change by a single digit, and
tracking behaviour must be BIT-UNCHANGED.** `src/` is HUMAN-GATED: READ only.
**`scripts/run_clip.py` is NOT human-gated and is the file to change.**

**S1 MACHINE: LOCAL is fine and preferred.** The pod is running G203 (byte identity) and must not
share the machine. You may run ONE short bounded local route invocation to verify the sidecar is
written, if and only if a local video is available; if not, verify by unit test and say so.

**S3 DEPENDENCY. Two landed rows independently concluded that the count must come from the ROUTE.**
  - **G199**: `ball_tracking.csv` is not a superset of the tracking table (852 tracking frames absent
    from its ball set), so no artifact-derived count exists. Returned `None` without clamping.
  - **G204** (landed `ade10f426`): the evaluated-frame ARITHMETIC now works, but it accepts only
    stable `decoded_frames`, `source_fps` and `max_frames`, and **the four committed tables do not
    carry them, so all four remain `None` and fail closed.**
  - **G197**: the gate is denominated on attempted frames and fails closed without an honest count.

**So the gate is honest and still unfeedable, and this row is what makes any row scoreable at all.**

**WHY NOTHING TRACKING-DERIVED MAY BE USED, verified by the orchestrator by reading the code:**
`unified_pipeline.py:992` `_is_gameplay` documents itself as *"Return True when YOLO detects enough
players"* and is **sticky** (`_gameplay_cache_until` ~3 s positive, `_no_gameplay_until` negative).
**The route's own notion of an attempted frame is detector-selected -- B1 in the producer.**
G177-ADJ fixes the line to hold: **"EVALUATED is decided before tracking; EMITTED is decided by
tracking."**

THE CHANGE, in `scripts/run_clip.py` only:
  (a) **Before tracking starts**, compute and persist an evaluated-frame count as a **SIDECAR JSON**
      next to the existing outputs. **Do NOT add a column to `tracking_data.csv`** -- a schema change
      would ripple into every reader, and G197 already showed how many readers exist.
  (b) The count must be a pure function of quantities decided before any detection: the source frame
      count, the source fps, the stride, and `max_frames`. **Derive the stride from the code rather
      than assuming it** -- read how the route actually strides and CITE the file and line. Do not
      hardcode 3 because G198 observed 3 on one clip.
  (c) Record in the sidecar, as named fields, every input you used and the formula, so a reader can
      recompute it without the video. Include the source path and its byte size.
  (d) **`cv2.CAP_PROP_FRAME_COUNT` is unreliable on some containers.** Validate it (G186 established
      the metadata-first pattern with a validated fallback). **If you cannot obtain a frame count you
      trust, write `null` and a machine-readable reason. Never guess, never substitute a
      tracking-derived quantity, and never fall back to the emitted table.**
  (e) Wire the sidecar into the direct scoring path added by G204 as the source of
      `decoded_frames`/`source_fps`/`max_frames`, so a freshly produced table becomes scoreable.

**TRACKING BEHAVIOUR MUST NOT CHANGE.** No new work inside the tracking loop, no reordering, no extra
decode pass that alters what the pipeline sees. **State explicitly in the memo how you know the route
still behaves identically**, and note honestly that the route is non-deterministic (G189/G195/G198)
so a row-count comparison across runs is NOT proof -- argue it from the diff instead.

MANDATORY EVIDENCE:
  - The sidecar for at least one real invocation (or, if no local video, a unit-tested construction
    with the inputs shown), with every field and the formula.
  - The stride derivation, with file and line cited.
  - A worked capped case and a worked uncapped case. **G204 corrected an earlier framing here:
    `mlb_...10893dca` at 39,035 decoded is UNCAPPED (6,506 evaluations at stride 6); `npb_01` is the
    true capped construct at 30,000 evaluations. Use G204's corrected examples, not G178's.**
  - The four G197 tables: state plainly that they remain `None` because they predate the sidecar,
    and that this row does not retrospectively score them.
  - A per-file test that fails without the change, plus `test_tracking_harness.py`,
    `test_tracking_harness_g197.py`, `test_attempted_frame_count_source.py` and
    `test_evaluated_frame_count_direct_path.py` -- paste all five.
  - A `git diff` over `CONFIG_VERSIONS` proving every threshold byte-identical.

ACCEPTANCE RULE:
  metric        = the sidecar exists with a recomputable count and named inputs; the direct path
                  consumes it; capped and uncapped worked cases
  before        = two independent rows (G199, G204) concluded no honest attempted count is reachable
                  from existing artifacts, so every table fails closed and nothing can be scored
  bar           = NO pass bar. Success is an honest count emitted before tracking, plus `null` with a
                  reason wherever it cannot be. **"The frame count cannot be trusted for this
                  container, so the sidecar is null" is a CORRECT result for that clip** and must be
                  reported, not engineered around.
  n             = at least one real invocation plus the unit tests; name what you could not run
  eye check     = none
  must not move = every threshold, every bar and verdict, `tracking_data.csv`'s SCHEMA, existing field
                  names, the coordinate contract, tracking behaviour, `src/` (READ ONLY), the daemon
                  path, the pod daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g206_route_emits_evaluated_count_2026-09-03.md with the sidecar, the
stride derivation with citation, both worked cases, the unchanged-threshold diff, the argument that
tracking behaviour is unchanged, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: the five named above, all pasted. NEVER a full pytest. **If a commit grows an allowlisted file,
raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12) and
run that rail test** -- G204 did this correctly, follow its example.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
