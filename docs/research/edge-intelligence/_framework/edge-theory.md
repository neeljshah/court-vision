# EDGE THEORY -- what "edge" is, how we know we have it, and where it lives
_Part of the edge-intelligence corpus. The conceptual backbone every sport file references. ASCII._

## What edge IS (and is not)
EDGE = a repeatable, positive difference between OUR probability and the price we can actually
TAKE, that survives out-of-sample and shows up as positive CLOSING-LINE VALUE (CLV).
- NOT "high model EV vs a soft line" alone -- that can be a model artifact (too-tight
  distribution, thin data). EV is a CANDIDATE; CLV/calibration is the PROOF.
- NOT "accuracy" -- minimizing MAE pulls predictions toward the market and DESTROYS edge where
  the model correctly diverges. (accuracy != edge -- a load-bearing project lesson.)
- NOT beating the CLOSE on a sharp mainline -- that market is efficient; we match it.

## The two honest yardsticks
1. CALIBRATION vs the devigged close (OOS, leak-free): Brier / ECE / Brier-Skill-Score. BSS>0
   means our probabilities are sharper than the devigged market on that market. This is the
   NORTH-STAR metric -- claim it confidently when real.
2. CLV (closing-line value): did we take a better NUMBER than the closing line? Positive CLV
   over a large sample is the market's own verdict that we were ahead of it. CLV is the bridge
   from "calibrated" to "would make money." Real money is GATED on proven positive CLV.
Note on DFS pick'em (PrizePicks standard): no two-way close -> CLV-vs-close is undefined; prove
via P(over) calibration vs realized + realized ROI at the fixed payout + DFS-line MOVEMENT.

## Why markets are mostly efficient (and where they crack)
A liquid market with sharp participants (Pinnacle, exchange, the closing consensus) integrates
all public info -> efficient. Cracks appear where one or more breaks down:
- LOW ATTENTION: soft books / DFS apps / niche leagues price lazily off a stale model.
- INFORMATION LAG: live in-game lines lag the realized state by seconds-to-minutes.
- SLOW UPDATE: stale lines on slow books after news/movement elsewhere.
- DIFFERENT CROWD: prediction markets (Kalshi/Polymarket) vs sportsbooks can diverge.
- CORRELATION BLINDSPOT: books price SGP legs independently, misjudging joint probability.
- STRUCTURAL: fixed-payout DFS pick'em can't move to kill a genuinely mispriced projection.
Edge = systematically exploiting these specific cracks with a calibrated model, not "being
smarter than the market" in general.

## The beatable-pocket taxonomy (ranked) -- see cut-list-no-edge.md for the inverse
P1 Soft/DFS player props (lazy pricing + per-player distributions we can model).
P2 Live/in-game lag (realized state -> reprice faster than the book).
P3 Stale/soft-book lines (line-shop + stale detection; execution edge).
P4 Prediction-market vs sportsbook divergence.
P5 Correlated SGP mispricing.
P6 Niche leagues / low-attention markets.

## Evidence tiers (every edge claim is tagged)
- HYPOTHESIS: a plausible pocket/lever, not yet measured. (Most start here.)
- CALIBRATION-PROVEN: OOS leak-free BSS>0 (sharper than the devigged close on that market).
- CLV-PROVEN: forward paper accrues positive CLV at a meaningful sample. (The bar for real $.)
A claim never jumps tiers without the evidence. Downgrades happen (e.g. opponent-adjust =
measured NULL; isotonic recal = OOS overfit -> deferred). Honest downgrades are successes.

## The path from data to edge (what the corpus operationalizes)
MORE/DEEPER DATA in a beatable pocket -> a better-CALIBRATED per-outcome DISTRIBUTION ->
priced against the SOFT line -> a CANDIDATE edge (tier: hypothesis) -> leak-free OOS check
(tier: calibration-proven) -> forward paper CLV (tier: CLV-proven) -> sized + (eventually) real.
Intelligence = pushing more depth into the pockets where this chain can complete, and CUTTING
the pockets where it provably cannot.
