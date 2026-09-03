# G134: grouping stability under G132's enlarged segment set

## Verdict

**ACCEPT.** The preregistered immutable-baseline grouping achieved the required
**25/25 baseline-match survival** on the frozen 30-frame, 68-visible-line
G115/G132 protocol. This is a candidate-grouping measurement only; it changes
no detector, calibration, coordinate contract, runtime caller, or solver.

## Instability distribution

Under G132's original single-pass enlarged grouping, the 25 baseline-matched
unique `(clip, frame_index, role)` lines classify as:

| outcome | count |
|---|---:|
| SURVIVED | 14 |
| MOVED | 0 |
| ABSORBED | 11 |
| FRAGMENTED | 0 |
| **total** | **25** |

The lost G132 line is
`ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p`, frame `11760`,
`lane_right`: **ABSORBED**. Baseline groups `4;24` matched its fixed hand
line; original enlarged grouping has no match; stable grouping retains `4;24`.
This agrees with G132's shifted closest replacement from
`[[258,225],[582,250]]` to `[[258,230],[582,251]]`.

Classifications are preregistered in
[`preregistration.json`](g134_grouping/preregistration.json): SURVIVED retains
the exact baseline segment membership; ABSORBED makes it a proper subset of an
enlarged group; FRAGMENTED distributes it across multiple groups; MOVED is the
otherwise-unexplained changed-fit fallback. Raw results are
[`line_outcomes.csv`](g134_grouping/line_outcomes.csv) and
[`outcome_distribution.csv`](g134_grouping/outcome_distribution.csv).

## Parameter semantics

The code states:

```python
cosine = float(np.cos(np.deg2rad(angle_deg)))
aligned = abs(float(np.dot(line[:2], reference[:2]))) >= cosine
same_offset = abs(line[2] - reference[2]) <= offset_px
if aligned and same_offset:
    group.append(segment)
```

Thus frozen `5.0` is `angle_deg`, the angular membership gate against the
first-segment group reference; frozen `10.0` is `offset_px`, the line-offset
membership gate. Neither is an outcome classifier: both govern membership, the
event that creates an ABSORBED group here. Fitting follows membership via
`cv2.fitLine`. Neither value changed.

## Preregistered proposal

Before scoring, the proposal fixed baseline candidate groups and fits by
calling `candidate_line_group_details(..., 5.0, 10.0)` on baseline proposals,
then grouped only G132-added proposals using the same call and appended those
supplementary groups. G132's existing baseline-first one-pixel endpoint
deduplication identifies additions. Baseline groups cannot be refit, merged,
replaced, or reordered; no acceptance parameter changes.

## Frozen remeasurement and G132 follow-on

| variant | recall | paired fixed-label precision | baseline-match survival |
|---|---:|---:|---:|
| baseline | 25/68 = 36.76% (Wilson [26.30%, 48.64%]) | 212/1,581 = 13.41% | 25/25 |
| original enlarged single-pass | 28/68 = 41.18% (Wilson [30.26%, 53.04%]) | 225/2,014 = 11.17% | 14/25 |
| stable enlarged grouping | 30/68 = 44.12% (Wilson [32.95%, 55.92%]) | 368/2,922 = 12.59% | **25/25** |

The stable row is the required G132 union follow-on: it uses G132's exact
enlarged proposal set and all frozen values, with only the preregistered stable
group boundary. Precision remains the G84 fixed-label transfer proxy, not a
new human labelling exercise.

## Eye check

All 11 affected-line side-by-side baseline/enlarged renders are in
[`g134_grouping/renders/`](g134_grouping/renders/). I reviewed evenly spaced
lexical positions 1, 3, 5, 7, 9, and 11, spanning NCAA and WNBA:

- `...IB-_u4gW3ds_1080p__f11760__baseline.jpg`
- `...IB-_u4gW3ds_1080p__f11760__lane_right.jpg`
- `...IB-_u4gW3ds__f19200__free_throw.jpg`
- `...sRtHQbywiTE__f5760__lane_right.jpg`
- `...wnba_01_1080p__f12720__free_throw.jpg`
- `...wnba_01__f13632__lane_right.jpg`

Each shows the fixed red hand line and changed gray enlarged candidate support,
consistent with ABSORBED classification. This is not a head slice.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --rebuild
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g134_grouping_stability --write
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g134_grouping_stability.py -q
```

The documented rebuild reads pod frames only and writes local reconstructed
tiles. The sole new focused test passed: `1 passed in 0.59s`.

## Verifier-contract self-check

- A2: independent CSV recomputation gave 120 unique role rows, 68 visible
  rows, recall 25/68, 28/68, and 30/68, survival 25/25, and unique candidate
  transfers 212/1,581, 225/2,014, and 368/2,922.
- A3: reviewed positions 1, 3, 5, 7, 9, and 11 over all 11 affected renders.
- A4: role, visible-role, baseline-match, and candidate units are unique.
- A5: isolated additions only; no pre-existing reader, schema, caller, or
  detector module changed.
- A7: every memo-named G134 evidence path exists, including preregistration,
  CSV artifacts, and all 11 renders.
- B1: all 68 frozen visible roles remain; none was post-score excluded.
- B2-B6: no existing schema, reader, gate, lifecycle, deployment, pod file,
  module, import, caller, or flag changed.
- B7: render inspection spans the full affected decision set.
- B8: preregistration fixed the proposal before scoring; no result selected a
  threshold.
- B9: recall/survival use unique roles; precision uses unique candidates.
- B10: detector `28.0`, grouping `5.0/10.0`, correspondence, calibration,
  manifest, seed, labels, thresholds, and coordinate contract are untouched.

## Not verified

- Generalization beyond the frozen 30-frame, 68-visible-line set.
- Fresh human labels for stable candidates; precision is the G84 transfer proxy.
- Detector, acceptance, calibration, homography, court-solve, runtime,
  deployment, or feature-flag changes.
