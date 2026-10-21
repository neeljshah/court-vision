# Model card: NBA win-probability stack (5-way NNLS)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: NBA win-probability stack, five base learners blended with non-negative least squares
  (meta "val_nnls_5way" in the result file).
- Version: not recorded. The result file under Receipts is the measured version.
- Base learners: XGBoost, LightGBM, logistic regression, MLP, naive Bayes (per-fold weights in
  `results/winprob_walk_forward_results.json`).

## Intended use and non-use

- Use: a calibrated NBA game win probability in the private engine (status LIVE in
  `docs/CAPABILITIES.md`, Models and calibration). Calibration measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a market comparison; the artifact holds no market baseline (`EVIDENCE.md` section A).
  The reproducible pregame comparison against the close is `nba_pregame_mov_elo.md`.
- Playoff behaviour of this model: not recorded.

## Inputs and data

- Sources: 73 features (`n_features` in the result file). The feature names are in the private
  engine (`src/prediction/win_probability.py`) and are not recorded on the public surface.
- Window: NBA seasons 2023-24 and 2024-25 (`seasons` in the result file); n=1,473
  (`docs/CAPABILITIES.md`). Two seasons by default, intentionally (`docs/KNOWN_LIMITATIONS.md`,
  Recency vs volume).
- As-of: result file dated 2026-07-20.

## Method

- 3-fold expanding walk-forward (train_end_frac 0.4 / 0.6 / ...); per fold 491 validation games;
  NNLS weights fit on the validation split of each fold (result file).
- Leak guard: the engine's walk-forward harness asserts max_train_date < min_test_date every fold
  (packet section 2C); excerpt: [WALK_FORWARD_LEAK_ASSERT.md](../method/WALK_FORWARD_LEAK_ASSERT.md).
  Purge / embargo for this stack: not recorded.
- Second corpus: none recorded, so the two-corpus rule of
  [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md) is not met.

## Evaluation

| As of | Metric | n | Value | Interval | Verdict | Source |
|---|---|---|---|---|---|---|
| 2026-07-20 | accuracy / Brier, 3-fold walk-forward | 1,473 | 0.709 / 0.193 (Brier std 0.0084) | fold std only; no CI | none (no market baseline in artifact) | `docs/CAPABILITIES.md`; `EVIDENCE.md` section A |

- No paired comparison exists (no market or baseline forecaster is scored on the same games), so
  no packet verdict applies. MDE: not applicable.

## Known limitations

- `sim_win_prob` (used as the `pregame_win_prob` feature) is polarity-inverted at the source;
  the v1 LightGBM models learned to flip it internally (`docs/KNOWN_LIMITATIONS.md`). Whether this
  stack consumes that feature: not recorded.
- Fold-to-fold spread: accuracy 0.676 to 0.737 (result file), so a single-fold number is not stable.
- Two training seasons: sensitive to regime change.
- The scored split is the split the NNLS weights were fit on; no separate test split is recorded,
  so the stack metric is optimistic by the blend-weight fit.
- Per-fold Brier for each base learner is in the result file. Reliability curve for this stack:
  not recorded.

## Retractions and corrections

- Retired (packet section 4 and the 2026-09-14 correction;
  [retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)): a full-season
  model-vs-close Brier pair quoted beside this stack had no artifact and did not reproduce.
- Retracted (retractions page, the end-of-Q3 in-play Brier row): the end-of-Q3 in-game
  win-probability figure was leak-inflated by two Q4-derived features; that model is covered on
  `ingame_conditioning.md`.

## Reproduce

- Private corpus; not reproducible from the public tree. The result file is a tracked recorded
  artifact (`EVIDENCE.md` section A, `RECEIPTS.md` row).

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `results/winprob_walk_forward_results.json` | 2130 | 5bbc429d6b779860bbad069620423b38e37c2558b33981bcdcfd7883b79adcf8 | 2026-10-20 | measured result (tracked; file date 2026-07-20) |

- Model binaries: which file under `data/models/` holds this stack is not recorded; none is hashed here.

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
