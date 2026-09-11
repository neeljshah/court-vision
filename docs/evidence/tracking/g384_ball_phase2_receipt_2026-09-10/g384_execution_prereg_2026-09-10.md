# G384 execution preregistration -- prepare-only continuation

Spec: `docs/evidence/tracking/specs/G384_spec.md`. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B, Q1 and Q6. This additive protocol inherits G373's sealed reference and does not alter any G363 or G373 artifact.

## Binding premise and source inventory

Before allocating any work, reconcile the entire queue from `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/adjudication_queue.csv` against `sheet_manifest_all.csv`, `reference_v2.csv`, and `adjudications_v2.csv` in that same directory. The expected result is 596 unique unresolved keys: 361 development and 235 held-out; every key is in the 1,620-key manifest and is absent from both settled tables. A key already settled by an adjudication, an existing completed rater-cache entry for its assigned pass, or a recorded candidate arm receipt is never allocated again. The raw rater-cache directory is read only and is never copied.

The phase-1 settled reference contains 1,024 keys and the completion target is the original 1,620 scheduled keys: 1,071 development and 549 held-out. The source sheets named by the manifest are native 1920x1080 JPEGs. The scorer frame table is a new additive table only: it preserves every G363 full-schema identity/context field and fixes `sheet_scale` to `1.0` for every native reference row.

## Completion protocol

The queue driver emits a deterministic interleaving of development and held-out queue keys, ordered by stable key within each split. No prediction, prior detector score, v1 label, or other rater result is presented to a rater. Terra and sol may only rate an uncompleted assigned key under the existing PC RAM gate. The finisher records an explicit VISIBLE, ABSENT, or UNKNOWN adjudication from native sheets. UNKNOWN is retained and is never silently removed.

All 596 queue keys are attempted and accounted for. No queued key is replaced. The full reference is rebuilt separately from the original settled reference plus the new adjudications. Development boxes retain the existing causal-neighbour de-duplication. A8 needs at least 500 audited unique development boxes from at least five development games. A10 is unavailable unless A8 is available. A9 remains LIMIT without the original pinned licence/dependency receipt.

## Native scoring guard and arm receipt

Before any call into `g363_score.score_arm`, the native frames-table builder asserts every row has `sheet_scale == 1.0`; a scaled row raises an error and cannot score. It also requires all reference keys and validates a native-coordinate planted match on at least 30 evenly distributed VISIBLE keys before a real scoring request.

There is at most one candidate held-out execution. The accounting receipt lists A0, A8, A9, and A10, their prerequisites, execution state, and every unmet quota. If reference completion, usability, quota, or remaining budget is incomplete, the affected arm is CLOSED AT LIMIT without a substitute score. No rating, training, scorer call, evaluator call, candidate selection, or candidate held-out execution is authorized by this prepare-only commit.

## Fixed quality bars and accounting

Reference usability remains median primary-rater centre disagreement no greater than one half of median native diameter, with at least 30 both-VISIBLE boxed pairs; report p90 and all unresolved keys. A score requires complete usable reference plus at least 150 VISIBLE and 150 ABSENT held-out labels. The inherited score bars are C = TP/549 at least 0.25, Wilson precision lower at least 0.90, and ALL FP/N_absent at most 0.01. Centre-only matching remains at most `max(3 px, diameter_720p/2)`; a prediction on UNKNOWN is a false positive.

Any later scored comparison must first use the shared evaluator with purging and symmetric nonzero embargo, with one stable evaluator state per scored tick, archive its evaluator records, state the sign convention as improvement = baseline loss minus candidate loss (positive = candidate better), and write its own sealed scoring amendment before its first metric. This file contains no scored comparison.

## Execution accounting

Machine allocation: PC for blind raters under the existing RAM gate; pod scratch worktree only for a future heavy scoring task, one GPU job at a time. The deployed pod tree, daemon, flags, `data/`, `data/registry/`, register, and ledger are untouched. Every future pod job checks for its exact worktree process before launch and is polled to completion. This prepare-only file is written with LF endings and is sealed before all later measurement.
SEAL sha256 db343a7a1e87a052647b79a68d40aaabee48d2824a8edaae8cbf1f1a21f87184
