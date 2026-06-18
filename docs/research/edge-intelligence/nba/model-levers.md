# NBA MODEL LEVERS -- every lever with a SHIP / REJECT / PENDING / HYPOTHESIS verdict

_Sport = NBA. Every modeling lever in the prop stack + MC sim + win-prob + in-game layer, with
the gate verdict and the artifact that earns it. Verdicts mirror the real eval-gate / WF
backtests / signal_lab_registry -- never hand-waved. A REJECT is a SUCCESS. ASCII._

## Verdict legend
SHIP = leak-free OOS improvement, in production. REJECT = gated and failed (recorded knowledge).
PENDING = built, not yet proven OOS. HYPOTHESIS = plausible, unmeasured.

## A. Prop point-prediction levers

| Lever | Where | Verdict | Evidence |
|---|---|---|---|
| Recency-decay sample weights `exp(-decay*age)` | prop_pergame train (decay=0.5) | **SHIP** | recency>volume; adding seasons hurts (cut-list CUT 2); `props_pergame_metrics.json` recency_decay=0.5 |
| NNLS 3-way blend (XGB/LGB/MLP) | prop_pergame `_blend` | **SHIP** | pts ensemble_lift +0.0051, reb +0.0211 (`props_pergame_metrics.json`) |
| q50 quantile head for {reb,blk,stl,tov,fg3m} | prop_quantiles | **SHIP** | shipped path; no-Gaussian P(over) |
| AST kept OFF q50/isotonic (preserve divergence) | prop_pergame:115 | **SHIP (deliberate)** | calibration_used=false for ast; accuracy!=edge -- pulling to mean kills the AST edge |
| Isotonic calibration on pts/reb/ast | calibration_pergame_*.joblib | **REJECT/OFF** | calibration_lift_r2 ~+0.003..0.006 but calibration_used=false; lift trivial, not worth the mean-pull |
| Per-stat regularization overrides (`_STAT_PARAMS`) | prop_pergame | **SHIP** | STL train/holdout gap 0.18 -> 0.011 (07:104) |
| 23 disabled feature blocks (tracking/hustle/on_off/gamelog_full/linescore/officials) | prop_pergame | **REJECT** | each annotated with the WF result that killed it; gamelog_full OOS ROI down all stats (07:99,185) |
| Atlas/intel point features (49 leaves) | atlas_features -> player_props | **REJECT (DEAD FUNNEL)** | base+atlas MAE pts +0.174, reb +0.064, ast +0.008 WORSE; only fg3m -0.003 (09:168); unread by served model anyway |
| Discovery loop candidates | discovery.py | **REJECT** | 10/10 discovered REJECT; flag OFF; SHIP not auto-grafted (09:176) |
| opp_def_matchup -> pts | signal_lab | **REJECT** | oos_rel +1.194%, unstable split-half (signal_lab_registry.parquet) |
| rest_days_pts | signal_lab | **REJECT** | oos_rel -0.161% |
| minutes_competitiveness / kitchensink | signal_lab | **REJECT** | no OOS lift |
| pbp_origin_transition (TO/fastbreak+OREB->PPP) | signal_lab | **VALIDATED, not grafted** | all gates pass, oos_rel -0.76% (rmse) -- promote via reviewed graft+retrain |
| rest_x_age, shot_clock_leverage, opp_position_defense_reb, oreb_matchup | signal_lab | **VALIDATED, not grafted** | passed honest gate; most likely real point-model wins on disk |
| Minutes-aware post-scaling (elasticity) | minutes_aware_props.py | **PENDING** | exists as post-hoc scalar; should be first-class minutes-conditional (07 plan item 7) |
| **Same-day freshness (minutes/lineup/scratch)** | not wired | **HYPOTHESIS (top lever)** | the only unmodeled accuracy lever; sim `out_ids` hook exists (08:88); blocked on feed |

## B. MC sim levers

| Lever | Verdict | Evidence |
|---|---|---|
| Shared-pie usage concentration (emergent teammate corr) | **SHIP** | corr ~-0.10 matches real (08:93); fixes the old rho-bug by construction |
| Dispersion lognormal shock (hold team total, re-pin marginals) | **SHIP** | fixes under-dispersed individuals (cov q10-q90 66%->80%) without breaking team total (08:117) |
| Count-stat recal (Poisson, real per-game mean) | **SHIP** | fixes zero-clumping (P(Wemby>=1blk) 60%->95% real, 08:122) |
| CV_COUNT_NB (NegBinom where var>1.5*mean) | **PENDING/gated** | default Poisson; NB only when genuinely overdispersed |
| Anchor (recency-blended target, top-8 pinned) | **SHIP w/ known bias** | over-predicts team total ~+4.5 playoff (08:200); s=0.5 zeroes bias but haircuts stars; shipped s=1.0 |
| Defense slopes (DEF_RIM/PERIM, conservative ~1.5x) | **PENDING** | in-sample 1-season NYK/SAS; not multi-corpus validated (08:204) |
| 2K rating curve / ROLE_W / interactions | **PENDING** | hand-set anchors (Wemby 99 etc.); not cross-season validated |
| Recency rates blend (RECENCY_W 0.6) | **SHIP (NYK/SAS only)** | cut playoff over-pred +0.98->+0.11, MAE 4.18->4.05 WF (08:140); but only 39 rows exist |
| Real PBP assist network / unassisted share | **SHIP (NYK/SAS only)** | from PBP ground truth (08:46); league-shallow |
| CV_AGENT_DEF_SUPP (per-defender suppression) | **gated OFF** | gate_def_supp.py; byte-identical when off |
| CV_LLM_SCHEME (scout knob nudges) | **REJECT for the number** | built/gated but rejected; scouting-only (LLM scheme-prior memory) |
| out_ids freshness drop | **SHIP (hook), unfed** | manual today; the freshness entry point |
| CV_MIN_VAR same-player corr corrector | **PENDING (bolt-on)** | realized pts-reb +0.2..0.35 above raw sim; patched at board time not native (08:208) |
| Extend recency/PBP/team_defense to 30 teams | **HYPOTHESIS (highest sim lever)** | re-run builders over full cache (08 quick-win 1) |

## C. Win-prob + correlation levers

| Lever | Verdict | Evidence |
|---|---|---|
| NNLS blend XGB(+LGB/LR/MLP/NB) win-prob | **SHIP (calibration)** | 69.1% accuracy = matches close, CLV~0 -- NOT an edge (07:218) |
| isotonic recal on win-prob | **PENDING/OFF** | clv_proxy is a proxy not realized CLV |
| Archetype-conditioned correlation recal | **SHIP (accuracy-only)** | correlation_recal.py wired; NO SGP price history -> not ROI-validated (07:225); CV_ARCHETYPE_CORR OFF |
| Hierarchical position priors | **PENDING** | hardcoded league means, not fit (07:226) |

## D. In-game levers

| Lever | Verdict | Evidence |
|---|---|---|
| Score-anchor + Brownian variance collapse (NBARepricer) | **SHIP (calibration)** | RMSE Q1 12.5->Q4 4.2; clean math (11:154) |
| predict_live anchor to pregame Elo + temp recal | **SHIP** | ECE 0.059->0.012; cohesion fix W146/W156 (11:176) |
| ingame_blend weight surface (P_live vs P0) | **PENDING (SYNTHETIC)** | REAL_OOS_VALIDATION_PENDING=True; flagship lever unproven on real data (11:296) |
| garbage_clamp (late blowout) | **SHIP** | hard clamp a linear blend can't express (11:188) |
| SBS routed/score ensemble (player props) | **REJECT-for-now / OFF** | MAE 1.01 vs 1.87 looks strong but single-corpus, default OFF; Brier 0.1772 vs 0.1706 LOSS until late Q4 (11:336) |
| ~20 legacy live_engine override heads | **mostly REJECT/OFF** | single-corpus, boundary-fragile; endQ3 fired across all Q4 (bug, gated) (11:333) |
| Consolidated Bayesian trust curve | **DATA-BLOCKED (identity no-op)** | trust_curve.json absent; fit corpus 2022-23 vs live 2025-26 (11:326) |

## E. Interval / uncertainty levers
| Lever | Verdict | Evidence |
|---|---|---|
| Conformal residual intervals (all 7 stats) | **SHIP** | conformal_*.json on disk; finite-sample coverage |
| Sigma inflation x1.86 (blk) per-stat | **PENDING (quick win)** | sigma too tight on EVERY stat; not yet wired; domains uses only a floor (07:209) |

## Prioritized lever queue (do in this order)
1. **Same-day freshness** (A) -- highest accuracy lever; blocked on feed -> get the feed first.
2. **Graft the 5 VALIDATED signal_lab signals** (A) -- already passed the honest gate; reviewed graft+retrain+re-gate.
3. **Inflate prop interval sigma per-stat** (E) -- pure calibration win, low risk.
4. **End the in-game blend SYNTHETIC->REAL OOS** (D) -- converts the flagship lever to measured.
5. **Extend recency/PBP/team_defense to 30 teams** (B) -- makes the sim's deepest signal real for every matchup.
6. **Joint-calibration-prove the SGP** (B/C) before any SGP $ claim.
