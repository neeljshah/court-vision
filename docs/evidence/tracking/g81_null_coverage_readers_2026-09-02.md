# G81: nullable coverage readers

## Result

ACCEPT. G50B's nulling remains unchanged: a `coverage_pct` on fewer than 30
frames is not measurable, and a fabricated numeric value would be misleading.
This reader-only correction makes bridge infill and tracklet merge preserve that
state as `null` instead of calling `float(None)`. No harness field, threshold,
verdict, or adequate-data value changed.

The original G50B reader survey was necessary but incomplete. It missed the
two readers below; they were found later by a gate audit. This memo repeats the
survey at every named nulled field rather than assuming a short import list was
complete.

## Required pre-fix reproductions

The inputs below are the same declared `court_feet` five-frame basketball
table, which the harness legally reports as `verdict=INSUFFICIENT_DATA` with
`coverage_pct=null`.

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "C:\\Users\\neelj\\nba-track-a3\\scripts\\platformkit\\tracking\\bridge_infill.py", line 163, in bridge_dataframe
    coverage_observed=_coverage(tracks, key),
  File "C:\\Users\\neelj\\nba-track-a3\\scripts\\platformkit\\tracking\\bridge_infill.py", line 99, in _coverage
    return float(evaluate(table, sport).coverage_pct)
TypeError: float() argument must be a string or a real number, not 'NoneType'
```

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "C:\\Users\\neelj\\nba-track-a3\\scripts\\platformkit\\tracking\\tracklet_merge.py", line 234, in merge_tracklets
    coverage_before=float(evaluate(tracks, key, allow_legacy_undeclared=True).coverage_pct),
TypeError: float() argument must be a string or a real number, not 'NoneType'
```

Both commands exited nonzero before the fix. After the reader-only change, the
same input exits zero and prints `bridge None None` and `merge None None`.

## Reader decision

| Reader | Unmeasurable coverage action | Why | Verdict or null? |
|---|---|---|---|
| `tracking/bridge_infill.py` | Propagate `null` into `coverage_observed` and `coverage_with_bridge`. | A bridge cannot measure coverage that its source report cannot measure. | Key on `INSUFFICIENT_DATA`; retain a direct-null guard for schema safety. |
| `tracking/tracklet_merge.py` | Propagate `null` into `coverage_before` and `coverage_after`. | Merging cannot convert an unmeasurable quality quantity into a numeric claim. | Key on `INSUFFICIENT_DATA`; retain a direct-null guard for schema safety. |

`INSUFFICIENT_DATA` is the cleaner primary test because it records why the
report has no coverage. The explicit `None` guard is retained so a future legal
null does not become another unchecked reader. Neither reader substitutes 0.0
or 1.0, and neither modifies harness nulling.

## Complete nullable-field consumer survey

The survey searched every tracked Python file for each of these thirteen exact
fields: `coverage_pct`, `det_per_frame`, `median_track_len`,
`ball_valid_pct`, `ball_in_bounds_pct`, `jump_p95`, `oob_pct`,
`zero_step_share`, `median_step_distance`, `distinct_position_ratio`,
`stationary_track_share`, `liveness_verdict`, and `jump_p95_ft_per_s`.

**n = 13 runtime QualityReport consumers.** Every field is either read by a
listed direct renderer/transform or safely preserved by a generic report
reader. Producers (`tracking_harness`, `metric_local_profile`, and
`liveness_metrics`), unrelated coverage metrics, and test fixtures were
inspected but are not counted as report consumers.

| Consumer | Nulled fields read | Verdict |
|---|---|---|
| `tracking/bridge_infill._coverage` | `coverage_pct` | Needs fix; fixed here. |
| `tracking/tracklet_merge.merge_tracklets` | `coverage_pct` | Needs fix; fixed here. |
| `baseball_calib_probe.probe` | coverage, ball, jump, OOB, median-step fields | Safe: copies JSON values without numeric coercion. |
| `corpus_rescore._metric_deltas` | All report metrics through generic report iteration | Safe: subtracts only values proved numeric. |
| `evidence_page._table` | coverage, detections, median length, ball, jump, OOB | Safe: `_number` renders null without arithmetic. |
| `ledger_report.report` | coverage and ball-valid | Safe: filters numeric values before medians. |
| `tracking/depth_replay._values` | coverage, jump, OOB | Safe: excludes null before `float`. |
| `tracking/tennis_sequential_plan.run_range` | coverage, median length, ball-valid, jump, OOB | Safe: propagates values unchanged. |
| `tracking_corpus_ab` | coverage, OOB, jump, ball-valid, median length | Safe: renders null as `NA` and compares only numeric values. |
| `tracking_timebase.timebase_metrics` | median step distance and jump | Safe: `per_second` preserves null. |
| `tracking_brain._metric_value` | coverage, ball-valid, jump, OOB | Safe: returns a value only for numeric inputs. |
| `answers/corpus_builder_v2._tracking` | coverage, detections, median length, ball-valid, jump, OOB | Safe: text formatter accepts null. |
| `answers/tracking_resolver` | All fields in verbatim game reports; aggregate subset via `tracking_brain` | Safe: preserves raw JSON or delegates to the numeric guard above. |

`track_daemon` and `track_daemon_done` contain a different completion-sidecar
`coverage_pct` derived from decoded-frame completeness, not the harness report
field; they are not consumers of this nullable schema.

## Verification

Exactly one new per-file test was added and run:

```text
python -m pytest scripts/platformkit/tracking/test_g81_null_coverage_readers.py -q
1 passed in 0.73s
```

The test calls both readers with the required five-frame report and verifies
all four coverage outputs are null. It also calls both with 30 frames and
asserts each reported coverage remains equal to the harness's adequate-data
coverage. `git diff --check` passed.

## VERIFIER_CONTRACT self-check

- **A7:** Confirmed at memo time that this memo, `specs/G81_spec.md`,
  `VERIFIER_CONTRACT.md`, `scripts/platformkit/tracking/bridge_infill.py`,
  `scripts/platformkit/tracking/tracklet_merge.py`, and
  `scripts/platformkit/tracking/test_g81_null_coverage_readers.py` exist.
- **B1:** No row or report is excluded; the readers only preserve the harness's
  existing unmeasurable result.
- **B2:** No field, status, or verdict is renamed or removed. The full
  thirteen-field reader survey is enumerated above, and its two failures are
  corrected.
- **B3:** No absent-evidence gate or quarantine path changed.
- **B4:** No claim, queue, or retry path changed.
- **B5:** No pod deployment, copy, restart, daemon action, or kill occurred.
- **B6:** No module moved or retired.
- **B7:** This is an exhaustive constructed five-frame reproduction, not a
  head-slice render claim.
- **B8:** No fitted or self-fit metric is asserted.
- **B9:** The constructed inputs contain five and 30 distinct frames,
  respectively; no denominator is recycled.
- **B10:** The harness, frame floor, thresholds, nulling loop, and verdict
  logic are untouched; adequate-data coverage is asserted unchanged.

## NOT VERIFIED

- No pod deployment or production reader run occurred; the verifier owns pod
  landing.
- No full test suite was run; only the required new per-file test was run.
- No historical corpus replay was needed for this deterministic reader-contract
  correction.
