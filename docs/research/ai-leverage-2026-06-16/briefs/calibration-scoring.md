# Probability Calibration + Proper Scoring for Sports Forecasting
_Researched 2026-06-16. Scope: post-hoc calibration methods, Brier/log-loss decomposition, reliability diagrams, conformal prediction, and the rigorous statistical bar for proving a model beats market-implied probabilities on OOS accuracy/calibration._

---

## TL;DR (5-8 bullets: the highest-leverage takeaways)

- **Calibration and accuracy are different things.** Calibration means "my 70% predictions win 70% of the time." Accuracy (classification) means "I pick the right side most often." A model optimized for calibration generated 69.86% higher average returns vs. an accuracy-optimized model in a controlled NBA study (Walsh & Joshi, 2024) -- but note this is still a betting-profit framing; the correct framing here is that calibration-optimized models produce *better probability estimates*, which is the project's stated goal.
- **The Brier score decomposes into Reliability - Resolution + Uncertainty (Murphy 1973).** Reliability is calibration error; Resolution is discriminative power (sharpness); Uncertainty is the base-rate variance you cannot control. To *prove* your model beats market-implied probs, you must show both lower Reliability (better calibrated) AND competitive or better Resolution -- not just a lower raw Brier.
- **Platt scaling is the right first-pass calibrator for small calibration sets; isotonic regression wins on large sets.** Beta calibration adds asymmetric flexibility. Temperature scaling is neural-net-only (rescales logits before softmax). All require a held-out calibration set fully disjoint from training -- cross-contamination invalidates the calibration.
- **Reliability diagrams are mandatory; ECE is not enough.** ECE is an L1 scalar that hides S-shaped or regime-specific miscalibration. Always plot the diagram (10-bin default, equal-width). The devigged market close is your baseline line -- plot yours and the market's side by side.
- **Use the Diebold-Mariano (DM) test to prove statistical significance** when comparing two scoring rules (Brier or log-loss differences) on the same OOS test set. DM is asymptotically standard normal, handles temporal correlation in forecast errors, and works with any loss -- not just quadratic. Report the p-value, not just the point difference.
- **Conformal prediction gives OOS calibration guarantees without distributional assumptions** (only exchangeability). Conformal win probabilities have been validated on NCAA basketball and shown to be better calibrated than standard methods especially at low-probability tails. This is a real option for this project's in-game layer.
- **The honest evaluation bar:** your model beats market-implied probs if and only if: (a) Brier score on OOS walk-forward is lower than the devigged close Brier, with DM p < 0.05; (b) reliability diagram shows your curve closer to the diagonal; (c) this holds on >= 2 independent corpora/seasons. A single-season gain is likely an artifact.

---

## Key Capabilities / Techniques (concrete: names, what they do, when to use)

### Calibration Methods

**Platt Scaling (Sigmoid Calibration)**
- Fits a logistic function `p = sigmoid(A*f + B)` over raw model scores, with A and B estimated by MLE on a held-out calibration set.
- Two parameters only -> low overfitting risk -> use when calibration set < ~1000 samples.
- Assumes the calibration curve is correctable by a sigmoid; fails if miscalibration is asymmetric or multi-modal.
- scikit-learn: `CalibratedClassifierCV(method='sigmoid')`.
- Preserves ranking (strictly monotonic), so AUC is unchanged.

**Isotonic Regression**
- Non-parametric piecewise-constant monotone mapping via Pool Adjacent Violators (PAV) algorithm.
- Minimizes squared error subject only to monotonicity; no functional form assumed.
- Outperforms Platt scaling empirically when calibration set >= ~1000 samples (RF: 0.9660 vs 0.9551 reliability in benchmarks).
- Risk: overfits on small sets; may introduce ties in output probabilities (can hurt AUC).
- scikit-learn: `CalibratedClassifierCV(method='isotonic')`.
- Use as the upgrade from Platt once you have enough per-sport per-season data.

**Beta Calibration**
- Generalizes Platt by allowing asymmetric sigmoid stretching (three parameters: a, b, c in a beta-link model).
- Handles cases where miscalibration differs between low-probability and high-probability regions -- common in rare-event markets (e.g., underdog heavy moneylines).
- Not in scikit-learn; use the `betacal` PyPI package.
- When to use: when reliability diagram shows the curve deviates asymmetrically from the diagonal (concave above it on one end, convex on the other).

**Temperature Scaling**
- Divides neural network logit vector by scalar T, then applies softmax. T > 1 widens/softens outputs; T < 1 sharpens.
- Single parameter; near-zero risk of overfitting.
- Only applicable to neural networks with accessible logits (PyTorch/TensorFlow). Not applicable to XGBoost, Random Forests, or any ensemble outputting direct probabilities.
- Preserves prediction rankings exactly (monotonic rescaling).

**Adaptive Temperature Scaling (ATS)**
- Predicts a per-sample temperature from model hidden features.
- 10-50% ECE improvement over standard temperature scaling for RLHF-tuned LLMs.
- Relevant if using Claude/LLM outputs as probability estimates in the scheme-prior or intelligence layer.

### Measurement Toolkit

**Brier Score and Murphy Decomposition**
```
BS = (1/n) * sum( (p_i - y_i)^2 )
   = Reliability - Resolution + Uncertainty

Reliability = sum_k (n_k/n) * (p_k_bar - o_k_bar)^2
Resolution  = sum_k (n_k/n) * (o_k_bar - o_bar)^2
Uncertainty = o_bar * (1 - o_bar)
```
- k indexes bins; p_k_bar = mean predicted prob in bin k; o_k_bar = observed frequency in bin k.
- Lower Reliability = better calibrated.
- Higher Resolution = better discriminated (sharper forecasts).
- Uncertainty is fixed by the dataset (cannot improve it).
- To beat the market: need lower Reliability AND at least equal Resolution vs. devigged close.

**Log-Loss (Cross-Entropy)**
```
LL = -(1/n) * sum[ y_i * log(p_i) + (1-y_i) * log(1-p_i) ]
```
- Unbounded; penalizes confident wrong predictions much more severely than Brier (logarithmic vs. quadratic).
- Both Brier and log-loss are *strictly proper scoring rules*: they cannot be gamed by shifting away from true probabilities.
- Report both; a model can improve one while degrading the other.
- For sports, log-loss is more sensitive to confident errors (e.g., a 95% prediction that loses).

**Expected Calibration Error (ECE)**
```
ECE = sum_b (|S_b| / n) * |acc(S_b) - conf(S_b)|
```
- L1 average gap between predicted and empirical probability per bin.
- NOT a proper scoring rule -- use only as a diagnostic, never as the optimization target.
- Standard: 10 equal-width bins. Equal-count binning gives different (often lower) ECE values -- be explicit about which you use.
- ECE < 0.02 is considered very good calibration in the literature.

**Reliability Diagram (Calibration Curve)**
- X-axis: mean predicted probability per bin.
- Y-axis: observed positive rate per bin.
- Perfect calibration: 45-degree diagonal.
- Below diagonal = overconfident; above = underconfident.
- S-shaped = regime-dependent miscalibration (common in sports: model is overconfident in blowouts, underconfident in tossups).
- scikit-learn: `calibration_curve(y_true, y_prob, n_bins=10)`.
- **For this project:** overlay your model's curve vs. the devigged market close's curve on the same axes. If yours is closer to the diagonal across all bins, you have a calibration win.

**Sharpness**
- Separate from calibration: sharpness is how spread out / extreme your predictions are (how far from 50%).
- A sharper model that is also well-calibrated is better than a less sharp one.
- The market has high sharpness (odds often near extremes for mismatches). Your model needs to match or exceed market sharpness to beat it.
- Operationalize: compare variance of predicted probabilities; or compare Resolution components of Brier decomposition.

### Statistical Testing

**Diebold-Mariano (DM) Test**
- Tests H0: equal expected score (Brier or log-loss) between two forecasters on the same OOS test set.
- Asymptotically standard normal; handles temporal autocorrelation via HAC variance estimator.
- Not restricted to quadratic loss -> directly applicable to Brier or log-loss differences.
- Steps:
  1. Compute per-game loss for model A and model B: d_t = L_A(t) - L_B(t).
  2. DM statistic: DM = mean(d) / sqrt(HAC_variance(d) / n).
  3. Compare to N(0,1); two-tailed p < 0.05 for significance.
- Python: `statsmodels` has no native DM, but implementation is trivial (5 lines with `arch` or manual HAC).
- **Use this to prove your model beats the market close** on Brier or log-loss; report the p-value.

**Rank Probability Score (RPS)**
- Generalization of Brier score to ordered multi-class outcomes (e.g., win/draw/loss).
- Relevant for soccer and any 3-outcome market.
- Assesses calibration across the cumulative distribution of outcomes.
- Used extensively in soccer forecasting research as the standard proper scoring rule.

### Conformal Prediction

**Conformal Win Probability**
- Generates OOS-guaranteed calibrated prediction *intervals* (not just point probabilities) under the exchangeability assumption only -- no distributional form needed.
- "Inductive conformal prediction": use a held-out calibration set to construct a nonconformity score -> derive coverage guarantees for any new prediction.
- Validated on NCAA basketball tournament (2020): conformal win probabilities were better calibrated at low-probability tails than standard methods.
- The stronger variant (isotonic distributional regression + conformal) provides stronger OOS calibration guarantees.
- Practical constraint: exchangeability assumption requires that calibration and test game distributions are exchangeable -- season-by-season splits can violate this if the sport changes significantly year-to-year.
- **When to apply:** in-game win probability (mid-game state is highly non-stationary; conformal bounds communicate honest uncertainty); also useful for totals/props at the tails.

---

## How THIS Project Should Use It (specific, actionable recommendations)

**1. Establish the baseline Brier score for the devigged market close**
- For every OOS game, compute the devigged market-implied probability from the closing line.
- Compute the Brier score of that market series. This is your target to beat.
- Compute Murphy decomposition for both your model and the market. You need lower Reliability; Resolution should be competitive.
- This is the only honest way to claim "we beat the best available predictor."

**2. Implement a calibration pipeline per sport**
- After each season/corpus: fit a Platt scaler on a held-out calibration season (not the training seasons, not the test season).
- Walk-forward: train on seasons 1-N, calibrate on season N+1, evaluate OOS on season N+2.
- Upgrade to isotonic once you have >= 1000 per-sport calibration examples (likely achievable for NBA moneylines).
- For soccer (3-way outcomes), use RPS not Brier and apply calibration per outcome class separately.

**3. Use the DM test to prove beats**
- Every time you claim "model X beats market close," run DM on per-game Brier loss differences.
- Report: point difference in Brier, DM statistic, p-value, N (number of OOS games).
- Require p < 0.05 AND N >= 200 (sports seasons are small; single seasons often < 100 games per team -> pool cross-league or multi-season).
- Honest reject = DM p >= 0.05 -> model NOT proven to beat the market on this metric/corpus.

**4. Plot reliability diagrams for every model+sport+season triple**
- Overlay your model's curve vs. devigged market close on the same axes.
- S-shaped curves indicate regime-specific miscalibration -> apply beta calibration or isotonic in those regimes.
- Check the tails specifically (< 0.25 and > 0.75) -- that is where market efficiency is most tested and where conformal methods help.

**5. Apply conformal prediction to the in-game layer**
- The in-game win probability module (mid-game state + pregame prior) is the most promising candidate for conformal coverage.
- Use inductive conformal: calibrate nonconformity scores on a held-out set of completed in-game sequences.
- Report prediction intervals, not just point probabilities: "at halftime, team A win probability is 0.61 [0.52, 0.70]."
- This is honest, communicates real uncertainty, and is scientifically defensible.

**6. Report ECE per model but never optimize it directly**
- ECE is not proper -> optimizing it can worsen Brier/log-loss.
- Use it as a quick diagnostic only; the true bar is Brier/log-loss with DM test.

**7. Sharpness check: verify your model is not collapsing to 50%**
- After calibration, compute variance of predicted probabilities and compare to market.
- If your model's variance is significantly lower, calibration may be artificially compressing predictions.
- Resolution component of Brier decomposition directly measures this.

**8. Beta calibration for asymmetric sports**
- Underdogs in NBA/MLB/tennis moneylines create asymmetric calibration challenges.
- Try `betacal` package when reliability diagram shows asymmetric deviation from diagonal.
- Especially relevant for tennis (large underdog probability mass) and MLB (ML odds span wide range).

---

## Gotchas / Limits

- **ECE depends on binning.** Equal-width vs. equal-count bins give different values. Always state which, use 10 bins as default, and report reliability diagram alongside scalar ECE.
- **Isotonic regression overfits on small sets.** With < 300 calibration samples, Platt scaling almost always wins. Sports datasets per-season-per-sport can be dangerously small.
- **Single-season DM tests are underpowered.** NBA regular season = ~1230 games, but your model predicts 2 teams per game -> 2460 predictions. Still, split by sport+market the sets shrink fast. Always pool across seasons or sports before claiming significance.
- **Brier decomposition bin choice affects Reliability/Resolution values.** Use the same binning scheme consistently; do not cherry-pick bins to show good calibration.
- **Temperature scaling does not apply here.** The core models are XGBoost/LightGBM/Monte Carlo, not neural nets with accessible logits. Do not apply temperature scaling to tree model outputs -- use Platt or isotonic instead.
- **Conformal exchangeability assumption.** Season-to-season rule changes (NBA in-season tournament, new teams, schedule changes) can violate exchangeability. Validate conformal coverage year-by-year.
- **Market implied probabilities must be devigged correctly.** Use additive (Shin) or multiplicative devig. Raw market odds include the vig and will appear "over-calibrated" compared to any model. Always remove vig before computing the market Brier baseline.
- **Calibration != edge.** A perfectly calibrated model that matches the devigged market exactly has zero prediction improvement over the market. The goal is to be better calibrated AND sharper (higher Resolution) -- this requires own data (freshness, in-game state, intelligence). This is achievable; claiming $ ROI from it requires price capture and CLV validation, which is a separate, harder bar.
- **Log-loss is sensitive to confident wrong predictions.** One catastrophically wrong confident prediction can dominate the log-loss comparison. Report median per-game log-loss or trimmed mean alongside the mean.

---

## Sources

- [Machine learning for sports betting: should model selection be based on accuracy or calibration? (Walsh & Joshi, 2024) - arXiv](https://arxiv.org/abs/2303.06021)
- [Machine learning for sports betting: Should model selection be based on accuracy or calibration? - ScienceDirect](https://www.sciencedirect.com/science/article/pii/S266682702400015X)
- [A Systematic Review of Machine Learning in Sports Betting (2024) - arXiv HTML](https://arxiv.org/html/2410.21484v1)
- [Using Conformal Win Probability to Predict the Winners of the Canceled 2020 NCAA Basketball Tournaments - Taylor & Francis](https://www.tandfonline.com/doi/full/10.1080/00031305.2023.2283199)
- [More on verification of probability forecasts for football outcomes: score decompositions, reliability, and discrimination - arXiv](https://arxiv.org/pdf/2106.14345)
- [Classifier Calibration: A survey on how to assess and improve predicted class probabilities - arXiv](https://arxiv.org/pdf/2112.10327)
- [A Deep Dive into Calibration of Language Models: Platt Scaling, Isotonic Regression, Temperature Scaling - KDnuggets](https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling)
- [The Complete Guide to Platt Scaling - Train in Data](https://www.blog.trainindata.com/complete-guide-to-platt-scaling/)
- [Brier Score vs Log Loss vs Calibration - MetricGate](https://metricgate.com/blogs/brier-score-vs-log-loss-vs-calibration/)
- [scikit-learn Probability Calibration documentation](https://scikit-learn.org/stable/modules/calibration.html)
- [Diebold-Mariano Test for Forecast Accuracy - EmergentMind](https://www.emergentmind.com/topics/diebold-mariano-test)
- [Comparing Probabilistic Forecasting Systems with the Brier Score - AMS Journals](https://journals.ametsoc.org/view/journals/wefo/22/5/waf1034_1.xml)
- [Calibration Over Accuracy: The Key to Smarter Sports Betting - OpticOdds](https://opticodds.com/blog/calibration-the-key-to-smarter-sports-betting)
- [Classifier Calibration at Scale: Empirical Study of Post-Hoc Methods - arXiv](https://arxiv.org/pdf/2601.19944)
