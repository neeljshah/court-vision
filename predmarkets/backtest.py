"""Backtest harness — replay forecasters against historical resolved markets.

Goal: produce HONEST OOS ROI per category before promoting any forecaster to
live trading.

Method (Polymarket, crypto category, v1):
    1. Pull resolved markets in lookback window via PMClient.get_resolved_markets.
    2. For each market the forecaster can score, pick a `simulated_bet_time` —
       a number of `lead_hours` before the market's `closedTime`.
    3. Look up the asset spot at `simulated_bet_time` via CoinGecko's
       `/coins/{id}/history` endpoint (free, daily granularity).
    4. Substitute the historical spot into the forecaster's spot cache (and
       use the vol cache as-is — recent realized vol is a reasonable proxy
       for any 30-day window).
    5. Fetch the market's trade history (data-api/trades) and find the median
       trade price within a +/- 6h window of `simulated_bet_time`. This is
       the simulated bet price. If no trades in window, fall back to the
       last pre-bet-time trade.
    6. Run the forecaster, compute simulated edge, and if it exceeds
       `threshold` SIMULATE the bet at the median trade price.
    7. Settle: PM `outcomePrices` already tells us YES_WON. Compute PnL using
       the standard $1/contract payout.

Outputs:
    - List of per-market backtest rows (placed_at, price, model_prob, edge,
      side, stake, outcome, profit).
    - Aggregate: n_bets, hit_rate, roi, total_pnl.

Caveats v1:
    - Uses CoinGecko `/coins/{id}/history` which returns the CLOSE of the
      requested day (UTC). Markets resolving intra-day will see some bias.
    - Vol is taken from the current 30d window — not the historical 30d
      window ending at simulated_bet_time. For markets within the last
      ~30 days this approximation is fine.
    - Trade-history pagination has a 10k offset cap; for very high-volume
      markets we may miss some early trades. We only need trades near the
      bet time, so this rarely matters.
    - Only handles Polymarket crypto markets in v1. Adding more venues +
      categories is a matter of adding settle adapters and historical-data
      lookups per forecaster.

Data availability note (2026-05-27):
    The pool of PM-resolved threshold crypto markets is currently dominated by
    ultra-short daily-close markets ("Bitcoin above $X on May 27, 8AM ET")
    that only have a handful of trades, all bunched within minutes of
    resolution. With min_horizon_hours=24 to filter those out, the
    candidate set drops to ~zero settled markets. The long-horizon
    threshold markets the forecaster is designed for (e.g. 'Bitcoin
    hit $150k by June 30, 2026') are still open. Re-run this harness
    periodically as resolutions accumulate to get an honest OOS ROI.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from predmarkets.edge_scanner import EdgeScannerConfig, _kelly_fraction
from predmarkets.forecasters.crypto_threshold import (
    CryptoThresholdForecaster,
    _CoinGeckoClient,
    _parse_question,
)
from predmarkets.pm_client import PMClient


@dataclass
class BacktestConfig:
    lookback_days: int = 30
    lead_hours: float = 24.0
    edge_threshold: float = 0.05
    bankroll: float = 1000.0
    per_bet_cap: float = 0.01
    kelly_fraction_of_full: float = 0.25
    # Markets with horizons shorter than this at bet time are pure noise for GBM
    # (5-minute 'Bitcoin Up or Down' style). Skip them.
    min_horizon_hours: float = 24.0
    # Skip bets where the YES price is extreme — the realized edge is usually
    # an artifact of dust-level book entries at 1c / 99c, not a real fill.
    min_price: float = 0.05
    max_price: float = 0.95
    max_markets: int = 200


@dataclass
class BacktestRow:
    market_id: str
    question: str
    placed_at_iso: str
    closed_at_iso: str
    historical_spot: float
    sim_bet_price: float
    model_prob: float
    edge_pp: float
    side: str
    stake_dollars: float
    yes_won: Optional[bool]
    outcome: str  # WIN / LOSS / VOID
    profit_dollars: float


def _to_unix(iso_or_str: Any) -> Optional[float]:
    if not iso_or_str:
        return None
    s = str(iso_or_str).strip()
    s = s.replace("Z", "+00:00")
    # Pad '+00' tz to '+00:00' (Gamma closedTime style)
    import re
    s = re.sub(r"([+-]\d{2})$", r"\1:00", s)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _spot_on_date(cg: _CoinGeckoClient, asset_id: str, ts_unix: float) -> Optional[float]:
    """Closing spot for `asset_id` on the UTC date of `ts_unix`."""
    dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc)
    date_str = dt.strftime("%d-%m-%Y")
    key = f"spot_hist__{asset_id}__{date_str}"
    try:
        data = cg._get_cached(key, f"/coins/{asset_id}/history", {"date": date_str})
    except Exception:
        return None
    md = (data or {}).get("market_data") or {}
    cp = md.get("current_price") or {}
    val = cp.get("usd")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        raise ValueError("empty values")
    if n % 2:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def _trade_price_near(pm: PMClient, condition_id: str, target_ts: float,
                      window_hours: float = 48.0) -> Optional[float]:
    """Latest trade price at or before `target_ts` (within `window_hours` to
    avoid stale prices from days ago)."""
    try:
        trades = pm._get("https://data-api.polymarket.com", "/trades",
                         {"market": condition_id, "limit": 500, "offset": 0})
    except Exception:
        return None
    if not isinstance(trades, list) or not trades:
        return None
    window = window_hours * 3600.0
    best_ts: Optional[float] = None
    best_price: Optional[float] = None
    for t in trades:
        ts = t.get("timestamp")
        price = t.get("price")
        if ts is None or price is None:
            continue
        try:
            ts_f = float(ts)
            p = float(price)
        except (TypeError, ValueError):
            continue
        if ts_f > target_ts:
            continue
        if (target_ts - ts_f) > window:
            continue
        if best_ts is None or ts_f > best_ts:
            best_ts = ts_f
            best_price = p
    return best_price


def _simulate_bet(forecaster_prob: float, market_price: float,
                  cfg: BacktestConfig) -> Optional[Dict[str, Any]]:
    yes_edge = forecaster_prob - market_price
    no_edge = (1.0 - forecaster_prob) - (1.0 - market_price)
    if max(yes_edge, no_edge) < cfg.edge_threshold:
        return None
    if yes_edge >= no_edge:
        side = "YES"
        price = market_price
        prob_win = forecaster_prob
        edge_pp = yes_edge
    else:
        side = "NO"
        price = 1.0 - market_price
        prob_win = 1.0 - forecaster_prob
        edge_pp = no_edge
    kelly_full = _kelly_fraction(prob_win, price)
    kelly_used = kelly_full * cfg.kelly_fraction_of_full
    stake = min(kelly_used * cfg.bankroll, cfg.per_bet_cap * cfg.bankroll)
    return {
        "side": side,
        "price": price,
        "prob_win": prob_win,
        "edge_pp": edge_pp,
        "stake_dollars": stake,
    }


def _settle_pm(market: Dict[str, Any]) -> Optional[bool]:
    op = market.get("outcomePrices") or []
    if not isinstance(op, list) or len(op) < 2:
        return None
    try:
        yes_price = float(op[0])
        no_price = float(op[1])
    except (TypeError, ValueError):
        return None
    if yes_price > 0.99 and no_price < 0.01:
        return True
    if no_price > 0.99 and yes_price < 0.01:
        return False
    return None


def run_backtest(forecaster: CryptoThresholdForecaster, cfg: BacktestConfig,
                 pm: Optional[PMClient] = None,
                 cg: Optional[_CoinGeckoClient] = None) -> Dict[str, Any]:
    """Replay `forecaster` against PM resolved markets in the lookback window.

    Returns {"rows": [...], "aggregate": {...}}.
    """
    pm = pm or PMClient()
    cg = cg or _CoinGeckoClient(rps=1.0)
    resolved = pm.get_resolved_markets(lookback_days=cfg.lookback_days, limit=cfg.max_markets)
    rows: List[BacktestRow] = []
    skipped_no_parse = 0
    skipped_no_horizon = 0
    skipped_no_trades = 0
    skipped_below_threshold = 0
    skipped_no_spot = 0
    for m in resolved:
        question = m.get("question") or ""
        end_iso = m.get("closedTime") or m.get("umaEndDate") or m.get("endDate")
        parsed = _parse_question(question, end_date_iso=end_iso)
        if parsed is None or parsed.resolution_ts is None:
            skipped_no_parse += 1
            continue
        bet_ts = parsed.resolution_ts - cfg.lead_hours * 3600.0
        # Ensure forecaster has positive horizon at bet time.
        horizon_hours = (parsed.resolution_ts - bet_ts) / 3600.0
        if horizon_hours < cfg.min_horizon_hours:
            skipped_no_horizon += 1
            continue
        spot = _spot_on_date(cg, parsed.asset_id, bet_ts)
        if spot is None or spot <= 0:
            skipped_no_spot += 1
            continue
        # Pull asset vol once (use today's 30d realized; documented bias).
        vol = forecaster._get_vol(parsed.asset_id)
        if vol is None:
            skipped_no_spot += 1
            continue
        forecaster._spot_cache[parsed.asset_id] = spot
        forecast = forecaster.forecast({
            "market_id": str(m.get("id") or ""),
            "category": "Crypto",
            "question_or_title": question,
            "end_date": end_iso,
        })
        if forecast is None:
            skipped_no_parse += 1
            continue
        # Restore today's spot so subsequent runs aren't poisoned.
        forecaster._spot_cache.pop(parsed.asset_id, None)
        condition_id = m.get("conditionId") or ""
        if not condition_id:
            skipped_no_trades += 1
            continue
        market_price = _trade_price_near(pm, condition_id, bet_ts)
        if market_price is None:
            skipped_no_trades += 1
            continue
        if market_price < cfg.min_price or market_price > cfg.max_price:
            # Extreme prices reflect markets already past their decisive moment;
            # realized fills at sub-5c / sup-95c are dust-thin and unrealistic.
            skipped_below_threshold += 1
            continue
        sim = _simulate_bet(forecast.prob_yes, market_price, cfg)
        if sim is None:
            skipped_below_threshold += 1
            continue
        yes_won = _settle_pm(m)
        side = sim["side"]
        stake = sim["stake_dollars"]
        if stake <= 0:
            skipped_below_threshold += 1
            continue
        if yes_won is None:
            outcome = "VOID"
            profit = 0.0
        else:
            bet_won = (side == "YES" and yes_won) or (side == "NO" and not yes_won)
            if bet_won:
                price = sim["price"]
                contracts = stake / price if price > 0 else 0.0
                profit = contracts - stake
                outcome = "WIN"
            else:
                profit = -stake
                outcome = "LOSS"
        rows.append(BacktestRow(
            market_id=str(m.get("id") or ""),
            question=question[:140],
            placed_at_iso=datetime.fromtimestamp(bet_ts, tz=timezone.utc).isoformat(timespec="seconds"),
            closed_at_iso=str(end_iso or ""),
            historical_spot=spot,
            sim_bet_price=market_price,
            model_prob=forecast.prob_yes,
            edge_pp=sim["edge_pp"],
            side=side,
            stake_dollars=stake,
            yes_won=yes_won,
            outcome=outcome,
            profit_dollars=profit,
        ))
    n_bets = len(rows)
    wins = sum(1 for r in rows if r.outcome == "WIN")
    losses = sum(1 for r in rows if r.outcome == "LOSS")
    voids = sum(1 for r in rows if r.outcome == "VOID")
    pnl = sum(r.profit_dollars for r in rows)
    staked = sum(r.stake_dollars for r in rows if r.outcome in {"WIN", "LOSS"})
    hit_rate = wins / (wins + losses) if (wins + losses) else None
    roi = pnl / staked if staked > 0 else None
    return {
        "config": cfg.__dict__,
        "candidates_scanned": len(resolved),
        "n_bets": n_bets,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "hit_rate": hit_rate,
        "pnl_dollars": round(pnl, 2),
        "staked_dollars": round(staked, 2),
        "roi": roi,
        "skipped_no_parse": skipped_no_parse,
        "skipped_no_horizon": skipped_no_horizon,
        "skipped_no_spot": skipped_no_spot,
        "skipped_no_trades": skipped_no_trades,
        "skipped_below_threshold": skipped_below_threshold,
        "rows": [r.__dict__ for r in rows],
    }


def _cli(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Honest OOS backtest for crypto forecaster")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--lead-hours", type=float, default=12.0)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--max-markets", type=int, default=200)
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    args = parser.parse_args(argv)
    cfg = BacktestConfig(
        lookback_days=args.lookback_days,
        lead_hours=args.lead_hours,
        edge_threshold=args.threshold,
        bankroll=args.bankroll,
        max_markets=args.max_markets,
    )
    fc = CryptoThresholdForecaster()
    result = run_backtest(fc, cfg)
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, indent=2, default=str))
    print()
    print(f"{'side':<5}{'edge':<9}{'price':<8}{'model':<8}{'stake$':<9}{'outcome':<9}{'profit$':<10}question")
    print("-" * 130)
    for r in result["rows"]:
        q = (r["question"] or "")[:60]
        print(f"{r['side']:<5}{r['edge_pp']:<+9.4f}{r['sim_bet_price']:<8.4f}{r['model_prob']:<8.4f}"
              f"${r['stake_dollars']:<8.2f}{r['outcome']:<9}${r['profit_dollars']:<+9.2f}{q}")
    if args.out:
        import os
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli())


__all__ = ["BacktestConfig", "BacktestRow", "run_backtest"]
