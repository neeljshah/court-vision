# METHOD: Shin devig (vs proportional / multiplicative)
_Method library / edge-intelligence corpus. Why we devig with the Shin model instead of the naive
proportional method, the math, the solver, and the failure modes. Grounded in the vetted Shin
reference. ASCII only._

## What devigging is and why it is load-bearing
Bookmaker odds carry an overround (vig): the implied probabilities `pi_i = 1/decimal_odds_i` sum
to more than 1 (the booksum B = sum(pi_i) > 1). To recover the bookmaker's FAIR probabilities you
must remove the overround. The eval gate scores model calibration vs the DEVIGGED close, so the
devig method directly shapes every Brier-Skill-Score and every "do we beat the close" verdict. A
WRONG devig manufactures or destroys apparent edge. This is also the baseline a +EV check uses.

## Proportional / multiplicative devig (the naive method -- and why it is biased)
    p_i = pi_i / B            (divide each implied prob by the booksum)
Simple, sums to 1. BUT it removes vig PROPORTIONALLY, which over-credits the favourite and
under-credits the longshot. Real books load MORE vig on longshots (the favourite-longshot bias,
FLB): the longshot's quoted price embeds extra margin. Proportional devig ignores this, so on
LOPSIDED markets it systematically MIS-states the fair favourite probability -- and "flatters a
model on lopsided markets" exactly because the baseline it is compared against is skewed. That is
why proportional is not the defensible baseline.

## The Shin model (what it corrects and the math)
Shin (1992/93) models the overround as arising from a proportion `z` of INSIDER (informed) money
the book protects against. Removing that insider component removes more margin from the longshot
than from the favourite -- i.e. it bakes in the favourite-longshot correction. For booksum
`B = sum(pi_i)` and insider proportion `z in [0,1)`:

    p_i(z) = ( sqrt( z^2 + 4*(1-z)*pi_i^2 / B ) - z ) / ( 2*(1-z) )

Solve for the single scalar z such that `sum_i p_i(z) == 1`. `z = 0` reduces to the no-vig case
(returns pi unchanged when B == 1). Larger z = more shrinkage of the implied probs. Because
`sum_i p_i(z)` is monotonically DECREASING in z, a bisection on z in [0, 1) converges cleanly.

## Why Shin over proportional (the WHEN)
- USE SHIN as the devig baseline for any two-way or n-way market you score calibration against or
  derive a fair prob from: h2h, totals over/under, run line, match result. It is the defensible
  reference precisely because it accounts for FLB.
- Proportional is acceptable ONLY as a quick approximation on near-symmetric two-way markets
  (both sides ~ -110), where Shin and proportional nearly coincide and z is tiny. On lopsided
  markets (heavy favourite) they diverge and Shin is correct.
- A devigged CLOSE is a fair-probability estimate, NOT a price you can bet. For +EV, evaluate
  against the BEST price you can actually take across books, never against the devigged close.

## The solver (vetted reference) and a gotcha
The closed-form Shin expression quoted in older docs did NOT normalise to 1 -- a QA pass caught
this. The vetted solver is a general n-outcome bisection that recovers probabilities summing to
EXACTLY 1. Pattern:

    pi = 1/odds                          # quoted implied probs, sum = B
    if |B - 1| < tol: return pi, z=0     # already fair, no overround
    assert B > 1                         # B < 1 means arbitrage / bad input -> do not devig, flag
    bisect z in [0, 0.999999] until sum_i p_i(z) == 1
    p = p / p.sum()                      # numerical clean-up

## Code pointers (reuse, never reimplement)
- `scripts/platformkit/eval_gate/shin.py` -- THE vetted reference. `shin_devig(pi)` (lines 35-63)
  returns `(fair_probs summing to 1, z)`; `_fair_probs_given_z(pi, z)` (27-32) is the closed form
  above; `shin_devig_decimal(odds)` (66-69) is the decimal-odds convenience wrapper;
  `implied_from_decimal` (20-24) asserts odds > 1.
- `scripts/platformkit/odds_shop.py` -- the consumer. `devig_twoway(price_a, price_b)` (73-81)
  calls `shin_devig_decimal` directly (it does NOT roll its own devig). The module's honesty
  contract is explicit: a +EV vs a SOFT book is an EXECUTION edge (line-shopping/arb), not a beat-
  the-sharp-close edge; `ev_vs_price = p*odds - 1` (114-124) must be evaluated against the best
  bettable price, never the devigged close.
- Production note: shin.py header says prefer `kernel.devig2` (or mberk/shin) in production IF
  vetted equivalent; shin.py is the leak-free REFERENCE the gate mirrors. Do not build a parallel
  devig stub that can drift from the gate (tests-mirror-real rule).

## Failure modes
- USING PROPORTIONAL ON LOPSIDED MARKETS -> mis-stated favourite fair prob -> fake/destroyed BSS.
- B < 1 (combined implied < 100%): NOT a devig case, it is an ARBITRAGE across books -> route to
  `detect_arb`, do not Shin-devig it (the assert guards this).
- NON-NORMALISED closed form: the old quoted formula did not sum to 1 -> always normalise / use
  the vetted bisection solver.
- DEVIG-AS-BETTABLE confusion: treating the devigged close as a price you can stake -> compute EV
  vs the best AVAILABLE price instead.
- z near 1: degenerate (book is "all insiders"); the bisection is clamped to 0.999999 -- if z
  pins to the bound the input odds are likely malformed.

## Proof tier
Shin devig is a METHOD, not an edge -- it is the defensible BASELINE the gate scores against. It
computes fair probabilities only and never implies a dollar edge. Its correctness is established
(QA-vetted, sums to 1, FLB-aware). Any edge measured AGAINST a Shin-devigged close still must
clear leak-free OOS BSS > 0 (CALIBRATION-PROVEN) and forward CLV (CLV-PROVEN); the market on sharp
mainlines is efficient, so most such measurements correctly come back as "match the close".
