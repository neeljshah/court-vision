# G279: Speed-threshold sensitivity of the G267/G270 detector-box result

## Verdict

**ACCEPT (measurement only): the frozen strict-over-40-ft/s results reproduce exactly: 4,090 / 29,973 = 0.136456 for all finite same-ID detector-box steps, and 2,507 / 23,783 = 0.105411 for the both-endpoints-on-court subset.** Rounded to one decimal percentage point, these are the published 13.6 pct and 10.5 pct figures. This row does not alter, replace, or select a new definition for the published 40 ft/s bar; it reports its full requested sensitivity curve.

**Robustness:** the fraction moves gradually around 40 ft/s (all steps: 15.1 pct at 35, 13.6 pct at 40, and 12.7 pct at 45; both-on-court: 12.0, 10.5, and 9.6 pct), so the published figure is robust to small cut-point changes rather than a cliff at 40 ft/s.

The units are detector boxes and emitted association IDs, not authenticated players. G273's blind sample found only 43 / 72 = 0.597 retained detections to be a player on the court of play; a substantial share of these steps are therefore not people at all. This curve describes detector-box motion, not player motion.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It makes no production change, threshold move, detector call, reassociation, video decode, render, source-tree edit, pod call, or disk check.

## Frozen local input and exact reproduction

The only opened measurement input was the committed artifact
`docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`,
12,446,681 bytes, SHA-256
`0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`.
No video was opened. Its inherited source identity is
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`,
2,931,985,407 bytes, 1920x1080, 30 fps, source frames 19599--23399 inclusive
(3,801 frames).

The retained artifact has 30,071 class-0 detector-box footpoints. For every emitted `track_id`, this row
sorts retained finite observations by source frame and pairs consecutive observations. Speed is court-footpoint
distance times 30 fps divided by the actual positive frame gap. This reproduces the G267/G270 population exactly:

| Reproduction check | Strict-over-40 numerator | Named denominator | Fraction |
|---|---:|---:|---:|
| G267 all finite same-ID detector-box steps | 4,090 | 29,973 eligible finite same-ID steps | 0.136456 |
| G270 both-endpoints-on-court detector-box steps | 2,507 | 23,783 eligible finite same-ID steps whose two projected feet are inside inclusive `0 <= x <= 50`, `0 <= y <= 94` ft | 0.105411 |

The harness aborts before curve output if either reproduction differs.

## Fixed-threshold curve

Every row uses strict `speed > threshold`; each denominator is printed in the table, not inferred. The
26.5 ft/s point is the **NBA average top speed** reference. The published 40 ft/s row remains the fixed
strict-over definition. **Bolt peak** is 40.7 ft/s, a contextual reference only; it is not selected as a new
threshold or added as a new headline.

| Threshold ft/s | All finite same-ID detector-box steps: count / 29,973 | Fraction | Both-endpoints-on-court detector-box steps: count / 23,783 | Fraction |
|---:|---:|---:|---:|---:|
| 20.0 | 7,131 / 29,973 | 0.237914 | 4,833 / 23,783 | 0.203212 |
| 25.0 | 5,941 / 29,973 | 0.198212 | 3,913 / 23,783 | 0.164529 |
| 26.5 (NBA average top speed) | 5,652 / 29,973 | 0.188570 | 3,692 / 23,783 | 0.155237 |
| 30.0 | 5,128 / 29,973 | 0.171087 | 3,295 / 23,783 | 0.138544 |
| 35.0 | 4,532 / 29,973 | 0.151203 | 2,849 / 23,783 | 0.119791 |
| 40.0 (published fixed bar) | 4,090 / 29,973 | 0.136456 | 2,507 / 23,783 | 0.105411 |
| 45.0 | 3,802 / 29,973 | 0.126847 | 2,281 / 23,783 | 0.095909 |
| 50.0 | 3,570 / 29,973 | 0.119107 | 2,113 / 23,783 | 0.088845 |
| 60.0 | 3,155 / 29,973 | 0.105261 | 1,807 / 23,783 | 0.075979 |

Lower thresholds mechanically produce larger fractions. In particular, the 20 and 25 ft/s rows are not a
"real error rate": below about 26.5 ft/s the bar starts excluding genuine athletic movement, so those points
bound the measurement rather than the tracker. No row in this table is proposed as a replacement threshold.

## Speed distributions

| Denominator | Median ft/s | p90 ft/s | p99 ft/s | p99.9 ft/s | Max ft/s |
|---|---:|---:|---:|---:|---:|
| All 29,973 eligible finite same-ID detector-box steps | 7.762 | 65.571 | 700.118 | 2,482.380 | 100,457.241 |
| 23,783 eligible both-endpoints-on-court detector-box steps | 7.117 | 42.753 | 417.774 | 870.436 | 1,368.623 |

## Named exclusions and denominator accounting

All 30,071 retained detector records are finite, so non-finite detector endpoints are **0 / 30,071** and no
same-ID step is excluded by the finite-endpoint requirement in this retained artifact. The all-steps curve
denominator is therefore 29,973 eligible finite same-ID steps.

The both-endpoints-on-court curve denominator is 23,783 / 29,973 eligible finite same-ID steps. The remaining
6,190 / 29,973 = 0.206524 are excluded only by that additional endpoint condition: 1,001 / 29,973 have exactly
one endpoint on court and 5,189 / 29,973 have neither endpoint on court. These are named conditional exclusions,
not deleted records; the all-steps curve retains every eligible finite same-ID step.

## Machine-readable artifact and check

The committed [machine-readable curve](g279_speed_threshold_sensitivity_artifact/g279_measurement.json) stores
the source path, byte size, hash, reproduction counts, fixed curve, quantiles, and all denominator accounting.
It records SHA-256 identities for this local route and the reused G267/G270 arithmetic routes.

```text
python -m pytest scripts/platformkit/tracking/test_g279_speed_threshold_sensitivity.py -q -p no:cacheprovider
2 passed in 2.93s
```

Contract self-check: A7 evidence paths exist; A9 names the opened artifact and inherited source identity with
bytes and resolution. B1 keeps every finite same-ID step and names all conditional exclusions; B2--B6 alter no
schema, lifecycle, deployment, production module, or module location; B7 uses the complete retained 3,801-frame
span; B8 uses no fitted residual; B9 names detector-record and step denominators; B10 retains the published
40 ft/s bar. Q does not apply. The new 188-line harness and 45-line focused test do not grow an allowlisted file,
so A12 requires no LOC-rail change.

## Limitations and NOT VERIFIED

- One clip, one camera shot, one non-deterministic detector draw, and source frames 19599--23399 only.
- The single inherited homography was measured at 5 px median and 19 px p90 on the seed frame only (G252).
  Map error propagates into every court-space speed and is not included in this curve.
- At 30 fps, one-frame footpoint jitter of a few pixels produces a large apparent speed. That is the localisation
  instability G272b found, and it is part of what this curve measures.
- This row cannot separate map error, footpoint jitter, identity swaps, or non-person detections from one another.
- It does not verify person precision or recall, on-court status, true identity, association accuracy, a second
  source draw, another clip, shot, arena, map, sport, or any production rule.
