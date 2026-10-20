# Model card: NBA player props (per-stat production models)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

## Name and version

- Name: NBA player-prop production models for PTS, REB, AST, FG3M, STL, BLK, TOV, scored through
  the production inference path by `scripts/verify_production_mae.py`.
- Version: the per-stat stack in the private engine (`src/prediction/prop_pergame.py`): per-game
  models plus q50 quantile models (XGBoost or LightGBM per stat) blended with NNLS weights from
  `data/models/meta_weights_pergame.json`. A release tag: not recorded.

## Intended use

- Point forecasts of a player's per-game box-score count. Accuracy measurement only.

## Not intended use

- Paper only. Not a wagering signal and not a sizing input; no return figure is computed or implied.
- No market comparison exists for these models (`docs/QUANT_BRIEF.md` section 1).
- Not to be described as a per-game model result until defect D8 is closed (see limitations).

## Inputs and leak guard

- About 190 NBA prop features (`docs/INDEX.md`, SIGNALS row); the exact list is in the private
  engine. Every CV-tracking feature carries SHAP 0.0 in production (`docs/CAPABILITIES.md`).
- Leak guard: last-20-percent-by-date chronological holdout; the verify script exits nonzero if
  any stat drifts more than 0.02 from the claimed values (packet section 3).

## Training data and period

- Corpus: NBA Stats API via nba_api plus ESPN box scores (data card C6,
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md`); default training seasons 2023-24 and 2024-25
  (`docs/KNOWN_LIMITATIONS.md`, Recency vs volume). Licence: NBA Stats API row is DECIDE.

## Validation protocol

- Measurement 1 (lead): production-model chronological holdout, 20,354 player-game rows,
  re-measured 2026-07-20.
- Measurement 2 (internal, separate label): walk-forward OOF, 50,954 rows per stat, artifact
  `data/cache/pregame_oof.parquet` (gitignored). The two measurements are never mixed.

## Measured performance

| As of | Measurement | n | PTS | REB | AST | FG3M | STL | BLK | TOV | Source |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-07-20 | MAE, production chronological holdout | 20,354 | 4.83 | 1.92 | 1.39 | 0.89 | 0.71 | 0.44 | 0.89 | packet section 3; `docs/CAPABILITIES.md` |
| not recorded | MAE, walk-forward OOF (internal) | 50,954 per stat | 4.58 | 1.90 | 1.34 | 0.88 | 0.71 | 0.515 | 0.88 | packet section 3 |

## Calibration diagnostics

- q10 / q90 bands calibrated to 80 percent empirical coverage on the training set; real coverage
  drifts on BLK / STL where q10 floors at zero (`docs/KNOWN_LIMITATIONS.md`, Quantile coverage).
- Conformal and calibration files exist under `data/models/` (local-only); their coverage numbers
  are not on the public surface.

## Known failure modes and limitations

- Defect D8 (OPEN): the props trainer is player-SEASON grain and generates some rolling features
  synthetically; rebuild at player-game grain before any prop claim (data card C6, defect register).
- Systematic PTS under-bias of about -0.45 on the walk-forward OOF frame (packet section 3; `docs/KNOWN_LIMITATIONS.md`).
- A leaky grid search once gave train R2 about 0.79 vs honest holdout about 0.06 on STL / BLK;
  corrective regularization is hard-coded (packet section 2C).
- Prior-season tracking aggregates: CEILING_ZERO on pts / reb / ast (`docs/CAPABILITIES.md`).

## Artifacts

| Path | Bytes | sha256 | Note |
|---|---|---|---|
| `scripts/verify_production_mae.py` | 7086 | 269a2ac6fbb3c90411b7e77e6e444b3ff938c644b95a2386adab05febeed1f79 | reproduction check (private repository) |
| `data/models/_meta.json` | 14541 | f9d36fd1e833d516b3085fe9af82aa66af8f7feeef1997e5764dad5ee8535c6a | training metadata (local-only) |
| `data/models/meta_weights_pergame.json` | 803 | ef7798ce3977eb2efdcb05dcbfff1d3db81b1569bab4df96615d9d4b8e13de60 | NNLS blend weights (local-only) |

- The 14 q50 files `data/models/quantile_pergame_*_q50.*` exist on this box and are not hashed here.

## Retraction and supersession history

- Retracted 2026-07-21: an assists-market candidate was regime-dependent (broke in the playoffs)
  and is not claimed (`docs/KNOWN_LIMITATIONS.md`; packet section 3).
- Retracted: a walk-forward prop return figure (per-stat BLK/STL splits) was a market-follow artifact; the grader picked direction from the devigged market lean and never read the model (packet section 4).
- Retired: the leaky grid-search R2 (above), superseded by the regularized settings.

## Owner and last verified

- Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
