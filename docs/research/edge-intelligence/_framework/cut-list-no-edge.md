# CUT-LIST -- where there is NO durable edge (stop spending here)
_Part of the edge-intelligence corpus. The directive: "get rid of constraints where no edge
is there." This file names the markets/efforts to DEPRIORITIZE so data + modeling + scraping
effort flows to the beatable pockets. Grounded in the system's own measured findings. ASCII._

## Principle
Effort is finite. Every hour spent trying to beat an EFFICIENT market is an hour not spent
deepening a BEATABLE one. We CUT (stop hunting $-edge; keep only as calibrated decision-support
or drop entirely) anything where the honest measured verdict is "we match the close" or worse.
Cutting is not defeatism -- it is REALLOCATION toward where edge actually lives.

## CUT 1 -- Sharp pregame MAINLINES (h2h / spread / total) on major sports
Evidence: full-season walk-forward backtests are well-calibrated but do NOT beat the close;
CLV ~ 0 (the cleanest efficiency proof in the project). The famous "+18.38% ROI" was a
market-follow + in-sample + flat-payout ARTIFACT (retracted; never reprint as current). The
sharp consensus (Pinnacle et al.) already integrates everything our team models know.
ACTION: keep mainline predictions as CALIBRATED decision-support + a CLV yardstick; STOP
hunting a mainline $-edge. Do not add features/seasons chasing it (17 feature-add reverts
already proved the ceiling).

## CUT 2 -- NBA PREGAME team markets as an edge source
Evidence: PTS/REB at the historical-data ceiling; 6 architectures + 4 levers REJECT;
recency>volume (adding seasons hurts); the ONLY durable model edge is AST pregame (~+7%,
prop-level, both directions, never in playoffs). NBA pregame matches the close.
ACTION: do NOT invest in more NBA pregame team-market modeling. Keep the AST prop edge (RAW,
calibrated). Redirect NBA effort to: (a) same-day FRESHNESS/availability (the one unmodeled
lever), (b) NBA PLAYER PROPS via the MC-sim ladder when season returns, (c) in-game.

## CUT 3 -- Momentum / "hot hand" style signals as bet drivers
Evidence: INT-81 momentum z_vs_null = -1.75; momentum-aligned bets perform WORSE than random.
ACTION: do not build betting signals on momentum/streak alignment. (Form as a RATE input to a
calibrated distribution is fine; "ride the hot hand" as an edge is not.)

## CUT 4 -- Rare-event player props where we measured negative skill
Evidence (World Cup, leak-free backtest): Cards (BSS -0.11), Assists (-0.07), Goals (-0.03),
Shots-on-Target (~0) -- worse than or equal to the base rate. Likely MLB analog: Total Bases /
RBIs / Runs (multi-outcome, teammate-dependent, Poisson is a poor shape).
ACTION: DEMOTE these to model-view-only / do not paper-bet them as edges; the calibration
tier already does this. Concentrate prop effort on the PROVEN stats (WC Saves; expected MLB
Hits / Pitcher-Ks / Walks) and on getting more data before trusting the rest.

## CUT 5 -- Over-flexible recalibration / signals on thin data
Evidence: isotonic P(over) recal on 24 WC matches OVERFITS (in-sample improves, OOS Brier
worse) -> DEFERRED. Single-fold lifts are artifacts (project-wide lesson; many reverts).
ACTION: do not ship calibration/feature tricks that only help in-sample. Gate every lever on
leak-free OOS improvement; re-fit only as data grows.

## CUT 6 -- Arbitrage as a profit center
Evidence: real two-book arbs are rare, fragile, and limit-constrained; honest contract says
arbs are not standing income.
ACTION: keep arb DETECTION (free, model-less, a nice flag) but do not architect around arb
as the money engine. Line-shopping (best price) is the durable execution edge, not arb.

## KEEP / PUSH (the contrast -- where effort SHOULD go)
- Soft/DFS PLAYER PROPS in PROVEN stats (per-player distributions vs lazy lines).
- LIVE / in-game repricing (books lag realized state -- the decisive combinable lever).
- STALE-line / soft-book line-shopping (execution edge, model-free).
- PREDICTION-MARKET vs sportsbook divergence (Kalshi/Polymarket).
- CORRELATED SGPs (joint distribution we can price; books misprice correlation).
- DEEPER DATA in the beatable pockets (the intelligence corpus + new sources) -- this is the
  lever that actually moves the ceiling, per the deepest-data north star.

## How to use this file
Every per-sport edge-map cites this cut-list. The paper loop should not accrue (or should
clearly quarantine) bets in CUT categories. When a new idea arrives, first ask: "is this in a
CUT category?" If yes, it needs extraordinary leak-free OOS evidence before any effort.
