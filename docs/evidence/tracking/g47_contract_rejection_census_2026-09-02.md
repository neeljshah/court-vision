# G47 Contract Rejection Census

The program's zero-pass headline must not be quoted as a tracking-quality statement for baseball, basketball, football, or soccer: their 119 contract-only reports were never quality-scored. This census does not establish a quality conclusion for tennis.

## Scope and live corpus

Diagnosis only. No source, harness, threshold, verdict, POD file, daemon, or
deployment was changed.

All counts below are a point-in-time, read-only POD measurement over this exact
glob:

```text
/workspace/nba-ai-system/data/tracking_reports/**/*.json
```

`pathlib.Path(...).glob("**/*.json")` found and parsed 187 of 187 JSON report
objects. All 187 had a list-valued `failures` field and all 187 carried
`jump_p95`; this supersedes the older 201-report observation for this live
glob. Sport report denominators were baseball 93, basketball 12, football 42,
soccer 25, and tennis 15.

The census first flattened and counted every member of every `failures` list,
without selecting a failure head: 116 distinct failure strings and 63 distinct
full failure signatures. Only after that enumeration, contract-only means a
report whose sole failure string begins with the observed
`coordinate_contract:` head. This selects 119 reports; the count with a second
failure is 0.

## Distinct contract reason strings, before cause grouping

| Exact failure reason string | Count |
|---|---:|
| `coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball; a preserved detection corpus is never a scorable game` | 66 |
| `coordinate_contract: rows declare coordinate_space image_px not accepted for sport football; a preserved detection corpus is never a scorable game` | 30 |
| `coordinate_contract: rows declare coordinate_space image_px not accepted for sport soccer; a preserved detection corpus is never a scorable game` | 15 |
| `coordinate_contract: NBA production tracking uses image pixels in x_position/y_position; x_norm/y_norm and ft_x/ft_y are image-affine values, and no persisted per-frame homography or equivalent court anchor is available` | 8 |

The reason diagnostics are informative: they identify the declared coordinate
space, sport, and, for basketball, the missing calibration/anchor condition.
There is no uninformative contract reason string in the 119.

## Cause grouping and classification

| Cause | Exact-reason members | Classification | Count by sport (contract-only / all reports) | Why |
|---|---|---|---|---|
| Preserved detection rows accurately declared as `image_px`, with no accepted court coordinate representation | Baseball, football, soccer strings above | (ii) legitimate rejection | baseball 66/93; football 30/42; soccer 15/25; subtotal 111/160 | The producer does declare its space, so this is not an undeclared/wrong declaration. Pixel observations without an accepted calibrated coordinate system cannot support court-coordinate quality metrics. |
| Basketball rows accurately declared as `image_px` and lack a court-calibration sidecar | Basketball string above | (ii) legitimate rejection | basketball 8/12 | The producer declaration is correct and the row itself records that calibration is absent; accepting it as court geometry would be wrong. |

No cause is classified as (i) producer defect or (iii) contract defect. The
contract is rejecting rows that explicitly say they are image pixels; the
required repair is to supply an accepted calibrated coordinate representation,
not to loosen the contract.

## Raw-row evidence

Each selected report basename joined exactly to one POD raw-table path under
`/workspace/nba-ai-system/data/tracking/<basename>/tracking_data.csv`: 66/66
baseball, 30/30 football, 15/15 soccer, and 8/8 basketball. All joined tables
are nonempty. Their raw row declarations were exhaustive, not sampled:

| Sport | Tables | Raw rows declaring `image_px` / raw rows | Coordinate columns populated |
|---|---:|---:|---|
| baseball | 66 | 2,015,136 / 2,015,136 | `x`, `y` |
| football | 30 | 1,664,073 / 1,664,073 | `x`, `y` |
| soccer | 15 | 1,197,323 / 1,197,323 | `x`, `y` |
| basketball | 8 | 32,355 / 32,355 | `x`, `y` |

Concrete quoted rows, one for each exact reason, are:

```json
{"calibration":"none","cls":"player","coordinate_space":"image_px","frame":"387","observation":"observed","track_id":"1","x":"151.15167236328125","y":"433.07464599609375"}
```

`/workspace/nba-ai-system/data/tracking/kbo_10/tracking_data.csv` (baseball).

```json
{"calibration":"none","cls":"player","coordinate_space":"image_px","frame":"18","observation":"observed","track_id":"1","x":"148.71600341796875","y":"172.493896484375"}
```

`/workspace/nba-ai-system/data/tracking/football_20pezoC5jRQ/tracking_data.csv` (football).

```json
{"calibration":"none","cls":"player","coordinate_space":"image_px","frame":"0","observation":"observed","track_id":"1","x":"202.11404418945312","y":"294.88067626953125"}
```

`/workspace/nba-ai-system/data/tracking/soccer_6dIn3fUfI6U/tracking_data.csv` (soccer).

```json
{"calibration":"none","cls":"player","coordinate_calibration_reason":"no_court_calibration_sidecar","coordinate_space":"image_px","frame":"90","observation":"observed","track_id":"1","x":"2582","y":"1251"}
```

`/workspace/nba-ai-system/data/tracking/ncaa_basketball_IB-_u4gW3ds/tracking_data.csv`
(basketball).

These rows are concrete evidence for the legitimate-rejection assignments:
they are observed player rows, their producers label them `image_px`, and the
basketball row expressly says `calibration=none` and
`no_court_calibration_sidecar`.

## The decision-relevant counterfactual

**119 of 119 would be scorable if their sole named coordinate cause were
actually fixed**: 66 baseball + 30 football + 15 soccer + 8 basketball. Here
"fixed" means the producer supplies an accepted calibrated coordinate space or
equivalent persisted anchor, not that the contract is weakened to accept raw
image pixels. The result means those 119 would reach the quality scorer; it
does not predict that they would pass coverage, out-of-bounds, jump, or
ball-valid checks.

## Reproduction procedure

On the POD, read the exact report glob above, parse each JSON object, and first
run `Counter(str(reason) for report in reports for reason in report["failures"])`.
Then select only reports satisfying both
`len(report["failures"]) == 1` and
`report["failures"][0].startswith("coordinate_contract:")`; group by the full
unmodified string and `sport`. Join each selected report stem to the raw-table
glob `/workspace/nba-ai-system/data/tracking/*/tracking_data.csv`, then count
`coordinate_space` across all rows. These commands read files only; no POD
artifact was created.

## Verifier self-check: section B

- B1: The initial 187-report failure enumeration included every report and
  every failure before selecting the named contract-only population.
- B2: No schema, field, status, or reader changed.
- B3: No gate or absent-evidence behavior changed.
- B4: No claim or failure path changed.
- B5: No POD copy, deploy, restart, or other pre-verification action occurred.
- B6: No module moved or retired.
- B7: No render or head-slice evidence is used; every report/table in scope was
  enumerated.
- B8: No fitted model or residual is presented as independent evidence.
- B9: Denominators are distinct JSON report files under the stated live glob;
  raw-row counts are separately identified and are not substituted for reports.
- B10: No harness threshold or gate value changed.

## Evidence-path self-check: A7

At memo time, the committed evidence artifacts are this memo,
`docs/evidence/tracking/specs/G47_spec.md`, and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. The quoted POD measurement
locations were checked read-only during the census; they are live POD paths,
not copied local evidence. Verify the three repository paths and re-run the
stated POD glob at verification time; a missing path is NOT VALIDATED.

## NOT VERIFIED

- No coordinate calibration was created, inferred, or replayed; therefore no
  post-repair quality score or pass/fail result is claimed.
- The live report corpus can change while POD services run; counts are the
  point-in-time snapshot measured for this memo.
- Tennis has no contract-only report in this snapshot (0/15), but this
  diagnosis does not determine its tracking quality.
- The historical 201-report `jump_p95` observation was not reproduced; the
  current exact report glob contains 187 such reports.
