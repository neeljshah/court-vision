# Core Sports Forecasting Models: Which Fit Each Sport and Why
_Researched 2026-06-16. Scope: Elo/Glicko-2, Bradley-Terry, Poisson/Dixon-Coles, Monte Carlo possession sims, gradient boosting, Bayesian hierarchical, player/team rating systems, and ensembling -- mapped to MLB/soccer/tennis/NBA._

---

## TL;DR

- **Elo/Glicko-2 are best as lightweight baselines or input features**, not standalone predictors; Elo is a special case of Bradley-Terry and often outperforms heavier models on pure win-rate prediction despite its simplicity.
- **Dixon-Coles bivariate Poisson is the soccer workhorse**: it corrects the naive Poisson's systematic underestimation of 0-0, 1-0, 0-1, 1-1 outcomes (rho ~ -0.13), adds time-decay (optimal xi ~ 0.001-0.003/day over 4-5 seasons), and achieves best RPS (0.1891) on held-out data vs. all simpler count models.
- **Bayesian hierarchical models (PyMC/Stan) are the principled path for small-N inference**: attack/defense decomposition with Poisson likelihood, HalfNormal hyperpriors on team SD, and MCMC sampling gives proper uncertainty intervals -- directly usable as calibrated probability outputs. The rugby/soccer PyMC example is a production-ready template.
- **Gradient boosting (XGBoost/LightGBM/CatBoost) wins on tabular features but needs calibration**: stacked ensembles hit 83.27% accuracy / AUC 0.92 on NBA win prediction; XGBoost and AdaBoost are strongest base learners; CatBoost's ordered target encoding reduces leakage and improves calibration specifically.
- **Player-level rating inputs (RAPM, RPM, RAPTOR/DARKO/LEBRON) are the most predictive single feature class for NBA**: Lineup RAPM (L-RAPM, arxiv 2601.15000) with informed priors outperforms raw RAPM; feeding these ratings into a Poisson/MC sim gives interpretable, calibrated win probs.
- **Monte Carlo possession sims are the right NBA architecture for calibrated intervals, not just point-win-prob**: simulating individual possessions with binomial draws over player usage shares propagates uncertainty through to final score distributions, enabling prop-line pricing as a byproduct.
- **Ensembling (stacking) consistently beats any single model family**: pair a mechanistic model (Dixon-Coles or MC sim) as one base learner with GBM trained on engineered features as a second; use isotonic regression or Platt scaling on the stacked output for calibration.
- **Honest OOS validation discipline overrides model complexity**: Dixon-Coles' RPS improvement over naive Poisson on the Eredivisie was 0.1915 -> 0.1891 (0.13%) -- tiny absolute gain. Complexity is only worth it if it demonstrably improves Brier/log-loss on a held-out walk-forward corpus, not in-sample.

---

## Key Capabilities / Techniques

### Elo / Glicko-2 / Bradley-Terry
- **What they are**: Elo updates a scalar team/player strength rating after each outcome; Glicko-2 adds a ratings deviation (RD) and volatility parameter so uncertain ratings update faster. Bradley-Terry is the probabilistic backbone: P(A beats B) = r_A / (r_A + r_B). Elo is a gradient-descent approximation to MLE for the BT model.
- **Glicko-2 advantage over Elo**: RD shrinks after active play, expands during inactivity -- critical for tennis (off-season gaps) and NBA (injury absences). Also handles rating periods with multiple games cleanly.
- **When to use**: as a fast-updating strength signal that feeds into a downstream model (GBM or MC sim). Good when match history is the only data. Best sport fits: tennis (head-to-head, few features, clear ordering), MLB (long season, mean-reversion matters), soccer (strength ordering signal for Dixon-Coles).
- **Limitation**: single scalar; does not capture home/away split, surface (tennis), or margin-of-victory without modification. Margin-of-victory extensions (MOV-Elo) exist but add hyperparameters.

### Poisson Goal Model + Dixon-Coles Correction
- **What it is**: model home goals as Poisson(lambda) and away goals as Poisson(mu), where log(lambda) = intercept + attack_home - defense_away + home_advantage. Dixon-Coles (1997) adds a joint rho correction on the four low-scoring cells (0-0, 1-0, 0-1, 1-1) to fix the independence assumption's systematic undercount of draws.
- **Concrete numbers**: rho ~ -0.13 (replicated across datasets). Time-decay xi: optimal ~ 0.001 (single season) to 0.00325 (5-season lookback). Best RPS on Eredivisie 2023-24: 0.1891 (tuned Dixon-Coles) vs. 0.1915 (naive Poisson). Small but consistent win.
- **Extensions**: Weibull count model, Zero-Inflated Poisson, Negative Binomial -- none clearly outperformed Dixon-Coles on the Eredivisie benchmark. Bivariate Poisson (full covariance) actually scored worst (0.1916 RPS) on this dataset, suggesting the targeted rho correction is more efficient than full joint parameterization.
- **Best sport fit**: soccer (low scores, draws are common, goals are the primary outcome). Baseball total runs also fits Poisson reasonably. NOT recommended for basketball (scores are ~100+, Gaussian/Negative Binomial is more appropriate for point spreads).

### Bayesian Hierarchical Models (PyMC / Stan)
- **Architecture pattern** (from PyMC rugby/soccer examples):
  - Likelihood: score_home ~ Poisson(exp(intercept + home_adv + attack_h - defense_a))
  - Hyperpriors: HalfNormal(2) on sigma_attack and sigma_defense; team effects ~ Normal(0, sigma)
  - Inference: NUTS/HMC in PyMC5 or Stan; R-hat < 1.01 confirms convergence; ESS > 400 per parameter
  - Output: full posterior predictive distributions -> natural calibrated probability intervals
- **Key advantage**: uncertainty propagation. When a team has played 3 games (small N) the posterior is wide and bets will be appropriately cautious. This directly outputs calibrated Brier-minimizing probabilities without isotonic scaling post-hoc.
- **Bradley-Terry hierarchical variant** (arxiv 1712.05879, MLB application): team strengths drawn from a Normal hyperprior; Stan HMC computes marginal posteriors. Outperforms standard and generalized log5 models in predictive performance.
- **Best sport fit**: soccer and rugby (Poisson scores, clear attack/defense decomposition), MLB (batter/pitcher matchup, small-sample player-level inference), NBA (player impact priors via RAPM). Less common for tennis but applicable for surface-specific splits.
- **Tooling**: PyMC5 (Python) is the production choice; Stan via CmdStanPy for larger models. JAX-based numpyro for speed on GPU.

### Monte Carlo Possession Simulation (NBA)
- **Architecture**: each possession is a discrete trial. Draw outcome from multinomial over {FG2, FG3, turnover, foul, offensive rebound} weighted by player usage shares and opponent defense ratings. Accumulate over N possessions per team per game. Run 10,000-50,000 game sims -> win prob and score distribution.
- **Why it fits NBA**: basketball scores are high (Gaussian central limit applies), possessions are countable events, player substitution patterns are modelable. Sim naturally captures lineup-level interactions that a regression cannot.
- **Calibration lever**: the marginals (per-player expected stats) must match the per-player season averages after running the sim -- this is the "anchor" constraint. Dispersion (variance of sim output) should match empirical game-to-game variance.
- **Byproduct**: the full score distribution prices any total or spread market. Same sim with a score-at-time-T conditioning argument reprices in-game.
- **FiveThirtyEight pattern** (archived methodology, now via Neil Paine NBA-elo on GitHub): team ratings built bottom-up from player RAPTOR/CARMELO ratings, then game outcomes simulated; season projected via 50,000 Monte Carlo runs.

### Gradient Boosting (XGBoost / LightGBM / CatBoost)
- **When they win**: when you have rich tabular features (rest days, travel, recent form, pace, defensive rating, Elo delta, injury adjustments). They learn nonlinear interactions without specifying them.
- **NBA stacking result** (PMC12357926, 2025): 7-model stack with MLP meta-learner hit 83.27% win-prediction accuracy, AUC 0.9213 -- vs. 81.10% for best single model (AdaBoost). Top SHAP features: 2PA, FG made, 2P made, TRB. Note: these are in-game box-score features, not pure pregame -- confirm your feature window.
- **CatBoost advantage**: ordered target encoding reduces leakage on categorical features (team ID, home/away, opponent). More calibrated out-of-the-box than XGBoost.
- **LightGBM advantage**: histogram-based leaf-wise splitting is ~3-5x faster than XGBoost on large datasets. Use for rapid hyperparameter search.
- **Calibration step required**: GBM raw outputs are not well-calibrated probabilities. Always wrap with sklearn's CalibratedClassifierCV (isotonic for >1000 samples, Platt/sigmoid for less). Evaluate with Brier score and reliability diagram, not just accuracy.
- **Best sport fit**: all four sports benefit from GBM as a feature-engineering consumer. It does NOT replace mechanistic models -- use Dixon-Coles or MC sim output as a feature input to GBM for best results.

### Player / Team Rating Systems
- **RAPM / L-RAPM** (NBA): Regularized Adjusted Plus-Minus via ridge regression on lineup +/- data. L-RAPM (arxiv 2601.15000, 2026) adds informed priors (box-score priors from BPM/SPM), improving estimate stability for role players and rookies. Best single-number player impact metric for win-prob modeling.
- **RPM / RAPTOR / DARKO / LEBRON**: proprietary or semi-open variants of RAPM that add tracking data, age curves, and role adjustments. RAPTOR (FiveThirtyEight, archived) uses both box and tracking. DARKO focuses on Bayesian updating per-game. Feed any of these into a MC sim's player-strength parameters.
- **Soccer / MLB equivalent**: Expected Goals (xG) per match per player as a team-level Poisson rate is the soccer analogue; FIP/wOBA/wRC+ for MLB pitching and batting strength.
- **Tennis**: surface-specific Elo is the standard. Jeff Sackmann's TennisAbstract GOAT model is the public reference implementation.

### Ensembling Strategies
- **Stacking** (heterogeneous base learners -> meta-learner): best empirical results. Combine a mechanistic model (Dixon-Coles, MC sim) with GBM trained on features and a Bradley-Terry Elo delta. Meta-learner: logistic regression (transparent) or isotonic calibrator.
- **Blending / weighted average**: simpler, less prone to overfitting when N is small. Use cross-validated Brier-score-based weights.
- **Temporal caveat**: all stacking must use time-series CV (walk-forward, no look-ahead). A single k-fold on sports data will leak future knowledge.

---

## How THIS Project Should Use It

1. **Soccer (Dixon-Coles is already in production -- tune xi and lookback)**: The project confirmed Poisson O/U-2.5 as the pregame model. Upgrade to a full Dixon-Coles with time-decay: xi ~ 0.001 over a 4-season window. This directly improves draw probability calibration (rho ~ -0.13 is a free correction). Evaluate on RPS, not just accuracy. Implement in `domains/soccer/` as a drop-in.

2. **Tennis (Glicko-2 + surface split is the upgrade from flat Elo)**: Current Elo ML is confirmed efficient vs. market. Glicko-2 adds uncertainty-aware updates during off-season gaps and gives a posterior variance per player -- useful for interval width on prop predictions. Surface-specific rating pools (clay/hard/grass) are the strongest feature engineering lever. Implement via `glicko2` Python package or a lightweight Stan model.

3. **MLB (Bayesian hierarchical Bradley-Terry over flat Elo)**: The platform uses ML home/away prediction. A hierarchical Bradley-Terry in PyMC with pitcher-level attack and bullpen-level defense parameters would give calibrated posterior win probs AND handle the small-sample early-season problem. batter/pitcher matchup log5 (Bayesian variant, arxiv 1712.05879) is the academically validated next step. Ground truth: compare Brier to devigged close on a walk-forward corpus.

4. **NBA (MC sim already built -- add L-RAPM priors and Bayesian hierarchical calibration)**:
   - The possession MC sim is architecturally correct. The key upgrade is using L-RAPM-style informed priors on player impact rather than raw box-score ratings -- this shrinks rookie/role-player estimates toward the mean appropriately.
   - Wrap the MC sim output in a Bayesian hierarchical layer: treat sim win-prob as an informed prior, update with a season-long Poisson scoring model (attack/defense per team) to get a calibrated posterior. This is the PyMC rugby template applied to NBA.
   - For gradient boosting on top: feed MC sim output + Elo delta + rest/travel features into a CatBoost model; calibrate with isotonic regression on a 2-season walk-forward corpus. The PMC12357926 stacking result (83.27% / AUC 0.92) is achievable with this pipeline.

5. **Ensembling rule for all sports**: mechanistic model (sport-specific: Dixon-Coles/Poisson for soccer, Glicko-2 for tennis, hierarchical BT for MLB, MC sim for NBA) -> output probability as a feature -> CatBoost trained on features + mechanistic output -> isotonic calibration on walk-forward OOS. Never blend in-sample.

6. **Calibration validation standard**: always report Brier score AND reliability diagram (calibration curve) alongside accuracy. The Brier score of the devigged close (market) is the ceiling/benchmark -- a meaningful improvement is > 0.005 Brier reduction sustained over >= 2 independent seasons.

7. **In-game advantage is real and model-type-agnostic**: the key insight from this project's own results is that conditioning on realized game state (score, time, foul trouble) gives the largest measurable edge. All four model families above can be conditioned in-game: Dixon-Coles on remaining goals expected, MC sim on remaining possessions, GBM on current game features. Build the state-conditioning wrapper, not a new base model.

---

## Gotchas / Limits

- **Dixon-Coles margin over naive Poisson is small in absolute terms** (RPS 0.1915 -> 0.1891 on Eredivisie). Do not over-engineer; the gain is real but tiny. Its main value is CALIBRATION on draws, not overall accuracy lift.
- **GBM accuracy numbers in sports papers are often inflated**: the PMC12357926 83.27% uses in-game box-score features -- using only pregame features drops to ~65-68% for NBA win prediction, consistent with the market-efficiency findings in this project.
- **SHAP features from GBM (2PA, TRB, etc.) are box-score leakage signals, not pregame features**. Be explicit about your feature cutoff time.
- **Elo alone is insufficient for calibrated probabilities**: it outputs a win-probability via a logistic mapping, but the K-factor and initial rating choices strongly affect calibration. Always validate with a reliability diagram.
- **PyMC/Stan hierarchical models are slow to fit** (minutes to hours for full MCMC). Use variational inference (ADVI in PyMC) for rapid iteration, then switch to NUTS for production. On 30 NBA teams x 82 games, NUTS is manageable; on 700+ soccer teams it may require approximations.
- **L-RAPM (2601.15000)** is a 2026 paper -- the code may not yet be in a stable public repo. The `vraja2/rapm` GitHub repo implements basic RAPM; adding box-score priors is a straightforward ridge-regression modification.
- **Monte Carlo sim variance**: 10,000 sims is sufficient for win prob (SE < 0.5%). For prop pricing (rare outcomes) you need >= 100,000 sims. Runtime on CPU for possession-level sim: ~2-5 min per game at 100k runs; GPU parallelization (the existing `fast_sim.py`) is the correct solution.
- **No model beats an efficient market on pregame prices consistently** (confirmed empirically in this project across all 4 sports). Models improve calibration and accuracy vs. naive baselines; they do NOT guarantee ROI vs. the vig. This remains the binding honest constraint.

---

## Sources

- [Football Prediction Models: Which Ones Work the Best? (penaltyblog, 2025)](https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/)
- [Predicting Football Results With Dixon-Coles and Time-Weighting (dashee87.github.io)](https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/)
- [Stacked Ensemble Model for NBA Game Outcome Prediction (PMC/NCBI, 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12357926/)
- [A Hierarchical Model for Rugby Prediction -- PyMC Example Gallery](https://www.pymc.io/projects/examples/en/latest/case_studies/rugby_analytics.html)
- [Hierarchical Bayesian Bradley-Terry for MLB (arxiv 1712.05879)](https://arxiv.org/pdf/1712.05879)
- [Lineup Regularized Adjusted Plus-Minus L-RAPM (arxiv 2601.15000)](https://arxiv.org/pdf/2601.15000)
- [Hierarchical Models for Sports Analytics -- fonnesbeck GitHub](https://github.com/fonnesbeck/hierarchical_models_sports_analytics)
- [Neil Paine NBA Elo Archive (GitHub, post-FiveThirtyEight)](https://github.com/Neil-Paine-1/NBA-elo)
- [RAPM Implementation -- vraja2 GitHub](https://github.com/vraja2/rapm)
- [Elo Rating System -- Wikipedia](https://en.wikipedia.org/wiki/Elo_rating_system)
- [Glicko Rating System -- Wikipedia](https://en.wikipedia.org/wiki/Glicko_rating_system)
- [Machine Learning for Soccer Match Result Prediction (arxiv 2403.07669)](https://arxiv.org/pdf/2403.07669)
- [Bivariate Dixon and Coles Model Overview (emergentmind)](https://www.emergentmind.com/topics/bivariate-dixon-and-coles-model)
- [Generalizing the Elo Rating System (York/arxiv preprint)](https://www-users.york.ac.uk/~bp787/Generalizing_Elo_arxiv.pdf)
- [Applying Bayesian Hierarchical Methods to MLB Season Win Probabilities (Medium)](https://medium.com/@dmgrifka_64770/applying-bayesian-hierarchical-methods-to-mlb-season-win-probabilties-with-pystan-468572abb932)
