# S347 prepare-only baseline scorer

Verdict: PREPARED; synthetic construct validation only. No real-corpus metric.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h5, CPU only.
All writes stayed in that worktree. The pod remained OFF. No data/ writes.
Vocabulary follows contract Q6; automated scan required.

## Before-condition reproduced

PowerShell Select-String was used because rg is unavailable. Equivalent checks:
`grep -n "mlb_clean" scripts/platformkit/ingame/gate_a0_ingame_vs_market.py`
and `grep -n "PHASE_FN" -A 6 scripts/platformkit/ingame/gate_a0_ingame_vs_market.py`.
The source quotes are:

```text
107:PHASE_FN = {'mlb_clean': phase_mlb, 'soccer_intl': phase_soccer}
271:    ap.add_argument('--sports', default='mlb_clean,soccer_intl')
```

The default and absent segmented mappings match the binding premise. The old
gate remains unchanged. New mappings cover segmented and segmented_r3 families;
an unknown name raises an error. Missing mandatory state fields stop the run.

## Deliverables and synthetic verification

- scripts/platformkit/ingame/baseline_four_arm.py: input integrity and committed
  seal guards, reused row loader/bootstrap, shared evaluator, four paired arms,
  two populations and weightings, phase cells, clustered intervals, concentration
  and leave-one-game-out diagnostics, reconstructible paired-loss archive.
- scripts/platformkit/ingame/baseline_four_arm_features.py: declared pure parsers
  and training-only logistic fitting using numpy and standard library.
- tests/platformkit/ingame/test_baseline_four_arm.py: synthetic tmp_path fixtures;
  29 passing cases (CONSTRUCT), no sampled or real-corpus calibration claim.
- docs/evidence/ingame/S347_PREREG_DRAFT_2026-09-21.md: UNSEALED draft awaiting
  orchestrator review, seal and commit before any scoring.
- docs/evidence/harness/S347_baseline_scorer_2026-09-21.md: this memo.

Reproduction commands, run from the worktree root:

```text
python -m pytest tests/platformkit/ingame/test_baseline_four_arm.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.baseline_four_arm --help
python -m scripts.platformkit.ingame.baseline_four_arm --self-check
```

For pytest, PYTHONDONTWRITEBYTECODE=1 and PYTEST_ADDOPTS selects a worktree-local
basetemp. Tests cover missing and mismatched manifests, exact file inventory,
unsealed/uncommitted/changed preregs, LF normalization, stable unique tick keys,
constant D=C, future-game truncation, own-outcome independence, embargo boundary
exclusion, phase coverage, transition semantics, loader retention, actual reused
bootstrap output, unequal tick/game weights, concentration and removal ranges.
The bootstrap report check uses synthetic inputs and 20 resamples for speed;
the scorer's default remains the inherited N_BOOT = 2000.
The module self-check scans all five deliverables for ASCII and Q6 vocabulary,
checks Python files stay at or below 300 lines, matches inherited bars to the
unchanged source and checks the unsealed draft and memo sentence.

## Contract B and Q self-audit

B1/B7/B8/B9: synthetic construction only; no selected real denominator. Warmup
keys are explicit, all arms share observations, and training is earlier games.
B2/B6: additive new files only; no existing schema, module or reader changed.
B3/B4: no item-claim queue or quarantine path is introduced.
B5/B11: no deployment or pod run; no real-system repeatability assertion.
B10/Q3: inherited bars are copied verbatim and checked automatically. The
single-game concentration rule is explicitly a proposed new draft rule.
Q1: seal/history/HEAD-content guards exist; delivered prereg is unsealed.
Q2: this prepare-only construct row computes no charged metric. Future trial
charging and launch K are the orchestrator's responsibility, not this CLI's.
Q4: shared walk_forward with strict redaction and unique states; full-game
purge plus nonzero symmetric embargo; scaling fits only the past training set.
The raw model_prob arm is not a meta-learner of an internally generated OOF arm.
Q5: one supplied corpus is labelled SINGLE-WINDOW; no AHEAD conclusion is emitted.
Q6: automated scan required and run using the listed module self-check.
Q7: all tests are explicitly constructed cases. Scored cells retain the inherited
30-game minimum. Q8: default and mapping premise rechecked before edits.
Q9: future CLI output retains row keys, timestamps, folds, raw declared states,
training game IDs and paired losses; source manifests identify reconstruction inputs.

## Source identity

All paths below are relative to C:/Users/neelj/nba-harness-h5 and are text inputs;
resolution is not applicable. No video or real corpus was opened for scoring.

| Input | Bytes |
|---|---:|
| docs/evidence/tracking/specs/S347_spec.md | 3620 |
| docs/evidence/tracking/VERIFIER_CONTRACT.md | 12532 |
| scripts/platformkit/ingame/gate_a0_ingame_vs_market.py | 12047 |
| scripts/platformkit/eval_gate/walkforward.py | 8411 |
| scripts/platformkit/eval_gate/state_key_guard.py | 516 |

Git diff of tracked paths is empty; all five deliverables are new files. No
commit was created in this sandbox; files are ready for lane_commit.

## Retained synthetic scratch files

Automatic approval review rejected recursive scratch cleanup as blocked by policy.
These generated test fixtures remain local, are ignored by git, and are not lane_commit deliverables.
Every retained scratch file is listed below relative to the worktree root:

- .tmp_s347_pytest/test_changed_prereg_refused0/manifest.json
- .tmp_s347_pytest/test_changed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_changed_prereg_refused0/prereg.md
- .tmp_s347_pytest/test_hash_mismatch_refused0/manifest.json
- .tmp_s347_pytest/test_hash_mismatch_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_hash_mismatch_refused0/prereg.md
- .tmp_s347_pytest/test_missing_listed_input_refu0/manifest.json
- .tmp_s347_pytest/test_missing_listed_input_refu0/prereg.md
- .tmp_s347_pytest/test_missing_manifest_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_missing_manifest_refused0/prereg.md
- .tmp_s347_pytest/test_seal_lf_normalization0/manifest.json
- .tmp_s347_pytest/test_seal_lf_normalization0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_seal_lf_normalization0/prereg.md
- .tmp_s347_pytest/test_uncommitted_prereg_refuse0/manifest.json
- .tmp_s347_pytest/test_uncommitted_prereg_refuse0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_uncommitted_prereg_refuse0/prereg.md
- .tmp_s347_pytest/test_unlisted_input_refused0/manifest.json
- .tmp_s347_pytest/test_unlisted_input_refused0/mlb_segmented/additional.jsonl
- .tmp_s347_pytest/test_unlisted_input_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_unlisted_input_refused0/prereg.md
- .tmp_s347_pytest/test_unsealed_prereg_refused0/manifest.json
- .tmp_s347_pytest/test_unsealed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_unsealed_prereg_refused0/prereg.md
- .tmp_s347_pytest/test_valid_synthetic_inputs_pa0/manifest.json
- .tmp_s347_pytest/test_valid_synthetic_inputs_pa0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest/test_valid_synthetic_inputs_pa0/prereg.md
- .tmp_s347_pytest_agent/test_changed_prereg_refused0/manifest.json
- .tmp_s347_pytest_agent/test_changed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_changed_prereg_refused0/prereg.md
- .tmp_s347_pytest_agent/test_hash_mismatch_refused0/manifest.json
- .tmp_s347_pytest_agent/test_hash_mismatch_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_hash_mismatch_refused0/prereg.md
- .tmp_s347_pytest_agent/test_missing_listed_input_refu0/manifest.json
- .tmp_s347_pytest_agent/test_missing_listed_input_refu0/prereg.md
- .tmp_s347_pytest_agent/test_missing_manifest_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_missing_manifest_refused0/prereg.md
- .tmp_s347_pytest_agent/test_seal_lf_normalization0/manifest.json
- .tmp_s347_pytest_agent/test_seal_lf_normalization0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_seal_lf_normalization0/prereg.md
- .tmp_s347_pytest_agent/test_uncommitted_prereg_refuse0/manifest.json
- .tmp_s347_pytest_agent/test_uncommitted_prereg_refuse0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_uncommitted_prereg_refuse0/prereg.md
- .tmp_s347_pytest_agent/test_unlisted_input_refused0/manifest.json
- .tmp_s347_pytest_agent/test_unlisted_input_refused0/mlb_segmented/additional.jsonl
- .tmp_s347_pytest_agent/test_unlisted_input_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_unlisted_input_refused0/prereg.md
- .tmp_s347_pytest_agent/test_unsealed_prereg_refused0/manifest.json
- .tmp_s347_pytest_agent/test_unsealed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_unsealed_prereg_refused0/prereg.md
- .tmp_s347_pytest_agent/test_valid_synthetic_inputs_pa0/manifest.json
- .tmp_s347_pytest_agent/test_valid_synthetic_inputs_pa0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_valid_synthetic_inputs_pa0/prereg.md
- .tmp_s347_pytest_agent/test_validated_loader_preserve0/manifest.json
- .tmp_s347_pytest_agent/test_validated_loader_preserve0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_validated_loader_preserve0/prereg.md
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l0/manifest.json
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l0/prereg.md
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l1/manifest.json
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l1/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l1/prereg.md
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l2/manifest.json
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l2/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_agent/test_validation_refuses_rows_l2/prereg.md
- .tmp_s347_pytest_final/test_changed_prereg_refused0/manifest.json
- .tmp_s347_pytest_final/test_changed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_changed_prereg_refused0/prereg.md
- .tmp_s347_pytest_final/test_hash_mismatch_refused0/manifest.json
- .tmp_s347_pytest_final/test_hash_mismatch_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_hash_mismatch_refused0/prereg.md
- .tmp_s347_pytest_final/test_missing_listed_input_refu0/manifest.json
- .tmp_s347_pytest_final/test_missing_listed_input_refu0/prereg.md
- .tmp_s347_pytest_final/test_missing_manifest_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_missing_manifest_refused0/prereg.md
- .tmp_s347_pytest_final/test_seal_lf_normalization0/manifest.json
- .tmp_s347_pytest_final/test_seal_lf_normalization0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_seal_lf_normalization0/prereg.md
- .tmp_s347_pytest_final/test_uncommitted_prereg_refuse0/manifest.json
- .tmp_s347_pytest_final/test_uncommitted_prereg_refuse0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_uncommitted_prereg_refuse0/prereg.md
- .tmp_s347_pytest_final/test_unlisted_input_refused0/manifest.json
- .tmp_s347_pytest_final/test_unlisted_input_refused0/mlb_segmented/additional.jsonl
- .tmp_s347_pytest_final/test_unlisted_input_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_unlisted_input_refused0/prereg.md
- .tmp_s347_pytest_final/test_unsealed_prereg_refused0/manifest.json
- .tmp_s347_pytest_final/test_unsealed_prereg_refused0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_unsealed_prereg_refused0/prereg.md
- .tmp_s347_pytest_final/test_valid_synthetic_inputs_pa0/manifest.json
- .tmp_s347_pytest_final/test_valid_synthetic_inputs_pa0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_valid_synthetic_inputs_pa0/prereg.md
- .tmp_s347_pytest_final/test_validated_loader_preserve0/manifest.json
- .tmp_s347_pytest_final/test_validated_loader_preserve0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_validated_loader_preserve0/prereg.md
- .tmp_s347_pytest_final/test_validation_refuses_rows_l0/manifest.json
- .tmp_s347_pytest_final/test_validation_refuses_rows_l0/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_validation_refuses_rows_l0/prereg.md
- .tmp_s347_pytest_final/test_validation_refuses_rows_l1/manifest.json
- .tmp_s347_pytest_final/test_validation_refuses_rows_l1/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_validation_refuses_rows_l1/prereg.md
- .tmp_s347_pytest_final/test_validation_refuses_rows_l2/manifest.json
- .tmp_s347_pytest_final/test_validation_refuses_rows_l2/mlb_segmented/ticks.jsonl
- .tmp_s347_pytest_final/test_validation_refuses_rows_l2/prereg.md

## NOT VERIFIED
- Real-corpus calibration performance or any measured comparison.
- Real manifests, complete state-summary coverage, and model_prob provenance.
- Whether close_ts is a valid outcome-availability timestamp on a real corpus.
- A real committed sealed prereg; synthetic git guards use monkeypatching.
- Production-scale runtime and memory requirements of per-tick fitting.
- Charged trial ledger, launch K, independent second corpus or min_corpora_eff.
- Orchestrator acceptance, landing commit, deployment or pod execution.
