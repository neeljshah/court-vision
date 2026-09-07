GAP G305 | sport basketball | worktree a6 | log g305_additive_registration_verdict
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check against every line of
section B before you report.
**MEASUREMENT AND ADDITIVE INSTRUMENTATION ONLY. `src/`, `domains/` and `kernel/` are READ and IMPORT
only.** Build in `scripts/platformkit/` (**not human-gated**; **additive only; <= 300 LOC per file**).
**`scripts/platformkit/tracking_harness.py` IS A SHARED MODULE (`docs/evidence/SHARED_MODULE_TOKEN.md`)
AND MUST BE BYTE-IDENTICAL AFTER THIS ROW.** You IMPORT it; you do NOT edit it, and you do NOT take the
token. Everything you build is a NEW module that wraps it.
**A registration result never translates into the ledger passed field.**
SOURCE OF EVERY CLAIM BELOW: `docs/research/astra_tracking_registration_2026-09-07.md` section 3.

**WHERE THIS ROW RUNS (step -1, MANDATORY, PER STEP):** **ENTIRELY LOCAL. NO POD, NO GPU, NO GPU
LEASE, NO `pod_run`.** Every input is a committed record or a synthetic table you construct. No disk
guard is required; this row writes tests and JSON only.

**PREMISE (step 0) -- BINDING BEFORE-CONDITION. Confirm all four readings in the CURRENT tree before
you build anything; if any one of them no longer holds, STOP, write the memo, commit, report
PREMISE FALSE -- a valid result that earns its own register row.**
  1. **`evaluate()` explicitly measures SELF-CONSISTENCY** -- `scripts/platformkit/tracking_harness.py`
     around **line 272** -- and **`self_consistency_only=True` survives even when `passed=True`**
     (around **line 395**). Quote both lines verbatim with their line numbers as you find them today.
  2. **The main basketball/WNBA bars are** (around line 25): bounds **[0,94] x [0,50] ft**;
     **>=6 player IDs on >=60% of attempted frames**; **OOB <= 5%**; **modal-stride max jump <= 6 ft**;
     **median track length >= 3 observations**. Ball presence **>= 30%** applies only when telemetry is
     not explicitly unavailable, else the verdict can be **PASS_NO_BALL** (lines 332, 366, 375).
     **< 30 emitted frames overrides PASS to INSUFFICIENT_DATA** (lines 257, 350, 405).
  3. **THE AXIS MISMATCH IS REAL:** `domains/basketball/tracking/geometry.py` around **line 28** uses
     **x <= 50, y <= 94**; the harness uses **x <= 94, y <= 50**. Confirm both readings.
  4. **`2026-09-01-v1` DOES NOT IDENTIFY A CRITERION.** The worktree copy carries the SAME config
     label but gates emitted-frame coverage and p95 displacement, **omits the median-track-length bar**
     and **has no attempted-frame gate** (WT tracking_harness.py lines 147, 164). Record the SHA256 of
     the harness file you actually imported. Memo-recorded hashes: main
     **c5a86154da32177f00b72c8b54651ce73b4d68c48001348848ff4df3c6bd2f95**, WT
     **8217037fa06f7467bcdf4164a69671a4e83f692044fe5f9dc9e1535ee1c5d807**. **A different hash is not a
     failure -- report it and say which file your numbers describe.**
  **Do NOT claim the pod uses either file.** That requires reading its actual dependency hashes and its
  `passed` / `verdict` / `failures` fields together, and this row does not touch the pod.

**CHANGE (step 1) -- three additive deliverables, (a) then (c) then (b). Nothing else.**

**(a) THE INSTRUMENT FALSIFIER -- one per-file test that DOCUMENTS the gap, it does NOT break it.**
  Construct a canonical tracking table that PASSES the current harness. Reflect it with
  **x' = 94 - x** (y and every id, frame and timestamp untouched). **Bounds, coverage, track lengths
  and pairwise distances are all preserved, while absolute court-end identity is wrong.** Run the
  UNCHANGED harness on both tables and **assert the CURRENT behaviour** -- i.e. assert that the
  reflected table still passes, if that is what it does. **THIS IS A MEASUREMENT, NOT A BREAK: the
  assertion pins today's behaviour so a later change is visible. Do NOT "fix" the harness. Do NOT move
  a bar. Do NOT propose a threshold.** Also assert and report that
  **`self_consistency_only` is True on the passing run**, which is the same finding stated a second way.
  If the reflected table does NOT pass, that is an equally valid, MORE interesting result: report it
  with the exact failure fields and say the memo's falsifier does not fire on this harness build.

**(c) THE AXIS-CONVENTION BOUNDARY TRANSFORM -- a small named transform plus its test.**
  Write the explicit transform between the `geometry.py` convention (x <= 50, y <= 94) and the harness
  convention (x <= 94, y <= 50), for BOTH coordinates AND the homography matrix, with the direction
  named in the function signature. **Test it on all four NAMED court corners** (name each corner in
  both conventions, do not test four anonymous points), plus one interior asymmetric point that would
  survive a wrong transform that merely swaps axes. **Round-trip exact to <= 1e-9 ft.**

**(b) THE ADDITIVE REGISTRATION VERDICT -- a new module that EMITS ALONGSIDE, never replaces.**
  Emit the triple **`registration_passed` / `player_tracking_passed` / `ball_tracking_passed`** next to
  the existing verdict. **The original harness `verdict`, its `passed` field, its `failures` list and
  its config label are RETAINED VERBATIM in the same record. Nothing existing is renamed, removed or
  recomputed.** `registration_passed` is computed ONLY from:
   - the **E1 frame-good rule**: correct shot/end orientation, finite H, and named held-out
     reprojection error **p90 <= 12 px AND max <= 24 px in original 1920x1080 pixels**, against the
     **fixed six correspondences** of a sealed G304 packet -- never nearest arbitrary edges,
     candidate-chosen points, fitted corners, or a censored search window;
   - **court-end identity** and **finite, observable rank** (an ill-conditioned solve is REFUSED and
     its rejection reported; confidence alone establishes neither rank nor court end);
   - **uncensored per-frame errors** -- every frame's error is stored, none clipped or windowed;
   - a **declared mode block**: offline/online, manual inputs, court convention, camera-shot
     eligibility, and a **sealed attempted-frame manifest** fixed BEFORE inference. Zero-row, rejected
     and uncalibrated frames stay in that pre-tracking manifest -- **defining attempts as frames after
     successful calibration only moves the denominator tautology upstream, so say plainly which
     denominator you used**;
   - **hashes stored with EVERY row**: harness, schema, liveness and producer. **Never reinterpret an
     old ledger row with current code.**
  Also carry, as reported FIELDS and never as a pass condition: **`q`** = independently eligible share,
  **`r`** = successful six-player tracking conditional on eligibility, and **`q * r`**, with the
  **necessary condition `q * r >= 0.60`** for 60% whole-broadcast coverage. **Even a perfect map cannot
  satisfy it if q < 0.60, and the historical court-bearing census is NOT proof of q -- visible lines
  and intersections need not supply an identifiable homography. State that.** Publish whole-broadcast
  yield as a **separate denominator** from the eligible-frame yield.
  **On a worked example only.** This row wires nothing into production, changes no default, and writes
  no real ledger row. `registration_passed` with no sealed G304 packet available is **`null`, never
  `False` and never `True`** -- an unmeasured field is not a failed one.

ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (a) the reflection test runs deterministically and reports the harness verdict on the
                  original AND on the **x' = 94 - x** table, plus the `self_consistency_only` value on
                  the passing run; (c) all four named corners plus one asymmetric interior point
                  round-trip through the axis transform in both directions; (b) the additive module
                  emits the three booleans, the `q` / `r` / `q * r` fields, the four hashes and the
                  declared mode block **alongside a byte-identical copy of the original verdict record**
                  on one worked example
  before        = the harness measures **self-consistency** (line 272) and `self_consistency_only=True`
                  survives `passed=True` (line 395); `geometry.py:28` is **x <= 50, y <= 94** against
                  the harness's **x <= 94, y <= 50**; and **no ledger row today stores harness, schema,
                  liveness and producer hashes together**
  bar           = **NO pass bar on the harness's behaviour** -- (a) is a documentation test and either
                  outcome is a full success. The bar is on THIS row's own artifacts: the reflection
                  test must be deterministic and must assert the observed current behaviour; the
                  four-corner round-trip must be exact to **<= 1e-9 ft**; and the additive record must
                  reproduce the original verdict **byte-identically** while adding the new fields
  n             = 4 named corners + 1 asymmetric interior point + the 2 harness runs of (a) + 1 worked
                  example for (b) = **CONSTRUCT**, every case enumerated, not sampled. The `n >= 30`
                  sampling rail does NOT apply and the verifier may not reject on it
  eye check     = **n/a -- this row has no frames and no renders.** Reproduction = re-run the single
                  test file and re-read the emitted JSON record; contract A2 applies, A3 does not
  must not move = `scripts/platformkit/tracking_harness.py` **BYTE-IDENTICAL** (verify with SHA256
                  before and after and print both); `docs/evidence/SHARED_MODULE_TOKEN.md` (do NOT take
                  the token); CONFIG_VERSIONS `2026-09-01-v1`; every existing threshold, verdict,
                  status value and field name; `src/`, `domains/`, `kernel/` (READ and IMPORT ONLY);
                  every historical ledger row; `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
NON-TAUTOLOGY: the additive verdict covers the frames in the sealed manifest and excludes none of them.
**If excluding the failing frames is what makes a number good, the metric is circular -- say so and
report REJECT yourself.** This row also may NOT claim the additive verdict is better than the existing
one: it has never been run against a real registration result, because none exists.

ATTEMPT 2 (the memo's limit measurement): if the additive record cannot be produced without editing the
shared harness, **measure and report exactly which harness internals are not reachable from outside**
-- name each function and field a wrapper cannot obtain -- and close the row **CLOSED AT LIMIT** with
that list, so the shared-module token can be requested for a later, precisely scoped edit. **Do not
take the token in attempt 2 either.**

EVIDENCE: `docs/evidence/tracking/g305_additive_registration_verdict_2026-09-07.md` with the four
premise readings quoted at their line numbers, the harness SHA256 before and after, the reflection
result table (original vs reflected verdict, failures, `self_consistency_only`), the four-corner
transform table in both conventions, the worked additive record in full, and a **NOT VERIFIED list**
that at minimum carries: that no real registration result was scored, that `q` and `r` are schema
fields and not measurements here, that the pod's actual harness is unread, and that the WT-vs-main
criterion divergence was read from the memo rather than re-diffed unless you re-diffed it.
**REQUIRED EVIDENCE DURABILITY:** the emitted record and both verdict dumps go under `docs/evidence/`.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: exactly one new per-file test, **importing full package paths** (`scripts.platformkit....`), run
as a single file only -- **NEVER a full pytest.** It carries (a), (b) and (c) and must pin: the
**x' = 94 - x** reflection, the **1e-9** corner tolerance, the **p90 <= 12 / max <= 24 px** frame-good
rule, the **q * r >= 0.60** necessary condition as a reported field, and that the original verdict
record is byte-identical in the additive output. **If a commit grows an allowlisted file, raise its
entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
