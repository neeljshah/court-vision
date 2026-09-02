# G33B: DAY baseball scale-validation failure bins, attempt 2

Date: 2026-09-02. Worktree: `a9`. Log: `cx_g33b_baseball_scale_bins`.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section B (including
A7 evidence-path check).

Verdict: **NOT VALIDATED -- the named DAY clips are present on the pod, but the
required 30-segment source decision set cannot be reproduced.** This is a
source/decoder decision-set discrepancy, not the earlier local-footage gap.

**G36 gate answer: G36 does not proceed. Both current sources are 720p, but an
exact historic run produces 23 current failures rather than the specified 21,
so whether `resolution_360p` dominates the required 21-failure population
cannot yet be told at n=21, and no interval comparison is valid.**

## Reproduced premise

This prerequisite was calculated before frame work from the complete rows of
the two named source artifacts, without combining their populations.

| Population | Named artifact | Complete arithmetic | Result |
|---|---|---|---|
| DAY | `baseball_scale_validation_2026-09-01/summary.json` | `(7 + 2) / (19 + 11)` | **9/30 = 0.300; Wilson 95 percent [0.167, 0.479]** |
| NIGHT | `baseball_scale_validation_2026-09-01/night_stride20/summary.json` | `(0 + 0) / (1 + 5)` | **0/6 = 0.000; Wilson 95 percent [0.000, 0.390]** |

NIGHT was not analysed. It remains CLOSED AT LIMIT under G11.

## Pre-count bin definitions

Before counting a DAY outcome, each target segment was to be placed at its
earliest applicable stage:

1. `resolution_360p`: source height is 360 pixels or less. This is the
   pre-detector input-fidelity stage.
2. `no_pitch_view`: no frame before the next detected cut passes the unchanged
   pitch-geometry detector, so the candidate cannot reach scale validation.
3. `rubber_unavailable`: pitch geometry is accepted, but every frame in the
   segment lacks a pitching-rubber landmark.
4. `scale_disagreement`: at least one usable rubber is found, but no
   same-frame rubber/chord pair passes the unchanged 10 percent agreement rule.
5. `other_validation`: none of the prior stages applies but the segment is
   unvalidated; each member would be individually described.

The ordered stages are mutually exclusive, and `other_validation` makes them
collectively exhaustive. The 2026-09-01 published segmenter begins a segment
only after pitch geometry is accepted, so `no_pitch_view` is expected to be
empty for its published segment population; it remains explicitly defined.

## Pod footage and read-only reproduction

The inventory names the required DAY sources as:

- `mlb__mlb_2iosUkpL0Bc.mp4`
- `mlb__mlb_ARtRmUHC7dw.mp4`

Both are present at
`/workspace/nba-ai-system/data/footage_corpus/` on the pod (148,216,834 and
125,624,139 bytes, respectively). No claim of absent footage is made.

The first read-only pod enumeration used the current geometry module and
created 32 segments, so it was not used for a bin count. The pod geometry file
has a different digest from the 2026-09-01 historic geometry. A second
read-only run supplied only the historic green-precondition geometry function
transiently over standard input; it created no pod file. Its field-mask,
segmenter, landmark detector, scale gate, source frame limit (600), stride (3),
and 10 percent tolerance matched the historic implementation. It also produced
32 segments. No file was copied with scp, deployed, stored, deleted, or changed
on the pod.

| Clip | Retained DAY artifact | Exact historic-function pod run | Consequence |
|---|---:|---:|---|
| `mlb_2iosUkpL0Bc` | 19 segments, 7 validated | 19 segments, 7 validated | Reproduces. |
| `mlb_ARtRmUHC7dw` | 11 segments, 2 validated | 13 segments, 2 validated | Does not reproduce. |
| DAY total | 30 segments, 9 validated, 21 failures | 32 segments, 9 validated, 23 failures | The target population is not reconstructible. |

The two added current-run failures cannot be identified as members or
non-members of the retained 21 without an excluded-set rule. Excluding them
would be circular. Accordingly, the current 23 is a reproduction diagnostic,
not the requested metric.

## Binning and eye check

No 21-segment bin distribution is reported. Binning the 23 current-run
failures would change both the stated denominator and the historical segment
definition in practice, so it would not answer G33B.

No renders were made or committed. The mandatory eye check is therefore **not
performed**, rather than being claimed from the invalid 23-segment set or from
historic head overlays.

## NOT VERIFIED

- The exhaustive five-bin distribution over the retained 21 DAY failures.
- A Wilson interval for each required bin over denominator 21.
- Whether any bin dominates the retained decision set, including
  `resolution_360p`.
- The mandatory two rendered and viewed segments per non-empty bin.
- An individual explanation for any `other_validation` segment.
- Equivalence of the pod's current source/decode population to the
  2026-09-01 measurement population.
- No code was added, so no new per-file test applies.

## Verifier contract self-check

| Requirement | Self-check |
|---|---|
| A7 evidence paths | Clear. This memo, the two named summaries, G53 provenance, and the corpus inventory exist at verification time. No nonexistent render path is cited as evidence. |
| B1 circular metric | Clear. The 23-current-failure diagnostic is explicitly excluded from the 21-failure metric; no rows were silently excluded. |
| B2 non-additive schema | Clear. No code, schema, field, status, or reader changed. |
| B3 fall-through loss | Clear. No gate or quarantine behavior changed. |
| B4 re-claim loop | Clear. No claim or failure behavior changed. |
| B5 pre-verification deploy | Clear. Pod frame work was read-only and transient; no source or file was deployed. |
| B6 orphans | Clear. No module, import, test, or command reference moved. |
| B7 head-slice evidence | Clear. No historic overlay or current render is used as bin evidence. |
| B8 self-fit as independent | Clear. No model or fitted residual is reported. |
| B9 degenerate denominator | Clear. The required denominator is named as the complete 21 artifact failures; the incompatible 23 is only a diagnostic. |
| B10 moved bar | Clear. The historic 600-frame limit, stride 3, segment semantics, same-row rule, rubber constant, 10 percent tolerance, G11 verdict, and all thresholds remain unchanged. |
