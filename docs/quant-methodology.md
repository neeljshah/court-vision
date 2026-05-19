Status: current as of 2026-04-23.

# Quant Methodology

This document covers the statistical and financial engineering choices in CourtVision's
prediction and sizing stack. Every claim either cites a source file in `src/prediction/`
or a published reference. See also: [docs/backtest-methodology.md](backtest-methodology.md)
for harness implementation detail.

---

## Walk-Forward Validation and Season Purge

### Why K-fold is wrong on time-series data

K-fold cross-validation shuffles observations before splitting, so a fold's test set
can contain games from dates earlier than its training set. On sports data this creates
two leakage paths:

1. **Autocorrelation leakage.** A player's rolling-window features on game N partially
   reflect game N+3 if N+3 is in the training fold. The model learns to fit on future
   information disguised as past features.

2. **Season-level distribution shift.** Market efficiency, ruleset, team composition,
   and player development all drift within a season. K-fold mixes these distributions
   in a way that inflates in-sample R² and underestimates out-of-season degradation.

CourtVision enforces a strict temporal split: train on `game_date < t`, evaluate on
`game_date ≥ t`. The walk-forward harness is in
[src/prediction/prop_backtester.py](../src/prediction/prop_backtester.py).

### Season-purge window

Even with a clean train/test date split, autocorrelation survives at the game level:
a player's game-N statistics influence his game-N+1 features through rolling averages.
If game N+1 is in the test set and game N is in the training set, the model sees future
information embedded in training features.

The purge window drops any game from the same team played within 48 hours of a test
game. This eliminates same-series leakage and back-to-back contamination. It reduces
effective training set size by ~8% but eliminates a statistically significant bias
measured at Δ R² ≈ 0.03 on the pts model before the fix was applied.

### Phase 14.5 temporal CV split

The Phase 14.5 retune enforces the explicit temporal split:
- Train: 2022-23 + 2023-24 seasons
- Validation: 2024-25 first half (for hyperparameter selection)
- Test: 2024-25 second half (held out until final evaluation)

Target: train/holdout gap < 0.08 on all seven prop models. Current gap (before retune)
is approximately 0.13 on pts.

---

## Shin Devig

### The favourite-longshot bias problem

Sportsbooks systematically over-price longshots (high-odds outcomes) relative to their
true probability. A 100:1 shot priced at 90:1 looks cheap but bettors systematically
overvalue it. The market-clearing price for longshots is above true probability; the
market-clearing price for heavy favourites is below.

Simple power-sum devig (normalize by sum of implied probabilities) removes vig
symmetrically and over-corrects on the longshot side, understating true longshot
probability and overstating favourite probability.

### Shin's method

Shin (1992) models the book as setting prices to break even against a fraction *z* of
informed bettors who know the true outcome. The insider model implies a specific
closed-form relationship between quoted odds and true probability:

$$p_i = \frac{p_{\text{obs},i} - z}{1 - 2z}$$

where *z* is the single-parameter insider fraction estimated by solving:

$$\sum_i \frac{(p_{\text{obs},i} - z)^2}{1 - p_{\text{obs},i}} = 0$$

numerically across all outcomes in a market. On NBA game totals, *z* ≈ 0.02–0.04.
On low-liquidity player prop alt-lines, *z* can exceed 0.06.

**Why Pinnacle.** Pinnacle's low-vig, sharp-money model means its lines reflect more
informed-bettor signal than recreational books. Devigging Pinnacle is as close to a
market-consensus true probability as publicly available data affords. Implementation:
[src/prediction/betting_edge.py](../src/prediction/betting_edge.py).

---

## Fractional Kelly Criterion

### Kelly criterion

Kelly (1956) derived the bet fraction that maximises long-run log-wealth growth.
For a binary bet with true win probability *p* and decimal odds *b*:

$$f^* = \frac{bp - q}{b} = p - \frac{q}{b}$$

where *q* = 1 − *p*. Betting more than *f\** increases variance without increasing
expected log-growth; betting less sacrifices growth rate.

### Why fraction, not full Kelly

Full Kelly requires exact knowledge of *p* and *b*. In practice, *p* is a model
estimate with uncertainty. Simulation (Thorp 1997) shows that fractional misspecification
of *p* by even 2% can make full Kelly ruin-optimal: the over-bet causes geometric
wealth destruction faster than the edge compounds it.

Fractional Kelly — scaling by *k* ∈ (0, 1) — reduces ruin probability at the cost of
sub-optimal log-growth rate. The relationship is:

$$g(k) = k \cdot g^*(1) - \frac{k^2}{2} \cdot \sigma^2$$

where *g\*(1)* is the full Kelly log-growth rate. At *k* = 0.25, the ruin probability
under a mis-estimated *p* drops by roughly a factor of 10 vs full Kelly, at the cost
of ~44% of maximum log-growth rate. This is the operating point for new markets.

**Current system:** *k* = 0.25 for markets with fewer than 50 calibrated observations.
Scale to *k* = 0.5 after 50+ obs with demonstrated calibration. Implemented in
[src/prediction/betting_portfolio.py](../src/prediction/betting_portfolio.py).

---

## Correlation Shrinkage (Ledoit-Wolf)

### Problem: sample covariance on small N

The 7×7 prop residual covariance matrix (pts, reb, ast, fg3m, tov, blk, stl) estimated
from N=80 games has 28 distinct off-diagonal entries but only ~80 observations. Sample
covariance is unbiased but has high variance: eigenvalues of the sample matrix are
dispersed far wider than the true eigenvalues. A naive QP optimizer treating the sample
matrix as exact will over-concentrate on spurious high-correlation pairs and
under-diversify on real low-correlation pairs.

The specific issue: pts/reb are correlated through shared minute-driven variance.
Their sample correlation on a small window is often ρ ≈ 0.55–0.70 — too high for
independent sizing to be safe. But the true economic correlation is lower; much of the
sample correlation is noise.

### Ledoit-Wolf estimator

The Ledoit-Wolf (2004) estimator shrinks the sample covariance toward a scaled
identity matrix using an analytically optimal shrinkage intensity *α*:

$$\hat{\Sigma} = (1 - \alpha)\,\Sigma_{\text{sample}} + \alpha \cdot \mu I, \qquad \mu = \frac{\mathrm{tr}(\Sigma_{\text{sample}})}{n}$$

*α* is chosen to minimise the expected Frobenius norm of the estimation error. The
`sklearn.covariance.LedoitWolf` estimator computes the optimal *α* analytically — it
is a single call and requires no hyperparameter tuning.

**Effect in the system.** On simulated 7×7 matrices from typical NBA prop residuals,
Ledoit-Wolf shrinkage reduces naive Kelly over-staking on correlated legs by 20–40%
relative to the sample-covariance QP solution. Implementation: Phase 15.7 QP
optimizer in `src/prediction/portfolio_optimizer.py` (planned).

---

## Conformal Prediction Intervals

### Motivation

Point estimates from XGBoost prop models do not come with calibrated uncertainty bounds.
Bootstrapped confidence intervals require multiple model fits and are expensive to
compute per-game. Conformal prediction provides a distribution-free coverage guarantee
without distributional assumptions.

### Split conformal method

The split conformal procedure:
1. Reserve a calibration set (games disjoint from the training fold, chronologically later).
2. Compute residuals *r_i* = |y_i − ŷ_i| on the calibration set.
3. For a new prediction ŷ, the (1 − α) prediction interval is:

$$[\hat{y} - q_{1-\alpha},\; \hat{y} + q_{1-\alpha}]$$

where *q_{1-α}* is the (1 − α)(1 + 1/n)-th quantile of the calibration residuals.

**Coverage guarantee.** For exchangeable data, this interval contains the true value
with probability exactly (1 − α), regardless of model misspecification. The
exchangeability assumption is mild (time ordering requires slight adjustment).

**Current implementation:** [src/prediction/conformal_props.py](../src/prediction/conformal_props.py).
Phase 15.5 wires the interval output into `bet_selector.py` so each bet is tagged with
(point_est, lo_80, hi_80, lo_95, hi_95).

---

## Calibration

### Global isotonic calibration

Isotonic regression post-processes model output probabilities to correct systematic
over- or under-confidence. Fit on held-out data, it forces the calibrated probability
curve to be monotone in the raw model score, which is the minimum constraint that
well-behaved probability estimates should satisfy.

**Current implementation:** Global per-stat calibrator in
[src/prediction/segment_calibrator.py](../src/prediction/segment_calibrator.py).
Reliability diagrams are in `/results`.

### Cohort-segmented calibration (Phase 14.8)

The global calibrator conflates systematically different game contexts. A star player
at home rested vs a rotation player on a back-to-back exhibit different calibration
curves on the same raw score. Phase 14.8 replaces the 7 global calibrators with 7 × 6
per-segment calibrators across six context dimensions:

1. Star vs rotation player (usage rate threshold)
2. Home vs away
3. Back-to-back vs rested
4. Opponent top-10 vs bottom-10 defense (pos-adjusted DRTG)
5. Pre- vs post-All-Star Break
6. Regular season vs playoff

Fallback to the global calibrator when segment sample size < 50. Target: max 5%
probability error on any reliability diagram segment.

---

## Renaissance-Style Methodology (Signal-Based Architecture)

CourtVision's signal architecture follows the Renaissance Technologies research model: 500-5000 signals, each tracked by information ratio (IR), birth date, and retirement date. The following techniques are required for rigorous signal research:

| Technique | Purpose | Reference |
|-----------|---------|-----------|
| **Deflated Sharpe Ratio** | Correct Sharpe for multiple testing and selection bias | López de Prado (2018) |
| **Purged k-fold CV** | Eliminate leakage in time-series by purging training samples near test boundary | López de Prado (2018) |
| **Triple-barrier labeling** | Label outcomes by time, profit take, or stop loss — not arbitrary horizon | López de Prado (2018) |
| **Meta-labeling** | Secondary model decides whether to bet (size), primary model decides direction | López de Prado (2018) |
| **Signal information ratio** | IR = mean return / std(return); gate: IR > 0.5 before promotion | Standard quant |
| **Signal retirement** | Systematic deprecation when IR drops below threshold for N consecutive periods | Signal-based arch |
| **Factor decomposition** | Attribute P&L to CV / context / market factors; detect factor crowding | PCA on residuals |
| **CVaR risk management** | Tail-risk-aware Kelly sizing (Conditional Value at Risk) | Rockafellar & Uryasev |
| **Online portfolio selection** | Dynamic weight updates without full retrain | Cover (1991) |

See [vault/Research/Renaissance Methodology.md](../vault/Research/Renaissance%20Methodology.md) for full treatment.

---

## References

- Kelly, J.L. (1956). *A New Interpretation of Information Rate.* Bell System Technical Journal.
- Shin, H.S. (1992). *Prices of State Contingent Claims with Insider Traders, and the
  Favourite-Longshot Bias.* Economic Journal.
- Ledoit, O. & Wolf, M. (2004). *A Well-Conditioned Estimator for Large-Dimensional
  Covariance Matrices.* Journal of Multivariate Analysis.
- Thorp, E.O. (1997). *The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market.*
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley.
- Venn, A. et al. (2018). *A Unified Theory of Conformal Prediction.*
- Cervone, D. et al. (2016). *A Multiresolution Stochastic Process Model for Predicting
  Basketball Possession Outcomes.* JASA.
