# Kalshi on this desk: fees, maker versus taker, and why the desk is paper only

PAPER ONLY. No order has ever been placed on any venue, and no live order path exists in this
repository. Calibration and execution-quality language only. Definitions of markout and fill realism
are on [CLV_AND_MARKOUT.md](CLV_AND_MARKOUT.md).

## 1. Fee schedule as modelled

Source in code: `scripts/platformkit/execution/venue_fees.py` (public), the one canonical fee module.
Its docstring records the citation: confirmed 2026-09-01 against the Kalshi help-centre fees article
(help.kalshi.com, article 13823805, page dated April 19, 2026), cross-checked against a secondary
aggregator (marketmath.io).

- Taker fee per order: 0.07 x C x P x (1 - P), rounded UP to the next cent.
- Maker fee per order: 0.0175 x C x P x (1 - P), rounded UP to the next cent (0.25 times the taker
  coefficient).
- C is the contract count and P the contract price as a fraction of the 1-unit payout. The rounding
  applies once per order, not once per contract, so the fee is not linear in size.

Not verified, and therefore not applied: a per-contract fee cap reported only by the secondary
aggregator; a sports-series fee exception mentioned on the same help page. The 0.25 maker ratio was
inherited from an earlier 2026-07-02 verification and was not independently re-confirmed on
2026-09-01. Anything the module cannot confirm against a primary source fails closed (raises) rather
than guessing. Fees are entry-side only; settlement carries no fee on this venue.

Consequence for the paper desk: a one-contract maker quote is always charged one cent, the minimum
the rounding allows, at every price. That is an over-charge relative to the unrounded schedule and is
conservative (`scripts/platformkit/execution/paper_maker.py`, the `_QTY` comment).

## 2. Maker versus taker

A taker crosses the spread and pays the taker fee; a maker rests a quote and pays the lower maker fee
only if filled. The paper desk models the maker side only:
`scripts/platformkit/execution/paper_maker.py` rests a paper quote, and a later captured book fills it
only when it trades strictly through the quote price (`trades_through`). Touching the price does not
fill, because the desk does not model queue position. When a tick carries only a mid, the book is
widened by one cent per side, which is optimistic in a wide late-game book (documented in the same
file).

## 3. The in-game model against the live Kalshi price (Gate A-0, measured)

Source: [GATE_A0_2026-09-14.md](evidence/ingame/GATE_A0_2026-09-14.md). Paired Brier on identical
ticks, game-clustered bootstrap CI (2,000 resamples); the source prints five decimals, rounded here to four.

| Sport | Model Brier | Kalshi price Brier | Delta | CI | Games | Reading |
|---|---|---|---|---|---|---|
| MLB win probability | 0.2377 | 0.2067 | +0.0310 | [0.0170, 0.0454] | 227 | BEHIND: the market is closer to the outcome |
| Soccer (international) | 0.2279 | 0.1427 | +0.0852 | [0.0488, 0.1270] | 51 | BEHIND |

Caveat carried from [QUANT_BRIEF.md](QUANT_BRIEF.md): both corpora later failed the join-integrity
check; the per-game segmented MLB revision (178 games) keeps the verdict, and 27 of the 51 soccer
files were kept after segmentation.

## 4. Why maker-side, and why paper only

- The in-game model trails the live price (section 3), so no taker strategy built on it is justified;
  the only question the desk can study honestly is execution quality of resting quotes.
- Forward record: to 2026-10-04 the paper desk has 0 qualified games in any sport, 136 TTL-30 credited
  paper fills on unqualified tape, and every pooled cell is INSUFFICIENT
  ([cumulative/2026-10-04.md](evidence/forward/cumulative/2026-10-04.md)).
- Six go-live gates were pre-registered on 2026-09-17 ([GO_LIVE_GATES.md](GO_LIVE_GATES.md)); gate G6
  needs at least eight consecutive weeks of shadow maker quoting with a fee-netted markout whose
  game-clustered 95% interval excludes zero, on at least two independent market families. It has not started as of 2026-10-19 (zero weeks collected) (fill realism is counts-only; no markout series exists), so the desk stays paper.

## 5. What is not claimed

No claim that the desk's quotes would be filled as modelled on a real queue, no markout level, and no
statement about returns. The fee module is a cost model only.

---
**Navigate:** [Methods page](CLV_AND_MARKOUT.md) - [Quant brief](QUANT_BRIEF.md) - [Evidence index](../EVIDENCE.md)
