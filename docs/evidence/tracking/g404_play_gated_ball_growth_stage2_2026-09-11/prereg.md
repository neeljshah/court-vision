# G404 play-gated ball-growth stage 2 preregistration

## Status and authority

This is a PREPARE-ONLY protocol for G404 on worktree a18. It is governed by
`docs/evidence/tracking/specs/G404_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. The local Astra source was absent
at preparation. No collection, gate inference, rating, adjudication, scoring,
training, held-out invocation, pod job, deployment, restart, register update, or
ledger update is authorized by this preregistration.

## Binding prerequisites

Before any dependent action, the finisher must write `input_hashes.csv` after
rehashing the accessible accepted G403 `instructions.md` and
`control_catalogue.csv`, plus the G364 weights, reference NPZ, reference labels,
and reference order/label map identified by G375. Each row must state the exact
worktree path, byte size, SHA-256, accessibility, and role. The G403 handoff,
source identity, and gate assets must all be accessible. Any missing item is
`PARTIAL` before collection or rating. A missing repository-relative asset is
reported as `ABSENT-IN-WORKTREE <path>`; it is never replaced by an asset from
another worktree.

The frozen gate is exactly the G375/G364 ResNet-18 cosine nearest reference class:
`USABLE_COURT`, with the first frozen reference index winning ties. It uses no
new fit, cutoff, smoothing, alternate classifier, ball detector, or ball-visibility
cue. This candidate-shot gate on known basketball games is not a sport-purity
claim.

## Fixed population and exclusions

The entire retained pool and all canonical game identities for original 530-box
DEV, held-out, and context sources are censused. Alternate uploads resolve to the
same canonical game identity. Eligible targets require at least 30 resolved games,
at least two competitions, native sources, and distinct prospective targets.
Any overlap with DEV, held-out, or context identities is named in
`disjointness.csv` and excluded before drawing. Video identifiers alone do not
establish disjointness.

Per eligible game, one median-offset section is retained and read back before
rotation. Actual decoded PTS, frame index, native dimensions, frame rate, pixel
digest, source path, source bytes, source SHA-256, and receiver path are retained.
Candidate keys are every two seconds strictly inside decoded span, mapped to the
nearest decoded PTS with earlier tie resolution. Duplicate pixels/indices collapse.
Candidates within one second of every prior rated, control, or context frame are
excluded before gate evaluation. The complete grid, exclusions, and gate outputs
are frozen before audit or ball work.

## Gate audit before any ball draw

Grid rows are sorted by canonical game, PTS, and source digest. Audit draws are
30 admitted and 30 excluded rows, each evenly indexed within the entire stratum
using `floor(j*(N-1)/29+0.5)`. Fewer than 30 rows in either stratum is `PARTIAL`.
Two raters independently label native full frames `PLAY`, `NONPLAY`, or `UNKNOWN`
without gate output or ball coordinates. `PLAY` requires visible multi-player
on-court basketball action; wide replay action qualifies. Wipes, bench, crowd,
portrait, graphics, and rim-only frames are `NONPLAY`.

The gate passes only with at least 27 of 30 jointly `PLAY` admitted frames and at
least 24 of 30 jointly `NONPLAY` excluded frames. Unknown or disagreement does not
count. Gate failure is `CLOSED AT LIMIT`: retain audit keys and stop without a
replacement classifier or ball collection. After a pass, exclude the 60 audit
frames and their one-second neighborhoods, then require at least 30 games with ten
distinct admitted targets each.

## Fixed 300-key draw and ratings protocol

Thirty games are drawn evenly from the complete ordered eligible set. Within every
game, ten admitted PTS targets are indexed with `floor(k*(M-1)/9+0.5)`, k=0..9.
All 300 keys, native manifests, and rounds freeze before labels. One frame per
game per round is required. No post-draw object filtering is allowed.

Each rater receives G403's 30 controls once without feedback and must achieve 30
of 30 state decisions plus all 20 known visible centre matches. Any failure is
`NOT VALIDATED` and stops real rating. For every real key, raw state and geometry
remain separate: an invalid box never erases a valid state. Raw three-label kappa
must be defined and at least 0.60 in every complete 30-key round and across all
300 keys. Undefined or incomplete kappa never passes.

Usability uses all valid raw both-visible pairs, requiring at least 30 pairs. The
median centre gap must be no greater than one half of the median raw visible
diameter, where diameter is `(box_w + box_h) / 2`; native `sheet_scale` is 1.0.
The finisher publishes both populations and median, p90, maximum, and resolution
diagnostics without conditioning on agreement or adjudication. Adjudication follows
raw sealing, preserves originals and uncertainty, and never repairs a failed raw
gate.

## Fixed outcome and artifacts

All 300 planned keys, including `ABSENT`, `UNKNOWN`, and failed outcomes, are kept
in `yield.csv`. Audited new unique boxes greater than 120 of 300, together with all
preceding bars and the complete identity/audit chain, permits only a later
collection proposal. At most 120 is `CLOSED AT LIMIT`; missing prerequisites or
supply is `PARTIAL`; control, raw reliability, or usability failure is
`NOT VALIDATED`. Existing 530 accepted boxes and G400's 116 unused additions remain
outside accepted DEV. The full training lock remains at least 1,500 accepted boxes
and at least 57 resolved games; this stage does not train.

Required evidence paths are `input_hashes.csv`, `census.csv`, `disjointness.csv`,
`source_receipts.csv`, `decoded_pts.csv`, `candidate_grid.csv`, `gate_outputs.csv`,
`gate_audit_draw.csv`, `gate_raw/`, `gate_audit.csv`, `draw.csv`,
`native_manifest.csv`, `batch_plan.csv`, `controls/`, `rater_raw/`,
`batch_receipts.csv`, `ratings.csv`, `kappas.csv`, `gaps.csv`, `diameters.csv`,
`adjudications.csv`, `new_boxes.csv`, `yield.csv`, `summary.json`, `repeats.json`,
`renders/`, and `SHA256SUMS` beneath this directory. Receivers and NOT VERIFIED
items are mandatory in the final memo.

## Execution boundary

The planned later heavy route runs only through the specified pod procedure after
this protocol is committed and prerequisites pass. It is not launched by this
prepare-only lane. Inputs are read one store at a time; no store above 300 MB is
bulk-read. Any later compute-only pod transfer records route-file hashes, machine,
CPU load, VRAM, source retention, scratch status, and repeat receipts. The
improvement sign convention for any later paired calibration comparison is baseline
loss minus candidate loss; positive means candidate better. This preparation makes
no comparison and reports no metric.
SEAL sha256 36ffa3620e776f6bb3a7e8e335fe1cb4dbd90791ac6d3994743e1cf48eeb4de4
