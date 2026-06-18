# PREDICTION-MARKET AUTOMATED TRADING -- NEW-SESSION KICKOFF PROMPT

> Paste the block below into a fresh Claude Code session to start building. Local-only doc
> (docs/research/ is gitignored). This is real money + regulated markets -- the honest rails
> are binding, not optional. ASCII only.

---

```
We are building an AUTOMATED PREDICTION-MARKET TRADING SYSTEM on top of the existing calibrated
4-sport prediction stack in C:/Users/neelj/nba-ai-system. The goal: turn the model's calibrated
probabilities into EXECUTED, RISK-MANAGED positions on prediction-market EXCHANGES (Kalshi,
Polymarket, and any sports event-contract venue), with best execution and a forward-validated P&L
record. This is decision-support + execution infrastructure, NOT a guaranteed money printer --
the realistic edges are cross-market arbitrage, thin-market mispricing, market-making/spread
capture, and trading the model's estimate vs the exchange price. Each must be FORWARD-VALIDATED on
paper before real capital. An honest "no edge here / unprofitable on paper" is a recorded SUCCESS.

WHY PREDICTION MARKETS (the thesis): they are EXCHANGES, not books -- no vig, you trade peers.
That opens three structural edges sportsbooks lack: (1) CROSS-MARKET ARBITRAGE -- same event priced
differently across Kalshi / Polymarket / the Shin-devigged sportsbook line -> lock the spread,
market-neutral; (2) MARKET-MAKING -- post two-sided quotes on thin markets, capture the spread,
manage inventory; (3) MODEL-vs-EXCHANGE -- trade our calibrated probability against the exchange
price where the model survives the gate. Liquid mainlines stay efficient; the edge is in arb, MM,
and thin/new markets.

REUSE (already built; read first, do NOT duplicate or edit human-gated trees):
  - scripts/platformkit/eval_gate/        : the leak-free gate = the JUDGE for any edge claim.
  - scripts/platformkit/ledger/           : append-only track-record ledger (log every position).
  - scripts/platformkit/forward_capture/  : the CLV/forward-capture clock + odds archive.
  - scripts/platformkit/market_coverage/  : prices EVERY market off the joint sim (the signal).
  - scripts/platformkit/edge_engine/      : information-edge extraction + bounded combiner.
  - scripts/platformkit/calibration_record.py + predict_matchup.py : the calibrated model output.
  - src/prediction/betting_portfolio.py (READ-ONLY) : fractional-Kelly + correlation + drawdown
    kill-switch already exist -- reuse the sizing/risk logic; do NOT edit human-gated src/.

ARCHITECTURE (build NEW under scripts/platformkit/pm_trading/):
  1. VENUE ADAPTERS (pm_trading/venues/): a MarketVenue interface (get_markets, get_orderbook,
     get_price, place_order, cancel, positions, balance) with a KalshiVenue + PolymarketVenue +
     a deterministic PaperVenue (simulated fills off a real or recorded order book). REAL venues
     are env-gated (KALSHI_API_KEY etc; key PRESENCE only, never a literal); PaperVenue is the
     default and the only one that runs without human-confirmed keys.
  2. SIGNAL LAYER (pm_trading/signal.py): map each open prediction-market contract to our
     calibrated probability (via market_coverage / predict_matchup) + the devigged sportsbook line
     where it exists. Output: fair_prob, market_prob, edge_bps, confidence -- the model authors the
     number, never an LLM.
  3. EDGE LAYER (pm_trading/strategies/): (a) cross_market_arb (same event, >threshold price gap
     across venues, net of fees+slippage); (b) model_vs_market (our prob vs exchange price, only
     where the model survives the gate forward); (c) market_maker (two-sided quotes on thin
     markets, inventory-bounded). Each strategy emits sized, risk-checked orders, never raw bets.
  4. EXECUTION LAYER (pm_trading/execution.py): BEST EXECUTION -- limit orders (never market unless
     forced), walk the book to a max-slippage cap, split large orders, respect venue tick/min size,
     time-in-force, and re-quote logic for the MM strategy. Log fills.
  5. RISK LAYER (pm_trading/risk.py): hard per-market + per-event + total exposure caps, fractional
     Kelly sizing (reuse betting_portfolio logic), correlation-aware exposure, a drawdown kill-switch
     that flattens + halts, daily loss limit, and a global ENABLED flag default OFF.
  6. P&L + CLV LEDGER (pm_trading/pnl.py): every order/fill/settlement -> the existing X3 ledger
     with pred_ts before the price move; grade forward P&L AND CLV vs the closing/settlement price.
     Logs probabilities + realized P&L only; no fabricated ROI.
  7. THE LOOP (pm_trading/run_trader.py): a daemon (fits the existing daemon framework) that polls
     venues -> signals -> strategies -> risk-check -> execute -> log, on an interval, with a
     PAPER-MODE default and a loud "PAPER -- WIRE KEYS + HUMAN-CONFIRM TO GO LIVE" banner.

BINDING HONEST RAILS (non-negotiable -- this is real money + regulated markets):
  - PAPER-FIRST: the system runs end-to-end on PaperVenue with NO real keys. NO real capital until a
    multi-week forward PAPER P&L + CLV record (logged in the ledger) is positive AND survives the gate.
  - EVERY edge gate-confirmed: a strategy goes live ONLY after forward-validated paper P&L > fees +
    slippage, with a Diebold-Mariano-style significance check; an in-sample backtest is NOT enough.
  - HARD RISK: position/exposure caps, drawdown kill-switch, daily loss limit, fractional Kelly (<=1/4),
    NO martingale/chasing, global ENABLED flag default OFF. The kill-switch is tested before anything.
  - LEGAL/COMPLIANCE (human-owned): Kalshi is CFTC-regulated; each venue's API Terms of Service govern
    automated trading; KYC, eligibility-by-jurisdiction, and tax are the human's responsibility. The
    agent NEVER stores a real key in code, NEVER places a real order, and flags go-live as HUMAN-CONFIRM.
  - NO fabricated edge/ROI/"printer" language anywhere; honest paper P&L only; record losing strategies
    as REJECTs (a success). Calibration + a real forward P&L record is the deliverable, never a promise.
  - Repo discipline: LOCAL commits only (origin is PUBLIC -- NEVER push; this trading code stays local /
    gitignored). Build only in scripts/platformkit/pm_trading/; do NOT edit src/ kernel/ api/
    scripts/team_system/ intel/. <=300 LOC/file, ASCII only, per-file tests only (full pytest freezes
    the box), conda env basketball_ai, prefix every bash with `cd /c/Users/neelj/nba-ai-system &&`.

BUILD ORDER (each step gated, paper-first):
  1. PaperVenue + the MarketVenue interface + tests (no real venue yet).
  2. signal.py wiring model_coverage/predict_matchup -> fair_prob per paper contract + tests.
  3. cross_market_arb + model_vs_market strategies (paper) + risk.py caps/kill-switch + tests.
  4. execution.py best-execution on the paper book + pnl.py -> ledger forward P&L/CLV + tests.
  5. run_trader.py paper daemon loop + a multi-week paper-validation harness (the gate for going live).
  6. Kalshi/Polymarket REAL adapters as env-gated stubs (no live call) + a HUMAN-CONFIRM go-live
     checklist (keys, KYC, ToS, tiny-stake pilot, kill-switch drill). STOP at the go-live line.

PROCESS: plan with /gsd:plan-phase or a Workflow fan-out; Opus /code-review + an honesty/risk gate on
every diff; per-file tests only; commit each step LOCALLY. Use /claude-api or claude-code-guide to verify
any volatile Kalshi/Polymarket API detail before relying on it. Report honestly: if paper P&L is negative
or a strategy rejects, say so plainly -- that is the system working.

FIRST MOVE: read the REUSE files above, then build step 1 (PaperVenue + MarketVenue interface + tests).
Report the paper-trading architecture and the go-live HUMAN-CONFIRM checklist when step 1 is green.
```

---

## Honest notes before you run it

- **The most realistic edge is cross-market arbitrage** (same event, different price across venues) -- it is market-neutral and closest to "low-variance," but it is capital- and speed-competitive and the gaps are small/fleeting. Market-making on thin sports contracts is next. Model-vs-exchange is real only where your model survives the forward gate.
- **Prediction markets are still mostly efficient on liquid contracts.** The money is in thin/new markets and arb -- and it is **capped by liquidity** (you can't size big) and **competitive** (bots already hunt arb). This is a real business, not a printer.
- **Paper-trade for weeks before real capital.** The forward paper P&L + CLV record is the only honest proof. If it's negative, the system just saved you money.
- **You own the legal/financial line:** API keys, KYC, jurisdiction eligibility, ToS for automated trading, taxes, and the go-live decision. The build stops at HUMAN-CONFIRM before any real order.
