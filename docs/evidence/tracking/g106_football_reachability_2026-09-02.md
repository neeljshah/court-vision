# G106 football reachability census

**Verdict: CLOSED AT LIMIT.** This is an additive eye-check census, not a
solver or coordinate-contract change. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the B1-B10
self-check below, and uses the same fixed-sample approach as
[`g95_football_calibration_survey_2026-09-02.md`](g95_football_calibration_survey_2026-09-02.md),
[`g91_soccer_landmarks_2026-09-02.md`](g91_soccer_landmarks_2026-09-02.md),
and [`g101_soccer_reachable_solve_2026-09-02.md`](g101_soccer_reachable_solve_2026-09-02.md).

## Fixed sample, exclusion, and method

This reuses G95's `seed = 95002` manifest unchanged: 12 sorted unique frames
from the interior 90 percent of each of nine clips, for **108 unique frames**.
No frame, seed, threshold, coordinate contract, or existing verdict changed.

G95's eye check established that four football-labelled clips are soccer, so
they are excluded from football-only headline metrics but remain named and
auditable in the full fixed sample:

- `football__football_34GmmlakBYU.mp4`
- `football__football_B7znSVfBnM4.mp4`
- `football__football_gek9fXGlwas.mp4`
- `football__football_h-_3BmAh9po.mp4`

They account for 48/108 frames. The football-only denominator is therefore
**60 unique `(clip_ordinal, frame)` pairs in five clips**; the census contains
exactly those 60 G95 rows, with no post-viewing exclusion. Re-review found no
fifth mislabelled clip, so there is no additional corpus-content evidence to
send to G99.

The per-frame labels, exact field definitions, and conservative point rule are
committed in [`g106_football_reach/frame_census.csv`](g106_football_reach/frame_census.csv)
and [`g106_football_reach/label_protocol.md`](g106_football_reach/label_protocol.md).
Every reviewed frame is in a committed G95 contact sheet, indexed in
[`g106_football_reach/renders.md`](g106_football_reach/renders.md). The renders
span all three time-distributed groups of each retained clip, not a head slice.

## Recomputed football-only result

| Per-frame metric | Frames / 60 | Share |
|---|---:|---:|
| No named visible line family | 32 | 53.33% |
| Two named families: yard stripes plus hash marks | 11 | 18.33% |
| Three named families: stripes, hashes, and a sideline | 15 | 25.00% |
| Four named families: stripes, hashes, sideline, goal line | 2 | 3.33% |
| One independent direction | 11 | 18.33% |
| Two independent directions | 17 | 28.33% |
| More than two independent directions | 0 | 0.00% |
| At least one identifiable point feature (conservative lower bound) | 28 | 46.67% |
| Legible painted yard number | 18 | 30.00% |
| G95-valid absolute-yard anchor | 0 | 0.00% |

The first four rows show why raw visible paint is encouraging but not a solve
condition. Yard stripes, hash marks, goal lines, and end lines are all
crossfield. Sidelines are the sole lengthwise family. Thus the maximum is two
directions even in the 17 wide broadcast views that have both; no reviewed
football frame has a third independent field direction.

The point lower bound is 92 visible point instances across the 60 frames:
64 visibly traceable yard-stripe/sideline intersections and at least one
individually identifiable hash mark in each of 28 frames. There are zero
visible goal-line/end-line corners and zero pylons under the protocol. These
are geometric pixel points, not named absolute field correspondences.

For audit against the unfiltered G95 survey, the numerators stay the same but
the denominator is 108: stripes or hashes are visible in 28/108 (25.93%), a
legible number in 18/108 (16.67%), and the four soccer clips are the named
48/108 exclusion. The football-only restatement is 28/60 for stripes or hashes
and 18/60 for legible numbers. G95 had not counted independent directions;
G106 measures them as 0, 1, or 2 rather than treating repeated stripes as
independent constraints.

## Degeneracy and aliasing decision

Repeated five-yard stripes can make a numerically tidy but periodically
ambiguous fit: translating by a whole number of yards can preserve stripe
residuals. Hash marks do not add a third direction, and the 18 legible painted
numbers are not G95-valid absolute anchors because this corpus supplies no
readable directional-arrow plus independent field-level/scale proof. The
existing football geometry path deliberately requires those conditions before
it will name an absolute yard correspondence.

**One-sentence answer:** Football `court_feet` is not reachable from this
football-only broadcast corpus: only 17/60 wide broadcast frames expose its
maximum two independent directions, none exposes a third, and 0/60 supplies a
G95-valid absolute-yard anchor to resolve periodic stripe aliasing.

## NOT VERIFIED

- No football homography, calibration, named-landmark registry entry,
  coordinate space, `court_feet` output, or detector was created or changed.
- No absolute yard identity, NFL/NCAA field level, asymmetric hash-row scale,
  directional-arrow reading, or transform accuracy was established.
- No fitted residual, held-out distance error, tracking-quality score, or
  solver success rate was measured.
- The conservative visible-point lower bound is not a claim that a detector can
  recover those marks or that the marks identify their field coordinates.
- No pod file, deployment, process, threshold, feature flag, or production
  reader was changed.

## Verifier self-check

### A7 evidence paths

At memo time, the following all exist: this memo; the G106 spec; the verifier
contract; G95, G91, and G101 memos; G95's `sample_manifest.json` and
`labels.csv`; G106's protocol, 60-row census, and render index; and every one
of the 15 G95 contact sheets named by the render index and census rows. The
census recomputation found 60 rows, 60 unique pairs, zero difference from the
G95 football-labelled row set, and zero missing source-render paths. A missing
named evidence path would make this result NOT VALIDATED.

### Section B

- **B1:** The football-only metric excludes exactly the four named soccer
  clips before counting geometry; it retains every one of the resulting 60 G95
  football frames, including zero-line and zero-point frames. The full 108
  denominator is also reported for audit.
- **B2:** No schema, existing field, status, or reader changed. The CSV and
  markdown files are additive evidence only.
- **B3:** No gate behavior changed; absent paint remains a measured zero, not
  a quarantine action.
- **B4:** No claim, queue, or retry path changed.
- **B5:** The pod was read-only. No source file was copied to it and no
  deployment, restart, or process action occurred.
- **B6:** No module was moved or retired, so no test/import/module reference
  can be orphaned.
- **B7:** The fixed seeded G95 decision set covers the interior 90 percent of
  every clip; all retained contact-sheet frames were reviewed, not head slices.
- **B8:** This is an eye-labelled visibility census. It presents no fit,
  residual, or self-fit validation.
- **B9:** Each unit is one unique `(clip_ordinal, frame)` pair; recomputation
  confirms 60 rows and 60 unique pairs.
- **B10:** No harness threshold, gate value, seed, coordinate contract, or
  existing verdict was changed.
