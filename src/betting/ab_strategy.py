"""ab_strategy.py — tier4-14 (loop 5).

A/B test framework for betting strategies. Lets the operator run multiple
named strategies (pregame_only, endQ2_recommend, endQ3_recommend, hedge, ...)
in parallel with split bankrolls, then compares per-strategy P&L, ROI, CLV,
and statistical significance.

Per-strategy bankroll cap: each strategy gets its own ring-fenced bankroll
(`data/ab_strategies.csv`). Stakes placed under strategy A do NOT reduce
strategy B's bankroll.  Real-money bankroll in pnl_ledger.csv is left as a
global pool so the operator stays in control of deposits/withdraws.

Data files:
    data/ab_strategies.csv     - {strategy, bankroll, max_bet_pct,
                                  created_at, allocated, realised}
    data/pnl_ledger.csv        - extended with `strategy` column (default
                                  "default" for back-compat rows).

Public API:
    register_strategy(name, bankroll, max_bet_pct=0.05) -> dict
    list_strategies()                                    -> list[dict]
    place_strategy_bet(strategy_name, **place_bet_kwargs) -> bet_id
    strategy_summary(strategy_name, date_range=None)    -> dict
    ab_compare(strategy_a, strategy_b, date_range=None) -> dict
"""
from __future__ import annotations

import csv
import math
import os
from datetime import datetime
from typing import Dict, List, Optional

from . import pnl_ledger as _pnl

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRATEGIES_CSV = os.path.join(PROJECT_DIR, "data", "ab_strategies.csv")

STRAT_COLS = [
    "strategy", "bankroll", "max_bet_pct", "created_at",
    "allocated", "realised",
]


# --------------------------------------------------------------------------- #
# Storage.                                                                    #
# --------------------------------------------------------------------------- #
def _strategies_path() -> str:
    """Indirection so monkeypatched STRATEGIES_CSV is honoured."""
    return STRATEGIES_CSV


def _load_strategies() -> List[Dict]:
    p = _strategies_path()
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _save_strategies(rows: List[Dict]) -> None:
    p = _strategies_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=STRAT_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, p)


def _find(rows: List[Dict], name: str) -> Optional[Dict]:
    name = (name or "").strip()
    for r in rows:
        if r.get("strategy", "") == name:
            return r
    return None


# --------------------------------------------------------------------------- #
# Public API.                                                                 #
# --------------------------------------------------------------------------- #
def register_strategy(
    name: str, bankroll: float, max_bet_pct: float = 0.05,
) -> Dict:
    """Create (or replace) a strategy entry. Returns the row."""
    name = (name or "").strip()
    if not name:
        raise ValueError("strategy name required")
    bankroll = float(bankroll)
    if bankroll <= 0:
        raise ValueError(f"bankroll must be > 0, got {bankroll}")
    max_bet_pct = float(max_bet_pct)
    if not (0 < max_bet_pct <= 1.0):
        raise ValueError(f"max_bet_pct must be in (0,1], got {max_bet_pct}")
    rows = _load_strategies()
    existing = _find(rows, name)
    rec = {
        "strategy":     name,
        "bankroll":     f"{bankroll:.2f}",
        "max_bet_pct":  f"{max_bet_pct:.4f}",
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "allocated":    existing["allocated"] if existing else "0.00",
        "realised":     existing["realised"] if existing else "0.00",
    }
    if existing:
        rows = [rec if r is existing else r for r in rows]
    else:
        rows.append(rec)
    _save_strategies(rows)
    return rec


def list_strategies() -> List[Dict]:
    return _load_strategies()


def _strategy_bets(name: str) -> List[Dict]:
    """All ledger rows tagged with this strategy (incl. back-compat "default")."""
    name = (name or "").strip()
    out = []
    for r in _pnl._load_ledger():
        s = (r.get("strategy") or "").strip() or "default"
        if s == name:
            out.append(r)
    return out


def _strategy_state(rec: Dict, name: str) -> Dict:
    """Compute live allocated/realised/available for a strategy."""
    bets = _strategy_bets(name)
    allocated = 0.0   # stakes currently at risk (open)
    realised = 0.0    # cumulative P&L from settled bets
    for b in bets:
        status = b.get("status", "")
        try:
            stake = float(b.get("stake") or 0)
        except ValueError:
            stake = 0.0
        if status == "open":
            allocated += stake
        elif status in ("won", "lost", "push"):
            try:
                realised += float(b.get("profit_loss") or 0)
            except ValueError:
                pass
    bankroll = float(rec.get("bankroll", 0) or 0)
    available = bankroll + realised - allocated
    return {
        "bankroll":  bankroll,
        "allocated": allocated,
        "realised":  realised,
        "available": available,
    }


def place_strategy_bet(strategy_name: str, **kwargs) -> str:
    """Place a bet attributed to a strategy with bankroll + per-bet cap checks.

    Accepts the same kwargs as pnl_ledger.place_bet. Raises ValueError if
    the strategy is unknown, the stake exceeds max_bet_pct of its bankroll,
    or the strategy's available bankroll is insufficient.
    """
    strategy_name = (strategy_name or "").strip()
    rows = _load_strategies()
    rec = _find(rows, strategy_name)
    if rec is None:
        raise ValueError(
            f"strategy {strategy_name!r} not registered "
            f"(known: {[r['strategy'] for r in rows]})"
        )
    stake = float(kwargs.get("stake", 0))
    if stake <= 0:
        raise ValueError(f"stake must be > 0, got {stake}")
    bankroll = float(rec["bankroll"])
    max_pct  = float(rec["max_bet_pct"])
    cap = bankroll * max_pct
    if stake > cap + 1e-6:
        raise ValueError(
            f"stake ${stake:.2f} exceeds {max_pct:.1%} cap "
            f"(${cap:.2f}) for strategy {strategy_name!r}"
        )
    state = _strategy_state(rec, strategy_name)
    if stake > state["available"] + 1e-6:
        raise ValueError(
            f"strategy {strategy_name!r} bankroll exhausted: "
            f"available ${state['available']:.2f}, requested ${stake:.2f}"
        )
    kwargs["strategy"] = strategy_name
    bid = _pnl.place_bet(**kwargs)
    # Update sidecar bookkeeping (best-effort; recomputed each query anyway).
    new_state = _strategy_state(rec, strategy_name)
    rec["allocated"] = f"{new_state['allocated']:.2f}"
    rec["realised"]  = f"{new_state['realised']:.2f}"
    _save_strategies(rows)
    return bid


# --------------------------------------------------------------------------- #
# Summaries + comparison.                                                     #
# --------------------------------------------------------------------------- #
def _summarise_bets(bets: List[Dict]) -> Dict:
    """Compute roi/win_rate/profit summary over a strategy's bets."""
    settled = [r for r in bets if r.get("status") in ("won", "lost", "push")]
    won = sum(1 for r in settled if r["status"] == "won")
    lost = sum(1 for r in settled if r["status"] == "lost")
    push = sum(1 for r in settled if r["status"] == "push")
    open_n = sum(1 for r in bets if r.get("status") == "open")

    def _f(s):
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0

    profits = [_f(r.get("profit_loss")) for r in settled]
    stakes  = [_f(r.get("stake")) for r in settled]
    tp = round(sum(profits), 2)
    ts = round(sum(stakes), 2)
    n_dec = won + lost
    return {
        "n_bets":       len(bets),
        "n_settled":    len(settled),
        "n_open":       open_n,
        "won":          won,
        "lost":         lost,
        "push":         push,
        "win_rate":     round(won / n_dec, 4) if n_dec else 0.0,
        "roi":          round(tp / ts, 4) if ts > 0 else 0.0,
        "total_profit": tp,
        "total_staked": ts,
        "avg_stake":    round(ts / len(settled), 2) if settled else 0.0,
    }


def _per_bet_returns(bets: List[Dict]) -> List[float]:
    out = []
    for b in bets:
        if b.get("status") not in ("won", "lost", "push"):
            continue
        try:
            s = float(b.get("stake") or 0)
            p = float(b.get("profit_loss") or 0)
        except ValueError:
            continue
        if s > 0:
            out.append(p / s)
    return out


def strategy_summary(
    strategy_name: str, date_range: Optional[str] = None,
) -> Dict:
    """Per-strategy P&L summary including bankroll state + CLV if available."""
    rows = _load_strategies()
    rec = _find(rows, strategy_name)
    if rec is None and strategy_name != "default":
        raise ValueError(f"strategy {strategy_name!r} not registered")
    bets = _strategy_bets(strategy_name)
    # Apply date_range filter to bets ourselves (pnl_summary's filter_by can't
    # express the "missing strategy column == default" back-compat rule).
    bets = _pnl._apply_filters(bets, date_range, None)
    summary = _summarise_bets(bets)
    summary["strategy"] = strategy_name
    if rec is not None:
        state = _strategy_state(rec, strategy_name)
        summary["bankroll_cap"]    = round(state["bankroll"], 2)
        summary["available"]       = round(state["available"], 2)
        summary["allocated_open"]  = round(state["allocated"], 2)
        summary["max_bet_pct"]     = float(rec.get("max_bet_pct", 0) or 0)
    # CLV best-effort (file may be absent).
    summary["clv"] = _aggregate_strategy_clv(strategy_name)
    summary["n_bets"] = len(bets)
    return summary


def _aggregate_strategy_clv(strategy_name: str) -> Optional[Dict]:
    """Compute mean CLV % + beat-close rate from data/pnl_ledger_clv.csv."""
    clv_path = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv.csv")
    if not os.path.exists(clv_path):
        return None
    pcts = []
    beats = 0
    n_w = 0
    with open(clv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            s = (r.get("strategy") or "").strip() or "default"
            if s != strategy_name:
                continue
            if r.get("closing_line", "") == "":
                continue
            n_w += 1
            try:
                pcts.append(float(r.get("clv_percent")))
            except (TypeError, ValueError):
                pass
            if str(r.get("beat_close", "")).lower() == "true":
                beats += 1
    if n_w == 0:
        return None
    return {
        "n_with_close":    n_w,
        "mean_clv_percent": (sum(pcts) / len(pcts)) if pcts else 0.0,
        "beat_close_rate": beats / n_w,
    }


def _welch_t(xs: List[float], ys: List[float]) -> Dict:
    """Welch's t-test (unequal variances). Returns t, df, two-sided p (approx)."""
    nx, ny = len(xs), len(ys)
    if nx < 2 or ny < 2:
        return {"t": None, "df": None, "p_value": None}
    mx = sum(xs) / nx
    my = sum(ys) / ny
    vx = sum((x - mx) ** 2 for x in xs) / (nx - 1)
    vy = sum((y - my) ** 2 for y in ys) / (ny - 1)
    se = math.sqrt(vx / nx + vy / ny) if (vx + vy) > 0 else 0.0
    if se == 0.0:
        return {"t": 0.0, "df": nx + ny - 2, "p_value": 1.0}
    t = (mx - my) / se
    # Welch-Satterthwaite df.
    num = (vx / nx + vy / ny) ** 2
    den = ((vx / nx) ** 2 / (nx - 1)) + ((vy / ny) ** 2 / (ny - 1))
    df = num / den if den > 0 else (nx + ny - 2)
    # Two-sided p via normal approx (df typically >30 with reasonable samples).
    # erfc-based survival function: p = erfc(|t| / sqrt(2))
    p = math.erfc(abs(t) / math.sqrt(2))
    return {"t": round(t, 4), "df": round(df, 2), "p_value": round(p, 4)}


def ab_compare(
    strategy_a: str, strategy_b: str, date_range: Optional[str] = None,
) -> Dict:
    """Paired comparison + Welch's t-test on per-bet returns."""
    sa = strategy_summary(strategy_a, date_range=date_range)
    sb = strategy_summary(strategy_b, date_range=date_range)
    bets_a = _strategy_bets(strategy_a)
    bets_b = _strategy_bets(strategy_b)
    ra = _per_bet_returns(bets_a)
    rb = _per_bet_returns(bets_b)
    test = _welch_t(ra, rb)
    winner = None
    if sa.get("roi", 0) != sb.get("roi", 0):
        winner = strategy_a if sa["roi"] > sb["roi"] else strategy_b
    confidence = None
    if test["p_value"] is not None:
        # Map p-value to a coarse confidence label.
        p = test["p_value"]
        confidence = (
            "high"   if p < 0.05 else
            "medium" if p < 0.20 else
            "low"
        )
    return {
        "strategy_a":   strategy_a,
        "strategy_b":   strategy_b,
        "summary_a":    sa,
        "summary_b":    sb,
        "n_a":          len(ra),
        "n_b":          len(rb),
        "mean_return_a": round(sum(ra) / len(ra), 6) if ra else 0.0,
        "mean_return_b": round(sum(rb) / len(rb), 6) if rb else 0.0,
        "welch_t":      test["t"],
        "df":           test["df"],
        "p_value":      test["p_value"],
        "winner":       winner,
        "confidence":   confidence,
        "date_range":   date_range,
    }
