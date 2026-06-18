# WIRING SPEC -- turn the DEAD FUNNEL into a GATED predict-time input (or honestly label it off)

_Part of the edge-intelligence corpus (`_wiring/`). Executable spec for a future BUILD agent.
Grounded in deep-dive 09 (the dead-funnel finding) + 07 (prop stack) + 01 (funnel disconnect).
HONESTY: markets are efficient; the bar is CALIBRATION vs the devigged close on >=2 corpora,
NEVER a $-edge. A NULL (atlas does not help) is the LIKELY and ACCEPTABLE outcome -- it lets us
stop pretending the funnel is alive. ASCII only. READ-ONLY on code; this file only proposes._

---

## 0. The problem, stated precisely (from deep-dive 09 sec 5)

The intelligence layer is BUILT, leak-safe, materialised (44 atlas parquets: 28 player + 16 team),
READ at predict time -- and then SILENTLY DROPPED. Three measured facts:

1. PARITY GAP. `src/prediction/player_props.py:2156` (inside the `CV_PROP_EXTRA_FEATURES` block,
   default ON at :2125) calls `atlas_feature_row(...)` and merges numeric `atlas_*` leaves into
   the `feats` dict (:2168-2170). But the SERVED model was never trained on them:
   `data/models/prop_stack_meta.json` contains NO `atlas_` and NO `disc_` feature names
   (verified `'atlas_' in meta == False`). The per-stat `prop_*_v3_lgb` models have a FIXED
   feature schema; `predict_pergame` slices X to the artifact's `n_features_in_`
   (`src/prediction/prop_pergame.py:4859`), so the injected `atlas_*` columns fall outside the
   schema and are discarded. The default-ON flag is a NO-OP for accuracy. This is exactly the
   train/inference-parity bug class (memory `feedback_train_inference_parity`).

2. EVEN IF WIRED, BULK ATLAS DOES NOT HELP POINT MEANS. `.planning/loop/atlas_lift.json`
   (49 atlas feats added to 129 base, n=101,765, 3-fold WF, run 2026-05-31, device cuda)
   measures `base+atlas` MAE minus `base` MAE -- POSITIVE = WORSE:

   | stat | delta_mae_mean | per-fold deltas | neg_folds | all_improve |
   |------|---------------|------------------|-----------|-------------|
   | pts  | +0.1739 (WORSE) | [-0.009, -0.006, +0.537] | 2/3 | False |
   | reb  | +0.0638 (WORSE) | [+0.003, -0.003, +0.191] | 1/3 | False |
   | ast  | +0.0084 (WORSE) | [-0.0002, +0.0004, +0.025] | 1/3 | False |
   | fg3m | -0.0030 (better) | [-0.0025, -0.0013, -0.0052] | 3/3 | True |

   Only fg3m clears the all-folds bar, by a trivial -0.003 MAE. Note every stat's third fold
   is the one that blows up (pts +0.537) -- a classic single-fold selection artifact in REVERSE
   (one bad fold dominates the mean), confirming the bulk add is noise, not signal.

3. The 49 wired leaves are a NARROW slice -- only `durability_load`, `quarter_shape_fatigue`,
   `rebounding_profile` (verified in `atlas_lift.json.atlas_features`). The other ~40 atlas
   sections contribute ZERO numeric features even to the failing experiment. So the layer is
   BOTH unread by the served model AND, where read, not additive.

CONCLUSION: there are exactly two honest end-states. This spec gives BOTH and a decision rule.

---

## 1. THE DECISION RULE (do this first, it is cheap)

Run the PER-SECTION ablation (`scripts/loop/eval_atlas_by_section.py` already exists, deep-dive 09
sec 6 item 2) BEFORE any retrain. Bulk +49 buried any real signal in fold-3 noise; per-section
isolates the 1-3 sections (if any) that clear the all-folds bar.

For each of the 44 sections S, each stat:
- compute WF MAE of `base` vs `base + atlas_<S>__*` (3-fold minimum, leak-free, the existing harness);
- a section PASSES for a stat iff `all_improve == True` (every fold improves) AND
  `delta_mae_mean <= -0.002` (a real, not trivial, reduction) AND it replicates on a 2nd corpus
  (different season split) -- the `>=2 corpus` bar from `_framework/proof-standards.md` sec item 4.

Decision:
- If >=1 section passes for >=1 stat -> go to **PATH A (retrain-with-atlas-then-gate)** for ONLY
  those (section, stat) pairs.
- If NO section passes (the likely outcome, consistent with deep-dive 09 sec 7 "ceiling is LOW") ->
  go to **PATH B (flag-off-and-label)** and stop pretending.

Write the per-section table to `data/frontend/atlas_section_lift.json` (NOT `data/registry/`).

---

## 2. PATH A -- retrain-with-atlas-then-gate (only the sections that passed sec 1)

The point of Path A is to close the parity gap HONESTLY: the model must be TRAINED on the same
atlas columns it is FED at inference, or the feed is a lie.

### A1. Build with parity (the binding requirement)
The single most expensive failure mode is: add columns to the inference builder but not the train
builder (or vice versa) -> the feature silently reads 0.0 / is sliced off. To prevent it:

- `feature_columns(stat)` (`prop_pergame.py:382`) is the ORDERED schema (canonical 129 cols; reb
  +3 = 132, verified at runtime). EXTEND it to append the passing `atlas_<S>__*` names AT THE END
  (append-only preserves the legacy 85/129 slicing logic).
- `build_pergame_dataset(...)` (`prop_pergame.py:3804`) walks each player's games chronologically.
  It must call `join_atlas_features(rows, ...)` (`src/loop/atlas_features.py:241`) keyed on EACH
  ROW's own `date` -- this is the leak-free per-row join (atlas_features.py enforces
  `row.as_of <= as_of` at :178). The atlas names come from `atlas_feature_names(...)`
  (atlas_features.py:293) RESTRICTED to the passing sections (pass a `sections=[...]` allowlist).
- `predict_pergame(stat, feature_row, ...)` (`prop_pergame.py:4859`) already merges `atlas_*` into
  `feats` (via player_props.py path); once the model's `n_features_in_` includes them and the
  feature_row carries them in the SAME ORDER, they are consumed instead of sliced off.

PARITY ASSERTION (write a per-file test): after retrain, assert
`model.n_features_in_ == len(feature_columns(stat))` AND that the trained `_meta.json` lists the
exact atlas names. This is the `feedback_pkl_integrity_check` discipline. If they mismatch, FAIL
the build -- do NOT ship a sliced model.

### A2. Retrain + re-gate
- Retrain ONLY the affected per-stat base + q50 heads on the extended frozen schema
  (`train_pergame_models(...)`, `prop_pergame.py:4197`); keep recency-decay weights + train-split
  median NaN-impute (no leak).
- Re-run `eval_atlas_lift.py` / `eval_atlas_by_section.py` -> the section-restricted lift must
  REPRODUCE the sec-1 pass (all_improve, >=2 corpora). A single good fold is an artifact
  (proof-standards sec item 4); reject if it does not replicate.
- Then the REAL gate: pipe the retrained predictor through `scripts/platformkit/eval_gate/run_gate.py`
  (`evaluate_corpus` walk-forward + Brier/BSS/ECE + clustered DM, deep-dive 01 sec 2c). SHIP only on
  no-regression-vs-frozen-baseline (`brier_model <= baseline + 0.005`) AND a calibration improvement
  that clears the ratchet. Record the verdict to `data/frontend/improve_ledger.jsonl` (NOT registry).
- HUMAN-GATED: `prop_pergame.py` lives under `src/**` (propose-only, human-gated-paths rule). Do NOT
  edit it autonomously. Emit the diff as a PROPOSED snippet under
  `docs/research/organization-sprint/` and surface it. The build agent's job is the harness + the
  proposed diff + the measured verdict, NOT the in-place src edit.

### A3. AST exception (do NOT calibrate it toward the mean)
AST deliberately stays on the BLEND path, NOT q50, because calibration-toward-the-mean kills the
~+7% AST divergence edge (deep-dive 07 sec 2; memory `feedback_ast_edge_is_real`). If an atlas
section passes for AST, wire it as an ADDITIVE feature but DO NOT route AST through isotonic
recal; preserve RAW. Treat AST lift with extra suspicion (the one signal we must not flatten).

---

## 3. PATH B -- flag-off-and-label (the likely + honest default)

If sec 1 finds no passing section (expected), STOP implying the funnel feeds predictions:

- Flip `CV_PROP_EXTRA_FEATURES` to default OFF (it is a no-op anyway; deep-dive 09 sec 5).
  PROPOSED change to `src/prediction/player_props.py:2125` -- human-gated, emit as a diff snippet.
- Relabel the atlas-injection block as SCOUTING-ONLY in a code comment + in `.planning/NOW.md`
  (deep-dive 09 sec 6 item 3): "44 atlases are a leak-safe descriptive SCOUTING + correlation
  asset; point-prediction lift measured ~0 (fg3m only, -0.003 MAE); not a predict-time input."
- Keep the genuinely-wired use that DOES pay off: `src/prediction/correlation_recal.py` reads
  `prop_corr_archetype_*` at predict time for parlay/joint COHERENCE (deep-dive 09 sec 3). That is
  the atlas layer's real ceiling (joint calibration, not point means) -- leave it ON, label it
  "calibration of correlations, not a point-edge."

---

## 4. GRAFT the 5 ALREADY-VALIDATED signals (the highest-probability real wins on disk)

`data/registry/signal_lab_registry.parquet` records 21 gated experiments: 16 REJECT, 5 VALIDATED
(deep-dive 09 sec 1c). These ALREADY passed the honest gate (walk-forward all-folds-improve +
null-shuffle z>=3 + ablation-vs-FULL + FDR) -- they carry `base_err/full_err/oos_rel/split_half/
ortho/verdict`. They are the most likely real point-lift on disk:

| signal_id | what it is | likely target stat |
|-----------|------------|---------------------|
| `pbp_origin_transition` | PBP play-origin / transition rate | pts, fg3m |
| `rest_x_age` | rest-days x age interaction | minutes-driven (pts/reb) |
| `shot_clock_leverage` | shot-clock-state scoring leverage | pts, fg3m |
| `opp_position_defense_reb` | opponent positional rebounding defense | reb |
| `oreb_matchup` | offensive-rebound matchup edge | reb |

GRAFT PROCEDURE (per signal, one at a time -- never bulk, that was the +49 mistake):
1. Confirm the signal's leak-rule + builder produce a per-row, as-of, leak-free column (check the
   `leak_rule` field in `signal_lab_registry.parquet`; reject if it reads any season-FINAL
   aggregate -- memory `feedback_no_season_final_features`).
2. Append it to `feature_columns(stat)` for its target stat ONLY (append-only).
3. Wire it into BOTH `build_pergame_dataset` (train) AND the inference feature_row (parity, sec A1).
4. Retrain that one stat's heads; re-gate through `run_gate.py`; require all-folds-improve on >=2
   corpora (re-verify the OLD validation still holds on the CURRENT corpus -- `oos_rel` may have
   been measured on a stale split; the lab verdict is necessary but not sufficient today).
5. SHIP only on no-regression + ratchet pass; record verdict + the (now re-measured) delta to
   `improve_ledger.jsonl`. If a previously-VALIDATED signal now fails the current-corpus gate,
   record the HONEST downgrade (a downgrade is a success, edge-theory sec "Evidence tiers").

These 5 are the ONLY items in this spec with prior gate evidence; everything else (the 44 bulk
atlases) starts at HYPOTHESIS and is expected to REJECT.

---

## 5. The bar (binding, from `_framework/proof-standards.md`)

Nothing in this spec ships without ALL of:
- LEAK-FREE construction (per-row as-of join; train/inference PARITY asserted in a per-file test).
- WALK-FORWARD OOS (the existing harness; no in-sample scoring).
- >=2 INDEPENDENT corpora/folds AGREE (the +49 fold-3 blowup is the cautionary tale).
- PROPER SCORING via the REAL `eval_gate` (no parallel stub; memory `feedback-tests-mirror-real`).
- No-regression-vs-frozen-baseline ratchet (only-improve-or-hold).

Evidence tier on every grafted feature: starts HYPOTHESIS; advances to CALIBRATION-PROVEN only on
leak-free OOS BSS>0 / MAE reduction replicated on >=2 corpora; CLV-PROVEN is N/A here (prop CLV
not yet computable -- deep-dive 12 sec 5).

## 6. Honest expected outcome
Per deep-dive 09 sec 7: the point-prediction ceiling for the atlas layer is LOW and largely
measured. The MOST LIKELY result of this entire spec is: Path B (flag off + relabel) + maybe 1-2
of the 5 validated signals surviving the current-corpus re-gate for reb/fg3m, worth single-digit
thousandths of MAE. That is a SUCCESS: it converts a silent no-op into either a small honest gain
or an honest "scouting-only" label, and it kills the biggest doc-vs-code honesty gap (01 sec 5).
