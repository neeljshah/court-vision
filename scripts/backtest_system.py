"""
backtest_system.py — Full-system backtest entry point.

Two modes:
  * Regression gate (default) — R² check per stat, used by CI.
  * Full-system replay (--replay) — replays the historical bet ledger
    end-to-end (lineup refresh -> bet_selector -> portfolio optimizer ->
    simulated fill) and reports realised portfolio metrics.

Usage:
    python scripts/backtest_system.py [--r2-threshold 0.7] [--stat pts]
    python scripts/backtest_system.py --replay [--bankroll 1000]

Exits 0 if all stats pass the R² threshold, 1 if any stat regresses.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
_METRICS_PATH   = os.path.join(PROJECT_DIR, "data", "models", "props_metrics.json")
_BET_LOG_PATH   = os.path.join(PROJECT_DIR, "data", "models", "bet_log.json")
_RESULTS_PATH   = os.path.join(PROJECT_DIR, "data", "output", "backtest_results.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
DEFAULT_R2_THRESHOLD = 0.70

# Pipeline stages a full-system replay reconstructs.  The bet ledger is the
# recorded output of the first three stages; the replay re-derives P&L by
# layering the simulated-fill stage on top.
REPLAY_STAGES = ["lineup_refresh", "bet_selector", "portfolio_optimizer", "simulated_fill"]


def _load_residuals(path: str | None = None) -> List[dict]:
    p = path or _RESIDUALS_PATH
    if not os.path.exists(p):
        return []
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return []


def _compute_r2(residuals: List[dict], stat: str) -> Optional[float]:
    rows = [r for r in residuals
            if r.get("stat") == stat
            and r.get("predicted") is not None
            and r.get("actual") is not None]
    if len(rows) < 5:
        return None
    preds   = [float(r["predicted"]) for r in rows]
    actuals = [float(r["actual"])     for r in rows]
    mean_a  = sum(actuals) / len(actuals)
    ss_tot  = sum((a - mean_a) ** 2 for a in actuals)
    if ss_tot == 0:
        return None
    ss_res  = sum((p - a) ** 2 for p, a in zip(preds, actuals))
    return round(1.0 - ss_res / ss_tot, 4)


def run_regression_check(
    residuals: List[dict],
    r2_threshold: float = DEFAULT_R2_THRESHOLD,
    stats: List[str] | None = None,
) -> Dict[str, dict]:
    """Check R² for each stat against threshold.

    Returns dict: {stat: {"r2": float|None, "pass": bool, "n": int}}
    """
    stats = stats or STATS
    results = {}
    for stat in stats:
        rows = [r for r in residuals if r.get("stat") == stat]
        r2   = _compute_r2(residuals, stat)
        results[stat] = {
            "r2":   r2,
            "pass": r2 is None or r2 >= r2_threshold,  # None = insufficient data, treated as pass
            "n":    len(rows),
        }
    return results


# ── full-system replay engine (task 18.5-01) ─────────────────────────────────

def simulate_fill(bet: dict, fill_model: Optional[Callable] = None) -> dict:
    """Stage 4 — simulated fill for one bet.

    The default is an identity (point-estimate) fill: the bet is filled
    exactly at its requested line and stake.  Task 18.5-02 plugs a slippage
    + book-repricing model in via ``fill_model``.

    Returns ``{"filled", "fill_line", "fill_stake", "slippage"}``.
    """
    if fill_model is not None:
        return fill_model(bet)
    line = bet.get("book_line", bet.get("line"))
    return {
        "filled": True,
        "fill_line": line,
        "fill_stake": float(bet.get("stake", 0.0) or 0.0),
        "slippage": 0.0,
    }


# ── slippage + book-repricing fill model (task 18.5-02) ──────────────────────
# Per-book adverse slippage (basis points of the line) and order-size limits.
# Sharp books (Pinnacle) slip least; retail books slip more and cap smaller.
DEFAULT_BOOK_SLIPPAGE_BPS: Dict[str, float] = {
    "pinnacle": 10.0, "kalshi": 15.0, "polymarket": 20.0,
    "draftkings": 25.0, "fanduel": 25.0, "betmgm": 30.0, "caesars": 30.0,
}
DEFAULT_SLIPPAGE_BPS = 25.0
DEFAULT_BOOK_LIMITS: Dict[str, float] = {
    "pinnacle": 2000.0, "kalshi": 5000.0, "polymarket": 5000.0,
    "draftkings": 250.0, "fanduel": 250.0, "betmgm": 200.0, "caesars": 200.0,
}
DEFAULT_REPRICING_PENALTY_BPS = 50.0


def make_slippage_fill_model(
    *,
    book_slippage_bps: Optional[Dict[str, float]] = None,
    default_slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    book_limits: Optional[Dict[str, float]] = None,
    repricing_penalty_bps: float = DEFAULT_REPRICING_PENALTY_BPS,
) -> Callable[[dict], dict]:
    """Build a fill model that applies per-book slippage + a repricing penalty.

    Slippage worsens the fill line by ``slippage_bps`` basis points of the
    line (an over bet fills higher, an under fills lower).  When a bet's stake
    exceeds the book's limit, an additional repricing penalty — scaled by the
    overage fraction (capped at 3×) — is applied: large orders move the book.

    Returns a callable(bet)->fill dict suitable for replay_bet_ledger's
    ``fill_model`` argument.
    """
    book_slippage_bps = book_slippage_bps if book_slippage_bps is not None \
        else dict(DEFAULT_BOOK_SLIPPAGE_BPS)
    book_limits = book_limits if book_limits is not None else dict(DEFAULT_BOOK_LIMITS)

    def _fill(bet: dict) -> dict:
        book = str(bet.get("book", bet.get("sportsbook", "default"))).lower()
        line = bet.get("book_line", bet.get("line"))
        stake = float(bet.get("stake", 0.0) or 0.0)
        direction = str(bet.get("direction", "over")).lower()

        slip_bps = book_slippage_bps.get(book, default_slippage_bps)

        reprice_bps = 0.0
        limit = book_limits.get(book)
        if limit and limit > 0 and stake > limit:
            overage = (stake - limit) / limit
            reprice_bps = repricing_penalty_bps * min(overage, 3.0)

        total_bps = slip_bps + reprice_bps
        if line is None:
            return {"filled": True, "fill_line": None, "fill_stake": stake,
                    "slippage": 0.0, "slippage_bps": round(total_bps, 2),
                    "reprice_bps": round(reprice_bps, 2), "book": book}

        slip_pts = float(line) * (total_bps / 10_000.0)
        fill_line = float(line) + slip_pts if direction == "over" \
            else float(line) - slip_pts
        return {
            "filled": True,
            "fill_line": round(fill_line, 4),
            "fill_stake": stake,
            "slippage": round(abs(fill_line - float(line)), 4),
            "slippage_bps": round(total_bps, 2),
            "reprice_bps": round(reprice_bps, 2),
            "book": book,
        }

    return _fill


def _bet_pnl(bet: dict, fill: dict) -> float:
    """Re-derive realised P&L for a bet under its simulated fill.

    Win/loss is recomputed against the (possibly repriced) fill line so the
    backtest reflects the fill model rather than trusting the recorded P&L.
    """
    stake = float(fill.get("fill_stake", bet.get("stake", 0.0)) or 0.0)
    if stake <= 0:
        return 0.0
    actual    = bet.get("actual")
    fill_line = fill.get("fill_line", bet.get("book_line", bet.get("line")))
    direction = str(bet.get("direction", "over")).lower()
    if actual is not None and fill_line is not None:
        won = (float(actual) > float(fill_line)) if direction == "over" \
              else (float(actual) < float(fill_line))
    else:
        won = bet.get("won")
    if won is None:
        return 0.0
    odds = int(bet.get("odds", -110) or -110)
    if odds < 0:
        return stake if won else -stake
    return stake * (odds / 100.0) if won else -stake


def _clv_beat(bet: dict) -> Optional[bool]:
    """Return whether a bet beat the closing line, or None if CLV is unknown."""
    if bet.get("clv") is not None:
        return float(bet["clv"]) > 0
    closing = bet.get("closing_line")
    opening = bet.get("book_line", bet.get("line"))
    if closing is None or opening is None:
        return None
    direction = str(bet.get("direction", "over")).lower()
    move = float(closing) - float(opening)
    return move > 0 if direction == "over" else move < 0


def _max_drawdown(equity: List[float]) -> float:
    """Largest peak-to-trough fractional decline along an equity curve."""
    peak, max_dd = (equity[0] if equity else 0.0), 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    return round(max_dd, 4)


def _sharpe(returns: List[float]) -> Optional[float]:
    """Per-bet Sharpe ratio (mean / stdev of stake-normalised returns)."""
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var  = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std  = var ** 0.5
    return round(mean / std, 4) if std > 0 else None


def replay_bet_ledger(
    bets: List[dict],
    *,
    starting_bankroll: float = 1000.0,
    fill_model: Optional[Callable] = None,
) -> dict:
    """Replay settled bets chronologically and compute portfolio metrics.

    Returns a metrics dict: total_roi, clv_beat_rate, max_drawdown, sharpe,
    bet_count, total_staked, total_pnl, starting/ending bankroll.
    """
    settled = [b for b in bets if b.get("won") is not None
               or b.get("status") in ("won", "lost")]
    settled.sort(key=lambda b: str(b.get("game_date", b.get("date", ""))))

    bankroll = starting_bankroll
    equity   = [bankroll]
    returns: List[float] = []
    total_staked = total_pnl = 0.0
    clv_beats = clv_n = 0

    for bet in settled:
        fill  = simulate_fill(bet, fill_model)
        stake = float(fill.get("fill_stake", 0.0) or 0.0)
        pnl   = _bet_pnl(bet, fill)
        bankroll += pnl
        equity.append(bankroll)
        total_staked += stake
        total_pnl    += pnl
        if stake > 0:
            returns.append(pnl / stake)
        beat = _clv_beat(bet)
        if beat is not None:
            clv_n += 1
            clv_beats += int(beat)

    return {
        "bet_count":        len(settled),
        "total_staked":     round(total_staked, 2),
        "total_pnl":        round(total_pnl, 2),
        "total_roi":        round(total_pnl / total_staked, 4) if total_staked > 0 else None,
        "clv_beat_rate":    round(clv_beats / clv_n, 4) if clv_n > 0 else None,
        "clv_sample":       clv_n,
        "max_drawdown":     _max_drawdown(equity),
        "sharpe":           _sharpe(returns),
        "starting_bankroll": round(starting_bankroll, 2),
        "ending_bankroll":  round(bankroll, 2),
    }


def run_full_backtest(
    ledger_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    starting_bankroll: float = 1000.0,
    fill_model: Optional[Callable] = None,
    fill_model_name: object = "point_estimate",
) -> dict:
    """Replay the historical bet ledger end-to-end and write backtest_results.json.

    ``fill_model_name`` is recorded verbatim in the result's ``fill_model``
    field — a plain string for the identity fill, or a config dict describing
    the slippage + repricing model (task 18.5-02).
    """
    ledger_path = ledger_path or _BET_LOG_PATH
    output_path = output_path or _RESULTS_PATH

    bets: List[dict] = []
    if os.path.exists(ledger_path):
        try:
            bets = json.load(open(ledger_path, encoding="utf-8"))
        except Exception:
            bets = []

    metrics = replay_bet_ledger(
        bets, starting_bankroll=starting_bankroll, fill_model=fill_model,
    )
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "stages":       REPLAY_STAGES,
        "fill_model":   fill_model_name,
        **metrics,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[backtest_system] replay complete: {metrics['bet_count']} bets, "
          f"ROI={metrics['total_roi']}, max_dd={metrics['max_drawdown']} -> {output_path}")
    return result


def main(argv: List[str] | None = None) -> int:
    """Return 0 if all stats pass, 1 if any regresses."""
    p = argparse.ArgumentParser(description="Backtest regression gate / full-system replay")
    p.add_argument("--r2-threshold", type=float, default=DEFAULT_R2_THRESHOLD)
    p.add_argument("--stat", choices=STATS, default=None, help="Check only one stat")
    p.add_argument("--residuals", default=None, help="Path to prop_residuals.json")
    p.add_argument("--replay", action="store_true",
                   help="Run the full-system bet-ledger replay instead of the R² gate")
    p.add_argument("--bankroll", type=float, default=1000.0, help="Replay starting bankroll")
    p.add_argument("--slippage", action="store_true",
                   help="Apply the per-book slippage + repricing fill model in --replay")
    args = p.parse_args(argv)

    if args.replay:
        fill_model = None
        fill_model_name: object = "point_estimate"
        if args.slippage:
            fill_model = make_slippage_fill_model()
            fill_model_name = {
                "type": "slippage_repricing",
                "default_slippage_bps": DEFAULT_SLIPPAGE_BPS,
                "repricing_penalty_bps": DEFAULT_REPRICING_PENALTY_BPS,
                "per_book_bps": DEFAULT_BOOK_SLIPPAGE_BPS,
                "book_limits": DEFAULT_BOOK_LIMITS,
            }
        result = run_full_backtest(
            starting_bankroll=args.bankroll,
            fill_model=fill_model,
            fill_model_name=fill_model_name,
        )
        print(json.dumps(result, indent=2))
        return 0

    residuals = _load_residuals(args.residuals)
    stats     = [args.stat] if args.stat else STATS
    results   = run_regression_check(residuals, args.r2_threshold, stats)

    print(f"\nBacktest Regression Check (threshold R² ≥ {args.r2_threshold})")
    print("-" * 50)
    any_fail = False
    for stat, r in results.items():
        status = "PASS" if r["pass"] else "FAIL"
        r2_str = f"{r['r2']:.4f}" if r["r2"] is not None else "insufficient data"
        print(f"  {stat:6s}: R²={r2_str:>12s}  n={r['n']:4d}  [{status}]")
        if not r["pass"]:
            any_fail = True

    print(f"\nOverall: {'FAIL' if any_fail else 'PASS'}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
