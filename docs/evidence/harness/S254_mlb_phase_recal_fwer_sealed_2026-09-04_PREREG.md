# S254 MLB phase recalibration FWER sealed preregistration

sealed_at_utc: 2026-09-04T08:08:26.2449950Z
spec: docs/evidence/tracking/specs/S254_spec.md
contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9

## Fixed comparison

- Sport and context: MLB in-game calibration.
- Incumbent: the S06 leak-free e4 probability named `model_prob` by `scripts/platformkit/ingame/s88_phase_recal.py`.
- Candidate: the `phase_platt` fit/apply pair from `scripts/platformkit/ingame/bucket_recalibration.py`, fit only on the purged CPCV callback train rows.
- Outcome and loss: binary `outcome` and per-tick Brier loss.
- Source partition: the S06 47,104-tick / 158-game scored partition reconstructed by `s88_phase_recal.build_records` from one read-only store discovered beneath `data/cache`; no prior paired-loss CSV supplies predictions.
- OOF engine: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`, with `n_groups=8`, `n_test_groups=1`, and `embargo_days=1`. Its callback emits each candidate probability. The imported `_purged` policy supplies the symmetric nonzero embargo and purge semantics.
- Informative filter: `scripts.platformkit.eval_gate.tick_informative.flag_ticks`, applied after OOF generation and before every Brier, p-value, CI, and BH calculation.

## Fixed family and replication

- Family size: 15 exhaustive phase buckets, exactly: `early|leading`, `early|leading_big`, `early|tied`, `early|trailing`, `early|trailing_big`, `late|leading`, `late|leading_big`, `late|tied`, `late|trailing`, `late|trailing_big`, `mid|leading`, `mid|leading_big`, `mid|tied`, `mid|trailing`, `mid|trailing_big`.
- Multiple-testing rule: Benjamini-Hochberg q=0.05 across all 15 buckets. No bucket will be removed for a label, p-value, or replication result.
- Unit: equal-weight game-cluster mean paired Brier loss; positive delta is incumbent loss minus candidate loss.
- Replication assignment: whole game IDs with an even first byte of `SHA-256("S254-replication-v1:" + game_id)` are primary and odd first bytes are replication. A game ID belongs to exactly one side; ISO week is not a partition key.
- Replication report: every bucket receives its replication-side equal-game delta and clustered CI; labels require a BH survivor in the full family and a same-direction replication CI.

## Fixed rails and artifacts

- No FWER ledger read or write, no flag change, and no data write.
- The run writes the paired-loss archive, JSON summary, and memo under `docs/evidence/harness/`; each paired row carries game ID, timestamp, incumbent probability, callback candidate probability, outcome, and both losses.
- The run asserts source denominator, nonempty purge, embargo_days > 0, no blocked train row, callback coverage, no split game IDs across replication sides, and timestamp order `sealed_at_utc < first_score_at_utc`.
- A result with zero BH survivors is valid and is reported with calibration language only.

seal_sha256: 91aa52f7948a4cf0abc9106f6163172ace74b454478cfece41fc3fd94efdb096
