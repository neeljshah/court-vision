# Model card: NBA win-probability stack (5-way NNLS)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: NBA win-probability stack, five base learners blended with non-negative least squares
  (meta "val_nnls_5way" in the result file).
- Version: not recorded. The result file below is the measured version.
- Base learners: XGBoost, LightGBM, logistic regression, MLP, naive Bayes (per-fold weights in
  `results/winprob_walk_forward_results.json`).

## Intended use

- A calibrated NBA game win probability in the private engine (status LIVE in
  `docs/CAPABILITIES.md`, Models and calibration). Calibration measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- Not a market comparison: the artifact holds no market baseline (`EVIDENCE.md` section A).
- Playoff behaviour of this model: not recorded.

## Inputs and leak guard

- 73 features (`n_features` in the result file). The feature names are in the private engine
  (`src/prediction/win_probability.py`) and are not recorded on the public surface.
- Leak guard: expanding walk-forward folds (train_end_frac 0.4 / 0.6 / ...); the engine's
  walk-forward harness asserts max_train_date < min_test_date every fold (packet section 2C).

## Training data and period

- NBA seasons 2023-24 and 2024-25 (`seasons` in the result file). n=1,473 (`docs/CAPABILITIES.md`).
- Recency choice: two seasons by default, intentionally (`docs/KNOWN_LIMITATIONS.md`, Recency vs volume).

## Validation protocol

- 3-fold expanding walk-forward; per fold 491 validation games; NNLS weights fit on the validation
  split of each fold (result file). Purge / embargo for this stack: not recorded.
- Second corpus: none recorded.

## Measured performance

| As of | Metric | n | Value | Verdict | Source |
|---|---|---|---|---|---|
| 2026-07-20 (file date) | accuracy / Brier, 3-fold walk-forward | 1,473 | 0.709 / 0.193 (Brier std 0.0084) | no market baseline in artifact | `docs/CAPABILITIES.md`; `EVIDENCE.md` section A |

## Calibration diagnostics

- Per-fold Brier for each base learner is in the result file. Reliability curve for this stack:
  not recorded.

## Known failure modes and limitations

- `sim_win_prob` (used as the `pregame_win_prob` feature) is polarity-inverted at the source;
  the v1 LightGBM models learned to flip it internally (`docs/KNOWN_LIMITATIONS.md`). Whether this
  stack consumes that feature: not recorded.
- Fold-to-fold spread: accuracy 0.676 to 0.737 (result file), so a single-fold number is not stable.
- Two training seasons: sensitive to regime change.
- The scored split is the split the NNLS weights were fit on; no separate test split is recorded, so the stack metric is optimistic by the blend-weight fit.

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `results/winprob_walk_forward_results.json` | 2130 | 5bbc429d6b779860bbad069620423b38e37c2558b33981bcdcfd7883b79adcf8 | measured result (tracked) |

- Model binaries: which file under `data/models/` holds this stack is not recorded; none is hashed here.

## Retraction and supersession history

- Retracted (packet section 4, 2026-09-14 correction): a full-season model-vs-close Brier pair
  quoted beside this stack had no artifact and did not reproduce; the reproducible pregame
  comparison is the MOV-Elo card (`nba_pregame_mov_elo.md`), not this stack.
- The end-of-Q3 in-game win-probability figure was leak-inflated by two Q4-derived features and
  is retracted; that model is covered on `ingame_conditioning.md`.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
