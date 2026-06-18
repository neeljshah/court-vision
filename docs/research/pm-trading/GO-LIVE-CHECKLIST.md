# PM-Trading Go-Live Checklist (HUMAN-CONFIRM)

**Status: PAPER ONLY. No real capital has been or will be deployed by the agent.**
This document is the human-owned gate between the paper system and real money.
Nothing below is automatable by the agent: the agent never stores a real key,
never flips `ENABLED`, never places a real order.

---

## 0. What the system is (honest)

A paper-first prediction-market trading stack on top of the calibrated 4-sport
model. Built under `scripts/platformkit/pm_trading/`:

- `venues/` — `MarketVenue` interface + deterministic `PaperVenue` (default) +
  env-gated `KalshiVenue`/`PolymarketVenue` stubs (key-presence only).
- `edge_signal.py` — devig + contract→edge_bps.
- `risk.py` — the gate: fractional Kelly (≤¼), exposure caps, drawdown +
  daily-loss kill-switch, global `ENABLED` (default OFF). Reuses the real
  `betting_portfolio` guard.
- `strategies/` — cross_market_arb, model_vs_market (gate-gated), market_maker.
- `execution.py` — best execution (slippage cap, splitting, re-quote).
- `pnl.py` — paper blotter + the real prediction ledger (CLV).
- `run_trader.py` — the PAPER daemon.
- `run_live.py` / `live_feed.py` — forward-log the model on REAL games (the
  multi-week track record).
- `validation.py` — the paper-validation gate (PASS/FAIL).

**Measured reality:** summer sports (MLB/tennis/World-Cup soccer) match the
devigged close — model edge ≈ 0 after vig. The only durable edge ever found
(NBA AST ~+5%) is regular-season-only. Structural edges (arb, market-making,
thin markets) are real but capacity-capped (~$100–$2k/opportunity), so a large
bankroll does not scale. **Expected value is small and may be negative.**

---

## 1. PASS the paper gate (necessary, not sufficient)

- [ ] `validation.py` reports **PASS** on the controlled scenario (sanity of the
      machinery) — already demonstrated.
- [ ] **Real-games forward record**: run `run_live.py` daily for **multiple
      weeks**; once outcomes settle, the real ledger (`read_ledger`) shows, on
      out-of-sample real games:
  - [ ] net paper P&L **> 0** after fees,
  - [ ] mean **CLV > 0** (beating the devigged close), with the lower CI bound
        above zero (not noise),
  - [ ] result **survives the eval_gate** (leak-free, ≥2 corpora, no single-fold
        artifact).
- [ ] An honest **FAIL/flat** here = **STOP**. Do not deploy. This is a success
      (the system told you the truth), not a bug to "fix" by loosening the gate.

## 2. Wire a real market-price source (currently absent)

- [ ] Implement `forward_capture` `RealFeed._raw_quotes()` against the odds API
      (`FORWARD_CAPTURE_ODDS_API_KEY`) and/or the real exchange order books.
      Until this exists, paper TRADES are 0 (the system only forward-logs).
- [ ] Confirm devig (`shin_devig_decimal`) produces sane fair lines on live data.

## 3. Risk rails verified on paper FIRST

- [ ] Drawdown kill-switch flattens + halts (tested).
- [ ] Daily-loss limit halts (tested).
- [ ] Per-market / per-event / total exposure caps enforced (tested).
- [ ] Fractional Kelly ≤ ¼, correlation haircut (tested).
- [ ] Set conservative real caps for your actual bankroll (NOT the test values).

## 4. Legal / compliance (HUMAN-owned — the agent cannot assess these)

- [ ] **Kalshi is CFTC-regulated.** Confirm eligibility + complete KYC yourself.
- [ ] Confirm **jurisdiction eligibility** for Polymarket (geofencing/ToS).
- [ ] Read each venue's **API ToS** re: automated/algorithmic trading; confirm
      it is permitted for your account.
- [ ] Understand **tax** treatment of contract P&L in your jurisdiction.
- [ ] Confirm you are using **risk capital you can lose**.

## 5. Keys & secrets (HUMAN-owned)

- [ ] Provision API keys in a secrets manager / env — **never** in code, never
      committed. The agent reads presence only.
- [ ] Scope keys to least privilege; set venue-side position/loss limits too.
- [ ] Have a manual **kill procedure** (revoke key + flatten) you can run by hand.

## 6. The go-live switch (explicit human action)

- [ ] Start with a **tiny** real allocation (e.g. a few hundred dollars), arb /
      market-making only, on the markets that PASSed.
- [ ] Flip `pm_trading.ENABLED = True` **yourself** (the agent never does).
- [ ] Watch the first sessions live; confirm fills, fees, and the kill-switch
      behave as on paper.
- [ ] Scale only if live P&L + CLV continue to clear the gate. Re-confirm caps.

---

## Hard invariants (never violated, even unattended)

- No real key stored/logged by the agent. No real order placed by the agent.
- `ENABLED` default OFF; flipping it on is a human action.
- No fabricated edge/ROI; a losing strategy is a recorded REJECT.
- Local commits only; the public origin never receives this or any key/ledger.
