# METHOD: CLV computation -- the formula, the sign convention, and the DFS-pickem caveat
_Part of the edge-intelligence method library (B). Reusable recipe. ASCII only.
Code pointers: scripts/platformkit/prop_line_history.py (the reference two-way CLV +
closing-line capture), scripts/compute_clv.py (operator CLI + the SIGN-FIX flag),
scripts/platformkit/odds_shop.py::devig_twoway (the Shin devig the CLV depends on).
Discipline: feedback_clv_over_roi, feedback_clv_sign_record_clv_backwards (the sign bug)._

## What CLV is and why it is THE yardstick
CLV (closing-line value) = did you take a BETTER number/price than where the line CLOSED?
The closing line is the market's sharpest, most-informed estimate. Beating it repeatedly is
the market's OWN verdict that you were ahead of it -- and it predicts long-run profit even
when short-term ROI is buried in variance. CLV is preferred over ROI because small-N ROI is
noise (e.g. -47% on 7 bets means nothing; +131% from a too-tight distribution is an
artifact). CLV is the bridge from "calibrated" to "would make money"; real money is GATED on
proven forward positive CLV (proof-standards.md bar 6).

## The exact formula (two-way market: sportsbook / Underdog)
Given a TAKEN bet (side, taken_price as decimal odds) and the CLOSING two-way prices
(close_over, close_under):
  1. DEVIG the close to a no-vig fair probability for the taken side. Use the vetted Shin
     solver: fair_over, fair_under = odds_shop.devig_twoway(close_over, close_under). This
     removes the bookmaker margin so we compare against the market's FAIR estimate, not its
     vig-loaded price. (prop_line_history.py lines 191-194.)
  2. taken_p = 1 / taken_price (the prob implied by the price you actually got).
  3. CLV as a percentage:
       clv_pct = (fair_close - taken_p) / taken_p * 100.0
     (prop_line_history.py::clv_vs_close, lines 196-198.)

## The SIGN convention (this has been gotten BACKWARDS -- pin it down)
POSITIVE clv_pct = you took a BETTER number than the close: your price implies a LOWER
probability than the fair close, i.e. you are paid as if the outcome is LESS likely than the
market's fair estimate now says it is. NEGATIVE = worse number. (prop_line_history.py lines
176-181.) The price-based path (clv_vs_close above) is the canonical sign.
For the LINE-units path (stat-line movement, compute_clv.py), the correct convention:
  - OVER  -> better is a LOWER line, so you beat the close when it closes HIGHER:
             clv_pts = close_line - placed_line
  - UNDER -> clv_pts = placed_line - close_line
This is gated behind CV_CLV_LINE_SIGN_FIX (default the CLI opts IN via setdefault at the
entrypoint; the unit-test baseline stays byte-identical with the flag OFF). The LEGACY
default INVERTED both signs (documented bug B-1). (compute_clv.py lines 95-108, 220-225.)
KNOWN GOTCHA (memory: feedback_clv_sign_record_clv_backwards): betting_portfolio.record_clv()
records CLV with the sign backwards -- do NOT re-endorse it; use the prop_line_history /
compute_clv conventions above as the source of truth.

## Capturing the close (you cannot compute CLV without it)
You must log the line UP TO kickoff so the LAST logged price is the closing proxy:
  - log_board_lines: every tick, append one row per PRICED edge to a JSONL time series
    (data/frontend/prop_line_history.jsonl). No dedup -- it is a time series. Pick'em rows
    (no real two-way price) are SKIPPED. (prop_line_history.py lines 57-102.)
  - closing_snapshot: the latest-ts logged price for an exact (match, player, stat, line)
    = the closing-line proxy. (lines 136-161.)
HONESTY: the close is only APPROXIMATED by the last logged line; it is only as good as the
logging cadence. The loop must actually run up to kickoff for the history to accrue.

## The DFS pick'em caveat (no two-way close exists)
On standard DFS pick'em (PrizePicks-style), there is NO two-way price and the projection
line does not move on a fair two-way -> CLV-vs-close is UNDEFINED. Do not fabricate one.
prop_line_history.py SKIPS pick'em rows in log_board_lines (no price, line 78-81) and
clv_vs_close requires a real two-way (returns None otherwise). Prove edge on pick'em a
DIFFERENT way (edge-theory.md note on DFS):
  1. P(over) CALIBRATION vs realized (leak-free OOS Brier/ECE on the over/under outcome).
  2. Realized ROI at the FIXED payout structure (e.g. the 2/3/4/5/6-pick power/flex tables),
     at a meaningful N, not small-N.
  3. DFS-LINE MOVEMENT: did the projection itself move toward our number after we flagged
     it? A consistent post-flag move is the pick'em analogue of CLV.
Underdog/sportsbook two-way props DO have a close -> use the clv_vs_close formula above.

## The recipe (two-way)
  1. Log board lines every tick to kickoff (log_board_lines).
  2. At settle, closing_snapshot -> (close_over, close_under) for the exact prop.
  3. devig_twoway(close) -> fair_close for the taken side.
  4. clv_pct = (fair_close - 1/taken_price)/(1/taken_price) * 100; POSITIVE = beat close.
  5. Aggregate beat-rate and mean CLV over a meaningful sample; that is the CLV-PROVEN bar.

## Failure modes
  - WRONG SIGN: the recurring bug. Use the conventions above; do not trust record_clv().
  - NO DEVIG: comparing taken_p to the vig-loaded closing price overstates CLV by the
    margin. Always devig the close (Shin).
  - STALE/MISSING CLOSE: if the loop didn't run to kickoff, the "close" is an early line and
    CLV is meaningless. Check the closing_snapshot ts is near kickoff.
  - PICKEM TREATED AS TWO-WAY: inventing a close for fixed-payout pick'em. Use the pick'em
    proof path instead; clv_vs_close correctly returns None.
  - SMALL-N: a positive CLV on a handful of bets is not yet CLV-PROVEN; accrue (the gate
    treats < ~60 settled as INSUFFICIENT_DATA).

## Evidence-tier reminder
Positive forward CLV at a meaningful sample is the CLV-PROVEN tier -- the bar for real money.
It is a separate, higher bar than CALIBRATION-PROVEN. No fabricated $-edge; CLV is the
honest measure, not a profit claim.
