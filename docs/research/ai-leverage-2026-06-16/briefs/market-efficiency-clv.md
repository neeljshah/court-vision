# Market Efficiency, Devigging, and CLV as a Validation Framework

_Researched 2026-06-16. Scope: devigging methods (multiplicative/Shin/power/worst-case), CLV as the gold-standard OOS diagnostic, walk-forward backtesting, multiple-corpora validation, and academic evidence on sports market efficiency -- synthesized from existing docs + current sources._

---

## TL;DR (highest-leverage takeaways)

- **CLV has 10x lower variance than ROI as an edge diagnostic** -- a 5% EV signal needs ~50 CLV observations to reach p<0.05 vs several thousand bet outcomes; this project's honest "CLV~0" read on the season backtest IS the correct verdict, not a failure of sample size.
- **Devigging method choice matters only in lopsided markets** -- all methods produce identical results at -110/-110; Shin and power diverge from multiplicative on heavy favorites/longshots where favorite-longshot bias (FLB) is strongest; multiplicative systematically underestimates favorite true probability.
- **Shin is the correct default for two-outcome props; power is equally good and avoids feasibility issues in multi-outcome markets** -- both correct for FLB; additive can produce negative probabilities; multiplicative is the weakest on props far from even-money.
- **Academic consensus (2023-2025): sports betting markets satisfy weak-form efficiency; any detectable inefficiency is short-lived and sport/league specific** -- the Hegarty & Whelan (2024) finding that normalized-probability tests are the right methodology (not inverse-odds) reinforces using devigged probabilities, not raw American odds, as the comparison basis.
- **Walk-forward + purge/embargo is the only valid backtest design** -- K-fold on time-ordered data is a correctness bug; a purge window (drop same-team games within 48h of test game) kills trivial autocorrelation; single-fold lifts are artifacts.
- **Multiple corpora (>=2 independent seasons/leagues) are required before claiming a signal survives** -- a finding that holds in corpus A only is likely data-mined; the existing platform already enforces this but it cannot be relaxed.
- **Pregame markets are efficient on PRICE (CLV~0 is the correct result for this project)** -- the value in a better model is CALIBRATION (lower Brier/log-loss, honest probability estimates) and IN-GAME conditioning, not pregame alpha over the close.

---

## Key Capabilities / Techniques

### 1. Devigging Methods

**Multiplicative (proportional normalization)**
- Formula: `p_fair_i = p_implied_i / sum(p_implied_all)`
- Each outcome's vig is proportional to its implied probability; favorites absorb more vig in absolute terms.
- Simplest; industry default; mathematically guaranteed to stay in [0,1].
- Weakness: does not correct for favorite-longshot bias (FLB). On -500/+350 markets, multiplicative gives 78.95%/21.05% vs Shin's 80.2%/19.8% -- a ~1.3pp difference on the underdog that compounds at scale.
- When to use: rough estimates on near-even markets; baseline comparison.

**Shin Method (Shin 1992/1993)**
- Models vig as arising from the book's protection against informed/insider bettors.
- Estimates parameter `z` = proportion of volume from informed bettors; solves iteratively (analytical closed form for two outcomes).
- Formula (two-outcome): `p_true = (p_observed - z) / (1 - 2z)`, where z is solved from `sum(p_observed_i - z)/(1-2z) = 1`.
- On NBA mainline props: z ~ 0.02-0.04; higher on lower-liquidity markets.
- Gives unbiased estimates validated on EPL; outperforms multiplicative on FLB correction.
- Python reference implementation: `mberk/shin` (PyPI), Rust-backed, convergence threshold 1e-12.
- When to use: default for all two-outcome props (over/under); multi-outcome markets where longshots are present.

**Power Method**
- Solves iteratively for exponent k such that `sum(p_implied_i ^ k) = 1`.
- No closed-form; stable within [0,1] always (avoids additive's negative-probability failure).
- Corrects FLB more aggressively than multiplicative but slightly less than Shin on heavy longshots; corrects less in the middle range.
- Recommended as best general default for two-outcome sports markets where Shin's iterative cost is a concern.
- When to use: multi-outcome futures or parlays; drop-in replacement for Shin when simplicity needed.

**Additive (equal-margin)**
- Formula: `p_fair_i = p_implied_i - (overround / n_outcomes)`
- Subtracts equal vig from each outcome. Theoretically addresses FLB in the opposite direction from multiplicative.
- Failure mode: can produce negative probabilities when longshots have low implied probability -- unusable on heavy favorites.
- When to use: only near even-money two-outcome markets; do not use on props outside ~-130/+110 range.

**Worst-Case Devig**
- Takes the most conservative EV estimate across all methods for a given market.
- Use for conservative edge reporting / auditing, not for model probability estimates.
- Not a probability estimator -- a risk-management floor.

**Probit Method**
- Applies probit (inverse normal CDF) transform to implied probabilities before redistributing vig.
- Strong on binary/symmetrical markets (point spreads, game totals near even).
- Less suitable for lopsided moneylines.
- Rarely implemented in practice; Shin dominates for the same markets.

### 2. CLV as the Gold-Standard Diagnostic

**Core formula:**
```
CLV_bet = devig(your_odds_at_placement) - devig(closing_line_odds)
```
Positive CLV: your probability was closer to true probability than the close -- you led the market.
Negative CLV: sharp money moved against you -- you were on the wrong side.

**Why CLV dominates ROI as a diagnostic:**
- Standard deviation of even-money P&L: ~1.00 per unit; SD of CLV: ~0.10 per unit.
- Consequence: for a 5% EV bettor, ROI significance requires ~thousands of bets; CLV significance requires ~50 bets.
- A system with positive CLV + negative ROI = variance (keep volume). A system with negative CLV + positive ROI = luck (do not scale).
- Validated empirically: a 19,930-bet real-money study showed 3.4% realized profit vs 4.0% CLV-implied EV, well within statistical noise (Buchdahl case study via Pinnacle).

**Statistical test:**
```python
from scipy import stats
import numpy as np
mean_clv = np.mean(clvs)
t_stat, p_value = stats.ttest_1samp(clvs, 0)
# Gate: mean_clv > 0 AND p < 0.05 AND N >= 500 (overall); N >= 100 per prop type
```

**Choosing the closing line benchmark:**
- Pinnacle (sharpest global, 2-3% margin, "winners welcome") is the gold standard -- reflects maximum sharp-money price discovery.
- Substitute: best available sharp-book close (bet365, Circa) when Pinnacle unavailable for a market.
- Never use a soft-book close (DraftKings, FanDuel) as the benchmark -- their close lags sharp money.

**CLV as calibration diagnostic (this project's use case):**
- Even when CLV~0 (markets efficient on price), devigged closing lines are the best available proxy for true probability.
- Brier score vs the devigged close is the correct calibration target -- if your model's Brier beats the market Brier (0.198 close vs 0.208 model in season backtest), you have better calibration than randomly sampling from the market, which IS value even without a price edge.
- The gap between model Brier and close Brier is the honest measure of where the model's probability estimates fall short.

### 3. Walk-Forward Backtesting

**Correct design (mandatory for time-ordered sports data):**
1. Expanding window: train on all data with `game_date < t`; evaluate on `game_date >= t`.
2. Purge window: exclude any game involving the same team within 48h of the test observation (eliminates back-to-back autocorrelation leakage).
3. Embargo: optionally add a gap between train end and test start (prevents feature spillover from shared rolling windows).
4. Never use K-fold cross-validation on time-ordered data -- future information leaks into training folds.

**Combinatorial Purged Cross-Validation (CPCV):**
- Extension of purged walk-forward that runs multiple non-overlapping test windows and aggregates.
- Reduces overfitting to a single backtest period; recommended for signal catalog evaluation (domains/<sport>/signal_catalog.py).
- Implementation reference: `mlfinlab` library or manual implementation.

**Purge/embargo parameters for NBA:**
- Purge: same-team within 2 games (accounts for rotation/injury carryover).
- Embargo: 3-day gap between train-end and test-start to prevent same-week news leakage.

### 4. Multiple-Corpora Validation

**The two-corpus minimum rule:**
- A signal that passes the walk-forward gate on one season's data is a single-fold lift -- likely an artifact.
- Confirmed edge requires: (a) pass on corpus A (e.g., 2023-24 NBA), then (b) independently pass on corpus B (e.g., 2024-25 NBA or same-sport different league).
- The platform already enforces this via `src.loop.gate`; the 60/60 REJECT result on the signal catalog IS the honest outcome.

**Cross-league / cross-sport validation:**
- A signal that holds across NBA + MLB or NBA + soccer is more robust than same-sport two-season.
- Risk: different market structures (liquidity, FLB magnitude, vig levels) can make cross-sport comparison misleading -- always report per-corpus metrics separately, not pooled.

**Temporal stability check:**
- Split each corpus into early-season / late-season segments; a signal that degrades sharply late-season may be absorbing within-season drift (recency bias in training data).
- NBA recency beats volume: confirmed existing finding -- rolling 5-10 game features should dominate full-season aggregates in feature importance.

### 5. Market Efficiency -- Academic Evidence (2023-2025)

**Hegarty & Whelan (2024), Scottish Journal of Political Economy:**
- Compared normalized-probability vs inverse-odds regression tests for market efficiency across tennis and soccer.
- Finding: inverse-odds method is biased against finding FLB (artifacts in the test, not the market); normalized-probability method is the correct test.
- Implication: always devig before comparing model to market; raw American odds comparisons are misleading.

**American Journal of Management (2023) -- Weak Form Efficiency:**
- Most sports betting markets satisfy weak-form efficiency: past price history alone does not yield persistent positive alpha.
- Exceptions: early-season mispricing (first 2-3 weeks when books lack current-season data) is recurrent but size-limited.

**Springer Annals of OR (2022) -- FLB structure:**
- Favorite-longshot bias magnitude varies by sport, league, and market type.
- NBA player props: FLB is moderate; Shin z ~ 0.02-0.04.
- Lower-liquidity alternates and parlays: higher z, larger FLB, Shin correction matters more.

**Tennis GNN paper (arXiv 2025):**
- Walk-forward at 85%/15% split; graph neural network on match history.
- Found intransitive player dominance structures (A beats B beats C beats A) that ATP ranking misses.
- Result: calibration improvements over market but not demonstrated CLV > 0 in OOS at scale.
- Takeaway for this project: structural/relational features (network-based) may improve calibration where simple box-score features plateau.

---

## How THIS Project Should Use It

### 1. Standardize on Shin for all devigging (replace multiplicative where used)

The existing `src/prediction/betting_edge.py` implements a two-outcome Shin approximation. Audit and extend:
- Confirm the implementation uses the full iterative solver (not just the two-outcome closed form) for three-way markets (soccer 1X2).
- For NBA over/under props at near-even odds (-110/-110): all methods give the same result -- Shin adds no value; keep multiplicative for speed.
- For NBA money-line or heavy-favorite same-team-parlay components: switch to Shin or power; the 1-2pp difference on 20% probability outcomes is material for calibration scoring.
- Use `mberk/shin` (PyPI, Rust-backed) rather than a hand-rolled solver for reliability and speed.

### 2. CLV as the honest OOS calibration benchmark (not just a betting diagnostic)

Current state: season backtest shows model Brier 0.208 vs close 0.198 (close wins by 0.010).
Next steps:
- Decompose the Brier gap by market type (moneyline vs total vs player prop) and by time-in-season to find where calibration is weakest.
- Use devigged Pinnacle closing probability (not devigged DraftKings) as the reference in all calibration plots.
- Track CLV distribution across the season walk-forward even when not placing bets -- a shift toward positive CLV mean signals that the model's probability estimates are converging toward the close (which = better calibration).
- Report calibration as: `ECE vs uniform` (baseline), `ECE vs market` (the real bar), and `Brier vs market`.

### 3. Walk-forward with explicit purge/embargo in all signal evaluations

Current `prop_backtester.py` implements the walk-forward correctly; the 48h same-team purge is in place.
Additions:
- Add a 3-day embargo (gap between last training game and first test game) to prevent rolling-window spillover.
- Implement CPCV for the signal catalog pipeline: instead of one walk-forward split, use 5 non-overlapping test windows covering the full season and average metrics; reduces single-window overfitting.
- Log per-window Brier and CLV separately (not just pooled) -- degradation across windows reveals regime instability.

### 4. Two-corpus gate before any signal leaves research surface

Enforce in `src.loop.gate`:
- A signal must pass the walk-forward Brier improvement threshold on corpus A (2023-24) AND corpus B (2024-25) before being flagged as a candidate.
- Cross-sport signals (e.g., a pace-adjustment factor that works for NBA and MLB totals) require per-sport independent gate passage.
- Log the per-corpus metrics in the signal registry alongside the pooled metric; honest rejects on corpus B after corpus A pass = valid research finding, not a failure.

### 5. FLB-aware calibration audit for in-game props

In-game props (live re-pricing) often carry higher vig and more FLB than pregame -- books are faster to move lines than to reprice tails.
- Run a FLB audit: for each probability decile, compute `mean(devigged_implied_prob)` vs `mean(actual_outcome_rate)`.
- If FLB is present (longshots over-priced), the model's calibration will look better than it is when using multiplicative devig as the benchmark -- switch to Shin to get an unbiased view.
- This matters for the in-game Brier improvement claim (Q1-Q3 0.34-0.40 -> better with conditioning): verify Shin-devigged market probability is the baseline, not multiplicative-devigged.

### 6. Early-season calibration window as a recurring structured test

Academic finding: first 2-3 weeks of each season are systematically under-modeled by books (no current-season data yet).
- Run a separate calibration evaluation for games 1-20 of each season vs games 21+ to quantify how much of any measured improvement comes from this structural window.
- If calibration improvement concentrates in games 1-20, that is a timing/freshness effect, not a model structural advantage -- important for honest attribution.

---

## Gotchas / Limits

- **CLV~0 does not mean the model is useless** -- it means pregame price is already incorporated by the market. Calibration (Brier) improvement and in-game conditioning are still real value; CLV is the price-edge diagnostic, not the calibration diagnostic.
- **Shin's z parameter is estimated per-market, not universal** -- z~0.02-0.04 is a typical NBA prop range but varies by liquidity and market type; do not hard-code z, always solve per market.
- **Devigging is only as good as the odds source** -- soft-book odds (DK, FD) have higher vig and slower price discovery; always devig using the sharpest available book (Pinnacle) for benchmarking, even if the actual bet fills elsewhere.
- **Purging is not enough if features use rolling windows** -- if a feature like "L5 game average" overlaps the purge window on the train side, leakage can survive purging; embargo handles this but adds complexity.
- **Multiple corpora cure overfitting but not distribution shift** -- a signal validated on 2023-24 and 2024-25 NBA still faces the risk that 2025-26 is a structural break (roster turnover, rule changes, pace shifts). Report calibration per season, not just pooled.
- **Favorite-longshot bias direction can reverse in low-liquidity markets** -- some prop markets show reverse FLB (favorites over-priced) depending on bettor composition; do not assume Shin always reduces favorite probability relative to multiplicative without checking empirically.
- **Academic papers on "exploiting soccer betting" often omit transaction costs and limiting** -- a 2023 arXiv paper (Gross-Klussmann) finds statistical edge in German lottery markets but does not demonstrate CLV > 0 vs sharp closing lines at realistic fill sizes; treat with skepticism.
- **Walk-forward on small seasons (< 82 games / sport) requires careful window sizing** -- tennis season is continuous but ATP tour has structural breaks (surface changes, Grand Slam vs tour); treat each surface as a separate mini-corpus.

---

## Sources

- [Closing Line Value CLV Demystified by Joseph Buchdahl - PinnacleOddsdropper](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- [How to Devig Odds: Comparing the Methods - Outlier](https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods)
- [Devigging Methods Explained: Power, Shin, Additive, Multiplicative - BetHero](https://betherosports.com/blog/devigging-methods-explained)
- [Automatically De-Vig Pinnacle Odds (4 Methods) - PinnacleOddsdropper](https://www.pinnacleoddsdropper.com/guides/how-to-devig-pinnacle-s-odds-for-betting-on-soft-books)
- [Shin Python Implementation - mberk/shin on GitHub](https://github.com/mberk/shin)
- [Comparing Two Methods for Testing the Efficiency of Sports Betting Markets - Hegarty & Whelan 2024 - ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S2773161824000193)
- [Weak Form Efficiency in Sports Betting Markets - American Journal of Management 2023 - ResearchGate](https://www.researchgate.net/publication/371069739_Weak_Form_Efficiency_in_Sports_Betting_Markets)
- [Beating the Average: Exploiting Soccer Betting Inefficiencies - arXiv 2023](https://arxiv.org/abs/2303.16648)
- [Intransitive Player Dominance and Market Inefficiency in Tennis Forecasting: GNN Approach - arXiv 2025](https://arxiv.org/pdf/2510.20454)
- [Risk Aversion and Favourite-Longshot Bias - Whelan, Economica 2024 - Wiley](https://onlinelibrary.wiley.com/doi/10.1111/ecca.12500)
- [Walk-Forward Optimization - QuantInsti](https://blog.quantinsti.com/walk-forward-optimization-introduction/)
- [Combinatorial Purged Cross-Validation - Towards AI](https://towardsai.net/p/l/the-combinatorial-purged-cross-validation-method)
