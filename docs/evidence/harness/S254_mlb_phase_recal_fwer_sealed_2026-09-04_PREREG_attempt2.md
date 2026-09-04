# S254 attempt 2 preregistration: MLB phase recalibration FWER

sealed_at_utc: 2026-09-04T09:14:35.1765197Z
spec: docs/evidence/tracking/specs/S254_spec.md
contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9

## Fixed scored comparison

- Sport and context: MLB in-game calibration.
- Incumbent: the S06 leak-free e4 probability named `model_prob` by `scripts/platformkit/ingame/s88_phase_recal.py`.
- Candidate: the `phase_platt` fit/apply pair from `scripts/platformkit/ingame/bucket_recalibration.py`, fit only on received purged CPCV callback train rows.
- Outcome and loss: binary `outcome` and per-tick Brier loss; bucket delta, raw-p test, and replication CI use equal-weight game-cluster mean paired losses.
- Source partition: reconstruct the S06 47,104-tick / 158-game partition from one read-only MLB JSONL store beneath `data/cache` through `s88_phase_recal.build_records`; prior paired-loss artifacts do not supply predictions.
- OOF engine: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with `n_groups=8`, `n_test_groups=1`, `embargo_days=1`, strict redaction, and the symmetric `_purged` policy. The callback emits every candidate probability.
- Team identities: reuse `scripts.platformkit.ingame.ingame_outcome_label.parse_mlb_ticker`, the canonical variable-width MLB ticker parser, with its canonical Kalshi and normalized ESPN MLB abbreviation set. Each of all 158 game IDs must resolve to two real canonical team identities before CPCV.
- Purge audit: sort states by `state_ts` exactly as `cpcv_evaluate` does. For all eight splits, record the purge-plus-symmetric-embargo train count and assert it equals the evaluated `n_train` route count.
- Informative filter: `scripts.platformkit.eval_gate.tick_informative.flag_ticks`, applied after CPCV prediction generation and before every Brier, raw-p, CI, and BH calculation.

## Fixed family, raw-p, and replication

- Family size: 15 exhaustive phase buckets, exactly: `early|leading`, `early|leading_big`, `early|tied`, `early|trailing`, `early|trailing_big`, `late|leading`, `late|leading_big`, `late|tied`, `late|trailing`, `late|trailing_big`, `mid|leading`, `mid|leading_big`, `mid|tied`, `mid|trailing`, `mid|trailing_big`.
- Multiple-testing rule: Benjamini-Hochberg q=0.05 across all 15 buckets. No bucket will be removed for a label, p-value, or replication result.
- Raw-p test: two-sided `scripts.platformkit.eval_gate.dm_test.diebold_mariano` on the per-game equal-weight mean paired Brier-loss series for each bucket.
- Bootstrap CI: `state_bucket_benchmark._cluster_bootstrap_ci` on the same per-game series, with 2,000 bootstrap resamples, `random.Random(42)`, and sorted-draw quantile indices 49 and 1949.
- Replication assignment: whole game IDs with an even first byte of `SHA-256("S254-replication-v1:" + game_id)` are primary and odd first bytes are replication. Hash-split sides must be reported as 83 primary and 75 replication game clusters; no game ID may split sides and ISO week is not a partition key.
- Replication report: every bucket receives its replication-side equal-game delta and fixed bootstrap CI. Labels require a BH survivor in the full family and a same-direction replication CI.

## Fixed rails and attempt-2 artifacts

- No FWER ledger read or write, no K read, no flag change, and no data write.
- Purge and symmetric embargo sizes are both one calendar day; the shared engine additionally retains its unchanged same-matchup and same-team purge semantics.
- Attempt-2 writes only new files whose scored artifact names carry `_attempt2`: paired-loss CSV, summary JSON, and lane memo. Attempt-1 artifacts and schema remain unchanged.
- The run asserts source denominator, all 158 canonical team parses, nonempty purge, one-day symmetric embargo, no blocked train row, callback coverage, all eight audit/evaluated n_train equalities, no split replication game IDs, and `sealed_at_utc < first_score_at_utc`.
- Zero BH survivors is valid and is reported using calibration language only.

seal_sha256: 030eb13aad94edbafeb0c54c18aa88bbb5f82da448e4ab3378fec5d8be13e136
