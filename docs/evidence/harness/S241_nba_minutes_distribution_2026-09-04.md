# S241 NBA minutes distribution

## Verdict

CLOSED AT LIMIT - premise falsified before any scored comparison.

The S241-required shared evaluator module is absent in this worktree. The
direct existence check returned `False`. The S246 evidence independently
records that the same requested utility is absent. Therefore an OOS minutes
score cannot be run through the exact S233 route required by S241 and contract
Q4. Contract Q8 makes this a valid close without a replacement implementation.

## Inputs opened

All inputs below are local source or evidence files; they have no image or
video resolution.

| Path | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `src/prediction/minutes_predictor.py` | 13463 | `30CDD12849997410A72357F28DAF7B9F885A6162CC9ECCE1E4B4F3FC157D44F7` | none |
| `src/prediction/minutes_floor_model.py` | 7923 | `E44D3130AE2B0D243D5A2EEF2493ABACBC46109B583F485D88F771F37160BF95` | none |
| `src/prediction/minutes_aware_props.py` | 5585 | `FC0198797BD3E8CC784737197A17CBD4762BF8701148D2CDB9205FA66DCF55D2` | none |
| `src/prediction/pts_minutes_model.py` | 11415 | `5604D6313A1EA6B47AF5D245413C980AA746D503B0433583C4D21249F961AEF2` | none |
| `docs/evidence/harness/S233_walkforward_embargo_prereg_2026-09-04.md` | 5604 | `19CE44E3DB42213E614D0F08E430344411F98581E9AD2E5172524D154CC1B1DB` | none |
| `docs/evidence/harness/S246_boxscore_scoring_harness_2026-09-04.md` | 3184 | `34D56A1F4F7563A482D97BC9A2E893B495454F78D28EBCFCB8DBF43264600B79` | none |

## Required module premise

All four named modules were read, along with every tracked caller found by a
repository caller survey.

| Module | Existing minutes output | Quantile output | Caller coupling |
|---|---|---|---|
| `minutes_predictor.py` | `expected_minutes`, heuristic `floor` and `ceiling`, scenario probabilities, `minutes_std` | None; `floor` and `ceiling` are not q10/q90 | Imported by `minutes_aware_props.py` and its focused tests |
| `minutes_floor_model.py` | `proj_min` point value | None | Imported by `prediction_orchestrator.py`, `player_props.py`, `minutes_predictor.py`, and tests |
| `minutes_aware_props.py` | Rescales props from `expected_minutes` | None | Imported by `player_props.py` and tests |
| `pts_minutes_model.py` | Internal point `mu_min`; public output is PTS | None | Imported by `oof_pts_minmodel.py` and tests |

The points minutes head also trains only on `target_min >= 1`, so it cannot be
used directly for a coverage calculation that includes DNP zero-minute rows.
The existing `MinutesPredictor.predict_minutes_distribution` name is a
scenario-summary API, not a quantile distribution API: it emits no q10, q50,
or q90 keys and does not define quantile calibration.

No caller signature needs to be changed for a future additive wrapper. The
limit is the missing required S233 shared evaluator, not a caller coupling.

## Evaluation status

No data store was opened. No preregistration was created because no scored
comparison was permitted after the prerequisite falsification. Accordingly:

| Requested result | Status |
|---|---|
| Fresh chronological 80/20 point MAE | Not computed; no valid shared evaluation route |
| q10/q50/q90 pinball loss | Not computed; no valid shared evaluation route |
| q10-q90 coverage | Not computed; no valid shared evaluation route |
| Holdout player-games and game clusters | Not computed; no data store opened |
| DNP handling | No rows scored or excluded; any future coverage evaluation must include zero-minute rows |
| Per-player quantile sample | Not created; no quantile model was fit |
| Differential artifact | Not created; no comparison was scored |

Preregistration path: not applicable. Preregistration SHA-256: not applicable.
This is not a scored claim, so Q1, Q2, Q4, Q5, and Q9 scoring requirements do
not apply. Q3 is satisfied because no acceptance bar changed. Q6 is satisfied:
this memo contains calibration language only.

## Focused test

No S241 code or test was created. The required synthetic quantile test is
inapplicable after the Q8 premise close; no test command was run.

## Verifier self-check

- B1: No metric, denominator, or exclusion set was produced.
- B2: No schema, status, or field changed.
- B3-B6: No gate, claim loop, deployment, move, or retirement changed.
- B7: No rows or renders were sampled.
- B8: No residual was fit or presented as independent evidence.
- B9: No metric denominator was used.
- B10: No threshold changed.
- Q1: No scored comparison occurred.
- Q2: No trial was charged and no ledger was touched, as required by S241.
- Q4: No OOS result was claimed outside the mandated missing evaluator.
- Q5: No AHEAD result was claimed.
- Q6: ASCII calibration-only prose.
- Q9: No differential exists because no score exists.

## Not verified

The additive quantile wrapper, synthetic quantile test, sealed preregistration,
fresh 80/20 point-MAE, embargoed pinball/coverage evaluation, per-player
sample, and paired-loss artifact remain unverified because the required S233
shared evaluator is absent.
