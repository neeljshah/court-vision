# G121 basketball paint-corner pixel targets

**Verdict: NOT VALIDATED.** This was a ground-truth labelling pass, not a
detector evaluation. It stopped before recording an invented coordinate when
the unchanged G111 visibility labels and their committed source renders
disagreed.

## Fixed subset stated before labelling

The intended subset is the 33 G111 manifest rows at slots `0`, `10`, and `15`
from each of the 11 clips. These are existing draws from G111's fixed global
seed `1112026`; no new frame sample or visibility census was made. The three
positions give one early, one middle, and one late temporal stratum from each
clip. The unchanged G111 labels yield 104 named corner-role rows in that
subset, which would have been a usable role denominator without labelling all
220 source frames. The exact selection is committed in
[`g121_corner_targets/subset_manifest.csv`](g121_corner_targets/subset_manifest.csv).

## Blocking eye check

Before placing any coordinate, I opened the committed source renders at native
resolution. At least these selected rows carry all four G111 paint-corner roles
but do not show a discernible paint intersection to place by eye:

- `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss`, frame `12806`, slot `10`:
  a mid-court view; neither paint rectangle is in the image.
- `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss`, frame `18924`, slot `15`:
  a player close-up with no paint rectangle.

The source frames are committed under
[`g121_corner_targets/renders/`](g121_corner_targets/renders/). Recording an
`x,y` for either case would be an extrapolation from information absent from
the source, not a pixel target by eye. It would also manufacture the ground
truth that G119 is required not to infer from its own proposals.
The two inspected blocker frames carry that finding as overlays in
[`g121_corner_targets/blocker_renders/`](g121_corner_targets/blocker_renders/).

## Committed artifact and result

[`g121_corner_targets/corner_pixel_targets.csv`](g121_corner_targets/corner_pixel_targets.csv)
retains all 104 G111 role keys, with empty coordinate fields and an explicit
`not_attempted_after_blocker` status. It is deliberately not a partial target
set presented as a complete denominator. The machine-readable summary is in
[`g121_corner_targets/summary.json`](g121_corner_targets/summary.json).

| Metric | Result |
|---|---:|
| Fixed G111 subset frames | 33 |
| G111 visible corner-role rows in subset | 104 |
| Committed pixel targets | 0 |
| Blind re-label rows | 0 |
| Median / p90 self-agreement displacement | NOT MEASURED: no first-pass targets |

No second pass was performed: a displacement computed after selecting arbitrary
positions would be a measure of repeated fabrication rather than annotation
precision. No detector, proposal scorer, recall computation, tolerance change,
or calibration action was run.

## Decision

G121 cannot supply G119 targets from the current G111 labels without silently
overriding their visibility claim. A subsequent row must first resolve the
G111 visibility/source-render mismatch with a separately specified audit;
this row does not relabel G111 or change its seed, manifest, labels, roles, or
coordinate contract.

## NOT VERIFIED

- Any pixel coordinate, self-agreement displacement, detector recall, role
  assignment, or G119 comparison.
- Any homography, `court_feet` declaration, line-calibration change,
  threshold change, downstream tracking behavior, pod write, or deployment.
- Whether the conflict is a G111 labelling error, a source-render association
  error, or another upstream provenance issue.

## Verifier self-check

- **A7:** every evidence path named above exists at report time: this memo,
  `g121_corner_targets/subset_manifest.csv`, `corner_pixel_targets.csv`,
  `summary.json`, the 33-file `renders/` directory, and the two-file
  `blocker_renders/` directory.
- **B1 circular metric:** clear. No detector output, successful target, recall,
  or displacement metric was calculated; every one of the 104 unchanged G111
  role keys is retained and explicitly unscored.
- **B2 non-additive schema:** clear. These are new evidence artifacts only;
  no production field, status, reader, or G111 schema changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. This is a named,
  persisted `NOT VALIDATED` evidence result, not a gate or claim-state change.
- **B5 pre-verification deploy:** clear. No pod or deployed file was written.
- **B6 orphans:** clear. No module, import, command, or test was moved or
  retired.
- **B7 head-slice evidence:** clear. The fixed selection covers slots 0, 10,
  and 15 in every clip rather than contiguous head frames.
- **B8 self-fit as independent:** clear. No fit, proposal, or scoring action
  occurred.
- **B9 degenerate denominator:** clear. The withheld denominator is 104 named
  role keys across 33 distinct committed `(clip, source_frame, slot)` rows,
  not recycled identifiers.
- **B10 moved bar:** clear. No threshold or coordinate-contract value changed.
