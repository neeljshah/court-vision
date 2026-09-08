# G310 PILOT -- produced BEFORE the preregistration was committed (NOT the headline)

## Why this directory exists

The G310 preregistration (`docs/evidence/tracking/g310_prereg_2026-09-07.md`, seal
`528211D145F773FEB428647C15157567C56B9DB3AD37033315F6E6D20A70DCD5`) was written and sealed before
any arm was run, but it was left UNCOMMITTED while a first pass of all seven route runs executed on
the pod. VERIFIER_CONTRACT Q1 requires that the sealed prereg predate the first metric in the
repository record, and an uncommitted file predates nothing in git.

Every number in this directory was therefore produced BEFORE commit `0e901359e`
("G310: preregistration sealed (Q1)"), so it is a PILOT. It is archived here for completeness and
for the reader who wants to see that the second pass was not the first look at the data. It is
NOT quoted as the row's result, and the memo's verdict line does not rest on it.

## What it contains

- `pilot_summary.json` -- the pilot driver report (per-run settings, GPU and disk probes, source probes).
- `pilot_proxies.csv` -- the pilot proxy table, seven rows.

## What the pilot measured (pilot numbers, not the headline)

Generated 2026-09-08T02:06:49Z. Ran in `/workspace/wt/a1` directly, not in a `pod_run` job root.
Frames requested 1500 per run; wall budget 3,600 s per run; native imgsz 1920.
Corpus probed 22 sources, 7 measured 1920x1080 eligible, 15 rejected.
Disk `du -sm /workspace` before 15024, after UNKNOWN (the 60 s probe timed out; UNKNOWN, never 0).

| tag | status | wall s | imgsz at construction | imgsz at call site |
|---|---|---|---|---|
| wnba_01_1080p_armP | COMPLETE | 363.7 | 640 | 640 |
| wnba_01_1080p_armN | COMPLETE | 776.6 | 1920 | 1920 |
| ncaa_basketball_IB-_u4gW3ds_1080p_armP | COMPLETE | 2603.4 | 640 | 640 |
| ncaa_basketball_IB-_u4gW3ds_1080p_armN | COMPLETE | 2155.9 | 1920 | 1920 |
| ncaa_basketball_mRkuGgeECak_armP | BUDGET_LIMIT | 3604.2 | (no summary) | (no summary) |
| ncaa_basketball_mRkuGgeECak_armN | BUDGET_LIMIT | 3604.5 | (no summary) | (no summary) |
| wnba_01_1080p_armP_repeat | COMPLETE | 1293.0 | 640 | 640 |

The pilot's own ARM P repeat differed from its first ARM P run on the same game and the same
settings (person rows 2185 vs 2116, median track length 216.0 vs 206.5, ball rows detected 417 vs
387, wall 1293.0 s vs 363.7 s), which is why the memo treats every arm as ONE DRAW.

`person_rows_per_evaluated_frame` is empty in `pilot_proxies.csv` because the route's own
`evaluated_frame_count.json` sidecar reports `"evaluated_frames": null` with
`"reason": "max_frames_is_detector_dependent_in_this_route"`. No denominator was substituted.
