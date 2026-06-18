# SOCCER-CLUB -- model levers (SHIP / REJECT / PENDING / HYPOTHESIS)
_Every modeling lever in the club-soccer stack with a verdict + the artifact that earns it, and a
prioritized lever queue. Verdicts come from the real leak-free gate (props_eval / recal_eval /
ratings WF), never hand-wave (proof-standards). ASCII._

## Lever ledger

### TEAM / scoreline levers
| Lever | Verdict | Evidence / artifact |
|---|---|---|
| Dixon-Coles bivariate Poisson scoreline matrix | SHIP (calibration only) | scoreline_engine.scoreline_matrix; rho=0 == closed-form O/U baseline to <1e-6 (tested anchor) |
| rho (low-score DC correction) | PENDING | rho_fit.py / rho_fit_eval.py exist; rho<0 inflates 0-0,1-1; gate on WF dECE; NOT shown to beat close |
| Full coherent market surface (markets.full_surface) | SHIP (expressiveness, NOT edge) | markets.py header: "does NOT add signal or edge over base Poisson"; prices 1X2/BTTS/AH/etc coherently |
| HFA lambda adjustment | PENDING | hfa_lambda.py + hfa_lambda_eval.py; home-field lift on lambdas; gate via WF |
| Finishing prior / as-of (xG-style) | PENDING | finishing_prior.py + finishing_asof.py; leak-free finishing-rate prior; calibration-only |
| SOT blend | PENDING | sot_blend.py; blends SOT-for/against; gate-pending |
| As-of rolling features (asof_features) | SHIP (input) | asof_features.parquet 25,834 rows; leak-free L10/asof shots+SOT for/against |
| Team markets as a $ EDGE | REJECT | cut-list CUT 1; season WF well-calibrated but does NOT beat close, CLV ~ 0 |

### PLAYER-PROP levers (the pocket)
| Lever | Verdict | Evidence / artifact |
|---|---|---|
| Per-90 rate, EB-shrunk, leak-free | SHIP (mechanism) | player_rates.player_rate; SHRINK_K=3.0; _prior_rows date<as_of strict (the one leak chokepoint) |
| Club-prior blend (capped min(starts,20)) | SHIP-WITH-CAVEAT | player_rates.py:203-224; the "0->reliable edges" unlock; per_start->per90 mild over-estimate + single-snapshot mild lookahead (deep-dive sec 5) |
| Expected minutes (start_prob x ~85 + sub) | SHIP (mechanism), error UNMEASURED | player_minutes.expected_minutes; backtest feeds REALIZED minutes -> live minute error not measured |
| NB dispersion (phi = var/mean, leak-free) | SHIP | dispersion.stat_dispersion; _MIN_N=40, per-stat prior phi when thin; widens too-tight Poisson tails |
| Opponent-adjust multiplier | REJECT (measured null) | team_defense.py; cache mode "+opp-adj" overall bss only +0.11; per-opponent table 1-3 matches deep, mostly shrunk to 1.0 |
| Isotonic recalibration (PAVA) | REJECT/DEFER (overfit) | prop_recal.py + recal_eval.py verdict "MIXED: OOS Brier +0.00393 worse, in-sample -0.0061 = overfit tell"; NOT applied at board |
| Honesty-first tier ranking | SHIP | prop_tiering.calibration_rank_key; weak-stat raw-EV can never outrank proven-stat row |
| Saves rate (GK) | CALIBRATION-PROVEN (WC) | prop_calibration.json bss +0.3365 n=662; must RE-PROVE on club + realistic lines |
| Shots / SOT / Fouls / Fouls-Drawn rates | HYPOTHESIS | WC marginal (+0.008/+0.005/+0.034/+0.026); thin (1 match/player); club depth should lift |
| Goals/Assists/Cards/Offsides rates | REJECT as bet driver | WC bss negative (-0.025/-0.074/-0.108/-0.016); cut-list CUT 4; model-view only |
| Position-conditioned dispersion + baselines | HYPOTHESIS | deep-dive medium #6; keepers vs outfield clearly need separate phi; gate via OOS |
| Hierarchical / partial-pooling rate model | HYPOTHESIS | deep-dive bigger-bet #8; replace capped linear blend with player<position<league prior |
| Joint/correlated props (copula, shared latent) | HYPOTHESIS | deep-dive bigger-bet #10; price SGP correlation books misprice (P5); full stat-pair validation |

### TEAM-PROP (corners / cards) levers -- NOT YET BUILT
| Lever | Verdict | Evidence |
|---|---|---|
| Per-team corners/cards NB rate | HYPOTHESIS | match_stats.parquet has 25,834 rows of team corners (mean 5.46) + cards (mean 1.84); deep, unmodeled |
| Referee cards fixed effect | HYPOTHESIS | match_stats has referee column; known real signal; must be leak-free (ref prior matches only) |

### IN-GAME lever -- NOT BUILT
| Lever | Verdict | Evidence |
|---|---|---|
| Live scoreline re-pricing (time-scaled lambdas) | HYPOTHESIS | scoreline_matrix re-feedable; P2 the decisive lever; no club live feed yet |

## Prioritized lever queue (do in this order)
1. INGEST club per-player box (5 leagues, multi-season) -- unblocks every prop lever (data, not model).
2. RE-PROVE Saves on club data at REALISTIC DFS lines (2.5/3.5) -- the proven-WC stat, biggest head start.
3. CAPTURE closing prop lines -> wire CLV into prop_paper -- without this NO prop graduates past calibration.
4. BUILD team corners/cards props on the 25,834-match corpus -- the deepest-N, least-attended pocket.
5. RE-TEST opponent-adjust as club data grows -- currently a measured null; deep club data may revive it.
6. MEASURE live-board minute error (backtest with PROJECTED not realized minutes) -- converts an
   unmeasured risk into a measured one; will honestly re-tier some stats down.
7. Position-conditioned dispersion; then hierarchical rates; then joint/correlated props (each OOS-gated).
8. (Bigger bet) club in-game repricing -- highest ceiling, most build.

## Honesty notes
Only 2 levers are SHIP-as-calibration (rate mechanism, dispersion) and 1 stat is CALIBRATION-PROVEN
(WC Saves). Two levers are explicit MEASURED REJECTS (opponent-adjust null, isotonic overfit) --
recorded as knowledge per proof-standards. Everything club-specific is HYPOTHESIS until the club
ingest + cache exist. No $ edge anywhere; team markets are a standing REJECT for $ (CUT 1).
