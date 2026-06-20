// riskTerms.ts -- plain-language InfoTip copy for the /risk page's risk terms.
//
// The shared GLOSSARY (frozen depth dir) covers units/tier/calibration/clv etc.
// This page-local map adds the DESCRIPTIVE risk-control vocabulary the /risk view
// needs (Kelly, RoR, floor, exposure, joint vs naive, correlation) WITHOUT editing
// the frozen glossary. Every string is passed to InfoTip via text={...}.
//
// HONESTY RAILS: every definition is DESCRIPTIVE risk in UNIT space, never a money
// amount, never prescriptive money advice, never a profit/safety guarantee. These
// must never imply an edge. ASCII only; no money-value field anywhere.

export const RISK_TERMS: Record<string, string> = {
  kelly:
    "Kelly sizing picks a stake proportional to the model's edge over the price. " +
    "We cap it at a QUARTER-Kelly fraction (0.25 * f*) and express it in UNITS, " +
    "never money -- a conservative, descriptive size, not financial advice.",
  quarter_kelly:
    "A capped quarter-Kelly stake: 0.25 times the full-Kelly fraction, floored at " +
    "zero. It deliberately under-bets relative to full Kelly to blunt model error " +
    "and variance. UNITS only -- there is no money path.",
  ror:
    "Risk-of-Ruin -- a model-CONDITIONAL probability that the open book's " +
    "units-weighted outcome falls to a ruin threshold, under a normal approximation " +
    "using the MODEL'S OWN probabilities. It is a DESCRIPTIVE stat about this paper " +
    "book, NEVER a guarantee of safety and NEVER a money figure.",
  floor:
    "A tier EV floor: the minimum probability-space expected value (per 1 unit " +
    "staked) a pick must clear to earn a tier. A=0.08, B=0.04, C=0.02; below the C " +
    "floor it is NO BET. When the close is a PROXY (not a true settled close) every " +
    "floor is raised +0.01. Matching the efficient close = no_bet = a SUCCESS.",
  exposure:
    "Total exposure = the naive sum of staked UNITS across all open legs. It is the " +
    "worst-case units at risk if every leg loses; UNITS only, never money.",
  joint:
    "Joint (correlation-adjusted) exposure is <= the naive sum: same-game legs are " +
    "treated as correlated (they do NOT diversify) while cross-game legs combine in " +
    "quadrature (they do). The gap is the diversification haircut. UNITS only.",
  variance:
    "Portfolio variance (UNITS-squared) of the units-weighted outcome, built from " +
    "each leg's Bernoulli model variance p*(1-p) plus a same-game covariance term. " +
    "Its square root (portfolio SD) is the typical unit swing. Units, never money.",
  correlation:
    "Legs on the SAME game move together (correlated) so they do not diversify; legs " +
    "on DIFFERENT games are treated as ~independent so they reduce joint risk. This " +
    "is why joint exposure is always <= the naive sum of stakes.",
  bankroll_units:
    "Bankroll is tracked in abstract UNITS, never money. Exposure and Risk-of-Ruin " +
    "are expressed as a fraction of these units -- a relative descriptive scale, not " +
    "a currency balance.",
  exposure_cap:
    "A descriptive ceiling on how many UNITS may be open per sport or per slate. It " +
    "is a risk-control limit a desk could read, not a prescription and not a money " +
    "amount; nothing here places or sizes a real-money bet.",
};
