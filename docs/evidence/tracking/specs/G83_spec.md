GAP G83 | sport all | worktree a6 | log cx_g83_frame_stride_metadata
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. Small, cheap, and it makes an already-landed fix actually work.
THE DEFECT: G48 landed `sampling_interval_s`, `sampling_interval_reason` and the derived
`jump_p95_ft_per_s` on every harness report, and the register recorded it as LANDED. It has never
carried a value in production. `jump_p95_ft_per_s` requires `metadata["frame_stride"]`, and
`adapter_run.py:124` -- the ONLY caller that passes `source_metadata` at all -- hands over
`probe_media`'s dict, which returns width, height, frame_rate, bit_rate and path, and NO stride. It
computes `plan.stride` and puts it in `options`, never in `metadata`. The other nine callers pass no
metadata whatsoever. So on every real run `sampling_interval_s` is None and
`sampling_interval_reason` reads "frame stride unavailable".
REPRODUCE THAT FIRST and paste the output. Do not take this description on trust -- run a real table
through the harness the way adapter_run does and show the null.
WHY IT MATTERS: G48 exists because the frozen 8.0 ft jump bar is applied to RAW per-step distances
whose sampling interval varies 25.1 pct across clips, so the same physical speed yields different
numbers on different clips. Comparing a SPEED instead is the entire point, and it is impossible
while the field is null. It also blocks G82, which must decide what statistic replaces jump_p95.
FIX: route the stride that `adapter_run` ALREADY computes into the metadata the harness receives.
  (a) Do not recompute or infer the stride. `plan.stride` exists; pass it.
  (b) The other nine callers pass no metadata. Say what happens to them: they keep reporting an
      explicit null WITH a reason, exactly as now. Do NOT invent a default stride and NEVER assume
      30 fps -- G38's memo already lists that assumption as NOT VERIFIED, and G27/G28 recorded that
      nyYk 360p and 720p differ 2x in frame index for the same duration.
  (c) Purely additive. No threshold, no verdict, no other field changes.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = fraction of reports written through adapter_run carrying a non-null
                  sampling_interval_s
  before        = 0.0 -- null on every real run, reason "frame stride unavailable"
  bar           = 1.0 through the adapter_run path with jump_p95_ft_per_s computed from it, AND
                  every other caller still emitting an explicit null-with-reason, AND no verdict
                  anywhere changing
  n             = >= 3 real tables through adapter_run, plus one caller that passes no metadata
  eye check     = n/a. Reproduction = the before and after report block, pasted.
  must not move = the 8.0 ft jump bar, every threshold, every verdict, and every existing field
DO NOT propose a speed-based bar in this row. That is G82 and it needs adjudication. This row only
makes the units exist so that adjudication becomes possible.
A LANDED FIELD THAT IS ALWAYS NULL IS NOT A LANDED FIX -- state that in the memo, because the
register said G48 was landed and nobody checked a real run. Say what a future lane should check
before declaring an additive field landed.
EVIDENCE: docs/evidence/tracking/g83_frame_stride_metadata_2026-09-0X.md with the reproduced null,
the routed value, the before/after report block, the no-verdict-change proof, and a NOT VERIFIED
list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: if you must touch tracking_harness.py, take the token in
docs/evidence/SHARED_MODULE_TOKEN.md and PUSH the release. Prefer to change only the CALLER, which
is where the defect actually is.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
