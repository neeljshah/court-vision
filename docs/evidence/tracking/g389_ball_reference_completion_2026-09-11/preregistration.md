# G389 Preregistration

## Scope

This is a prepare-only protocol for completing the fixed native ball-reference queue. No rating, scoring, training, inference, GPU work, pod job, register change, or ledger change is authorized by this artifact.

## Fixed inputs

- `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv`
- `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/reference_v2.csv`
- `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/adjudication_queue.csv`
- `docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/adjudications_g384.csv`
- `docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/queue_reconciliation.csv`
- `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheets/`

The binding before-condition is a whole-set join of all 1,620 manifest keys with the G373 reference and all 90 G384 decisions. It must reproduce 1,114 settled, 506 pending, 301 development pending, 205 held-out pending, 312 counted development boxes, held-out settled labels 157/161/26, and zero candidate executions. A changed count requires a new whole-set seal. A completed queue is FALSIFIED only after rerunning this exact condition and recording its output.

## Allocation and adjudication protocol

Pending keys are the manifest keys after completed-key subtraction. They retain the original split, the 332/549 split construction, and 739 extra-development keys. Sort by split, game, section, frame_index, frame_key. Partition the ordered pending keys into 30 contiguous equal-quantile bins. The deterministic permutation takes one next key per bin in round-robin order until empty. Checkpoints are exactly 30, 120, 240, 360, and 506.

Two adjudicators receive disjoint assignments. An independently sealed, evenly selected 30-key duplicate audit is permitted only as repeated review, never as new frames. Each primary judgment is blind: native full sheet first; record `VISIBLE`, `ABSENT`, or `UNKNOWN`, with native centre and diameter or box where visible. `UNKNOWN` is available only after an actual native-sheet review and is never an unvisited-task marker. Reveal legacy annotations only after the blind judgment is sealed. Conflict reconciliation retains uncertainty and cannot overwrite primary-rater disagreement.

Every batch verifies output count, stable-key uniqueness, and native image-open receipts. A completed key cannot be re-claimed. Restart allocation excludes all completed keys. The merge retains every original G373 and G384 decision and every manifest key; absence is represented explicitly rather than dropped.

## Non-scoring reports and fixed bars

Prepared reports will state settled and unsettled counts by split and reason, development positives, `UNKNOWN`, usable native boxes, causal-neighbour deduplication, and held-out context separation. The development readiness bar is at least 500 unique valid development boxes from at least five development games, based on the full 1,071-key development census. A complete census below that bar is `CLOSED AT LIMIT`; meeting it is only `READY FOR G390 CHECK`.

The inherited usability statement retains its fixed rule: median centre disagreement no greater than 0.5 times median native diameter, at least 30 both-visible pairs, with p90, maximum, and missingness named. The 30 transform controls are evenly selected visible keys and are controls, not detector results. The acceptance rows and bars are those in `docs/evidence/tracking/specs/G389_spec.md`; none may be changed.

## Verifier and language constraints

This protocol follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including additive schemas, explicit missingness, no perpetual re-claim, even sampling, and evidence-path checks. There is no scored comparison in this prepare-only lane, so evaluator, purge, embargo, evaluator-state, differential-archive, and charged-trial requirements are not invoked. If a later scored comparison is proposed, its preregistration and seal must predate it. Any future loss delta uses: improvement equals baseline loss minus candidate loss; positive means candidate better.

The Claude finisher alone may measure after this artifact is sealed. The memo skeleton must retain a prepare-only placeholder verdict and finish with an explicit `NOT VERIFIED` list.
SEAL sha256 15684f9c6439f3853074d90fbb9c515f54709965e6146db2551ee7de853d1091
