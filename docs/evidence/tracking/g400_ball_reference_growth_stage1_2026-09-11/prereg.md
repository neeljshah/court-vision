# G400 Stage 1 Preregistration

Status: PREPARE-ONLY. This artifact fixes the protocol and bars before any census, source opening, retention, frame selection, rating, adjudication, export, control, or metric calculation. This pass has opened no tracking catalogue, media object, receiver, or rating input.

Scope: one uniform-growth annotation stage only. It is not a training, detector, calibration, inference, scoring, deployment, daemon, or live-feed activity.

Population rule: after the binding whole-set census, retain only genuinely NEW basketball games across at least two competitions with resolved canonical identities, retained decodable native sources, and no old DEV, held-out, or causal-context identity overlap. Alternate uploads and unresolved identities are named exclusions. If fewer than 30 eligible games remain, record PARTIAL with the exact inventory; do not substitute, wait for supply, rate, or draw.

Draw rule: sort the complete eligible population by competition, canonical game identity, and source digest. Draw 30 indices using floor(j*(N-1)/29+0.5), j=0..29. For each selected game, choose exactly one section by the sealed median-PTS section rule, then ten native frames nearest fractions k/11, k=1..10, earlier tie. Frames must be at least one second apart and have distinct raw pixel digests. A failed source or decode remains a planned state; it is never replaced, upscaled, or selected by detector or visibility cue.

Native rule: every planned state records actual source path, bytes, raw digest, dimensions, fps, PTS schedule, and sheet_scale=1.0. Native-to-720p coordinates use actual source height. The 530-box / 27-game old reference is preserved unchanged and remains separate from the additive stage output.

Rating rule: freeze ten round orders before dispatch. Each round contains one target per selected game. Two independent raters provide VISIBLE, ABSENT, or UNKNOWN and, when VISIBLE, native box or centre/diameter without peer answers, predictions, or prior labels. Preserve originals, image-open/runtime receipts, duplicate-completed-answer checks, and unvisited states separately from reviewed UNKNOWN. Claude resolves disagreements only after raw answers seal.

Fixed bars: each complete n=30 raw batch and the pooled n=300 three-label Cohen kappa must be at least 0.60; undefined kappa is UNKNOWN, never agreement. Usability requires at least 30 both-VISIBLE pairs and median primary centre gap no larger than 0.5 times median native diameter, with p90, maximum, missingness, and per-resolution diagnostics reported. Run exactly 30 even native planted-centre/transform controls; require 30/30 centre-rule matches, exact numeric roundtrip within tolerance, and zero false positives. Controls are not detector evidence.

Completion and yield rule: account for all 300 planned states. Yield is accepted new boxes divided by 300, never VISIBLE states or judgments. At 120 or fewer accepted boxes, report CLOSED AT LIMIT for this uniform route. More than 120 accepted boxes plus every fixed reliability and usability bar can only support a proposal for a future fixed stage. The full milestone remains at least 970 added boxes from at least 30 new games and at least 1,500 total boxes over more than 57 games; this stage cannot represent that milestone as met.

Reproduction rule: two fresh processes must reproduce saved-table arithmetic and delivered-render digests. This establishes arithmetic and rendering only; rating and audit repeatability remain unmeasured. No scored comparison is authorized by this preregistration.

Machine rule: future retention/native decode uses the pod only through the approved wrapper because sources are too large for this PC; paired ratings are PC work only under the shared resource gate. This PREPARE-ONLY pass runs locally because it writes only protocol text and pure helper code.

Evidence plan: create only the named stage directory files after their corresponding action: census.csv, game_disjointness.csv, draw.csv, source_receipts.csv, pts.csv, native_manifest.csv, batch_plan.csv, rater_raw/, batch_receipts.csv, ratings.csv, kappa.csv, adjudications.csv, box_audit.csv, reference.csv, new_boxes.csv, transform_controls.csv, yield.csv, summary.json, repeats.json, renders/, common_receipts/, and SHA256SUMS with its byte-domain declaration. Missing inputs are explicitly ABSENT-IN-WORKTREE or planned, never zero.
SEAL sha256 eda637cb7eba86bce3b2a9b4b5850c47e140cf5f5bd08e6778bd8bf856c1bfca
