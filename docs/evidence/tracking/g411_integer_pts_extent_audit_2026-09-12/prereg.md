# G411 preregistration

## Scope

Preparation only. This artifact authorizes no rating, inference, scoring, producer execution, deployment, restart, flag change, register write, ledger change, or pod job. The Claude finisher performs the retained-input measurement after this artifact is committed.

## Fixed inputs and representation contract

Use exactly the 30 source identities in `docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11/draw.csv`, in original even order, and the G408 archived schedules from `docs/evidence/tracking/g408_pts_duration_stop_proposal_2026-09-11/`. Paths carrying another `nba-track-aNN` prefix resolve beneath this worktree root. No source replacement is allowed. Retain source path, bytes, SHA-256, resolution, stream time base, frame index, integer PTS, best-effort timestamp, and source order before any outcome calculation.

The historical representation is the archived decimal-seconds schedule. The candidate representation is an integer PTS plus its stream time base, compared as exact rational values. Integer PTS must come from the retained source bytes; rounded decimal seconds must never be multiplied to manufacture it. Missing PTS remains missing. Best-effort timestamps are diagnostics only.

## Frozen mechanics and bars

For each source, establish the rational origin from the first valid PTS. The deadline is origin plus exactly 100 seconds. Validate every PTS before stride filtering. Preserve duplicate and source order. A PTS at the deadline is first excluded; a PTS before the deadline is admitted. Missing, malformed, or backwards PTS terminates UNKNOWN. Keep explicit frame-cap precedence unchanged. Archive last admitted and first excluded endpoints separately.

The inherited extent bar is exactly `abs(first_boundary_extent_s - 100) <= 1/validated_fps`, using unrounded values and the G408 validated FPS. Temporal containment is 30/30. The historical G408 26/30 result is retained as history only; no epsilon, endpoint swap, alternate rate, extra interval, or rounding-to-pass is allowed. A real miss yields PARTIAL.

## Required later measurement

Before extraction, reproduce the binding condition over the whole 30-source set: 30/30 containment, 26/30 historical extent passes, and four excesses near 0.000000333 seconds from stored unrounded values. If it does not reproduce, reconcile before extraction; missing binding is PARTIAL. Then compare archived decimal serialization and extracted rational PTS, retain every mismatch and anomaly, and replay the unchanged mechanics once per representation. Enumerate exact-at-boundary, one-timestamp-unit-either-side, duplicate, missing, backwards, dropped-neighbor, and skipped-by-stride cases for each observed time-base/rate pair. Two fresh saved-input reproductions are required.

## Reporting constraints

No result is claimed in this preparation pass. Delta sign convention for any later loss comparison: improvement equals baseline loss minus candidate loss; positive means candidate better. The memo must name this preregistration and its seal, distinguish preparation from measurement, end with NOT VERIFIED, and state that patched-module behavior, deployment, runtime after frame 3000, and decoder live PTS behavior remain not verified.
SEAL sha256 f7d5b33dc3ec131b744244f97597a9ffc950e3af99b6b893733d679a9414923b
