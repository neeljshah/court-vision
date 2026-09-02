# G50B: NULL n-dependent metrics on degenerate reports

## Contract and result

This implements the adjudicated G50B decision in
`docs/evidence/tracking/specs/G50B_spec.md` under
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. Newly written normal reports
with `insufficient_data == true` now keep their counts, metadata, failures,
`passed`, and `verdict`, while reporting the sample-derived values below as
JSON `null`. No threshold, gate, field name, or historical report was changed.

## POD premise reproduction

All denominators were measured read-only on the POD. The canonical raw-table
glob `data/tracking/*/tracking_data.csv` contains 184 tables; 10 have fewer
than 30 distinct `frame` values. The two nonempty thin cases are
`tennis_07` (4 frames) and `tennis_09` (2 frames). The other eight have zero
frames and already take the existing failed-report path, where
`insufficient_data` remains false; this row does not change that path.

The current POD report glob `data/tracking_reports/**/*.json` has 187 reports
that carry both `jump_p95` and `n_frames`, rather than the earlier 201-report
observation. Its currently deployed harness has zero reports with
`insufficient_data == true`, because this harness change was deliberately not
deployed. On a newly written report from the two nonempty thin tables above,
the fields classified below will newly be null.

## Field classification

| Fields set to null | Reason |
|---|---|
| `coverage_pct`, `det_per_frame` | Fractions or means over the thin frame sample. |
| `median_track_len`, `median_step_distance`, `jump_p95` | Distribution summaries requiring sufficient observations. |
| `ball_valid_pct`, `ball_in_bounds_pct`, `oob_pct`, `zero_step_share`, `distinct_position_ratio`, `stationary_track_share` | Sample proportions or ratios. |
| `liveness_verdict` | Categorical conclusion derived from those thin-sample motion statistics. |
| `jump_p95_ft_per_s` | Derived directly from the null raw jump quantile. |

| Fields deliberately retained | Reason |
|---|---|
| `n_frames`, `n_unique_games`, `n_duplicate_frame_track_rows`, `ball_rows` | Counts report what was observed; they are not estimated quality metrics. |
| `sport`, `config_version`, ball telemetry fields, source fields, sampling interval fields, `self_consistency_only` | Identity, availability, and source metadata, not sample-quality readouts. |
| `insufficient_data`, `failures`, `passed`, `verdict` | The adjudicated flag and pre-existing gate outcome must remain byte-identical. |

## Two-frame before/after reproduction

The same constructed two-frame basketball input was evaluated using the
pre-change `HEAD` harness source and the changed source. This is also covered
by the non-tautological fixture assertion below.

```json
before={"ball_in_bounds_pct":1.0,"ball_rows":2,"ball_valid_pct":1.0,"coverage_pct":1.0,"det_per_frame":7.0,"distinct_position_ratio":1.0,"failures":["median_track_len 2.00 < 3.00","stationary_track_share 1.0000 > 0.1490"],"insufficient_data":true,"jump_p95":0.02,"jump_p95_ft_per_s":0.2,"liveness_verdict":"SUSPECT","median_step_distance":0.02,"median_track_len":2.0,"n_duplicate_frame_track_rows":0,"n_frames":2,"n_unique_games":1,"oob_pct":0.0,"passed":false,"sampling_interval_s":0.1,"stationary_track_share":1.0,"verdict":"FAIL","zero_step_share":0.0}
after={"ball_in_bounds_pct":null,"ball_rows":2,"ball_valid_pct":null,"coverage_pct":null,"det_per_frame":null,"distinct_position_ratio":null,"failures":["median_track_len 2.00 < 3.00","stationary_track_share 1.0000 > 0.1490"],"insufficient_data":true,"jump_p95":null,"jump_p95_ft_per_s":null,"liveness_verdict":null,"median_step_distance":null,"median_track_len":null,"n_duplicate_frame_track_rows":0,"n_frames":2,"n_unique_games":1,"oob_pct":null,"passed":false,"sampling_interval_s":0.1,"stationary_track_share":null,"verdict":"FAIL","zero_step_share":null}
```

## Verification

One new per-file test was added and run, exactly once:

```text
python -m pytest scripts/platformkit/test_tracking_harness_g50b.py -q
1 passed in 0.32s
```

The one fixture constructs four reports: 2, 29, 30, and 31 frames. It asserts
that every classified field is null below 30, no classified field is null at
or above 30, the retained count/provenance fields stay populated, and,
independently of the null assertions, that the pre-change fixture verdicts are
unchanged: 2 -> `passed is False`; 29, 30, and 31 -> `passed is True`.

Read-only POD replay selected the two thin metric reports plus eight evenly
spaced full metric reports from the 54 report-metric-bearing tables. It ran
the harness in its explicit audited legacy mode only to replay legacy source
tables under their stored coordinate contract. All 10 historical `passed`
values matched; historical verdict flips = 0. The selected reports were
tennis_07 (4), tennis_09 (2), football_Z8Ezd95NnjM (79),
football_yahhMkUWd7c (268), kbo_08 (1436), mlb_2026-08-30_2143de43 (1763),
npb_06 (565), soccer_c1mzmBGHQr4 (292), tennis_04 (3789), and
wnba_kangps_g2 (5987). The final WNBA table still matched `passed=False` but
returned zero replay frames under its current source contract; the other nine
preserved their historical frame count. No POD file was written, copied,
deployed, or restarted.

## Reader survey

| Reader | Handling of null metric fields |
|---|---|
| `scripts/platformkit/adapter_run.py` -> `tracking_timebase.py` | `per_second` already returns null when raw `jump_p95` is null. |
| `tracking_regression.py`, `corpus_rescore.py`, `tracking/depth_replay.py` | Filter non-numeric values and omit null metrics from comparisons. |
| `tracking_corpus_ab.py`, `baseball_calib_probe.py`, `tracking/tennis_sequential_plan.py` | Preserve/format report values; no direct numeric arithmetic on the affected fields was found. |
| `tracking/bridge_infill.py`, `tracking/tracklet_merge.py` | Known incompatibility: each calls `float(evaluate(...).coverage_pct)` and will raise on an insufficient-data input. They are intentionally not changed in this row. |
| `track_daemon_done.py` | Its persisted `coverage_pct` comes from the separate decoded-frame manifest, not the harness report field. |

## Verifier self-check (section B)

- B1: no rows are excluded from any computed metric; existing calculations run before masking.
- B2: no field, status value, or reader is removed; readers are surveyed above.
- B3/B4: no gate, claim, or failure path changed.
- B5: no POD deployment or file copy occurred.
- B6: no module moved or retired.
- B7: no render or head-slice evidence is used.
- B8: the fixture asserts the expected pre-change `passed` value where nulls appear.
- B9: the POD denominator is distinct `frame` values, counted from the canonical CSV-table glob.
- B10: `MIN_FRAMES_FOR_METRICS`, all threshold maps, and gate calculations are unchanged.

## Evidence-path self-check (A7)

At memo time these tracked evidence paths exist: this memo,
`docs/evidence/tracking/specs/G50B_spec.md`,
`docs/evidence/tracking/VERIFIER_CONTRACT.md`,
`scripts/platformkit/tracking_harness.py`, and
`scripts/platformkit/test_tracking_harness_g50b.py`. The POD-only paths named
above were confirmed by the read-only commands during this run.

## NOT VERIFIED

- No newly written POD report was produced: deployment is explicitly out of scope.
- The two known transform readers that coerce `coverage_pct` to `float` remain
  incompatible with an insufficient-data report; that follow-up is not silently
  folded into G50B.
- The reported 201-report observation was not reproduced on the current POD;
  the current precise report glob count is 187.
