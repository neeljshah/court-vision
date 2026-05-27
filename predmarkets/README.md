# predmarkets — Polymarket + Kalshi edge scanner

A dry-run prediction-markets pipeline that snapshots open markets on both
venues, runs probability forecasters against each open market, identifies
mispricings, sizes bets via Kelly with risk caps, logs intended orders to a
CSV ledger, and auto-grades them as markets resolve.

**No live order placement is wired up anywhere in this module.** Every output
is dry-run. Promoting to live trading requires a separate code path that does
not exist in this tree.

## Quick start

```bash
# Run the full daily cycle (settle yesterday → snapshot today → scan → place → summary)
python -m predmarkets.morning_briefing

# Or run individual stages:
python -m predmarkets.snapshot              # both venues
python -m predmarkets.edge_scanner --snapshot data/pm/markets_2026-05-27.parquet \
    --overrides manual_probs.json
python -m predmarkets.dry_run_placer place --snapshot data/pm/markets_2026-05-27.parquet
python -m predmarkets.dry_run_placer settle
python -m predmarkets.dry_run_placer summary
python -m predmarkets.backtest --lookback-days 90 --lead-hours 24
```

## Module layout

| Module                                          | What it does                                                                     |
| ----------------------------------------------- | -------------------------------------------------------------------------------- |
| `predmarkets/pm_client.py`                      | Read-only Polymarket client (Gamma + CLOB + Data API). No wallet, no HMAC.       |
| `predmarkets/kalshi_client.py`                  | Read-only Kalshi client. Handles legacy + `orderbook_fp` schemas, MVE filtering. |
| `predmarkets/snapshot.py`                       | Daily parquet snapshot of open + resolved markets per venue.                     |
| `predmarkets/edge_scanner.py`                   | Forecaster ABC + EdgeScanner with Kelly + slippage guard.                        |
| `predmarkets/forecasters/crypto_threshold.py`   | GBM closed-form pricing of crypto threshold markets via CoinGecko.               |
| `predmarkets/forecasters/llm_forecaster.py`     | Claude-backed forecaster for Politics / Geopolitics / Entertainment / Sports.    |
| `predmarkets/dry_run_placer.py`                 | CSV ledger writer + venue-aware auto-settle + per-model/category roll-up.        |
| `predmarkets/backtest.py`                       | OOS replay against PM resolved markets with historical CoinGecko spot.           |
| `predmarkets/morning_briefing.py`               | One-command operator workflow + markdown report.                                 |

## Data flow

```
[Polymarket] -> pm_client ----+
                              +-- snapshot.py --> data/{pm,kalshi}/markets_<date>.parquet
[Kalshi]     -> kalshi_client +                                |
                                                               v
forecasters/* --(Forecaster ABC)-- edge_scanner.py --(EdgeScanner.scan)--> ranked edges
                                                                                  |
                                                                                  v
                                                                       dry_run_placer.py
                                                                                  |
                                                                                  v
                                                              data/predmarkets_ledger/ledger.csv
                                                                                  |
                                                                                  v
                                                              (auto-settle when markets resolve)
                                                                                  |
                                                                                  v
                                                              backtest.py (honest OOS ROI)
                                                              morning_briefing.py (daily report)
```

## Forecaster coverage

- **Crypto threshold** (`CryptoThresholdForecaster`): "Will Bitcoin be above $X by date Y?" / "Will BTC reach $K by Z?" / "Will ETH dip to $L?". Uses CoinGecko spot + 30d realized vol + GBM closed-form + reflection-principle touch barrier. Range markets ("between $A and $B") are skipped — multi-strike pricer not yet built.
- **LLM general-purpose** (`LLMForecaster`): everything else (Politics / Geopolitics / Entertainment / Science / Sports / World). Claude Haiku 4.5 with calibrated system prompt requesting structured JSON. Daily on-disk cache + 5-min ephemeral prompt cache for batch efficiency. Set `ANTHROPIC_API_KEY` env var to activate; gracefully no-ops without it.

To add a new forecaster, subclass `predmarkets.edge_scanner.Forecaster`, implement `applies_to(market)` + `forecast(market) -> Forecast | None`, and register it in `predmarkets/morning_briefing.py:_section_scan_and_place`.

## Risk caps (Kelly sizing)

`EdgeScannerConfig` defaults (override in `morning_briefing.run(...)`):

| Cap                              | Value | Meaning                                                       |
| -------------------------------- | ----- | ------------------------------------------------------------- |
| `kelly_fraction_of_full`         | 0.25  | Bet 1/4-Kelly to dampen variance                              |
| `per_bet_cap` (× bankroll)       | 0.01  | Max 1% per single bet                                         |
| `per_category_cap` (× bankroll)  | 0.05  | Max 5% total across one category                              |
| `total_exposure_cap` (× bankroll)| 0.20  | Max 20% bankroll deployed across all open dry-run rows        |
| `edge_threshold`                 | 0.05  | Reject any edge < 5 percentage points                         |
| `max_slip_pp`                    | 0.02  | Reject any bet that would walk > 2pp past best price          |

## Scheduling (operator setup)

The morning_briefing is idempotent and safe to run on a daily cron. On Windows
Task Scheduler, schedule it for ~9 AM ET so PM markets that resolved overnight
get settled before the day's scan:

```powershell
# Once a day at 09:00 ET
schtasks /Create /SC DAILY /ST 09:00 /TN "PredMarkets Briefing" /TR ^
  "conda activate basketball_ai && python -m predmarkets.morning_briefing"
```

On macOS / Linux:

```cron
0 13 * * * cd /path/to/nba-ai-system && conda run -n basketball_ai \
  python -m predmarkets.morning_briefing >> data/cache/predmarkets_cron.log 2>&1
```

A heartbeat-style health check is not yet wired up — the cron stdout/log file
is the system of record. Promote that to a watchdog if the briefing ever
starts running unattended for weeks.

## Honest limitations as of last update

- Polymarket public-read access from US IPs is working but not guaranteed.
  The clients raise `PMGeoBlockedError` on HTTP 403 so callers can surface
  it cleanly.
- The crypto forecaster's edges concentrate on long-horizon BTC tail-risk
  markets (e.g. NO on "BTC dips to $45K by EOY 2026"). The model assumes
  drift = 0 and 30-day realized vol — both can be tuned.
- The LLM forecaster's calibration is unmeasured. Confidence is capped at
  0.45 (high label) so Kelly sizing stays conservative.
- The backtest harness is plumbed but the resolved-market pool currently has
  no long-horizon threshold markets to score. OOS ROI requires waiting for
  the open markets to resolve.
- Range markets ("between $A and $B") and Up/Down 5-minute markets are
  explicitly skipped — adding a multi-strike pricer is the next forecaster
  upgrade.
- No election / polling forecaster, no econ-consensus forecaster, no
  sports-specific forecaster (Monte Carlo through remaining playoff games).
  The LLM forecaster covers these in general but a grounded model would
  beat it on calibration.
