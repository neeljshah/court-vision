# G33B: DAY baseball scale-validation failure bins

Date: 2026-09-02. Worktree: `a9`. Log: `cx_g33b_baseball_scale_bins`.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section B.

Verdict: **NOT VALIDATED -- the repaired premise reproduces, but the source
frames required for the exhaustive DAY-only binning and mandatory eye check are
no longer available locally or on the pod.**

**G36 gate: `resolution_360p` is 0 of 21 DAY failures (Wilson 95 percent
[0.000, 0.155]) from the retained source-dimension census, so it is not the
dominant bin; however, the required complete failure-bin distribution and eye
check cannot be reproduced, so this lane cannot release G36.**

## Pre-count declarations

This section was written before examining any per-segment failure outcome or
tally. The target population is exactly the 21 DAY segments that did not
validate in `docs/evidence/tracking/baseball_scale_validation_2026-09-01/summary.json`.
NIGHT is excluded: its separately measured 0/6 result is closed at limit under
G11.

Each failing segment is assigned to exactly one bin by evaluating these stages
in order and stopping at the first failed stage.  The unchanged 2026-09-01
segmenter only starts a segment after it has accepted pitch-view geometry; its
scale rule uses the chord and the pitching rubber.  Plate evidence is
diagnostic only and cannot cause a scale-validation failure.

1. **`resolution_360p`**: the source clip height is 360 pixels or lower. This
   input-fidelity check precedes every detection stage; if it applies, it is
   the first bin even if the segment also lacks later evidence.
2. **`no_pitch_view`**: `resolution_360p` does not apply, but the stored
   segment has no frame accepted by the unchanged pitch-view detector. Such a
   segment cannot reach scale estimation. (The 2026-09-01 segment definition
   should make this bin empty; retaining it makes the ordering explicit.)
3. **`rubber_unavailable`**: the segment reached pitch-view geometry but none
   of its pitch-view frames has a usable pitching-rubber landmark under the
   unchanged detector output.
4. **`scale_disagreement`**: a usable rubber landmark exists in one or more
   pitch-view frames, but no same-frame rubber/chord scale pair meets the
   unchanged agreement rule, so the segment is unvalidated.
5. **`other_validation`**: none of the four preceding first-stage conditions
   applies, but the segment remains unvalidated. Every member will be described
   individually in the completed memo.

These bins are mutually exclusive because a segment stops at its earliest
failed stage. They are collectively exhaustive because an unvalidated segment
either fails one of the four ordered stages or is retained in
`other_validation` for an explicitly described unchanged validation outcome.

## Reproduced premise

The complete named source populations were recomputed before any per-segment
work:

| Population | Arithmetic from named summary | Result |
|---|---|---|
| DAY | `(7 + 2) / (19 + 11)` from `summary.json` | **9/30 = 0.300; Wilson 95 percent [0.167, 0.479]** |
| NIGHT | `(0 + 0) / (1 + 5)` from `night_stride20/summary.json` | **0/6 = 0.000; Wilson 95 percent [0.000, 0.390]** |

NIGHT remains CLOSED AT LIMIT under G11 and was not analysed. These are
separate populations throughout this memo.

## Evidence availability and attempted reproduction

The retained `docs/evidence/tracking/gapfinder_2026-09-02/pod_corpus_census.json`
identifies both DAY clips as 1280x720. Therefore every one of the 21 DAY
failures belongs to a source taller than 360 pixels, giving the stated
`resolution_360p` count of 0/21. This does not identify the remaining first
failure stage for any segment.

The complete per-segment measurement cannot be reconstructed:

1. The local worktree has no `data/videos/bridge/mlb_2iosUkpL0Bc.mp4` or
   `data/videos/bridge/mlb_ARtRmUHC7dw.mp4`, and no detailed segment sidecar.
   It retains only four illustrative DAY rejection overlays.
2. A read-only standard-input probe on the pod at those historic paths opened
   neither file (both were 0x0 and processed zero frames).
3. A read-only exact-name search under the pod's persisted
   `/workspace/nba-ai-system/data` found neither source clip. No pod file was
   written, copied, deployed, restarted, or removed.

Without the source frames, the unchanged segmenter cannot be rerun to recover
all 21 first-failure outcomes, and overlays cannot be rendered. Counting from
the four illustrative overlays would be a head-slice measurement and would not
meet the denominator or eye-check requirements.

## Binning result

| Predeclared bin | Count / 21 | Wilson 95 percent | Status |
|---|---:|---:|---|
| `resolution_360p` | 0/21 | [0.000, 0.155] | Reproduced from the retained 720p source-dimension census. |
| `no_pitch_view` | not reproducible | not applicable | Requires the absent per-frame segmenter output. |
| `rubber_unavailable` | not reproducible | not applicable | Requires the absent per-frame landmark output. |
| `scale_disagreement` | not reproducible | not applicable | Requires the absent per-frame validation output. |
| `other_validation` | not reproducible | not applicable | Cannot be assessed until the preceding bins are reconstructed. |

No bin distribution is claimed. In particular, the zero count for the
cross-cutting 360p input property is not substituted for an exhaustive
first-failure classification.

## Eye check

**Not performed.** The two existing DAY rejection overlays per source are not
two rendered segments from every non-empty predeclared bin, and no additional
render can be made without the missing source clips. No render is committed
under `docs/evidence/tracking/g33b_renders/`; claiming otherwise would be
fabricated evidence.

## NOT VERIFIED

- The exhaustive 21-segment DAY failure-bin distribution.
- The Wilson intervals for every bin other than the source-dimension
  `resolution_360p` count.
- Two rendered and viewed segments from every non-empty bin.
- Any individual DAY segment's first-failure stage or an `other_validation`
  explanation.
- Whether another bin is dominant, or whether its interval separates from the
  next bin at n=21.
- The prerequisite for releasing G36 beyond the limited 360p source-dimension
  finding above.
- No code was added, so no new per-file test applied.

## Verifier contract B self-check

| Condition | Self-check |
|---|---|
| B1 circular metric | Clear. The only count, 0/21 for source height at most 360, covers every DAY failure and excludes none. No incomplete distribution is presented as a metric. |
| B2 non-additive schema | Clear. No code, field, status, schema, or reader changed. |
| B3 fall-through loss | Clear. No gate or quarantine behavior changed. |
| B4 re-claim loop | Clear. No claim or failure handling changed. |
| B5 pre-verification deploy | Clear. The pod interactions were read-only; no file was copied or deployed. |
| B6 orphans | Clear. No module, import, test, or command was moved or retired. |
| B7 head-slice evidence | Clear. The four illustrative overlays are explicitly not used as evidence; no sampled render supports a bin claim. |
| B8 self-fit as independent | Clear. No model, residual, or fitted result is reported. |
| B9 degenerate denominator | Clear. The sole reported denominator is the explicit complete set of 21 DAY failures; the complete distribution remains unverified. |
| B10 moved bar | Clear. No tolerance, same-row rule, rubber constant, segment definition, G11 verdict, or harness threshold changed. |
