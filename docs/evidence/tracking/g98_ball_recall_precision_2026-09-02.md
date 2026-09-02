# G98 - Tennis Ball Recall and Precision (2026-09-02)

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), section A including
A7 and section B. Assignment: [G98_spec.md](specs/G98_spec.md). Prior
calibration: [G92](g92_ball_criterion_calibration_2026-09-02.md). Prior
spatial-gate stop: [G44B](g44b_ball_spatial_gate_2026-09-02.md).

## Verdict

**NOT VALIDATED - Step 0 falsified the measurement premise.** No ball recall,
precision, tolerance, tracker denominator, Wilson interval, or metric render
is reported. This is the required stop result, not a zero-valued tracker
measurement.

## Step 0 - did the calibration change any decision?

It did not. The complete comparison in
[step0_identity_check.md](g98_ball_metrics/step0_identity_check.md) joins all
109 G92 calibrated rows to the three prior G78 resolved chunks by canonical
`(clip, source_frame)` identity:

| Clip | Joined decisions | Label changed under card |
|---|---:|---:|
| `tennis_09` | 32 | 0 |
| `tennis_10` | 47 | 0 |
| `nyYk_720p` | 30 | 0 |
| **Pooled** | **109** | **0** |

G92's 45/60 agreement with the fixed G85 blind labels is likewise the exact
same agreement set as before calibration, not merely the same count: all 60
blind rows join; 45 frames agree under both label sets; 0 frames are old-only
agreements and 0 are new-only agreements. Per clip, the old/new agreement is
12/20 for `tennis_09`, 14/20 for `tennis_10`, and 19/20 for `nyYk_720p`.

The exemplar card therefore did not do the job its changed-decision check was
meant to establish. Measuring detector recall or precision against an
unchanged, still-contested decision set would build on an unverified premise,
which G98 expressly prohibits. The measured 75.0% label agreement (Wilson
95% CI 62.8% to 84.2%) remains a constraint on any future result, but it is
not used to decorate a tracker metric here because no tracker metric is
validly available.

## Measurement intentionally not performed

- **Tolerance:** not preregistered or selected. Selecting one after entering a
  failed premise would create an unusable measurement artifact.
- **Recall:** not computed. The expected positive count remains 110/150 from
  G92, but this row did not reach a valid measurement entry condition.
- **Precision:** not computed. No tracker ball-row denominator was queried.
- **Per-clip and pooled metrics:** not computed. Consequently there are no
  Wilson intervals, and no pooled result can be mistaken as describing one
  dominant clip.
- **Eye check:** not applicable. The required bidirectional disagreement
  renders distinguish tracker versus label errors only after valid tracker
  comparisons exist; rendering them now would imply a measurement that this
  stop result rejects.
- **Y-gate:** untouched. The unresolved 78% versus 52% y-gate disagreement
  remains outside this row.

## Required next condition

Do not retry this metric merely by rerunning the tracker. A successor must
first demonstrate a material, reviewable decision change under a genuinely
sharpened criterion or obtain an independently adjudicated label set. It must
then carry the observed label disagreement into every metric claim and retain
the immutable G65/G78/G85/G92 sources.

## VERIFIER_CONTRACT section A and A7

- **A1:** No executable code or test was added. There is no per-file test to
  rerun; this evidence-only stop is recomputed from durable CSV inputs.
- **A2:** Recomputed the full 109-row old/calibrated join and the full 60-row
  old/new blind-agreement join. Both reproduce the counts above.
- **A3:** No metric renders exist because Step 0 barred metric measurement.
  The premise comparison itself covers the complete 109-row decision set and
  every 60-row blind decision, not a head slice.
- **A4:** The comparison has 109 unique `(clip, source_frame)` label
  identities; the blind comparison has 60 unique identities, all joined.
- **A5:** No field, schema, reader, or production code changed.
- **A6:** The lane commit uses only explicit G98 evidence paths. The required
  verifier landing action is performed after the commit, without deployment.
- **A7:** Every evidence path named by this memo exists at verification time:
  `VERIFIER_CONTRACT.md`, `specs/G98_spec.md`,
  `g92_ball_criterion_calibration_2026-09-02.md`,
  `g44b_ball_spatial_gate_2026-09-02.md`,
  `g98_ball_metrics/step0_identity_check.md`,
  `g65_ball_labels/resolved/`,
  `g92_criterion/calibrated_labels.csv`, and
  `g85_consistency/blind_labels.csv`.

## Section B self-check

- **B1:** No metric or label row was excluded: the premise comparison includes
  all 109 calibrated rows and all 60 blind rows. No recall or precision claim
  was made from a subset.
- **B2:** No schema, status, field, or reader changed.
- **B3:** No gate was changed or caused absent evidence to quarantine.
- **B4:** No claim path was added or changed.
- **B5:** Nothing was copied to, deployed on, or run on the pod.
- **B6:** No module, test, import, or command reference was moved or retired.
- **B7:** The evidence is the entire decision set, rather than a head-slice;
  no tracker-render selection was represented as an eye check.
- **B8:** No tolerance, detector rule, or residual was fit or scored. The
  unchanged-label finding compares add-only artifacts, not a self-fit metric.
- **B9:** Counts are unique frame decisions, not recycled identifiers.
- **B10:** No harness threshold, y-gate, coordinate contract, or feature flag
  changed.

## NOT VERIFIED

- Tennis-ball recall or precision, per clip or pooled.
- Any spatial tolerance or Wilson interval for tracker performance.
- Whether any tracker disagreement is a tracker error or a label error.
- A resolution of the 78% versus 52% y-gate discrepancy.
- Any production tracking quality, gate change, detector improvement, or
  downstream teacher eligibility.
