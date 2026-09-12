# G416 Court Point Proposal Preregistration

Status: PREPARE ONLY. No rating, inference, scoring, pod job, deployment, or restart is authorized in this stage.

Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q1, Q3, and Q6; G416 specification version 2026-09-12 v1.

Machine and scope: PC only. This stage reads committed evidence and writes preparation code and a memo skeleton. EMPTY model set. No source video, model, or data store is opened.

Binding before-condition: reproduce G410's complete replay observation census from docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/branch_trace.jsonl and matrices.jsonl. Required values are 279 independent checks, 37 check sections, and 7 CLAMP_GUARD_REPRODUCED rows across 5 sections. Each replay check must bind to a replay matrix by exact section_id and frame. The future finisher must separately census original G402/G410 rows and replay emitted keys and must not bind an original row only by section and frame.

Equivalent-proposal check: before any future measurement, search the worktree for shadow_court_x, shadow_court_y, and would_violate_existing_guard outside this G416 specification. An existing additive proposal is FALSIFIED. A missing named source is PARTIAL, with no substitute source.

Future draw: sort the 37 observed sections by source digest then section_id. Draw exactly 30 positions using floor(j*(N-1)/29+0.5), j=0..29. For each drawn section use its middle saved tick. A missing binding remains UNKNOWN and is never replaced.

Future proposal semantics: derive a nominal unpadded box bottom-centre in native coordinates using TOPCUT=60 and PAD=15, convert it back to cropped coordinates before M then M1, use archived clipping, integer centre, homogeneous division, and int32 serialization. Never add 60 to a court-map point. Missing, invalid, singular, or nonfinite inputs preserve original x_position and y_position and yield shadow_status=UNKNOWN.

Additive fields only: shadow_court_x, shadow_court_y, shadow_status, matrix receipt, source receipt, call receipt, and would_violate_existing_guard. Original x_position, y_position, boxes, guard constants 250 and 350, ankle routes, and non-box routes remain unchanged. A box-foot alternative on ankle or non-box routes is hypothetical.

Future controls: independently calculate the homogeneous-corner oracle and compare it with the proposal on the 30 draw snapshots and all 32 exhaustive cases over 2 sizes, 2 clip states, 2 matrix-validity states, 2 receipt-binding states, and 2 box states. Missing receipt is an UNKNOWN control outcome, not numerical agreement.

Fixed verdict boundary: empirical CLAMP improvement is NOT VALIDATED at entry because independently bound replay CLAMP coverage has fewer than 30 sections. Any future paired comparison is descriptive unless it has at least 30 independently bound sections. Delta sign convention: improvement equals baseline loss minus candidate loss; positive means the candidate is better. No scored comparison is made in this prepare stage.

Required future evidence: COMMON artifacts, binding_deficits.csv, replay_shadow_points.csv, original_retention.csv, paired_clamp_counts.csv, construct_cases.csv, oracle_checks.csv, compatibility.csv, reader_manifest.csv, renders, a byte-identical PROPOSED diff receipt, and an explicit NOT VERIFIED list.
SEAL sha256 ad581968ad764fcb4b8b19e18d71ec4b533fdef14b8ebec6b0455416745d68fa
