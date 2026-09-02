# G48 sampling-interval instrumentation

Date: 2026-09-02. Scope: additive fields in
`scripts/platformkit/tracking_harness.py`. No pod copy or deployment was made.

## Premise reproduction

The stated 28-of-187 premise is **FALSIFIED in this worktree**. I counted the
glob `**/*.json`, recursively walking each parseable JSON document and counting
every object containing `jump_p95` as a harness-report node. The result is
**16 report nodes, 0 with a sampling block**, not 187 reports with 28 blocks.

The 16 nodes are one in `tennis_baseline.json` and five each in
`tennis_09.json`, `tennis_10.json`, and `tennis_nyYk2nPZAwY_720p.json`, all
under `docs/evidence/tracking/`. Consequently, there is no on-disk interval
distribution to reproduce: its count is zero. The claimed 0.0800--0.1001 s
range cannot be verified from this checkout.

The worktree also contains no existing canonical tracking-row tables to rerun:
there are no tracking CSVs under `data/`, and the 16 historical report nodes
contain summary metrics rather than source rows. Thus the required re-run over
at least 10 existing tables cannot be performed here. This memo does not claim
that check passed.

## Additive report fields

Every `QualityReport` now has these informational fields:

- `sampling_interval_s`: `frame_stride / frame_rate`, rounded to four decimal
  places, when both run-configuration values are valid.
- `sampling_interval_reason`: null when the interval is known; otherwise a
  named reason, including unavailable source fps. No 30 fps default is used.
- `jump_p95_ft_per_s`: `jump_p95 / sampling_interval_s`, rounded to two decimal
  places, or null when the interval is unavailable.

The interval reads only `source_metadata.frame_stride` (or its existing
`stride` spelling) and `source_metadata.frame_rate`; it does not inspect frame
gaps in tracking rows. The three fields are appended to the report schema and
are not read by `passed`, `verdict`, failures, or any threshold.

## Before and after report block

Constructed basketball fixture, source fps 25, same rows and same existing
fields. The after case supplies frame stride 3.

```json
before={"jump_p95":0.02,"jump_p95_ft_per_s":null,"passed":true,"sampling_interval_reason":"frame stride unavailable","sampling_interval_s":null,"verdict":"PASS"}
after={"jump_p95":0.02,"jump_p95_ft_per_s":0.17,"passed":true,"sampling_interval_reason":null,"sampling_interval_s":0.12,"verdict":"PASS"}
```

## Verification

`python -m pytest scripts/platformkit/test_tracking_harness.py -q` passed:
24 tests. The one new test constructs four reports: known 25 fps at stride 1,
known 25 fps at stride 3, unknown fps at stride 3, and known 30 fps at stride
5. It asserts the interval/reason and derived field, keeps `passed`, `verdict`,
and failures unchanged, and compares every pre-existing report field byte for
byte between an interval-missing and interval-known fixture.

Historical verdict re-run status: **NOT VERIFIED**, because the required ten
existing source tables are absent from this worktree. No historical report was
rewritten, so no historical verdict was altered by this change.

## Verifier contract B self-check

- B1: no metric is scored and no rows are excluded.
- B2: fields are additive; existing names and values are unchanged in the test.
- B3-B4: no quarantine or claim path is touched.
- B5: no deployment was performed.
- B6: no module moved or retired.
- B7-B9: no render, sample, residual, or denominator claim is made.
- B10: threshold maps, including the tennis 8.0 ft `jump_p95_max`, are
  byte-identical; the new fields do not gate.

## NOT VERIFIED

- The spec's 187-report denominator, 28 recorded intervals, and 0.0800--0.1001
  second distribution are absent from this worktree.
- A ten-table historical rerun cannot be performed without the missing canonical
  tracking-row tables.
- No newly written production report has been generated; the constructed test
  covers the report schema only.
