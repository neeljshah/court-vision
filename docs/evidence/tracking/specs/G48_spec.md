GAP G48 | sport all | worktree a4 | log cx_g48_sampling_interval
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. ADDITIVE ONLY. You may NOT move the 8.0 ft jump bar.
PREMISE (step 0, reproduce it): only 28 of 187 harness reports (15.0 pct) carry a sampling block.
Among the reports that DO record it, the sampling interval spans 0.0800-0.1001 s, a 25.1 pct
spread; for the other 159 reports it is simply unknown. The harness compares a RAW per-step
distance against a frozen 8.0 ft bar (scripts/platformkit/tracking_harness.py, the jump section).
Reproduce both counts and the interval range yourself from the reports on disk before proceeding,
and say in the memo exactly which glob you counted over -- the 187 denominator must be stated,
not inherited.
LIMIT (step 1): a distance bar compared across clips with different sampling intervals is not
comparing like with like. The same physical speed produces a jump number that differs by 25 pct
depending only on the clip's stride and frame rate. That is a units defect, not a threshold
defect, and no choice of bar fixes it while the interval is unrecorded. It also undermines G38,
whose entire diagnosis rests on jump magnitudes, and whose memo already lists the 30 fps
assumption as NOT VERIFIED.
CHANGE (step 2): ADDITIVE ONLY, and in this order.
  (a) Record the sampling interval on EVERY report. The interval is (frame stride) / (source fps).
      Both are already known at run time. If a clip's fps genuinely cannot be read, record
      sampling_interval_s as null and a reason string -- never silently default to 30 fps.
  (b) Report an ADDITIONAL derived field, jump_p95_ft_per_s = jump_p95 / sampling_interval_s,
      null when the interval is null. This is a NEW field that gates NOTHING.
  (c) Leave jump_p95 and the 8.0 ft bar and the pass/fail logic BYTE-IDENTICAL. `passed` must not
      read either new field. Prove this with a test that asserts the verdict is unchanged on a
      fixture whose interval varies.
DO NOT propose a speed bar in this row. Choosing one is a threshold change and needs adjudication;
this row exists to make that adjudication POSSIBLE by producing the units.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fraction of newly written reports carrying a non-missing sampling block
  before        = 28 of 187 (15.0 pct) -- reproduce this number yourself
  bar           = 1.0 on newly written reports (a recorded null with a reason counts as recorded),
                  AND every pre-existing field byte-identical in name and value, AND `passed`
                  provably independent of both new fields
  n             = >= 4 constructed reports spanning: known fps, unknown fps, a stride of 1, and a
                  stride > 1; plus a re-run over >= 10 existing tables proving no verdict flips
  eye check     = n/a (a schema change); reproduction = a before/after report block in the memo
  must not move = the 8.0 ft jump bar, every other harness threshold, every existing field name,
                  and every existing verdict. If ANY historical verdict flips, that is a REJECT
                  and you must report it rather than adjusting the fixture.
NON-TAUTOLOGY: do not compute the interval from the tracking rows themselves (the median frame
gap), because that is derived from the same sampling you are trying to characterise and would
agree with itself by construction. Read the stride and the fps from the run configuration and the
source. If you can only get it from the rows, say so explicitly and label the field derived.
EVIDENCE: docs/evidence/tracking/g48_sampling_interval_2026-09-0X.md with the reproduced 28/187,
the interval distribution, the before/after report block, the no-verdict-flip result, and a
NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy, no scp. Report the files you would deploy and let the verifier land them.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token. Take it in
docs/evidence/SHARED_MODULE_TOKEN.md before editing (edit that file alone, commit it alone, push --
the push is the lock) and release it when you report. It is currently free.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
