# Validation Methodology — Proving the Edge Before Risking Capital

*CLV framework — how to prove edge exists before deploying capital.*

---

## The Test That Matters Above All Others

```
CLV = devig(your_probability_at_placement) - devig(closing_line_probability)
```

Average CLV > 0 over 500+ predictions, statistically significant (p < 0.05): the edge is real.

Everything else — R² on prop models, SHAP attribution on CV features, AUC on calibration curves — is supportive evidence. CLV is the verdict.

---

## Why Closing Line, Not Realized P&L

Realized ROI on 312 picks is a noisy estimator of edge. Over a small sample, luck dominates. The closing Pinnacle line is an almost-unbiased estimator of true probability — it reflects a full day of sharp money correcting the opening line, with the most sophisticated bettors in the world (some of whom have institutional data access) having taken their shots.

Consistently beating the close means: you identified the correct direction before sharp money corrected it. You have information that is not in the market. That is the definition of edge.

**A system with positive CLV but negative realized ROI** is probably having bad variance. Run more volume.  
**A system with negative CLV but positive realized ROI** got lucky. Do not scale. Fix the model.

---

## Step-by-Step Validation Protocol

### Step 1: Collect historical closing lines

Source: OddsPortal historical archives, or The Odds API historical endpoint.

For every game where the model produced a prediction in 2024–25:
- Record the Pinnacle no-vig closing line (or best available sharp book closing line)
- Record time at which the closing line was captured (should be within 5 minutes of tip-off)

### Step 2: Match to model predictions

For each prediction, record:
- Game ID, player ID, prop type (pts/reb/ast/fg3m/blk/stl/tov)
- Model predicted probability (e.g., P(pts > 27.5) = 0.58)
- The line at time of prediction (the number used, e.g., 27.5)
- The book being evaluated against

### Step 3: Compute no-vig probabilities

Apply Shin devig to both the prediction-time line and the closing line:

```python
# Shin devig — solve for z numerically per market
def shin_devig(p_over: float, p_under: float) -> tuple[float, float]:
    # p_over + p_under > 1.0 due to vig
    # Solve: z such that (p_over - z)/(1 - 2z) + (p_under - z)/(1 - 2z) = 1
    z = (p_over + p_under - 1) / (2 * (p_over + p_under - 1) + 2)
    return (p_over - z) / (1 - 2*z), (p_under - z) / (1 - 2*z)
```

Implementation: [`src/prediction/betting_edge.py`](../../src/prediction/betting_edge.py)

### Step 4: Compute CLV per bet

```python
clv = model_prob_devigged - closing_prob_devigged
```

Positive CLV: your probability estimate was closer to true probability than the book at close.  
Negative CLV: the closing price moved against your bet — you were on the wrong side of sharp money.

### Step 5: Aggregate and test

```python
import scipy.stats as stats

clvs = [...]  # array of per-bet CLVs
mean_clv = np.mean(clvs)
t_stat, p_value = stats.ttest_1samp(clvs, 0)

print(f"Mean CLV: {mean_clv:.4f}")
print(f"t={t_stat:.2f}, p={p_value:.4f}")
print(f"N={len(clvs)}")
```

**Decision gate:** If mean CLV > 0 and p < 0.05 with N ≥ 500: proceed to build execution infrastructure. If not: fix the model first.

### Step 6: Break down by category

```python
# By prop type
for prop in ['pts', 'reb', 'ast', 'fg3m', 'blk', 'stl', 'tov']:
    subset = [(c, r) for c, p, r in zip(clvs, props, results) if p == prop]
    print(f"{prop}: CLV={np.mean([c for c,_ in subset]):.4f}, N={len(subset)}")

# By model confidence tier
# By time of bet placement (open vs pre-game)
# By home vs away player
```

Find where CLV is positive (strongest markets) and where it is negative (fix or avoid).

### Step 7: Calibration check

Calibration: do events assigned 60% probability actually happen 60% of the time?

```python
from sklearn.calibration import calibration_curve
prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=10)
```

Reliability diagram: plot `prob_true` vs `prob_pred`. A well-calibrated model lies on the diagonal. Systematic over-confidence (curve below diagonal) or under-confidence (above diagonal) indicates a calibration problem.

Fix: Platt scaling or isotonic regression on holdout set.

Implementation: [`src/prediction/player_props.py`](../../src/prediction/player_props.py) (CalibrationLayer)

---

## Walk-Forward Validation

CLV testing uses historical data. The internal model validation uses walk-forward, season-purged backtesting.

**Rules:**
1. Train on all games with `game_date < t`
2. Evaluate on games with `game_date ≥ t`
3. Purge window: drop any game involving the same team within 48 hours of the test game (kills trivial autocorrelation)
4. K-fold cross-validation is NOT used — it is a correctness bug on time-ordered data

The walk-forward harness: [`src/prediction/prop_backtester.py`](../../src/prediction/prop_backtester.py)

---

## Minimum Sample Requirements

| Test | Minimum N | Statistical threshold |
|------|-----------|----------------------|
| Overall CLV significance | 500 bets | p < 0.05 |
| Per-prop-type CLV | 100 bets per type | p < 0.10 |
| Calibration check | 200 bets per probability decile | ECE < 0.05 |
| Model retrain gate | 80 CV games | Δ R² > 0.05 on holdout |
| Paper trading gate | 50 bets | CLV beat rate ≥ 55%, paper ROI ≥ 3% |
| Live capital gate | Pass paper trading + manual review | All circuit breakers tested |

---

## Validation Targets

| Metric | Target |
|--------|--------|
| Settled picks | 500+ |
| CLV vs Pinnacle | > 0, p < 0.05 |
| pts model R² | ≥ 0.50 (at 80 CV games) |
| Calibration ECE | < 0.05 across all prop types |
| Calibration training | Platt scaling applied post-residual generation |

**Note on CLV figures:** CLV is measured against Pinnacle's closing line, which is not the price at which any bet is placed. Actual fills occur at DraftKings, FanDuel, and exchanges with wider vig and lower limits. Realistic fill modeling is planned to close this gap.

---

## What Counts as Settled

A bet is settled when:
1. Game completed
2. Closing Pinnacle line was recorded before tip-off (within 5 minutes)
3. Player was NOT a late-reported DNP

DNP-impacted bets are voided and excluded from both CLV and ROI computations.

---

## The Null Hypothesis

Explicitly: **Your model has zero edge vs closing lines.** If you cannot reject this null (with reasonable sample size), the edge is not real. Fix the model before building execution infrastructure.

This framing matters because the base rate of confident-sounding prediction systems with no real edge is high. The CLV test against sharp closing lines is nearly the only test that cannot be gamed by data leakage, look-ahead bias, or selection.

---

## The Fork in the Road

The CLV test is binary:

**CLV > 0, p < 0.05:** The edge is real. Build the machine (execution infrastructure, account rotation, P2P adapters, dashboard, portfolio correlation management). Every dollar invested in the stack is justified.

**CLV ≈ 0 or negative:** Fix the model first. Possible issues:
- Calibration is off (model probabilities are biased)
- Feature leakage (walk-forward logic error)
- CV features are noisier than they appear (validate against SportVU ground truth)
- Sample is too small (need more games, more predictions)

Do not deploy capital on a system that has not passed this test.

---

*See [edge-taxonomy.md](edge-taxonomy.md) for the theoretical basis of each edge. See [calibration.md](../models/calibration.md) for implementation details of probability calibration.*
