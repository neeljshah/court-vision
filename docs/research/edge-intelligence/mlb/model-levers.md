# MLB MODEL LEVERS -- every lever, SHIP / REJECT / PENDING / HYPOTHESIS + evidence
_Part of the edge-intelligence corpus. Every modeling knob in the MLB stack with its real verdict from
the code/proof layer, and a prioritized queue. A REJECT/NULL is a SUCCESS. Tiers per proof-standards.md.
ASCII only._

## Verdict log

| Lever | Where | Verdict | Evidence |
|---|---|---|---|
| **Empirical-Bayes shrink rate** (SHRINK_K=30 PA, K_START=3) | `player_rates_mlb.py:32-34` | **SHIP** (machinery) | Correct tool for thin priors; leak-free `_prior_rows` (`:91`, strictly date<as_of). But UNMEASURED for props (n=0). |
| **Leak-free exposure** (recent-15 mean PA/BF, lineup-slot prior) | `exposure_mlb.py:51,80` | **SHIP** (machinery) | Self-separates starters (~24 BF) from relievers; leak-free. Unmeasured live. |
| **Poisson count dist** (per stat) | `prop_engine_mlb` via `_make_p_over` | **PENDING** | Sound for Ks/Hits/Walks/Outs; mis-specified for TB/RBIs/Runs (var!=mean). No OOS score yet. |
| **NegBinom dispersion r for PROPS** | `prop_distribution(dispersion=...)` | **REJECT (unused) -> PENDING** | The one tail-widening lever exists but is NEVER set/fit for props (limitation #5). Poisson tails too tight on Ks -> fabricates edges. FIT a per-stat r from realized outcomes. |
| **Team MOV-Elo win-prob** | `proof_mlb/beat_the_close_ml.final_ratings` | **SHIP** (calibration) | Leak-free WF; W150 parity (same object scored vs close). MATCHES_CLOSE -> efficient, keep as support. |
| **NegBinom run surface + FITTED r** | `negbinom_engine.fit_dispersion_first_half:78` | **SHIP** | MoM r on first 50% (leak-free); closes W149 hardcoded-r gap; `_MIN_R=0.5`, under-disp -> Poisson. |
| **Win-prob anchoring (tie-split)** | `predictor._anchor_nb_tiesplit:72` | **SHIP** | Tilts lambdas (sum preserved) so NB-matrix ML == Elo p_home -> coherent surface. |
| **SP first-6 form feature** | `asof_sp_form.py:170` (EW 0.35, MIN_STARTS=3) | **SHIP** (feature, validated) | Strips bullpen IP (the big career-mean confound); leak-free snapshot-before-update. |
| **SP-Elo offset** `p=sigmoid(elo_logit + w*z_sp)` | `sp_elo_offset.py:133` (w fitted bounded log-loss min) | **SHIP-but-NOT-DELIVERED** | Validated leak-free in proof layer; **NOT wired into `MLBPredictor`** (limitation #8). Live win-prob is pure Elo -> the biggest game variable is absent. TOP team-side action. |
| **In-game recalibrator** (W156) | `predict_live` | **SHIP-as-NULL** (CALIBRATION-PROVEN) | Identity: held-out ECE 0.0085, slope 0.98; a fitted Platt worsens it. Honest measured NULL = success. |
| **In-game per-inning run curve** | `repricer._INNING_SHARES:36` | **PENDING (in-sample)** | Fit on the same linescores it scores; OOS deferred to `proof_mlb/curve_oos.py`. Don't trust late-inning edges yet. |
| **F5 fraction = 0.521** | `markets.py:46` | **PENDING (in-sample)** | Empirical on 27,983 games but in-sample; replace with OOS version. |
| **Park factor in PROP rate** | `asof_park.py` exists | **HYPOTHESIS (unwired)** | Park effect large in MLB; not multiplied into the per-PA prop rate yet (limitation #6). |
| **Opposing-pitcher factor in prop rate** | -- | **HYPOTHESIS** | The biggest remaining prop signal; analog of soccer opponent strength. Not built. |
| **Platoon (L/R) split in prop rate** | -- | **HYPOTHESIS** | Splits needed from statsapi season stats; not built. |
| **Season-prior shrink target** (replace coarse league pool) | `_league_per_exposure` today | **HYPOTHESIS (high ceiling)** | MLB full season makes a season prior informative (unlike NBA recency>volume). Highest-ceiling rate fix. |
| **Compound model for Total Bases / H+R+RBI** | -- | **HYPOTHESIS** | count x base-value or per-event categorical; raises the floor on the rough stats. |
| **Joint same-player prop model** (copula) | -- | **HYPOTHESIS** | No joint exists; parlays mispriced (limitation #7). After marginals calibrate. |
| **Isotonic recal on prop p_over** | `recalibration.py` exists | **HOLD/REJECT-on-thin** | cut-list CUT 5: isotonic OVERFITS on thin data (WC 24-match case deferred). Re-fit only as N grows; gate OOS. |
| **Two-arm self-improve ratchet** | `self_improve.improve_cycle` | **INSUFFICIENT_DATA** | mlb n=12 settled << MIN_RECAL_GAMES=60; ratchet cannot engage yet. Honest. |

## Prioritized lever queue (do in this order)
1. **Backfill gamelogs to 1-2 seasons** (`ingest_player_stats.ingest_range`, keyless) -- not a model lever
   but the gate for ALL prop levers below. Validate: row count + span + `props_eval_mlb` n>0.
2. **Run `props_eval_mlb` -> publish per-stat Brier/ECE/BSS.** First honest verdict. Validate: BSS per
   stat, demote the rough ones.
3. **Fit per-stat NegBinom r from realized outcomes; wire as default `dispersion`.** Cheapest correctness
   fix (Poisson tails too tight). Validate: ECE/tail calibration improves OOS vs Poisson.
4. **Wire SP-Elo offset into `MLBPredictor`.** Validate: re-score vs close (BSS, cluster-robust DM) -- ship
   only if no regression.
5. **Add park + opposing-SP + platoon factors to the prop rate.** Validate: per-stat BSS improves OOS.
6. **Season-prior shrink target.** Validate: lower-variance rates, better early-game calibration.
7. **Compound TB model; then joint same-player model.** Validate: tail calibration on the full stat-pair
   surface (retro-full-surface, not just the dominant pair).
8. **Replace in-sample inning curve / F5 fraction with OOS versions** before they drive a live number.
