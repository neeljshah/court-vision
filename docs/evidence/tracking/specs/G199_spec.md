GAP G199 | sport all | worktree a7 | log g199_attempted_frame_count_source
**This makes scoring HARDER and is additive (B2). No threshold, bar or verdict may change by a single
digit.** `src/` is HUMAN-GATED: READ only. Build in `scripts/platformkit/`.

**S1 MACHINE: LOCAL is fine and preferred.** This is CSV bookkeeping plus per-file tests over
committed artifacts. No video decode, no model inference, no `run_clip.py`, **no pod**. The pod is
busy with G198. If you believe you need the pod, stop and say why instead.

**S3 DEPENDENCY.** Two landed rows:
  - **G197** (landed `93baf7587`) added `coverage_attempted_frames_pct` and
    `ball_valid_attempted_frames_pct`, gated them, and made them `None` when no honest attempted count
    is supplied. It accepts a count ONLY as the explicit `evaluate(..., attempted_frames=...)`
    argument or as one stable non-null `attempted_frames` column value on every row.
  - **G179** established that strided adapters DECODE more source frames than they ATTEMPT, so
    `decoded_frames` must NOT be used as the attempted count.

THE PROBLEM THIS ROW EXISTS TO FIX: **no committed table supplies an attempted count, so after G197
every corrected coverage value is `None` and every table fails closed on `attempted_frames
unavailable`.** The gate is now honest but unfeedable. Nothing can pass until a real count reaches it.

THE CANDIDATE, verified by the orchestrator over a WHOLE file (S2), not a sample:
  - `data/tracking/ball_tracking.csv` has **2,000 rows and 2,000 distinct `frame` values**, and its
    `detected` column is `0` on **409** of them and `1` on 1,591.
  - `scripts/run_clip.py:25` documents it as "Per-frame ball position + detection flag".
  - So this file records **one row per frame the pipeline processed, whether or not anything was
    found**. That is an attempt record, and it lives in a DIFFERENT file from the `tracking_data.csv`
    being scored, so using it is not circular.

**WHAT YOU MUST VERIFY BEFORE USING IT, and report either way:**
  1. **Is the `ball_tracking.csv` frame set a SUPERSET of the paired `tracking_data.csv` frame set?**
     Check on every paired artifact you can find, and report the count of violations. **If it is not a
     superset, it is NOT a valid denominator** -- a denominator smaller than its own numerator's
     support is incoherent -- and you must say so and STOP rather than clamping, padding or taking a
     max. Report that as the finding.
  2. Whether the frame values are strided, and whether the two files share the same stride. State it.
  3. Whether any paired file is truncated relative to the other (an early exit), and how you tell.

THE CHANGE, and B2 binds it hard:
  (a) Add a helper in `scripts/platformkit/` that, given a tracking table path, locates its paired
      ball table and returns an attempted-frame count **or `None`**. **Never guess, never fall back to
      `nunique()` of the table being scored** -- that is the exact defect G197 removed.
  (b) Wire it into the DIRECT harness scoring path only, as the `attempted_frames` argument.
      **Do NOT touch the daemon path** -- G179 already handles that, and the pod daemon and keeper must
      not be edited, restarted or deployed over.
  (c) Change no existing field name and no threshold.

MANDATORY EVIDENCE:
  - The superset check from (1) across every paired artifact, with the **violation count over the
    whole set**, not an example.
  - Before/after for the four committed tables G197 scored: which now receive a real count, which stay
    `None`, and the resulting verdict for each. **A row going from `None` to FAIL is the EXPECTED
    direction. A row going to PASS must be justified frame-by-frame, not accepted.**
  - A per-file test that fails without the change, plus `test_tracking_harness.py` and
    `test_tracking_harness_g197.py` -- paste all three.
  - A `git diff` over the `CONFIG_VERSIONS` table proving every threshold is byte-identical.

ACCEPTANCE RULE:
  metric        = superset-violation count over all paired artifacts; per-table attempted count
                  obtained or `None`; resulting verdicts
  before        = the corrected gate is `None` on every committed table and fails closed, so no row
                  can be scored on a non-circular denominator at all
  bar           = NO pass bar. **"`ball_tracking.csv` is not a valid superset, so no honest attempted
                  count exists in the current artifacts" is a FULL SUCCESS** and is more valuable than
                  a wired-up number, because it would say the ROUTE must be changed to emit one.
                  Do not manufacture a count to make the gate feedable.
  n             = every paired artifact you can find (CONSTRUCT); name any excluded and why
  eye check     = replaced by REPRODUCTION (Q7): recomputed from committed artifacts
  must not move = every threshold, every bar and verdict, existing field NAMES, the eligibility
                  definition, the coordinate contract, `src/` (READ ONLY), the daemon path, the pod
                  daemon and keeper, the corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g199_attempted_frame_count_source_2026-09-03.md with the superset
check, the per-table before/after, the unchanged-threshold diff, and a NOT VERIFIED list. Commit
BEFORE reporting (A7).
TEST: your new per-file test plus the two named above, all pasted. NEVER a full pytest.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
