# G38B: labelled tennis jump-cause join, attempt 2

Date: 2026-09-02. Gap: G38B. Contract: \`VERIFIER_CONTRACT.md\`, including A7
and section B. This is read-only. No selector, solver, camera lock, coordinate
contract, harness threshold, or tracking code changed.

**Verdict: NOT VALIDATED.** The requested endpoint-label metric has no
constructible denominator. G66 supplies 210 render-labelled candidate boxes, but
the exact labelled clips have zero retained selected-player tracking tables locally
and on the pod. A candidate box is not a selected endpoint. There are therefore
zero observed stride-adjacent >8 ft selected-player jump pairs to join; this memo
does not substitute a candidate proxy for that metric.

## Premise reproduction and provenance

G38 used \`tennis_02\` through \`tennis_05\`; G66 labels \`tennis_09\`,
\`tennis_10\`, and \`tennis_nyYk2nPZAwY_720p\`. There is no clip overlap.

The original G38 raw tracking tables are absent locally and on the pod. Thus the
G38 quantiles, distance-band concentration, and stride-adjacent counts cannot be
recomputed from rows. The pre-G59 pod summary reports still exist and reproduce
the stored frozen harness values, but their source frame rate is null and they
contain no G48 sampling block. They are historical report values only, not a new
row-level reproduction.

| G38 clip | report written UTC | stored frozen jump_p95 (ft) | G48 interval | speed |
|---|---|---:|---|---|
| tennis_02 | 2026-09-01 06:48 | 22.13 | absent | unavailable |
| tennis_03 | 2026-09-01 07:30 | 34.36 | absent | unavailable |
| tennis_04 | 2026-09-01 07:31 | 10.03 | absent | unavailable |
| tennis_05 | 2026-09-01 07:39 | 36.79 | absent | unavailable |

The reports predate the G59 rejected-code deployment and its 2026-09-02
remediation. No post-G59 raw table exists for the four G38 clips, so no
post-remediation corpus was substituted. The G38 10-29 ft concentration and
speed signature are **NOT VERIFIED from retained rows** in this attempt.

## Exact labelled clips and speed observations

| exact G66 clip | labels | local selected tables | pod selected tables | joinable endpoints |
|---|---:|---:|---:|---:|
| tennis_09 | 70 | 0 | 0 | 0 |
| tennis_10 | 70 | 0 | 0 | 0 |
| tennis_nyYk2nPZAwY_720p | 70 | 0 | 0 | 0 |
| total | 210 | 0 | 0 | **0** |

Only summary reports remain. Where a G48-style sampling interval exists, jumps
are expressed as speed:

| report identity | relationship to G66 | interval (s) | jump_p95 speed (ft/s) | signature |
|---|---|---:|---:|---|
| tennis_09 | exact clip; only 2 report frames, no selected rows | 0.0800 | 19.13 | not present |
| tennis_10 | exact clip; empty report, no selected rows | 0.0834 | 0.00 | not observed |
| tennis_nyYk2nPZAwY | 360p sibling, not joinable to 720p labels | 0.0800 | 239.00 | sibling only |

At 0.0800 s, the historical 10-29 ft band is 125.00-362.50 ft/s. The 360p
nyYk sibling's 239.00 ft/s p95 lies in that speed band. It is not evidence
about endpoints on the labelled 720p clip. The exact 720p labelled clip has no
selected rows or interval-bearing report, so its signature is **NOT MEASURED**.

The endpoint join rate is not a percentage: retained labels = 210 distinct
candidate rows; retained selected endpoints = 0; retained stride-adjacent >8 ft
selected-player pairs = 0; joined endpoints = 0. The endpoint-label fraction
and its Wilson interval are not computable.

## G66 candidate-level split

G66 remains candidate-level evidence, not endpoint evidence:

| label | count / 210 | share | 95 percent Wilson interval |
|---|---:|---:|---|
| player | 51 | 24.3% | [19.0%, 30.5%] |
| non_player_person | 155 | 73.8% | [67.5%, 79.3%] |
| uncertain | 4 | 1.9% | [0.7%, 4.8%] |
| duplicate_of_player | 0 | 0.0% | [0.0%, 1.8%] |
| not_a_person | 0 | 0.0% | [0.0%, 1.8%] |

It establishes a sample dominated by other people, not duplicate detections or
non-person detections. The proxy-positive stratum and summary p95 do not reveal
which candidate was selected, so neither is used as an endpoint surrogate.

## Mandatory eye check

Using \`random.Random(20260902).sample\`, I selected four rows each from
\`player\`, \`non_player_person\`, and \`uncertain\`, and reviewed all 12
source-frame-plus-crop renders. This is category-balanced, not a head slice.
These are candidates, not jump partners.

| sample | stored label | render observation |
|---|---|---|
| G66_010 | non_player_person | courtside person behind left advertising |
| G66_035 | non_player_person | ball kid or staff by umpire chair |
| G66_074 | player | on-court tennis player |
| G66_100 | player | on-court tennis player |
| G66_175 | player | appears courtside official, not match player; label unchanged |
| G66_183 | non_player_person | kneeling ball kid at left sideline |
| G66_188 | uncertain | top-edge broadcast clock obscures candidate |
| G66_191 | uncertain | top-edge broadcast clock obscures candidate |
| G66_192 | uncertain | top-edge broadcast clock obscures candidate |
| G66_193 | uncertain | top-edge broadcast clock obscures candidate |
| G66_196 | non_player_person | seated chair official |
| G66_199 | player | on-court tennis player |

Eleven calls agree with the stored label. G66_175 is one visual disagreement.
This does not relabel G66, recalculate its split, or reopen the empty duplicate
and not-a-person branches.

## Verifier self-check

- A7: all local paths below exist at memo time. Pod reports were read in place
  and are explicitly pod-only; they do not support the endpoint metric.
- B1: no endpoint row was excluded; no endpoint metric is scored because its
  named input is absent.
- B2-B4: no schema, reader, gate, or claim path changed.
- B5: pod use was read-only; no deployment, copy, restart, or removal occurred.
- B6: no module moved or retired.
- B7: 12 visual samples are seed-selected and category-balanced.
- B8: no fit or self-fit is claimed.
- B9: the 210 candidates are distinct candidate CSV rows; no track id is used
  as a denominator.
- B10: the frozen 8.0 ft bar and all named mechanisms are unchanged.

## Evidence paths

- docs/evidence/tracking/VERIFIER_CONTRACT.md
- docs/evidence/tracking/g38_tennis_jump_diagnosis_2026-09-02.md
- docs/evidence/tracking/g48_sampling_interval_2026-09-02.md
- docs/evidence/tracking/g66_player_candidate_labels_2026-09-02.md
- docs/evidence/tracking/g66_player_candidate_labels/labels.csv
- docs/evidence/tracking/g66_player_candidate_labels/label_summary.json
- docs/evidence/tracking/g66_player_candidate_labels/sampling.json
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_010.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_035.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_074.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_100.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_175.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_183.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_188.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_191.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_192.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_193.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_196.jpg
- docs/evidence/tracking/g66_player_candidate_labels/renders/G66_199.jpg
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_02.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_03.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_04.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_05.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_09.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_10.json
- pod-only, checked read-only: /workspace/nba-ai-system/data/tracking_reports/tennis/tennis_nyYk2nPZAwY.json

## NOT VERIFIED

- No original G38 tracking table survives to reproduce its quantile,
  stride-adjacent count, or 10-29 ft concentration from rows.
- No exact G66 clip has a selected-player tracking table, so the endpoint-label
  fraction, join rate, and Wilson interval cannot be computed.
- The nyYk 360p speed signature is sibling-only and must not be assigned to the
  720p labels.
- The G66 split is not re-adjudicated; one of 12 independent visual calls
  disagreed with its stored label.
