Status: current as of 2026-06-18.

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
optimizer in `scripts/team_system/portfolio_optimizer.py`.

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
curves on the same raw score. Phase 14.8 replaces the 7 global calibrators with
per-segment calibrators across eight segments (`src/prediction/segment_calibrator.py`
SEGMENTS list):

1. Star
2. Role (rotation player)
3. Back-to-back
4. Early season
5. Home
6. Road
7. Post-injury return
8. Post-trade

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

See [_vault_legacy_archive/Research/Renaissance Methodology.md](../_vault_legacy_archive/Research/Renaissance%20Methodology.md) for full treatment.

---

## The Validation Toolkit -- each technique, what it catches, how it is implemented

> Every claim in this repo is a CALIBRATION / SHARPNESS measurement (Brier, RMSE, ECE),
> never a $ edge or ROI. The techniques below are the instruments that decide whether a
> candidate is a real lift or an artifact. An honest REJECT / NULL is a SUCCESS: it is the
> correct output of the framework on an efficient market. Path refs are to the real,
> read-only code that implements each test. See [docs/PROOFS.md](PROOFS.md) for the
> claim -> runnable-proof index and [docs/MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md)
> for the full efficiency result.

| Technique | What it catches | How it is implemented | Path |
|---|---|---|---|
| **Expanding-window walk-forward** | Lookahead / future leakage; in-sample R^2 inflation; over-fit that does not survive out-of-time | Sort states by timestamp; for each test state, train only on states strictly earlier; collect per-state probabilities for scoring. The harness never trains a model -- it orchestrates the leak-free split. | `scripts/platformkit/eval_gate/walkforward.py`; `src/loop/gate.py::_fold_bounds` / `walk_forward_delta` |
| **Purge + embargo** | Same-team back-to-back autocorrelation; rolling-window spillover across the train/test boundary | Drop same-team games within `PURGE_HOURS=48` of the test game; drop the same matchup within `EMBARGO_DAYS=3` of the boundary | `scripts/platformkit/eval_gate/walkforward.py` (`_same_team`, `_same_matchup`) |
| **Vintage / availability assertion** | A feature secretly known only after the prediction time (the most common silent leak) | `assert_vintage` asserts every feature's availability timestamp is strictly before the prediction `state_ts`; raises an `AssertionError("LEAK: ...")` that the gate converts into a hard FAIL | `scripts/platformkit/eval_gate/walkforward.py::assert_vintage` |
| **Truncation-invariance leak test** | Streaming / in-game features that peek at future events -- a feature at time T must be byte-identical with or without later events | Re-featurize a truncated event stream and assert past rows are byte-identical | `tests/test_ingame_leak_free.py` (per JOB_EVIDENCE_PACKET) |
| **Permutation null-shuffle (G3)** | A signal whose lift is coincidental row-alignment rather than real predictive content | Permute the signal column (breaks alignment, preserves marginal distribution); re-run the ablation; require the real (negative) delta to beat the null cloud by `z >= 3.0` standard deviations | `src/loop/gate.py::null_shuffle_control` |
| **Noise / p0 control** | A pipeline that "improves" even on pure noise (a broken harness) | The null-shuffle's permuted column is the noise control: a correct harness produces ~0 mean delta on shuffled input; a positive shuffled delta exposes a leak in the harness itself | `src/loop/gate.py::null_shuffle_control` (the `null_deltas` cloud) |
| **Ablation vs full** | A signal that looks predictive alone but adds nothing once the full production feature matrix already explains it | Train FULL vs FULL+signal on a single chronological holdout (last 25%); require relative holdout improvement `<= -_ABLATION_REL_EPS`. NEVER scores the signal in isolation. | `src/loop/gate.py::ablation_vs_full` |
| **Benjamini-Hochberg FDR** | False discoveries from testing many candidates (multiple-comparisons inflation) | Rank all tested p-values; reject only those with `p <= (rank/m) * q`, `q=0.10`, across the FULL experiment history bookkept by the ledger | `src/loop/gate.py::benjamini_hochberg` |
| **Cluster-robust Diebold-Mariano** | Fake significance from i.i.d. SE when many states within one game are correlated (a naive SE runs ~3x too narrow) | DM on per-state loss differences `d_t = loss_close - loss_model`, clustering the variance by `game_id` with a `G/(G-1)` finite-cluster correction; two-tailed p via `erf` (no scipy) | `scripts/platformkit/eval_gate/dm_test.py::diebold_mariano` |
| **>=2-corpora replication** | A single-corpus / single-fold lift masquerading as durable (single-fold lifts are artifacts) | Require the lift to hold across `min_folds` folds in the primary corpus AND in `min_corpora >= 2` independent corpora; a loss on any fold/metric is a hard REJECT | `improve/multifold_guard.py::replicated` |
| **Multi-seed bootstrap stability** | A metric jump driven by one lucky random seed | Bootstrap-resample under 8 seeds x `n_boot` draws; `stable=True` only when the p10 lower bound of the improvement distribution is `>= 0` (the lift survives the unlucky tail) | `improve/seed_stability.py::stable` |
| **All-proper-scores unanimity** | Shipping a candidate that wins one proper score while silently regressing another (the most expensive self-improvement bug) | `score_gate` compares Brier+log-loss (prob) or CRPS+pinball (interval); ships ONLY if the candidate does not regress ANY applicable proper score beyond `_EPS`; names the dissenting score on reject | `improve/proper_score_gate.py::score_gate` |
| **RMSE + signed bias, never MAE** | MAE rewards shrink-to-median artifacts (predicting the conditional median lowers MAE without sharpening) | Point forecasts are graded on RMSE and signed bias, never MAE | enforced across the `proof_<sport>/` harnesses (see PROOFS) |
| **CLV over ROI** | ROI's huge small-N standard error hiding (or manufacturing) an apparent edge | CLV against the Shin-devigged sharp close is approximately unbiased and converges ~5x faster than ROI; CLV is measured FORWARD, never claimed retrospectively. When no captured close exists yet, CLV is NON-BLOCKING (recorded pending), never a false fail. | [docs/backtest-methodology.md](backtest-methodology.md); `src/loop/gate.py::clv_check` |
| **Import-isolation (F5)** | A sport adapter that secretly depends on another sport's code or on `src.data`/`src.sim` | Each sport's `run_proof.py` imports zero other-sport domain code and zero `src.data`/`src.sim`/`src.tracking`/`src.pipeline` | `scripts/platformkit/proof_<sport>/run_proof.py` |

### Why these compose, not just stack

The instruments are layered so that an artifact must defeat ALL of them to ship. A signal
that overfits one calendar half is caught by the >=2-corpora replication guard; one that
rides a lucky seed is caught by the bootstrap p10 floor; one that wins Brier but loses
log-loss is caught by the all-proper-scores unanimity rule; one that wins in isolation but
adds nothing to the full model is caught by ablation-vs-full; one that survives by chance
across many tests is caught by Benjamini-Hochberg. The documented track record is that the
candidates correctly REJECT -- the framework's job is to refute, not to confirm.

---

## The honest gatekeeper -- SHIP / VARIANCE_ONLY / DEFER / REJECT

`src/loop/gate.py::evaluate(signal)` runs a candidate through five criteria, evaluated
JOINTLY (criterion 3 measures the marginal delta of adding the signal column to the FULL
production matrix, never the signal alone), and returns one of four verdicts:

| Criterion | Test | Pass condition |
|---|---|---|
| 1. Walk-forward | `walk_forward_delta` -- expanding folds, FULL+signal vs FULL | ALL evaluated folds have `delta_score < 0` (improvement) |
| 2. Null-shuffle | `null_shuffle_control` -- real delta vs shuffled-signal null | real delta beats the null cloud by `z >= 3.0` |
| 3. Ablation vs full | `ablation_vs_full` -- marginal holdout delta on last 25% | relative improvement `<= -_ABLATION_REL_EPS` |
| 4. Calibration | `calibration_check` -- ECE (winprob), 80% coverage (sigma), or residual non-degeneracy (point) | ECE `< 0.10` / coverage in `[0.70, 0.90]` / `|bias| < spread` |
| 5. CLV | `clv_check` vs the sharpest close | `clv >= _CLV_FLOOR`, or NON-BLOCKING `(None, True)` when no close is captured yet |

Plus a multiple-comparisons guard: a per-signal Benjamini-Hochberg p (recomputed across the
full ledger history) and a final held-out set touched EXACTLY ONCE.

**Verdict policy** (from `evaluate`):

| Verdict | When | Meaning |
|---|---|---|
| **SHIP** | `wf_all & null_pass & ablation_pass & calibration_ok & clv_pass & fdr_pass` | Real, replicated, calibrated lift -- promote |
| **VARIANCE_ONLY** | sigma target with calibration+null pass, OR point estimate fails but calibration improves + null + clv pass | The point estimate is not the lever; the interval / Kelly sizing improves -- ship for sizing only |
| **DEFER** | No leak-safe feature matrix could be built, or no evaluable walk-forward fold (rows too few) | INSUFFICIENT DATA -- never a false SHIP; coverage is the blocker, not the signal |
| **REJECT** | Otherwise; `_reject_reason` names every failed criterion | The honest, expected outcome on an efficient market -- recorded as a SUCCESS |

DEFER is the system's INSUFFICIENT_DATA state: the gate fails closed (returns DEFER rather
than guessing) whenever it cannot construct a leak-safe `(base_matrix, signal_column, target,
dates)` bundle or cannot fill a single fold. A thin slice ABSTAINS rather than printing a
result -- see the n<50 ABSTAIN rows in [docs/CALIBRATION_RECORD.md](CALIBRATION_RECORD.md).

### The eval-gate offline contract (regression / leak only)

`scripts/platformkit/eval_gate/run_gate.py --golden` runs the same machinery end-to-end
OFFLINE on the committed SYNTHETIC golden fixture and labels each corpus
`BEATS_CLOSE` / `MATCHES_CLOSE` / `BEHIND` (`_verdict`: BEATS requires `bss>0` AND DM
`p<0.05` AND `n>=200`; MATCHES when the 95% CI on the loss difference overlaps 0; BEHIND
otherwise -- honest, recorded, NON-blocking). Crucially the gate BLOCKS only on a
regression vs the frozen baseline (`brier_model > baseline + 0.005` AND a significant DM
of model-vs-baseline per-game losses) or a leak-guard assertion -- NEVER on "fails to beat
the close". The golden fixture is a synthetic reproducibility anchor, not a real calibration
claim; `BSS <= 0 / MATCHES_CLOSE` is an honest success.

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
- Diebold, F.X. & Mariano, R.S. (1995). *Comparing Predictive Accuracy.* Journal of
  Business & Economic Statistics. (The clustered-SE variant is in `eval_gate/dm_test.py`.)
- Benjamini, Y. & Hochberg, Y. (1995). *Controlling the False Discovery Rate.* JRSS-B.

**Sibling docs:** [backtest-methodology](backtest-methodology.md) (harness construction) -
[PROOFS](PROOFS.md) (claim -> proof index) - [MARKET_EFFICIENCY_PROOF](MARKET_EFFICIENCY_PROOF.md)
(the efficiency result) - [CALIBRATION_RECORD](CALIBRATION_RECORD.md) (per-sport audit) -
[CEILING](CEILING.md) (realistic bounds) - [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) -
[full doc map](INDEX.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
