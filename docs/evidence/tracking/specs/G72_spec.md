GAP G72 | sport baseball (contract, affects all) | worktree a6 | log cx_g72_metric_local_profile
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This IMPLEMENTS an already-adjudicated decision. Implement it;
do not re-open it and do not extend it.
THE ADJUDICATION (orchestrator, 2026-09-02, recorded in the G69 register row): G69 ran the harness
on a constructed metric_local fixture and established that metric_local rows are NOT scorable today
-- every reported zero is a `_failed_report` placeholder rather than a score. It then enumerated
which metrics are meaningful in metric_local units and proposed an additive, space-scoped profile.
That proposal is ACCEPTED IN PRINCIPLE subject to four binding conditions, reproduced below.
Read docs/evidence/tracking/g69_metric_local_scorability_2026-09-02.md FIRST -- it contains the
metric-by-metric table you must implement against. Do not re-derive that table.
WHY IT MATTERS: G47 measured that baseball is 66 of 93 contract-only rejections, the largest block
of any sport, and the calibration strategy established that the baseball centre-field view is
STRUCTURALLY uncalibratable (its landmarks are near-collinear along the pitch axis, so the
homography is ill-posed by geometry). Without this profile, baseball fails coordinate_contract
forever and its "zero pass" is misread as a tracking-quality statement.
IMPLEMENT: an additive, space-scoped local profile.
  (a) It evaluates ONLY the non-spatial metrics G69 listed as meaningful: frame/game/duplicate
      counts, ball presence and capability, coverage, detections per frame, track length, sample
      sufficiency, source and sampling metadata, and zero_step_share as a repeated-output
      diagnostic only.
  (b) Spatial fields are marked `not_applicable` -- NEVER 0, and never a null that a reader will
      see as zero. This is condition (b) and it comes straight from the G50 lesson: a
      plausible-looking number gets misquoted, an explicit not-applicable cannot.
  (c) It emits a SCOPED result label, PASS_METRIC_LOCAL / FAIL_METRIC_LOCAL, distinct from the
      court_feet `passed` / `verdict`.
  (d) The court_feet profile, its thresholds and the rung requirement are UNTOUCHED.
  (e) `image_px` is accepted by NEITHER profile. There is no cast, no fallback and no promotion
      from image_px to metric_local or court_feet. Acceptance stays an EXACT declaration match,
      never a range or magnitude inference. This is what makes the change safe and it is
      non-negotiable.
THE BINDING CONDITION THAT GATES ACCEPTANCE: ship a test proving a court_feet report's verdict is
**BYTE-IDENTICAL** before and after this change. If ANY existing verdict moves, that is a REJECT
and you report it rather than adjusting the fixture. Replay at least 10 existing court_feet reports
through the changed harness and diff every field.
ALSO REQUIRED: a test asserting that a scoped result can never be counted as a court_feet pass --
condition (a) of the adjudication is that PASS_METRIC_LOCAL is NOT a pass and no summary may add
them together. If any existing aggregation would sum them, that is a defect you must NAME (and it
becomes its own row); do not silently fix aggregation logic here.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (i) court_feet verdict stability, (ii) whether a metric_local fixture now scores
  before        = metric_local rows produce `_failed_report` placeholders and score nothing;
                  court_feet verdicts as they stand today
  bar           = court_feet verdicts byte-identical on >= 10 replayed reports, AND the G69
                  metric_local fixture produces real values for the meaningful metrics with every
                  spatial field `not_applicable` and a scoped label
  n             = >= 10 replayed court_feet reports plus the G69 fixture; state both
  eye check     = n/a (a contract and schema change). Reproduction = before/after report blocks
                  for both a court_feet report and the metric_local fixture, pasted in the memo.
  must not move = every court_feet threshold, every court_feet verdict, the rung ladder, and the
                  image_px rejection. Nothing about a sport that CAN reach court_feet changes.
SCOPE DISCIPLINE: implement the profile only. Do NOT switch baseball's producer over to it, do not
re-score any historical baseball report, and do not touch the baseball adapter. Turning it on for a
sport is a separate row with its own before/after.
DURABILITY (A7): commit the replay outputs and both before/after report blocks under
docs/evidence/tracking/g72_metric_local_profile/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g72_metric_local_profile_2026-09-0X.md with the byte-identical
replay result, both report blocks, the four conditions each addressed explicitly, and a
NOT VERIFIED list.
TEST: the two tests above, in one new per-file test module; run only that file. Never a full pytest.
POD: no deploy, no scp, no daemon restart, never kill anything -- another session has live
processes there. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push except the token. Report the sha.
SHARED MODULE: tracking_harness.py is under the token. Take it in
docs/evidence/SHARED_MODULE_TOKEN.md (edit that file alone, commit it alone, push -- the push is
the lock) and PUSH THE RELEASE when you report. A lane earlier today pushed its acquire and left
the release unpushed, which looks to everyone else like the token is still held.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
