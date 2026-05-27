"""strategy_d_plus_sizing_backtest.py — iter-17 stake-sizing on top of Strategy D.

Hypothesis: iter-10 Strategy D (BLK/FG3M/STL only, flat $100) yields +28.80% ROI
on 418 bets. iter-9 showed soft-line smallest-edge bucket [0.5, 0.75) has the
HIGHEST per-bucket ROI (+14.47%). Combining D's stat filter with inverse-edge
stake sizing should outperform either alone.

Strategy variants on the SAME 418-bet D ledger:
    D-flat        : $100 flat (iter-10 baseline).
    D-inv-bucket  : $200 / $100 / $50 / $25 step by |edge| bucket.
    D-inv-linear  : stake = clip($200 * (1.5-|edge|)/1.0, $25, $200).
    D-flat-tight  : $100 flat, only bet if |edge| in [0.4, 0.9] (sweet spot).
    D-flat-loose  : $100 flat, threshold |edge| > 0.3 (more soft-line bets).

Also reports per-|edge|-bucket hit rate on the 418-bet D pool to confirm /
refute the iter-9 pooled finding holds at the 3-stat scale.

Forward test: tonight's 6-bet WCF G7 ledger (data/bets/strategy_d_2026-05-27.csv,
settled) is replayed under each variant.

Report: vault/Reports/iter17_strategy_d_plus_sizing.md
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.stake_sizing_backtest import (  # noqa: E402
    run as run_iter10,
    PROFIT_RATIO_AT_M110,
    VALIDATED_STATS,
)

REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "iter17_strategy_d_plus_sizing.md")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                          "iter17_strategy_d_plus_sizing.json")
FORWARD_CSV = os.path.join(PROJECT_DIR, "data", "bets",
                           "strategy_d_2026-05-27.csv")


# ────────────────────────────────── variant stake fns (operate on |edge|) ────

def _stake_D_flat(abs_edge: float) -> float:
    return 100.0


def _stake_D_inv_bucket(abs_edge: float) -> float:
    if abs_edge < 0.75:
        return 200.0
    if abs_edge < 1.00:
        return 100.0
    if abs_edge < 1.50:
        return 50.0
    return 25.0


def _stake_D_inv_linear(abs_edge: float) -> float:
    raw = 200.0 * max(0.0, (1.5 - abs_edge) / 1.0)
    return float(min(200.0, max(25.0, raw)))


def _stake_D_flat_tight(abs_edge: float) -> float:
    if 0.4 <= abs_edge <= 0.9:
        return 100.0
    return 0.0


def _stake_D_flat_loose(abs_edge: float) -> float:
    if abs_edge > 0.3:
        return 100.0
    return 0.0


VARIANTS: Dict[str, callable] = {
    "D-flat":         _stake_D_flat,
    "D-inv-bucket":   _stake_D_inv_bucket,
    "D-inv-linear":   _stake_D_inv_linear,
    "D-flat-tight":   _stake_D_flat_tight,
    "D-flat-loose":   _stake_D_flat_loose,
}


# ────────────────────────────────── helpers ──────────────────────────────────

def _pnl(stake: float, outcome: str, profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0  # push


def _max_drawdown_chrono(bet_records: List[Tuple[str, float]]) -> float:
    """Cumulative-PnL peak-to-trough on a date-sorted list."""
    if not bet_records:
        return 0.0
    bet_records = sorted(bet_records, key=lambda x: x[0])
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for _d, pnl in bet_records:
        cum += pnl
        if cum > peak:
            peak = cum
        if cum - peak < dd:
            dd = cum - peak
    return float(-dd)


def _bucket(ae: float) -> str:
    if ae < 0.75:
        return "[0.50, 0.75)"
    if ae < 1.00:
        return "[0.75, 1.00)"
    if ae < 1.50:
        return "[1.00, 1.50)"
    return "[1.50+]"


# ────────────────────────────────── main ─────────────────────────────────────

def run() -> dict:
    print("\n  iter-17 Strategy D + alternative stake sizing\n")
    res = run_iter10()
    all_bets = res["bets"]
    print(f"  iter-10 bet ledger total: {len(all_bets)}")

    # Filter to Strategy D pool: only the 3 validated stats
    d_bets = [b for b in all_bets if b["stat"] in VALIDATED_STATS]
    print(f"  Strategy D pool (BLK/FG3M/STL): {len(d_bets)}")

    # ───── per-bucket hit rate within the D pool ─────
    per_bucket = defaultdict(lambda: {"n": 0, "wins": 0, "losses": 0,
                                      "pushes": 0, "pnl_at_100": 0.0})
    # also per-stat × bucket
    per_stat_bucket = defaultdict(lambda: defaultdict(
        lambda: {"n": 0, "wins": 0, "losses": 0, "pushes": 0}))
    for b in d_bets:
        bk = _bucket(b["abs_edge"])
        rec = per_bucket[bk]
        rec["n"] += 1
        if b["outcome"] == "win":
            rec["wins"] += 1
        elif b["outcome"] == "loss":
            rec["losses"] += 1
        else:
            rec["pushes"] += 1
        rec["pnl_at_100"] += _pnl(100.0, b["outcome"])
        sb = per_stat_bucket[b["stat"]][bk]
        sb["n"] += 1
        if b["outcome"] == "win":
            sb["wins"] += 1
        elif b["outcome"] == "loss":
            sb["losses"] += 1
        else:
            sb["pushes"] += 1

    # ───── strategy results ─────
    variant_results: Dict[str, dict] = {}
    for vname, stake_fn in VARIANTS.items():
        bet_pnl_by_date: List[Tuple[str, float]] = []
        total_staked = 0.0
        total_pnl = 0.0
        n_bets = 0
        wins = losses = pushes = 0
        for b in d_bets:
            stake = stake_fn(b["abs_edge"])
            if stake <= 0:
                continue
            p = _pnl(stake, b["outcome"])
            total_staked += stake
            total_pnl += p
            n_bets += 1
            if b["outcome"] == "win":
                wins += 1
            elif b["outcome"] == "loss":
                losses += 1
            else:
                pushes += 1
            bet_pnl_by_date.append((b["date"], p))
        roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
        dd = _max_drawdown_chrono(bet_pnl_by_date)
        pnl_dd = (total_pnl / dd) if dd > 0 else float("inf")
        variant_results[vname] = {
            "n_bets": n_bets,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "max_drawdown": round(dd, 2),
            "pnl_per_dd": (round(pnl_dd, 2)
                           if pnl_dd != float("inf") else None),
        }
        pnl_dd_str = f"{pnl_dd:.2f}" if pnl_dd != float("inf") else "inf"
        print(f"  {vname:<14} n={n_bets:>3} stk=${total_staked:>8,.0f} "
              f"PnL=${total_pnl:>+9,.0f} ROI={roi:>+6.2f}% "
              f"MaxDD=${dd:>7,.0f} PnL/DD={pnl_dd_str}")

    # ───── forward test on tonight's 6-bet ledger ─────
    fwd_per_variant = _forward_test(FORWARD_CSV)

    return {
        "d_pool_size": len(d_bets),
        "per_bucket": {k: dict(v) for k, v in per_bucket.items()},
        "per_stat_bucket": {s: dict(b) for s, b in per_stat_bucket.items()},
        "variants": variant_results,
        "forward_test": fwd_per_variant,
        "iter10_skips": res.get("skips"),
    }


def _forward_test(csv_path: str) -> dict:
    """Replay tonight's settled 6-bet ledger under each variant.

    The ledger uses real moneyline odds (not -110), so use per-bet decimal
    profit ratio from `odds` column.
    """
    if not os.path.exists(csv_path):
        return {"error": f"missing {csv_path}"}
    bets: List[dict] = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                line = float(r["line"])
                pred = float(r["model_pred"])
                edge = float(r["edge"])
                odds = int(r["odds"])
                status = r["status"].strip().upper()
            except Exception:
                continue
            ae = abs(edge)
            outcome = "win" if status == "WIN" else ("loss" if status == "LOSS"
                                                     else "push")
            # decimal profit ratio for the bet's actual odds
            if odds > 0:
                pr = odds / 100.0
            else:
                pr = 100.0 / abs(odds)
            bets.append({
                "player": r["player"], "stat": r["stat"],
                "abs_edge": ae, "outcome": outcome, "profit_ratio": pr,
                "odds": odds, "status": status,
            })
    fwd: Dict[str, dict] = {}
    for vname, stake_fn in VARIANTS.items():
        staked = 0.0
        pnl = 0.0
        nb = 0
        wins = losses = pushes = 0
        per_bet: List[dict] = []
        for b in bets:
            stake = stake_fn(b["abs_edge"])
            if stake <= 0:
                per_bet.append({
                    "player": b["player"], "stat": b["stat"],
                    "abs_edge": round(b["abs_edge"], 3),
                    "stake": 0.0, "pnl": 0.0, "status": b["status"],
                })
                continue
            p = _pnl(stake, b["outcome"], profit_ratio=b["profit_ratio"])
            staked += stake
            pnl += p
            nb += 1
            if b["outcome"] == "win":
                wins += 1
            elif b["outcome"] == "loss":
                losses += 1
            else:
                pushes += 1
            per_bet.append({
                "player": b["player"], "stat": b["stat"],
                "abs_edge": round(b["abs_edge"], 3),
                "stake": round(stake, 2), "pnl": round(p, 2),
                "status": b["status"],
            })
        roi = (pnl / staked * 100.0) if staked > 0 else 0.0
        fwd[vname] = {
            "n_bets": nb, "wins": wins, "losses": losses, "pushes": pushes,
            "total_staked": round(staked, 2),
            "total_pnl": round(pnl, 2),
            "roi_pct": round(roi, 2),
            "per_bet": per_bet,
        }
    return fwd


# ─────────────────────────────────  report  ──────────────────────────────────

def save_report(out: dict) -> None:
    L: List[str] = []
    L.append("# Iter-17 — Strategy D + Alternative Stake Sizing\n")
    L.append(f"D-pool size (BLK/FG3M/STL @ |edge|>0.5): **{out['d_pool_size']}** bets.\n")
    L.append("Bankroll notional $10k, odds -110 (decimal profit 0.9091). "
             "Drawdown is chronological peak-to-trough on cumulative PnL.\n")

    # Variant comparison
    L.append("## Strategy comparison (within the D pool)\n")
    L.append("| Strategy | n_bets | Total Staked | PnL | ROI% | MaxDD | PnL/DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for v, d in out["variants"].items():
        pnl_dd = d["pnl_per_dd"]
        pnl_dd_s = f"{pnl_dd:.2f}" if pnl_dd is not None else "inf"
        L.append(f"| {v} | {d['n_bets']} | ${d['total_staked']:,.0f} | "
                 f"${d['total_pnl']:+,.0f} | {d['roi_pct']:+.2f}% | "
                 f"${d['max_drawdown']:,.0f} | {pnl_dd_s} |")
    L.append("")

    # Per-bucket hit rate
    L.append("## Per-|edge| bucket hit rate (D pool, 418 bets)\n")
    L.append("| Bucket | n | wins | losses | pushes | hit% | PnL@$100 | ROI@$100 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    bucket_order = ["[0.50, 0.75)", "[0.75, 1.00)", "[1.00, 1.50)", "[1.50+]"]
    for bk in bucket_order:
        r = out["per_bucket"].get(bk)
        if not r:
            continue
        decisive = r["wins"] + r["losses"]
        hit = (r["wins"] / decisive * 100.0) if decisive else 0.0
        staked_flat = 100.0 * r["n"]
        roi_flat = (r["pnl_at_100"] / staked_flat * 100.0) if staked_flat else 0.0
        L.append(f"| {bk} | {r['n']} | {r['wins']} | {r['losses']} | "
                 f"{r['pushes']} | {hit:.2f}% | ${r['pnl_at_100']:+,.0f} | "
                 f"{roi_flat:+.2f}% |")
    L.append("")

    # Per-stat × bucket
    L.append("## Per-stat × bucket hit rate\n")
    L.append("| Stat | Bucket | n | wins | losses | hit% |")
    L.append("|---|---|---:|---:|---:|---:|")
    for stat in sorted(out["per_stat_bucket"].keys()):
        for bk in bucket_order:
            sb = out["per_stat_bucket"][stat].get(bk)
            if not sb or sb["n"] == 0:
                continue
            decisive = sb["wins"] + sb["losses"]
            hit = (sb["wins"] / decisive * 100.0) if decisive else 0.0
            L.append(f"| {stat.upper()} | {bk} | {sb['n']} | {sb['wins']} | "
                     f"{sb['losses']} | {hit:.2f}% |")
    L.append("")

    # Pick a winner
    winner = max(out["variants"].keys(),
                 key=lambda v: (out["variants"][v]["pnl_per_dd"]
                                if out["variants"][v]["pnl_per_dd"] is not None
                                else 1e9))
    L.append("## Recommendation\n")
    w = out["variants"][winner]
    L.append(f"- **Best PnL/DD:** **{winner}** "
             f"(PnL=${w['total_pnl']:+,.0f}, MaxDD=${w['max_drawdown']:,.0f}, "
             f"PnL/DD={w['pnl_per_dd']}).")
    # also best raw PnL
    best_pnl_v = max(out["variants"].keys(),
                     key=lambda v: out["variants"][v]["total_pnl"])
    bp = out["variants"][best_pnl_v]
    L.append(f"- **Best raw PnL:** **{best_pnl_v}** "
             f"(${bp['total_pnl']:+,.0f} on ${bp['total_staked']:,.0f} staked, "
             f"ROI {bp['roi_pct']:+.2f}%).")
    L.append("")

    # Forward test
    L.append("## Forward test — tonight's WCF G7 6-bet ledger (real odds)\n")
    fwd = out.get("forward_test", {})
    if fwd.get("error"):
        L.append(f"_({fwd['error']})_")
    else:
        L.append("| Strategy | n_bets | Staked | PnL | ROI% |")
        L.append("|---|---:|---:|---:|---:|")
        for v, d in fwd.items():
            L.append(f"| {v} | {d['n_bets']} | ${d['total_staked']:,.0f} | "
                     f"${d['total_pnl']:+,.2f} | {d['roi_pct']:+.2f}% |")
        L.append("")
        # show per-bet detail under recommended variant
        L.append(f"### Per-bet detail under **{winner}**")
        L.append("| Player | Stat | |edge| | Stake | Status | PnL |")
        L.append("|---|---|---:|---:|---|---:|")
        for pb in fwd[winner]["per_bet"]:
            L.append(f"| {pb['player']} | {pb['stat'].upper()} | "
                     f"{pb['abs_edge']:.2f} | ${pb['stake']:,.0f} | "
                     f"{pb['status']} | ${pb['pnl']:+,.2f} |")
        L.append("")

    L.append("## Quirks / caveats\n")
    L.append("- D pool size is from the iter-10 recomputed ledger; should be "
             "418 by construction (iter-10 baseline match).")
    L.append("- Forward test odds are real moneyline odds from the live ledger "
             "(not -110), so its profit ratio per bet differs from backtest.")
    L.append("- `D-flat-tight` and `D-flat-loose` change the bet COUNT, "
             "not just sizing — directly comparable to D-flat by ROI but not "
             "by total PnL.")
    L.append("- iter-9 per-bucket finding was POOLED across all 7 stats. "
             "If the 3-stat per-bucket table above still shows the smallest "
             "bucket winning, the soft-line effect is robust at the D scale.")
    L.append("- Drawdown uses date-sorted cumulative PnL (chronological), "
             "matching iter-10 methodology.")
    L.append("")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  report -> {REPORT_PATH}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            **out,
        }, fh, indent=2, default=str)
    print(f"  cache  -> {CACHE_PATH}")


def main() -> None:
    out = run()
    save_report(out)


if __name__ == "__main__":
    main()
