# 09 -- Intelligence / Signal Layer, the 28+16 Atlases, and the DEAD FUNNEL

Area owner doc for a deep project-understanding read. READ-ONLY survey; ASCII only.
Honesty rails: markets are efficient; the honest win is CALIBRATION, not a $-edge.
Where this layer was measured honestly it mostly REJECTS, and that is recorded as a
success, not hidden. Paper-only throughout.

This area covers: the descriptive intelligence layer (`intel/`, `data/intelligence/`),
the atlas system (28 player + 16 team sections persisted as `data/cache/atlas_*.parquet`),
the signal registry/factory (`data/registry/`), the read-side bridge
(`src/loop/atlas_features.py`), and the LLM-free discovery loop
(`src/loop/discovery.py` + `src/loop/orchestrator.py`). The headline finding is the
**dead funnel**: a large, leak-safe intelligence layer is BUILT and materialised but is
effectively UNREAD at predict time, and where it IS wired the honest ablation shows it
does not help point accuracy.

---

## 1. INVENTORY -- what EXISTS and is USED

### 1a. Atlas source modules (`intel/`) -- the ARM-B builders
30 `player_*.py` modules + (team modules continue past the listing cutoff). Each is an
`AtlasSection` subclass (contract in `src/loop/atlas.py`). Materialised output is
**28 player + 16 team = 44** atlas parquets (verified: `ls data/cache/atlas_* | wc -l == 44`).
The `.planning/loop/atlas_registry.json` registers all 44 section keys.

Representative player sections (file -> purpose):
- `intel/player_shot_profile.py` -- shot location/type distribution + creation splits (188KB parquet, largest player atlas).
- `intel/player_usage_role.py` -- usage rate, role, on/off context.
- `intel/player_situational_splits.py` -- clutch/leverage/score-margin scoring splits (298KB parquet).
- `intel/player_vs_scheme_splits.py` -- player performance vs defensive scheme (276KB).
- `intel/player_quarter_shape_fatigue.py` -- per-quarter pts/reb/ast/min + Q4 fade + B2B decay.
- `intel/player_durability_load.py` -- age, minutes load, injury/DNP rates, load-mgmt.
- `intel/player_rebounding_profile.py`, `player_playmaking_network.py`, `player_pick_and_roll_profile.py`,
  `player_spacing_gravity.py`, `player_isolation_profile.py`, `player_transition_scoring.py`,
  `player_foul_drawing.py`, `player_foul_tendency.py`, `player_ft_profile.py`,
  `player_turnover_profile.py`, `player_defensive_profile.py`, `player_form_streak_dynamics.py`,
  `player_monthly_form.py`, `player_rest_b2b_splits.py`, `player_pace_fit.py`,
  `player_matchup_splits.py`, `player_score_margin_splits.py`, `player_scoring_creation.py`,
  `player_shot_clock_scoring.py`, `player_post_up_profile.py`, `player_catch_shoot_vs_pullup.py`,
  `player_consistency_variance.py`, `player_clutch_scoring.py`, `player_archetype_classification.py`.

Team sections (16): `team_bench_production`, `team_clutch_team`, `team_coach_tendencies`,
`team_defensive_assignments`, `team_defensive_scheme`, `team_offensive_scheme`,
`team_halfcourt_offense`, `team_lineup_synergy`, `team_matchup_adjustments`,
`team_pace_identity`, `team_paint_defense`, `team_rebounding_scheme`, `team_three_pt_defense`,
`team_transition_defense`, `team_transition_halfcourt_splits`, `team_turnover_forcing`,
`team_ft_foul_environment`, `team_rotation_patterns`.
(NOTE: source modules + registry list slightly MORE team sections than the 16 materialised
parquets -- a few team builders have no current parquet on disk, a minor inventory drift.)

### 1b. The loop machinery (`src/loop/`)
- `atlas.py` -- `AtlasSection` ABC + `AtlasArtifact` dataclass + `CVSlot` (reserved CV slots). USED.
- `atlas_features.py` -- the READ-SIDE bridge: atlas parquet/store -> flat leak-safe `atlas_*` model features. USED only by `player_props.py` (see 3) and `eval_atlas_lift.py`.
- `orchestrator.py` -- the never-stop two-arm driver (ARM A signals, ARM B intel). USED by `scripts/loop/run_loop.py`.
- `discovery.py` -- LLM-free deterministic transform proposer (the inexhaustible candidate source). USED by orchestrator behind `CV_LOOP_DISCOVERY` (default OFF).
- `gate.py` / `gate_nmin.py` -- the honest gate (walk-forward + null-shuffle + ablation-vs-FULL + FDR). USED.
- `error_miner.py` -- residual-derived hypothesis miner. USED by orchestrator ARM A.
- `intel_validator.py` -- leak/coverage/face-validity/dedup validation of atlas artifacts. USED by ARM B.
- `profile_factory_bridge.py` -- persists a validated section (1 parquet + 1 `sec_` fn + registry). USED by ARM B.
- `memory_writer.py`, `ledger.py`, `store.py` (`PointInTimeStore`), `signal.py`, `simulator.py`, `joint_verification.py`, `report_generator.py`, `wiring.py`. USED.
- `ingame_atlas_corrector.py` -- live projected-final corrector. Flag `CV_INGAME_ATLAS` (default 0). Consumed only by `src/ingame/sbs_shadow.py` + `scripts/loop/ingame_shadow_logger.py` (shadow path).

### 1c. Registries (`data/registry/`)
- `signal_registry.parquet` -- 86 signal DEFINITIONS, 11 cols (`signal_id, entity, domain, granularity, source, formula, leak_rule, consumer, ev_tier, coverage_pct, status`). Every row `status == "folded"`; consumers dominated by `scouting`/`corr-model`/`point-model-candidate`. `SIGNAL_REGISTRY.md` = human-readable mirror ("86 signal definitions across 3 entities x 15 domains").
- `signal_lab_registry.parquet` -- 21 rows, the HONEST gated-experiment record: 16 REJECTED, 5 VALIDATED (`pbp_origin_transition`, `rest_x_age`, `shot_clock_leverage`, `opp_position_defense_reb`, `oreb_matchup`). Carries `base_err/full_err/oos_rel/split_half/ortho/verdict/reason`.
- `signal_edge_registry.parquet` -- 40 rows, per-(signal,corpus,regime) ROI/CI/lift. Small-N, wide CIs (e.g. ast playoffs n=33 roi -30.68). Betting-edge framing -- treat as REJECT evidence, NOT a claimed edge.
- `iteration_ledger.parquet`, `roadmap.json`, subdirs (`signal_registry/`, `model_registry/`, `calibration_registry/`, `domain_registry/`, `engine_registry/`, `foundry_scoreboard/`). HUMAN-GATED (never auto-written by the loop).

### 1d. Materialised intelligence (`data/intelligence/`)
151 artifacts: 99 parquet + 50 json + 1 pkl + 1 png. Highlights:
- `atlas_features_sidecar.parquet` (261KB), `built_signals_sidecar.parquet` (399KB), `confidence_ensemble.parquet` (2.98MB), `blk_residual_head_v1.parquet` (1.7MB).
- `atlas_redundancy_matrix.parquet` -- documents redundant atlas pairs (e.g. opp_def x paint r~0.987).
- `player_atlas_feature_list.json` (`features` + `feat_cols`), `player_atlas_viz.png`.
- corr/parlay assets: `anti_correlation_parlay_candidates.parquet`, `compound_signal_hunt_v3/v4.parquet`, `cv_consistency_kelly.parquet`, `archetype_scheme_advantages.json`.
- The actual atlas LIFT measurement lives in `.planning/loop/atlas_lift.json` (see 5).

---

## 2. HOW IT WORKS -- data flow + key algorithms

### 2a. ARM B build path (intel -> parquet)
`Orchestrator._run_intel_arm` (orchestrator.py:335) -> for each discovered `AtlasSection`:
`section.build(entity_id, as_of)` (atlas.py:136, leak-safe, only data `<= as_of`) ->
`intel_validator.validate(section, art)` -> on pass, `profile_factory_bridge.register_section`
writes `data/cache/atlas_<entity>_<name>.parquet` + a `sec_` fn + registry entry, AND writes
into the `PointInTimeStore`. Confidence ladder `confidence_from_n` (atlas.py:30): high>=20, med>=5, else low.
Entity universe resolved via `_section_entities` (orchestrator.py:468) falling back to
`data/cache/profiles/PLAYER_INDEX.json` / `TEAM_INDEX.json`.

### 2b. Read-side bridge (atlas parquet -> model features)
`atlas_features.atlas_feature_row(entity_id, as_of, entity_type, sections, store)` (atlas_features.py:191):
- Primary source = `PointInTimeStore.read_atlas(... as_of)` (records stamped `<= as_of`).
- Fallback = disjoint parquet, but with a LEAK GUARD (`_section_dict_from_parquet`, line 158):
  a row is dropped if `row.as_of > as_of_iso` (line 178) so a single-snapshot parquet cannot leak future state.
- `_flatten` (line 92) emits numeric/categorical leaves as `atlas_<section>__<dotted.path>`, skipping
  `_note`/`_source` DEFER stubs, nulls, `_cv_fields`, and any `_`-prefixed key.
- `join_atlas_features(rows, ...)` (line 241) enriches a prop-feature-matrix row list per row keyed on the
  row's own `date` -> leak-free per row. `atlas_feature_names(...)` (line 293) returns the stable schema.

### 2c. The LLM-free discovery loop (the inexhaustible proposer)
`discovery.discover(target, top_k, seen_families)` (discovery.py:244):
1. `load_pergame_matrix` (line 223) builds the leak-safe pergame matrix via `prop_pergame.build_pergame_dataset`.
2. `enumerate_specs` (line 89): rank base cols by `|corr(col, target)|`, take top 24, then enumerate
   UNARY `(square, log1p_abs, zscore)` + BINARY `(interact, ratio, diff)` transforms; family-dedup via
   blake2b `family_key` (anti-re-roll across iterations).
3. `_screen_score` (line 131): cheap `|corr(cand, target)|`, drop degenerate or `>0.92` collinear with any base col.
4. Top-K go to the EXISTING honest `gate.evaluate` (walk-forward all-folds-improve + null-shuffle z>=3 +
   ablation-vs-FULL + FDR). The gate, NOT a model, decides. Candidate injected via `_gate_matrix` fast path
   (no per-row build), so leak-safe by construction (pure function of leak-safe base cols).
5. Verdicts appended to `.planning/loop/discovered_signals.jsonl` (`record_discovered`, line 269).

ARM-A `_run_discovery_arm` (orchestrator.py:293) runs this ONLY when `CV_LOOP_DISCOVERY` is set
(default OFF). A SHIP is recorded as validated-ready but is NOT auto-grafted into the served model --
the graft is an explicit reviewed step. So even SHIPs from discovery do not change served predictions.

---

## 3. HOW IT IS USED -- callers / consumers

- **Discovery/orchestrator**: `scripts/loop/run_loop.py` -> `Orchestrator.run(forever=...)`. ARM B builds atlases; ARM A gates seed-signals + discovery candidates. Idle-backoff to 30 min when nothing resolves.
- **atlas_features read at PREDICT time**: exactly ONE production caller --
  `src/prediction/player_props.py:2156`, inside the `CV_PROP_EXTRA_FEATURES` block (default ON, player_props.py:2125).
  It calls `atlas_feature_row(pid, as_of=game_date or today, sections=None)` and merges numeric `atlas_*`
  leaves into the `feats` dict (only if key not already present, line 2170).
- **atlas_features eval**: `scripts/loop/eval_atlas_lift.py` + `eval_atlas_by_section.py` + `eval_atlas_lift_ingame.py`
  (ablation harness -> `.planning/loop/atlas_lift.json`).
- **In-game corrector**: `src/loop/ingame_atlas_corrector.py` consumed only by `src/ingame/sbs_shadow.py`
  + `scripts/loop/ingame_shadow_logger.py`, behind `CV_INGAME_ATLAS=0` -> shadow only, not served.
- **Correlation assets** (`prop_corr_archetype_sameplayer/teammate.json`) ARE read at predict time by
  `src/prediction/correlation_recal.py` -- this is a genuinely-wired, archetype-conditioned residual-correlation recalibrator (for parlay/joint coherence, not point means).

---

## 4. STRENGTHS

- **Real leak discipline.** The read bridge enforces a strict `row.as_of <= as_of` guard
  (atlas_features.py:178) and per-row date-keyed joins -- a function-of-leak-safe-inputs argument that holds.
  The discovery engine injects candidates as pure transforms of an already-leak-safe matrix.
- **Honest gate, honest ledger.** `signal_lab_registry.parquet` shows 16 REJECT / 5 VALIDATE and
  `discovered_signals.jsonl` shows 10/10 REJECT -- the layer records its own failures instead of hiding them.
  This is exactly the "an honest REJECT is a success" rail in practice.
- **Breadth + provenance.** 44 materialised atlases + 86 catalogued signal definitions + 151 intelligence
  artifacts, each confidence/provenance-stamped, with reserved CV slots (`CVSlot`) for future tracking data.
  As a SCOUTING / descriptive asset this is genuinely deep and well-structured.
- **Truly LLM-free closed loop.** Discovery enumerates an inexhaustible deterministic candidate space and
  the gate decides -- no model marks its own homework, FWER is controlled via BH-FDR recomputed each iteration.
- **Redundancy is measured** (`atlas_redundancy_matrix.parquet`) rather than ignored.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

### THE DEAD FUNNEL (the central finding)
1. **Atlas features are injected at predict time but the served model was never trained on them.**
   `data/models/prop_stack_meta.json` contains NO `atlas_` and NO `disc_` feature names
   (verified: `'atlas_' in meta == False`). The stacker is per-stat `{coef, intercept}` over base model
   predictions; the underlying `prop_*_v3_lgb` models have a fixed feature schema. So the `atlas_*` columns
   merged into `feats` at player_props.py:2168 are **silently dropped** -- classic train/inference parity
   gap (the "most expensive bug class" in the project's own notes). The intelligence is built, persisted,
   read, and then thrown away. CV_PROP_EXTRA_FEATURES being default-ON is effectively a no-op for accuracy.

2. **Even if wired, the honest ablation says it does NOT help.** `.planning/loop/atlas_lift.json`
   (49 atlas feats added to 129 base, n=101,765, 3-fold WF) measures `base+atlas` MINUS `base` MAE:
   - pts: +0.174 (WORSE), neg_folds 2/3, all_improve False
   - reb: +0.064 (WORSE), 1/3, False
   - ast: +0.008 (WORSE), 1/3, False
   - fg3m: -0.003 (marginal improve), 3/3, True
   Only fg3m clears the all-folds bar and by a trivial margin. The 49 wired atlas leaves are dominated by
   `durability_load`, `quarter_shape_fatigue`, `rebounding_profile` -- a narrow slice of the 44 atlases; the
   other ~40 sections contribute zero numeric features to even this (failing) experiment. So: the layer is
   both UNREAD by the model and, when read, NOT additive for point means.

3. **Discovery has shipped nothing.** 10/10 discovered candidates REJECT; discovery is flag-gated OFF by
   default; even a SHIP is explicitly NOT auto-grafted. The "inexhaustible proposer" has not moved a number.

4. **86 signals all `folded`, mostly scouting.** The signal_registry consumers are `scouting`/`corr-model`,
   not `point-model`. The catalog is a scouting taxonomy, not a live feature feed. coverage_pct is `None`
   for the catalog rows -- coverage is undocumented in the registry itself.

### Other risks
- **In-sample / small-N edge tables.** `signal_edge_registry.parquet` ROI cells (e.g. n=33, CI [-58, -2])
  are pure variance; must never be read as edges (and the no-edge rule forbids it).
- **Redundancy.** Measured pairs at r>0.95 (opp_def x paint, matchup_grid x tempo) mean nominal "44 atlases"
  overstates independent information.
- **Inventory drift.** Registry/source modules list a few team sections with no parquet on disk; `as_of`
  on the disjoint parquets is a single snapshot (2026-06-02 for most), so historical training rows mostly
  hit the leak-guard DROP and get nothing -- the parquet fallback is near-empty for real backtests.
- **Stranded heavy artifacts.** `blk_residual_head_v1.parquet` (1.7MB), `confidence_ensemble.parquet` (3MB),
  `compound_signal_hunt_v3/v4` -- built, not on any served predict path found here.
- **Flag sprawl.** `CV_PROP_EXTRA_FEATURES` (default ON but no-op), `CV_LOOP_DISCOVERY` (OFF),
  `CV_INGAME_ATLAS` (OFF) -- the "ON" flag does nothing useful; the useful work is behind OFF flags.

---

## 6. PLAN TO GET BETTER (prioritized)

QUICK WINS (low risk, high clarity):
1. **Close the parity gap honestly or stop pretending.** Either (a) retrain the per-stat models WITH the
   `atlas_feature_names()` columns in the training schema so injected columns are actually consumed, then
   re-run `eval_atlas_lift.py`; or (b) given the measured non-lift, gate `CV_PROP_EXTRA_FEATURES` OFF by
   default and label the atlas-injection block as scouting-only. Right now it is a silent no-op that implies
   intelligence is feeding the model when it is not.
2. **Per-section lift, not bulk.** `eval_atlas_by_section.py` exists -- run it per atlas to find the 1-3
   sections (if any) that clear all-folds, and wire ONLY those. Bulk +49 buried any real signal in noise.
3. **Surface the dead-funnel state in `.planning/NOW.md`** so it stops reading as "80-artifact intelligence
   layer feeding predictions." Document: built, leak-safe, mostly unread, fg3m-only marginal.

MEDIUM:
4. **Re-target discovery at residuals, not raw stats.** Current discovery enumerates transforms vs the raw
   target; feed it the BASE-model residuals (what the model still gets wrong) so candidates compete only on
   orthogonal information. Couples discovery.py to `error_miner` residual logs.
5. **Promote the 5 VALIDATED signals into the served feature schema** (`pbp_origin_transition`, `rest_x_age`,
   `shot_clock_leverage`, `opp_position_defense_reb`, `oreb_matchup`) via an explicit reviewed graft +
   retrain + re-gate -- these already passed the honest gate and are the most likely real wins on disk.
6. **Lean into the IN-GAME corrector.** The project's repeated finding is the only real edge is in-game
   freshness/conditioning. `ingame_atlas_corrector.py` is built and shadow-only; validate it on replay
   (CRPS/Brier), and if it clears, that is where atlas intelligence most plausibly pays off.

BIGGER BETS:
7. **Make the atlas a same-day fresh feed, not a stale snapshot.** The leak-guard drops the single-snapshot
   parquet for historical rows; backfill per-date atlas snapshots into the PointInTimeStore so backtests
   actually see atlas state -- otherwise no honest measurement of atlas value is even possible historically.
8. **Fill the reserved CV slots.** Every section reserves null `CVSlot`s for tracking-derived fields
   (defender distance, box-outs, etc.). Those are the genuinely unpriced inputs; wiring real CV data into
   them is the only path to information the market may not have.

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

As a **point-prediction feature source**, the ceiling is LOW and already largely measured: the honest
3-fold ablation shows atlas features do not reduce pts/reb/ast MAE (they increase it) and help fg3m
trivially. This is consistent with the project's standing conclusion that pregame is at its data ceiling
and the market is efficient -- adding descriptive aggregates of the same history does not beat recency, and
can only pull toward the market (accuracy != edge). Best realistic outcome on point means: a tiny,
fg3m-like, all-folds-positive contribution from 1-3 hand-picked sections, worth single-digit-thousandths of
MAE, framed as calibration not edge.

The HIGHER ceiling for this layer is NOT point means. It is:
- **Joint/correlation coherence** (already live via `correlation_recal.py`) -- archetype-conditioned residual
  correlation genuinely improves multi-leg/parlay calibration without claiming an edge.
- **In-game conditioning** -- the one place freshness is structurally available; if `ingame_atlas_corrector`
  clears replay validation it is the most defensible win.
- **Scouting / explainability** -- 44 deep, provenance-stamped profiles are a strong descriptive product
  and a strong demo asset even at zero predictive lift.

What limits it: the layer is built on the same historical box/PBP data the base model already digests, so
it carries little orthogonal information; markets price team strength efficiently; and the only genuinely
new inputs (the reserved CV slots) are unfilled. Until same-day freshness or real CV data lands, the honest
verdict is: a deep, leak-safe, well-audited SCOUTING + correlation asset whose point-prediction lift is
near zero -- and the system should say so rather than imply the funnel is alive.
