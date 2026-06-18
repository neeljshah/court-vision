# METHOD: Kelly sizing -- fractional Kelly, correlation-aware SGP, and the caps
_Part of the edge-intelligence method library (B). Reusable recipe. ASCII only.
Code pointers: src/prediction/betting_portfolio.py -- KELLY_FRACTION/MAX_BET_PCT/
MAX_DRAWDOWN_PCT/MAX_OPEN_BETS (lines 71-75), kelly_corr() (line 160), kelly_b_stake()
(line 263), build_corr_matrix from RESIDUALS (line 509), _load_corr_matrix (line 63).
src/** is HUMAN-GATED -- this file documents/explains; it does not edit the engine._

## The math (single bet)
Full Kelly stake fraction on a bet at decimal-equivalent payout b (American odds -> b),
with win probability p and q = 1 - p:
  f* = (p*b - q) / b
If f* <= 0 there is no edge -> stake 0. (betting_portfolio.py lines 230-232.)
p MUST be the CALIBRATED win prob, not (implied + edge). The engine takes
win_prob_override (from the isotonic/calibration layer) and only falls back to the
implied+edge heuristic when no calibrated prob is supplied (lines 221-226). Garbage p ->
Kelly massively over-bets; this is the single biggest sizing risk.

## Why FRACTIONAL Kelly (never full)
Full Kelly is growth-optimal only with the TRUE p and independent bets. We have neither:
p is an estimate (estimation error makes full Kelly over-bet), and prop bets are
correlated. Full Kelly's drawdowns are brutal even when right. The engine uses
QUARTER-Kelly: KELLY_FRACTION = 0.25 (line 74), so f = f* * 0.25 (line 235). Quarter-Kelly
trades a small amount of long-run growth for a large reduction in variance/drawdown -- the
correct trade when p is uncertain. Treat 0.25 as a ceiling, not a target; go lower when p
is thin/uncertain (e.g. a freshly-fit, not-yet-CLV-proven model).

## Correlation-aware sizing (the SGP / portfolio problem)
Prop legs are NOT independent: a player's PTS, REB, AST, FG3M share minutes/usage/pace, so
their outcomes co-move. Sizing each leg at its own Kelly DOUBLE-COUNTS the bankroll and
over-exposes a single correlated factor. Two layers in the engine:
  1. Per-bet correlation reduction (kelly_corr, lines 213-239): if stat + open_stats are
     given, load the persisted residual correlation matrix (_load_corr_matrix) and set
     corr_with_open = mean |corr| of this stat vs already-open stats. Then
       corr_penalty = 1 - (corr_with_open * existing_exposure / bankroll)
       f = f * max(0, corr_penalty)
     i.e. the more correlated exposure already on the book, the smaller this bet.
  2. The matrix MUST be built from RESIDUALS, not raw stats (build_corr_matrix, lines
     509-535). Correlating raw stats inflates the correlation via shared usage/minutes
     variance (the v1 bug); correlating (predicted - actual) residuals isolates the part
     the model did NOT already account for -- the correlation that actually matters for
     joint risk. This is a load-bearing detail: a residual corr of ~0.3 can be a raw corr
     of ~0.7. Use residual corr in sizing.
For a true SGP (same-game parlay) priced as one ticket: do NOT size legs independently and
multiply. Price the JOINT distribution (the Monte Carlo sim emits coherent marginals +
joint), get a single ticket p, and Kelly-size the TICKET. Independent-leg multiplication
both misprices the parlay (books' own blindspot, P5 pocket) and missizes our stake.

## The caps (hard guards -- all in betting_portfolio.py)
  - MAX_BET_PCT = 0.04: cap ANY single bet at 4% of bankroll (line 75; applied line 242).
    A backstop against a calibration error or fat-tail payout blowing up one stake.
  - MAX_DRAWDOWN_PCT = 0.15: halt betting when drawdown exceeds 15% of the reference
    bankroll (line 73; check_drawdown_ok, applied lines 198-211). Needs bankroll_start;
    CV_INFER_BANKROLL_START (default OFF) can infer it from realized PnL but can silently
    flip a stake to 0 -- a deliberate behavior-change gate.
  - MAX_OPEN_BETS = 20: never more than 20 bets in flight (line 72) -- bounds total
    correlated exposure independent of any single-bet math.
  - kelly_b_stake variant (line 263) sizes proportionally to edge magnitude with
    _KELLY_B_FRACTION=0.25 and _KELLY_B_MAX_U=3.0 (cap 3 units) to limit blowup.

## The recipe (apply in order)
  1. Get CALIBRATED p (calibration layer / isotonic), not implied+edge.
  2. f* = (p*b - q)/b; if <=0, stake 0.
  3. f = f* * 0.25 (quarter-Kelly; lower if p is uncertain/unproven).
  4. Correlation penalty using the RESIDUAL matrix vs open exposure.
  5. Clamp to MAX_BET_PCT (4%); respect MAX_OPEN_BETS and the drawdown halt.
  6. For SGP: price the joint, size the ticket once -- never multiply independent legs.

## Failure modes
  - OVER-CONFIDENT p -> Kelly over-bets superlinearly. Quarter-Kelly + 4% cap are the
    safety net, but the real fix is calibrated, CLV-proven p before sizing at all.
  - RAW-stat correlation matrix understates joint risk (inflated corr) OR, if mis-signed,
    fails to shrink correlated exposure. Always build from residuals.
  - SIZING UNPROVEN EDGE: Kelly assumes the edge is real. Until a market is CLV-PROVEN
    (clv-computation.md, proof-standards.md bar 6), size at PAPER only / a tiny fraction.
    Calibration alone does not justify a Kelly stake of real money.
  - IGNORING EXISTING EXPOSURE: sizing each bet in isolation ignores the portfolio; the
    corr_penalty + MAX_OPEN_BETS exist precisely to prevent that.

## Evidence-tier reminder
Sizing is downstream of proof. No $-edge is claimed here. Real-money Kelly is GATED on
forward positive CLV at a meaningful sample; before that, paper-only and fractional.
