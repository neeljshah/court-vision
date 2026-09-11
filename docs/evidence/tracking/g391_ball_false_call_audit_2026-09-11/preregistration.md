# G391 Blind False-Call Audit Preregistration

Status: PREPARE-ONLY. This protocol is sealed before labels, adjudication,
reproduction, scoring, inference, or a pod job. Claude finisher measurement is
required before any measurement verdict.

Governing documents: `docs/evidence/tracking/specs/G391_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Fixed sources and binding

The finisher must open each named input separately and rehash it before any
measurement:

- `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv`
- `docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/reference_v3.csv`
- `docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/predictions_A8.csv`
- `docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/paired_frame_scores.csv`

The binding requires 549 held-out keys, 259 rank-0 OBSERVED calls, 90 TP, 169
FP, and FP label counts VISIBLE=100, ABSENT=50, UNKNOWN=19. The initial
prepare-only rehash has a mismatch against every hash quoted in G391; it is
recorded in the memo and no measurement may silently promote it. The required
read-only a11 handoff and verifier disposition have not been evidenced in this
worktree; provenance remains unresolved and this package is diagnostic-only.

## Frozen review protocol

Freeze all 259 called keys while retaining all 549 states. Sort by
`game/section/frame_index/key`, make 30 equal-quantile bins, and round-robin
across them. Give raters opaque packet identifiers only. Packets must not
expose reference label, confidence, split, or scorer outcome.

Two independent raters inspect full native context and then the fixed
candidate-centred crop with neutral marker. Each records exactly one candidate
object value: BALL, PERSON_OR_APPAREL, CROWD, SIGNAGE_OR_GRAPHIC, EQUIPMENT,
COURT_OR_LOGO, OTHER, or UNKNOWN. Each separately records a visible-ball
centre, diameter, and uncertainty; it must not infer an occluded ball. Raw
judgments are sealed before reference reveal. Reconciliation preserves both
originals, retains UNKNOWN FP, and records BALL centre-rule miss, second ball,
reference dispute, and unresolved cases separately.

## Frozen ceiling and conditional shadow

Raw reproduction uses native-to-720p centre matching, rank-0 OBSERVED calls,
and all 549 keys including no-detection frames. A suppression output is a
subset of raw calls: it cannot add a TP. No quality bar is changed: C0>=0.25,
precision lower>=0.90, and ALL FP/188<=0.01.

The present archive is expected to lack the complete causal plus disjoint DEV
supply. Missing history passes a raw call through. Only a future complete,
immutable archive may use the two immediately preceding decoded frames within
0.2 s, with both OBSERVED calls and speed no greater than the nearest-rank p95
from at least 30 disjoint DEV reference pairs. Confirmed no-detection
suppresses. No sweep, interpolation, future frame, new inference, or token is
allowed.

## Evidence and convention

The finisher must create all evidence named by G391, use even sampling for the
required cards, run only the focused G391 test, and perform the contract B
self-check. This preregistration test reads this file, normalizes CRLF to LF,
and hashes bytes above the seal line; it never uses a committed-object read at
landing time.

If any loss delta is later reported, improvement means baseline loss minus
candidate loss; positive means candidate better. This prepare-only package has
no delta and no measurement verdict.
SEAL sha256 94878be3b837b2231f8ed4931cdaa6a21f8eb8d5f3543a1320ff248dd4fa48a3
