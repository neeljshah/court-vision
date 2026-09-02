# G88: modal-stride-adjacent `jump_max` implementation

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including A7 and section B. This implements the accepted G82 decision without
changing a bar, coordinate contract, or production deployment.

## Implementation

`scripts/platformkit/tracking_harness.py` now computes `jump_max`, the maximum
Euclidean player displacement among only the row pairs whose positive frame gap
equals the table's unique modal positive frame gap. Rows are sorted by
`track_id, frame`; `groupby(frame).diff()` supplies the per-pair gap; zero and
negative gaps do not participate in selecting a stride. The unique gap with
the greatest count is the modal stride. Every pair at any other gap is excluded
from this statistic, including a 200-frame reappearance.

If two or more positive gaps tie for greatest count, there is no clear modal
stride. The harness does not resolve that tie arbitrarily: `jump_max` and
`jump_max_modal_stride_frames` are null and the normal report is an explicit
`jump_max unmeasurable` failure. No input is dropped or quarantined.

The gated bar values are byte-for-byte unchanged: basketball 6.0 ft, tennis,
soccer, and football 8.0 ft, and baseball-family 10.0 ft. `jump_max_max` holds
those same values for the new statistic; `jump_p95_max` remains as a
compatibility key at the same values and is no longer read by the harness gate.

## Naming and reader decision

This is additive, not a semantic rename. `jump_max` is the only new gated
reported number and is never called `jump_p95`. The existing `jump_p95` field
continues to contain the literal raw consecutive-row p95, and
`jump_p95_ft_per_s` continues to be a p95-derived informational field. They are
deprecated as gate metrics but retained so existing report JSON readers and
historical artifacts do not receive a max under a p95 name. The full grep
survey and disposition are in
`docs/evidence/tracking/g88_jump_statistic_impl/reader_survey.csv`.

Metric-local reports declare the added spatial `jump_max` field
`not_applicable`, matching the existing spatial-field contract.

## Re-measured verdict impact

The implementation was replayed over 12 existing retained tracking tables,
not G82's proposal result. The complete paired result is in
`docs/evidence/tracking/g88_jump_statistic_impl/verdict_impact.csv`:

- PASS to FAIL: 0
- FAIL to PASS: 0

Ten basketball production tables remain coordinate-contract FAILs because they
have no persisted court-calibration sidecar; they do not exercise either jump
statistic. `0022501165` likewise remains that full-verdict FAIL, while a
quality-only calculation using this implementation's modal-stride helper gives
3-frame mode, 30,376 eligible pairs, raw p95 2.160134 ft, and `jump_max`
10.207963 ft. The retained court-feet tennis table `G83_tennis_09` exercises
the full harness and remains PASS: raw p95 1.64 ft, modal stride 2, and
`jump_max` 2.32 ft.

All table paths and SHA-256s used for the replay are recorded in the paired
artifact. They are retained local sources under `data/tracking/` in the main
worktree; no source rows were edited.

## Constructed sensitivity

`docs/evidence/tracking/g88_jump_statistic_impl/sensitivity.csv` contains four
100-frame, 10-player, court-feet constructions with 990 modal-stride pairs.
At 1.010%, 3.030%, and 4.949% 40-ft teleports, the legacy p95 remains 0.02 ft
but the implemented `jump_max` is 40.02 ft and fails the unchanged 6.0-ft
basketball bar. The 6.061% row shows the expected p95 transition at 39.98 ft.
Thus the new statistic detects a 40-ft teleport well below the old roughly-6%
prevalence point.

The focused test is
`scripts/platformkit/test_tracking_harness_g88_jump_statistic.py`; it passed
with `python -m pytest scripts/platformkit/test_tracking_harness_g88_jump_statistic.py -q`.
It checks the unchanged bar, a low-prevalence teleport, an excluded 68-frame
reappearance, and the tied-mode behavior.

## Verifier self-check

- A7: every repository evidence path named above exists. The local raw source
  paths and their hashes are listed in `verdict_impact.csv`; each existed at
  measurement time.
- B1: the excluded set is named before scoring: all pairs whose frame gap is
  not the unique positive modal stride. It is a sampling-adjacency definition,
  not derived from displacement or failure status.
- B2: `jump_max` and its stride field are additive. `jump_p95` remains a real
  p95 compatibility field, and every grep-identified reader is surveyed.
- B3: ambiguous stride reports remain explicit ordinary harness failures; no
  report is silently discarded or made to pass.
- B4: the failure is attached to the report and does not alter claim routing.
- B5: no pod copy, deployment, or remote process was performed.
- B6: no module was moved or retired; one focused G88 test was added.
- B7: not applicable; this is a statistic replay with no visual sample claim.
- B8: no fitted parameter or self-fit comparison is presented.
- B9: the denominator is literal modal-stride player row pairs: 990 in each
  construction and 30,376 for the G82 basketball statistic replay.
- B10: all existing threshold values remain unchanged; the new config values
  equal their retained legacy counterparts.

## NOT VERIFIED

- The ten coordinate-contract basketball replays establish full-verdict impact
  but cannot validate a court-feet quality result until persisted calibration
  sidecars exist.
- No pod deployment was requested or performed; the verifier lands code on
  the pod after acceptance.
- No claim is made about a ft/s gate. G83 remains the separate owner of the
  sampling-interval work.
