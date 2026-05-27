"""cap_sweep_iter23.py — iter-23 per-game cap sweep for Strategy D.

iter-22 finding: max_per_game_pct = 2.0% (the iter-18 proposal) is TOO
aggressive — 99.25% of games hit the cap, $70K of stake removed, PnL
slashed from $27.4K uncapped to $7.4K capped.

iter-23 goal: find the optimal cap % that retains >=80% of uncapped PnL
while keeping MaxDD <= $500. Sweep 2.0 -> 8.0 in 0.5% steps.

Reuses iter-22's prediction pool — builds it once, caches to
data/cache/iter23_preds.json on first run, then loads from cache on
subsequent calls. This is the same per-stat threshold pool that
iter-22's `scripts/backtest_iter18_proposed_config.py` produced
(BLK 0.35, FG3M 0.60, STL 0.50, strict `>`).

Constraints honoured:
  - Does NOT modify config/strategy_d.yaml (default).
  - Updates config/strategy_d.yaml.iter18_proposed with elbow cap%.
  - LOCAL only, no model retraining, no pip installs, no git pushes.
  - Runtime budget: 6 min (prediction cache makes subsequent runs <2s).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Reuse iter-22's prediction pipeline + helpers
from scripts.backtest_iter18_proposed_config import (  # noqa: E402
    build_predictions, _pnl, _max_drawdown_chrono,
    _per_stat_threshold, _passes_threshold, forward_test_tonight,
    _load_yaml_lite, STATS,
)

PREDS_CACHE = os.path.join(PROJECT_DIR, "data", "cache", "iter23_preds.json")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "iter23_cap_sweep.md")
SUMMARY_CACHE = os.path.join(PROJECT_DIR, "data", "cache",
                             "iter23_cap_sweep.json")
CONFIG_PATH = os.path.join(PROJECT_DIR, "config",
                           "strategy_d.yaml.iter18_proposed")

# Sweep grid — 2.0 to 8.0 in 0.5 steps (13 values), plus uncapped sentinel
CAP_GRID = [round(2.0 + 0.5 * i, 2) for i in range(13)]  # 2.0,2.5,...,8.0


# ───────────────────────────────────────────────────── prediction pool ──────
def _build_proposed_cfg() -> dict:
    """The iter-18-proposed thresholds (cap doesn't matter — set later)."""
    return {
        "threshold": {
            "edge_min": 0.35, "edge_operator": ">",
            "per_stat_overrides": {"blk": 0.35, "fg3m": 0.60, "stl": 0.50},
        },
        "sizing": {"mode": "flat", "base_stake": 100.0,
                   "max_per_bet_pct": 5.0, "max_per_game_pct": 2.0},
        "bankroll": {"amount": 10000.0},
        "stats_filter": list(STATS),
    }


def _filter_candidates(preds: List[dict], cfg: dict) -> List[dict]:
    """Apply per-stat thresholds to derive the candidate bet pool."""
    stats_filter = set(cfg.get("stats_filter") or STATS)
    cands: List[dict] = []
    for p in preds:
        if p["stat"] not in stats_filter:
            continue
        if p["outcome"] == "skip":
            continue
        thr, op = _per_stat_threshold(cfg, p["stat"])
        if not _passes_threshold(p["abs_edge"], thr, op):
            continue
        cands.append({**p, "stake_pre_cap": 100.0})
    return cands


def load_or_build_preds() -> List[dict]:
    """Build predictions once and cache; reuse cache on subsequent runs."""
    if os.path.exists(PREDS_CACHE):
        print(f"  loading cached predictions from {PREDS_CACHE}")
        with open(PREDS_CACHE, encoding="utf-8") as fh:
            return json.load(fh)
    print("  no prediction cache — building from scratch (one-time)…")
    t0 = time.time()
    preds = build_predictions()
    print(f"  built {len(preds)} predictions in {time.time()-t0:.1f}s")
    os.makedirs(os.path.dirname(PREDS_CACHE), exist_ok=True)
    with open(PREDS_CACHE, "w", encoding="utf-8") as fh:
        json.dump(preds, fh)
    print(f"  cached -> {PREDS_CACHE}")
    return preds


# ─────────────────────────────────────────────── single-cap simulation ──────
def simulate_cap(candidates: List[dict], per_game_pct: float,
                 bankroll: float = 10000.0) -> dict:
    """Apply proportional per-game cap to candidates; return summary."""
    per_game_cap = bankroll * (per_game_pct / 100.0)
    by_game: Dict[str, List[dict]] = defaultdict(list)
    for c in candidates:
        by_game[c["game_key"]].append(c)

    games_total = len(by_game)
    games_hit_cap = 0
    bets: List[Tuple[str, float, str]] = []  # (date, stake, outcome)
    for _gk, lst in by_game.items():
        total_pre = sum(b["stake_pre_cap"] for b in lst)
        if total_pre > per_game_cap:
            games_hit_cap += 1
            scale = per_game_cap / total_pre
            for b in lst:
                bets.append((b["date"], b["stake_pre_cap"] * scale,
                             b["outcome"]))
        else:
            for b in lst:
                bets.append((b["date"], b["stake_pre_cap"], b["outcome"]))

    n_bets = len(bets)
    total_staked = sum(s for _, s, _ in bets)
    pnl_chrono: List[Tuple[str, float]] = []
    total_pnl = 0.0
    wins = losses = pushes = 0
    for d, stake, outcome in bets:
        pnl = _pnl(stake, outcome)
        total_pnl += pnl
        pnl_chrono.append((d, pnl))
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            pushes += 1
    dd = _max_drawdown_chrono(pnl_chrono)
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0
                                              else 0.0)
    return {
        "cap_pct": per_game_pct,
        "n_bets": n_bets,
        "wins": wins, "losses": losses, "pushes": pushes,
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_pct": round(roi, 4),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 4)
                   if pnl_dd != float("inf") else None),
        "games_total": games_total,
        "games_hit_cap": games_hit_cap,
        "cap_fraction": (round(games_hit_cap / games_total, 4)
                         if games_total else 0.0),
    }


def simulate_uncapped(candidates: List[dict]) -> dict:
    """No cap applied — every candidate bets full $100."""
    bets = [(c["date"], c["stake_pre_cap"], c["outcome"]) for c in candidates]
    n_bets = len(bets)
    total_staked = sum(s for _, s, _ in bets)
    pnl_chrono: List[Tuple[str, float]] = []
    total_pnl = 0.0
    wins = losses = pushes = 0
    for d, stake, outcome in bets:
        pnl = _pnl(stake, outcome)
        total_pnl += pnl
        pnl_chrono.append((d, pnl))
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            pushes += 1
    dd = _max_drawdown_chrono(pnl_chrono)
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0
                                              else 0.0)
    games = {c["game_key"] for c in candidates}
    return {
        "cap_pct": float("inf"),
        "n_bets": n_bets,
        "wins": wins, "losses": losses, "pushes": pushes,
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi_pct": round(roi, 4),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 4) if pnl_dd != float("inf") else None),
        "games_total": len(games),
        "games_hit_cap": 0,
        "cap_fraction": 0.0,
    }


# ───────────────────────────────────────────────────────── elbow finder ─────
def find_elbow(sweep: List[dict], uncapped: dict,
               pnl_retention_min: float = 0.80,
               maxdd_ceiling: float = 500.0) -> dict:
    """Pick the LOWEST cap that meets both retention + DD constraints."""
    target_pnl = uncapped["total_pnl"] * pnl_retention_min
    candidates = []
    for row in sweep:
        retained_pct = (row["total_pnl"] / uncapped["total_pnl"]
                        if uncapped["total_pnl"] > 0 else 0.0)
        meets_pnl = row["total_pnl"] >= target_pnl
        meets_dd = row["maxdd_dollars"] <= maxdd_ceiling
        candidates.append({
            **row,
            "retained_pnl_pct": round(retained_pct * 100.0, 2),
            "meets_pnl": meets_pnl,
            "meets_dd": meets_dd,
            "meets_both": meets_pnl and meets_dd,
        })
    elbow = None
    for c in sorted(candidates, key=lambda x: x["cap_pct"]):
        if c["meets_both"]:
            elbow = c
            break
    return {"target_pnl": round(target_pnl, 2),
            "uncapped_pnl": uncapped["total_pnl"],
            "candidates": candidates,
            "elbow": elbow}


# ───────────────────────────────────────────────────── config update ────────
def update_proposed_config(new_cap_pct: float, reasoning: str) -> None:
    """Rewrite the iter18_proposed yaml with the new cap + reasoning header."""
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        lines = fh.readlines()
    new_lines: List[str] = []
    iter23_comment = (
        f"# iter-23 cap sweep: 2.0% was too aggressive (99.25% of games "
        f"hit cap,\n"
        f"# only 27% of uncapped PnL retained). Sweep 2.0->8.0 in 0.5% "
        f"steps:\n"
        f"# {reasoning}\n"
    )
    inserted_comment = False
    for ln in lines:
        # update the cap line itself
        if "max_per_game_pct" in ln and ":" in ln and not ln.lstrip().startswith("#"):
            indent = ln[: len(ln) - len(ln.lstrip())]
            new_lines.append(
                f"{indent}max_per_game_pct: {new_cap_pct}        "
                f"# iter-23 elbow (was 2.0)\n"
            )
            continue
        # insert iter-23 header before the threshold block
        if not inserted_comment and ln.startswith("threshold:"):
            new_lines.append(iter23_comment)
            new_lines.append("\n")
            inserted_comment = True
        new_lines.append(ln)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        fh.writelines(new_lines)


# ─────────────────────────────────────────────────── forward (tonight) ─────
def forward_with_cap(cfg: dict, cap_pct: float) -> dict:
    """Run iter-22's forward_test on tonight's ledger with overridden cap."""
    cfg = json.loads(json.dumps(cfg))  # deep copy
    cfg.setdefault("sizing", {})["max_per_game_pct"] = cap_pct
    return forward_test_tonight(cfg)


# ─────────────────────────────────────────────────────────────── main ──────
def main() -> None:
    t_main = time.time()
    print(f"\n  iter-23 — cap sweep for iter-18-proposed config")
    preds = load_or_build_preds()
    print(f"  prediction pool: {len(preds)} (post-feature-build)")

    cfg = _build_proposed_cfg()
    candidates = _filter_candidates(preds, cfg)
    print(f"  candidates after per-stat thresholds: {len(candidates)}")

    sweep: List[dict] = []
    for cap_pct in CAP_GRID:
        r = simulate_cap(candidates, cap_pct)
        sweep.append(r)
        print(f"   cap {cap_pct:>4.1f}%: n={r['n_bets']:4d} "
              f"staked=${r['total_staked']:>8,.0f} "
              f"PnL=${r['total_pnl']:>+9,.0f} "
              f"ROI={r['roi_pct']:>+6.2f}% "
              f"DD=${r['maxdd_dollars']:>5,.0f} "
              f"hit={r['cap_fraction']*100:>6.2f}%")
    uncapped = simulate_uncapped(candidates)
    print(f"   uncapped  : n={uncapped['n_bets']:4d} "
          f"staked=${uncapped['total_staked']:>8,.0f} "
          f"PnL=${uncapped['total_pnl']:>+9,.0f} "
          f"ROI={uncapped['roi_pct']:>+6.2f}% "
          f"DD=${uncapped['maxdd_dollars']:>5,.0f}")

    elbow_data = find_elbow(sweep, uncapped,
                            pnl_retention_min=0.80,
                            maxdd_ceiling=500.0)
    elbow = elbow_data["elbow"]
    if elbow is None:
        print("\n  WARN: no cap meets both retention + DD constraints. "
              "Falling back to highest-retention cap with DD<=500.")
        # fallback: max PnL with DD<=500
        eligible = [c for c in elbow_data["candidates"]
                    if c["maxdd_dollars"] <= 500.0]
        if eligible:
            elbow = max(eligible, key=lambda x: x["total_pnl"])
            elbow_data["elbow"] = elbow
    if elbow:
        print(f"\n  ELBOW: cap {elbow['cap_pct']}%  "
              f"PnL=${elbow['total_pnl']:+,.0f} "
              f"(retains {elbow['retained_pnl_pct']:.1f}% of uncapped) "
              f"DD=${elbow['maxdd_dollars']:,.0f} "
              f"hit={elbow['cap_fraction']*100:.2f}%")

    # Forward test on tonight's WCF G7 with elbow cap
    fwd = None
    if elbow:
        fwd = forward_with_cap(_load_yaml_lite(CONFIG_PATH), elbow["cap_pct"])
        if not fwd.get("error"):
            print(f"\n  Tonight WCF G7 @ cap {elbow['cap_pct']}%: "
                  f"n={fwd['n_bets']}  "
                  f"W/L/P={fwd['wins']}/{fwd['losses']}/{fwd['pushes']}  "
                  f"PnL=${fwd['total_pnl']:+,.2f}  "
                  f"ROI={fwd['roi_pct']:+.2f}%")
        else:
            print(f"  forward error: {fwd['error']}")

    # Update the iter18_proposed yaml with elbow cap
    if elbow:
        reasoning = (
            f"# elbow at {elbow['cap_pct']}% retains "
            f"{elbow['retained_pnl_pct']:.1f}% of uncapped PnL "
            f"(${elbow['total_pnl']:+,.0f} of ${uncapped['total_pnl']:+,.0f}) "
            f"with MaxDD=${elbow['maxdd_dollars']:,.0f} (<= $500)."
        )
        update_proposed_config(elbow["cap_pct"], reasoning)
        print(f"\n  config updated -> {CONFIG_PATH}")

    # Save cache + report
    os.makedirs(os.path.dirname(SUMMARY_CACHE), exist_ok=True)
    with open(SUMMARY_CACHE, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "n_candidates": len(candidates),
            "sweep": sweep,
            "uncapped": uncapped,
            "elbow_data": elbow_data,
            "forward_tonight": fwd,
        }, fh, indent=2, default=str)
    print(f"  cache  -> {SUMMARY_CACHE}")

    # Markdown report
    save_report(sweep, uncapped, elbow_data, fwd)
    print(f"\n  total runtime: {time.time()-t_main:.1f}s")


def save_report(sweep: List[dict], uncapped: dict, elbow_data: dict,
                fwd: dict | None) -> None:
    L: List[str] = []
    L.append("# Iter-23 — per-game cap sweep for Strategy D\n")
    L.append("Same prediction pool as iter-22 (full 2024 playoffs canonical "
             "CSV, BLK / FG3M / STL only, per-stat thresholds BLK 0.35 / "
             "FG3M 0.60 / STL 0.50, strict `>`). Sweeps `max_per_game_pct` "
             "from 2.0% to 8.0% in 0.5% steps to find the elbow that "
             "retains >=80% of uncapped PnL while keeping MaxDD <= $500.\n")
    L.append("## Sweep table\n")
    L.append("| Cap % | n_bets | Staked | PnL | ROI% | MaxDD | "
             "PnL/DD | Cap fires % |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    L.append(f"| 2.0 (iter-22) | {sweep[0]['n_bets']} | "
             f"${sweep[0]['total_staked']:,.0f} | "
             f"${sweep[0]['total_pnl']:+,.0f} | "
             f"{sweep[0]['roi_pct']:+.2f}% | "
             f"${sweep[0]['maxdd_dollars']:,.0f} | "
             f"{(sweep[0]['pnl_dd'] if sweep[0]['pnl_dd'] is not None else float('inf')):.2f} | "
             f"{sweep[0]['cap_fraction']*100:.2f}% |")
    for row in sweep[1:]:
        L.append(f"| {row['cap_pct']:.1f} | {row['n_bets']} | "
                 f"${row['total_staked']:,.0f} | "
                 f"${row['total_pnl']:+,.0f} | "
                 f"{row['roi_pct']:+.2f}% | "
                 f"${row['maxdd_dollars']:,.0f} | "
                 f"{(row['pnl_dd'] if row['pnl_dd'] is not None else float('inf')):.2f} | "
                 f"{row['cap_fraction']*100:.2f}% |")
    L.append(f"| inf (uncapped) | {uncapped['n_bets']} | "
             f"${uncapped['total_staked']:,.0f} | "
             f"${uncapped['total_pnl']:+,.0f} | "
             f"{uncapped['roi_pct']:+.2f}% | "
             f"${uncapped['maxdd_dollars']:,.0f} | "
             f"{(uncapped['pnl_dd'] if uncapped['pnl_dd'] is not None else float('inf')):.2f} | "
             f"0.00% |")
    L.append("")

    elbow = elbow_data.get("elbow")
    L.append("## Elbow identification\n")
    L.append(f"- Target: retain >=80% of uncapped PnL "
             f"(>= ${elbow_data['target_pnl']:+,.2f}) AND MaxDD <= $500.")
    if elbow is None:
        L.append("- **No cap meets both constraints.**\n")
    else:
        L.append(f"- **Elbow: cap {elbow['cap_pct']}%** — "
                 f"PnL ${elbow['total_pnl']:+,.0f} "
                 f"({elbow['retained_pnl_pct']:.1f}% of uncapped), "
                 f"MaxDD ${elbow['maxdd_dollars']:,.0f}, "
                 f"cap fires {elbow['cap_fraction']*100:.2f}% of games.\n")

    L.append("## Tonight's WCF G7 forward test\n")
    if fwd is None or fwd.get("error"):
        L.append(f"_({fwd.get('error') if fwd else 'no elbow found'})_\n")
    else:
        L.append(f"With cap {elbow['cap_pct']}%: n={fwd['n_bets']} bets, "
                 f"W/L/P={fwd['wins']}/{fwd['losses']}/{fwd['pushes']}, "
                 f"staked ${fwd['total_staked']:,.2f}, "
                 f"PnL **${fwd['total_pnl']:+,.2f}** "
                 f"(ROI {fwd['roi_pct']:+.2f}%).\n")
        L.append("| Player | Stat | |edge| | Stake | Status | PnL |")
        L.append("|---|---|---:|---:|---|---:|")
        for b in fwd.get("per_bet", []):
            L.append(f"| {b['player']} | {b['stat'].upper()} | "
                     f"{b['abs_edge']:.2f} | ${b['stake']:.2f} | "
                     f"{b['status']} | ${b['pnl']:+,.2f} |")
        L.append("")

    L.append("## Notes\n")
    L.append("- Cap is applied PROPORTIONALLY: when sum of candidate stakes "
             "in a game exceeds the cap, all stakes scale down by the same "
             "factor (preserves edge ranking within game).")
    L.append("- Elbow rule: pick the LOWEST cap% meeting both constraints "
             "(most conservative).")
    L.append("- Prediction pool cached at "
             "`data/cache/iter23_preds.json` — rebuild is a one-time cost.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
