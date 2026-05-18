# court-vision-router

Cross-venue execution router for NBA prediction markets. Takes a win-probability signal from [Court Vision](https://github.com/neeljshah/nba-ai-system) and fills a target notional across **Polymarket** (Polygon CLOB) and **SX Bet** (SX Chain RFQ) at the best size-weighted price.

**Read-only by default — order submission is stubbed.** The router produces signed dry-run payloads; swapping `DryRunWallet` for a real `eth_account`-backed wallet flips it live.

---

## Why this exists

ParlayX-style syndicate execution has three hard parts:

1. **Venue abstraction.** Polymarket is a CLOB on Polygon. SX Bet is RFQ/maker orders on SX Chain. Different settlement tokens, different signature schemes, different book structures. The execution engine should not care which is which.
2. **Large orders.** A $100 bet fills on top-of-book. A $50k bet has to *walk* each book and usually *split* across venues. Greedy top-of-book routing leaves size on the table.
3. **Signal.** You only want to route where edge exists. Court Vision's win probability — built on spatial CV features (defender distance, spacing, fatigue) not in opening lines — is the signal this router filters on.

This repo is the minimum honest sketch of all three.

---

## Architecture

```
router.py                  # orchestrator + CLI
execution.py               # size-weighted book walk + multi-venue splitter
chain.py                   # Wallet protocol, Polygon + SX Chain ctxs, DryRunWallet
venues/
  base.py                  # Book / Level / Venue protocol
  polymarket.py            # Gamma + CLOB adapter (chain="polygon")
  sx_bet.py                # markets/orders adapter (chain="sx")
tests/test_execution.py    # 5 unit tests, no network
```

Adding a new venue = one file implementing `Venue` (`find_market`, `fetch_book`, `submit_order`) + a `chain` attribute. No changes to `execution.py` or `router.py`.

---

## Execution logic

```
for each venue:
    book  = venue.fetch_book(market)
    quote = walk_book(book, target_usd)            # size-weighted avg price + slippage
    keep quote if (cv_prob - avg_fill_price) >= MIN_EDGE

sort quotes cheapest avg price first
greedily consume until target_usd is filled
emit per-chain signed payloads via chain.wallet_for(venue.chain)
```

Book walk reports **slippage_bps** — the basis-point gap between top-of-book and size-weighted fill. That's the number the syndicate desk actually cares about.

---

## Chain abstraction

```python
from chain import wallet_for
wallet = wallet_for(venue.chain)        # "polygon" → Polygon USDC.e, "sx" → SX Chain USDC
sig = wallet.sign_order(payload)        # EIP-712 (stubbed)
gas = wallet.estimate_gas_usd(payload)
```

`Wallet` is a `Protocol`. Swap `DryRunWallet` for an `eth_account`-backed impl and the router goes live without edits elsewhere.

---

## Usage

```bash
pip install requests
python router.py                                          # defaults: Lakers vs Suns, $100, cv=0.62
python router.py --game "Celtics vs Knicks" \
                 --team-a Celtics --team-b Knicks \
                 --cv-prob 0.58 --notional 25000 --min-edge 0.025
python -m pytest tests/ -q                                # 5 tests, no network
```

Output: JSON to stdout + `example_output.json`. Includes per-venue books, per-venue quotes with slippage, allocations, unrouted residual, and dry-run signed payloads per chain.

---

## Status today (2026-04-24)

No live Lakers vs Suns game exists right now, so both venues return `"no active market found"` and routing status is `none`. That's the correct behavior — rerun on game day and you'll see books, slippage, and splits. The test suite exercises the execution engine against synthetic books so correctness doesn't depend on a live market.

---

## Disclaimer

Research/educational. Does not place, recommend, or facilitate wagers. `DryRunWallet` is the default; no keys are read from the environment.
