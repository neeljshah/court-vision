"""backtest_iter18_proposed_config.py - iter-22 end-to-end OOS validation.

Runs the FULL 2024 playoffs canonical OOS set (BLK / FG3M / STL) through the
iter-18-proposed config (config/strategy_d.yaml.iter18_proposed):
  * per-stat |edge| thresholds  (BLK 0.35, FG3M 0.60, STL 0.50, strict ">")
  * flat $100 candidate stake
  * 2% per-game bankroll cap = $200 on $10k bankroll (proportional scale-down
    of ALL candidate stakes within a single game when total exceeds cap)

Then reports:
  - Per-config comparison vs default (thr 0.50 flat $100) and iter-18 sweep
    (thr 0.35 flat $100 no cap).
  - Fraction of games hitting the $200 cap.
  - Cap-induced PnL difference (uncapped vs capped, restricted to games
    that hit the cap).
  - Per-stat PnL contribution under the proposed config.
  - Forward test on tonight's WCF G7 settled ledger with cap on.

Constraints honoured:
  - Reads config/strategy_d.yaml.iter18_proposed (no writes to strategy_d.yaml).
  - Uses iter-6 _build_asof_row for leak safety.
  - LOCAL only, no model retraining, no git pushes.
  - No new pip packages (uses csv + json + ad-hoc yaml parse).
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _build_asof_row, _resolve_player_id, _season_for_date,
    _classify_result, _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import feature_columns  # noqa: E402
from src.prediction.prop_quantiles import _inverse  # noqa: E402


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CONFIG_PATH = os.path.join(PROJECT_DIR, "config",
                           "strategy_d.yaml.iter18_proposed")
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_DIR, "config", "strategy_d.yaml")
FORWARD_CSV = os.path.join(PROJECT_DIR, "data", "bets",
                           "strategy_d_2026-05-27.csv")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "iter22_proposed_config_backtest.md")
CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                          "iter22_proposed_config_backtest.json")

STATS = ("blk", "fg3m", "stl")
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)  # 0.9091


# ─────────────────────────────────────────────────── tiny yaml loader ────────
def _load_yaml_lite(path: str) -> dict:
    """Minimal YAML reader for the simple flat-with-nesting strategy_d files.

    Avoids a pyyaml dependency. Supports:
      key: value          (str/int/float/bool/null)
      key:                (then indented children -> nested dict)
      - item              (list under a key)
      "0.50-0.75": 200    (quoted keys for bucket_weights)
    """
    root: Dict[str, object] = {}
    stack: List[Tuple[int, dict]] = [(-1, root)]
    pending_list_key: Optional[str] = None
    pending_list_indent: Optional[int] = None
    pending_list: Optional[list] = None

    def _coerce(v: str):
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            return v[1:-1]
        if v.startswith("'") and v.endswith("'"):
            return v[1:-1]
        low = v.lower()
        if low in ("null", "~", "none", ""):
            return None
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            if "." in v or "e" in low:
                return float(v)
            return int(v)
        except ValueError:
            return v

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # strip trailing comments
            stripped = re.sub(r"\s+#.*$", "", line)
            indent = len(stripped) - len(stripped.lstrip())
            content = stripped.strip()

            # list item line — list items belong to the most recent key
            # opened at a STRICTLY smaller indent. Pop frames whose indent
            # is >= the OWNING key's indent (recorded in pending_list_indent)
            # so the grandparent (which holds the slot for pending_list_key)
            # becomes the active parent.
            if content.startswith("- "):
                item = _coerce(content[2:])
                if pending_list is None:
                    if pending_list_key is None or pending_list_indent is None:
                        continue  # bare list at top level — skip
                    while stack and stack[-1][0] >= pending_list_indent:
                        stack.pop()
                    parent = stack[-1][1]
                    existing = parent.get(pending_list_key)
                    if isinstance(existing, list):
                        pending_list = existing
                    else:
                        pending_list = []
                        parent[pending_list_key] = pending_list
                pending_list.append(item)
                continue
            else:
                pending_list = None
                pending_list_key = None

            # key: value or key:
            m = re.match(r"^([^:]+):\s*(.*)$", content)
            if not m:
                continue
            key = m.group(1).strip()
            if key.startswith('"') and key.endswith('"'):
                key = key[1:-1]
            value_str = m.group(2)

            # pop stack to parent for this indent
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]

            if value_str == "":
                # opens a child block: could be dict OR list (we don't know yet)
                child: Dict[str, object] = {}
                parent[key] = child
                stack.append((indent, child))
                pending_list_key = key
                pending_list_indent = indent
            else:
                parent[key] = _coerce(value_str)

    # Repair: any opened-dict that received only list items gets replaced by a
    # list. We never assigned because list-items appended into setdefault list.
    # That branch handled itself.
    return root


# ─────────────────────────────────────────────── model load & prediction ────
def _load_qstat_xgb(stat: str):
    import xgboost as xgb
    path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        raise SystemExit(f"  [abort] missing OOS artifact: {path}")
    m = xgb.XGBRegressor()
    m.load_model(path)
    return m


def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


# ─────────────────────────────────────────────────────── prediction pass ────
def build_predictions() -> List[dict]:
    """Predict every (player, date, stat) row for BLK / FG3M / STL.

    Returns enriched preds with game_key = (date, opp, venue) -- a player's
    game is uniquely defined by the date plus the opponent team plus the
    venue (home/away). The same opp+venue+date can hold multiple players from
    the same team facing the same opponent in the same game.
    """
    models = {s: _load_qstat_xgb(s) for s in STATS}

    rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stat", "").lower() in STATS:
                rows.append(r)

    names = sorted({r["player"] for r in rows})
    name2pid = {nm: _resolve_player_id(nm) for nm in names}

    preds: List[dict] = []
    skips = defaultdict(int)
    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}
    t0 = time.time()
    for i, r in enumerate(rows):
        stat = r["stat"].lower()
        try:
            line = float(r["closing_line"])
            actual = float(r["actual_value"])
            d = datetime.fromisoformat(r["date"])
        except Exception:
            skips["bad_row"] += 1
            continue
        pid = name2pid.get(r["player"])
        if pid is None:
            skips["no_pid"] += 1
            continue
        season = _season_for_date(d)
        is_home = (r["venue"] == "home")
        key = (pid, r["date"], r["venue"], r["opp"])
        if key not in row_cache:
            row_cache[key] = _build_asof_row(
                pid, r["opp"], d, season, is_home=is_home,
                rest_days=2.0, gamelog_dir=GAMELOG_DIR,
            )
        feat = row_cache[key]
        if feat is None:
            skips["no_history"] += 1
            continue
        try:
            pred = _predict_qstat(stat, models[stat], feat)
        except Exception as e:
            skips[f"err:{type(e).__name__}"] += 1
            continue

        edge = pred - line
        ae = abs(edge)
        if edge > 0:
            rec = "OVER"
        elif edge < 0:
            rec = "UNDER"
        else:
            rec = "PUSH_LINE"
        actual_result = _classify_result(actual, line)
        if rec == "PUSH_LINE":
            outcome = "skip"
        elif actual_result == "PUSH":
            outcome = "push"
        else:
            outcome = "win" if rec == actual_result else "loss"

        preds.append({
            "date": r["date"],
            "player": r["player"],
            "venue": r["venue"],
            "opp": r["opp"],
            "stat": stat,
            "line": line,
            "actual": actual,
            "pred": pred,
            "edge_signed": edge,
            "abs_edge": ae,
            "rec": rec,
            "outcome": outcome,
            "game_key": f"{r['date']}|{r['venue']}|{r['opp']}",
        })
        if (i + 1) % 500 == 0:
            print(f"   ...{i+1}/{len(rows)} ({time.time()-t0:.1f}s) "
                  f"preds={len(preds)}")
    print(f"  predicted {len(preds)} rows in {time.time()-t0:.1f}s. "
          f"skips: {dict(skips)}")
    return preds


# ─────────────────────────────────────────────────────────── PnL helpers ────
def _pnl(stake: float, outcome: str,
         profit_ratio: float = PROFIT_RATIO_AT_M110) -> float:
    if stake <= 0:
        return 0.0
    if outcome == "win":
        return stake * profit_ratio
    if outcome == "loss":
        return -stake
    return 0.0


def _max_drawdown_chrono(records: List[Tuple[str, float]]) -> float:
    if not records:
        return 0.0
    records = sorted(records, key=lambda x: x[0])
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for _d, pnl in records:
        cum += pnl
        if cum > peak:
            peak = cum
        dd = min(dd, cum - peak)
    return float(-dd)


# ─────────────────────────────────────────── threshold + cap simulation ────
def _per_stat_threshold(cfg: dict, stat: str) -> Tuple[float, str]:
    thr_block = cfg.get("threshold") or {}
    op = thr_block.get("edge_operator", ">=") or ">="
    default = float(thr_block.get("edge_min", 0.50))
    overrides = thr_block.get("per_stat_overrides") or {}
    v = overrides.get(stat)
    if v is None:
        return default, op
    try:
        return float(v), op
    except (TypeError, ValueError):
        return default, op


def _passes_threshold(ae: float, thr: float, op: str) -> bool:
    if op == ">":
        return ae > thr
    return ae >= thr


def simulate(preds: List[dict], cfg: dict,
             apply_cap: bool = True) -> dict:
    """Apply cfg thresholds + (optional) per-game cap; return PnL summary."""
    sizing = cfg.get("sizing") or {}
    base_stake = float(sizing.get("base_stake", 100.0))
    bankroll = float((cfg.get("bankroll") or {}).get("amount", 10000.0))
    per_game_pct = float(sizing.get("max_per_game_pct", 6.0))
    per_game_cap = bankroll * (per_game_pct / 100.0)
    stats_filter = set((cfg.get("stats_filter") or STATS))

    # Step 1: derive candidate stakes (pre-cap) per pred.
    candidates: List[dict] = []
    for p in preds:
        if p["stat"] not in stats_filter:
            continue
        if p["outcome"] == "skip":  # zero-edge -> no bet
            continue
        thr, op = _per_stat_threshold(cfg, p["stat"])
        if not _passes_threshold(p["abs_edge"], thr, op):
            continue
        candidates.append({**p, "stake_pre_cap": base_stake,
                           "thr": thr, "op": op})

    # Step 2: group by game_key; if total stake > per_game_cap, proportionally
    # scale all stakes in that game down.
    by_game: Dict[str, List[dict]] = defaultdict(list)
    for c in candidates:
        by_game[c["game_key"]].append(c)

    games_hit_cap = 0
    games_total = len(by_game)
    cap_lost_stake = 0.0
    cap_uncapped_pnl = 0.0
    cap_capped_pnl = 0.0
    for gk, lst in by_game.items():
        total_pre = sum(b["stake_pre_cap"] for b in lst)
        if apply_cap and total_pre > per_game_cap:
            games_hit_cap += 1
            scale = per_game_cap / total_pre
            uncapped_g = sum(_pnl(b["stake_pre_cap"], b["outcome"]) for b in lst)
            cap_uncapped_pnl += uncapped_g
            for b in lst:
                b["stake"] = b["stake_pre_cap"] * scale
            capped_g = sum(_pnl(b["stake"], b["outcome"]) for b in lst)
            cap_capped_pnl += capped_g
            cap_lost_stake += (total_pre - per_game_cap)
        else:
            for b in lst:
                b["stake"] = b["stake_pre_cap"]

    # Step 3: aggregate
    n_bets = 0
    wins = losses = pushes = 0
    total_staked = 0.0
    total_pnl = 0.0
    by_stat: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "losses": 0, "pushes": 0,
                 "staked": 0.0, "pnl": 0.0})
    pnl_chrono: List[Tuple[str, float]] = []
    for c in candidates:
        stake = c["stake"]
        if stake <= 0:
            continue
        pnl = _pnl(stake, c["outcome"])
        n_bets += 1
        total_staked += stake
        total_pnl += pnl
        s = c["stat"]
        by_stat[s]["n"] += 1
        by_stat[s]["staked"] += stake
        by_stat[s]["pnl"] += pnl
        if c["outcome"] == "win":
            wins += 1
            by_stat[s]["wins"] += 1
        elif c["outcome"] == "loss":
            losses += 1
            by_stat[s]["losses"] += 1
        else:
            pushes += 1
            by_stat[s]["pushes"] += 1
        pnl_chrono.append((c["date"], pnl))

    decisive = wins + losses
    hit = (wins / decisive) if decisive else 0.0
    roi = (total_pnl / total_staked * 100.0) if total_staked > 0 else 0.0
    dd = _max_drawdown_chrono(pnl_chrono)
    pnl_dd = (total_pnl / dd) if dd > 0 else (float("inf") if total_pnl > 0
                                              else 0.0)

    return {
        "n_bets": n_bets,
        "wins": wins, "losses": losses, "pushes": pushes,
        "hit_pct": round(hit * 100.0, 2),
        "roi_pct": round(roi, 2),
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "maxdd_dollars": round(dd, 2),
        "pnl_dd": (round(pnl_dd, 2) if pnl_dd != float("inf") else None),
        "games_total": games_total,
        "games_hit_cap": games_hit_cap,
        "cap_fraction": (round(games_hit_cap / games_total, 4)
                         if games_total else 0.0),
        "cap_lost_stake": round(cap_lost_stake, 2),
        "cap_uncapped_pnl_at_capped_games": round(cap_uncapped_pnl, 2),
        "cap_capped_pnl_at_capped_games": round(cap_capped_pnl, 2),
        "cap_pnl_delta_at_capped_games": round(
            cap_capped_pnl - cap_uncapped_pnl, 2),
        "by_stat": {s: {
            "n": v["n"], "wins": v["wins"], "losses": v["losses"],
            "pushes": v["pushes"], "staked": round(v["staked"], 2),
            "pnl": round(v["pnl"], 2),
            "hit_pct": (round(v["wins"] / (v["wins"] + v["losses"]) * 100, 2)
                        if (v["wins"] + v["losses"]) else 0.0),
            "roi_pct": (round(v["pnl"] / v["staked"] * 100, 2)
                        if v["staked"] > 0 else 0.0),
        } for s, v in by_stat.items()},
    }


# ─────────────────────────────────────────────────────── forward (tonight) ──
def forward_test_tonight(cfg: dict) -> dict:
    """Apply iter-18-proposed config to tonight's WCF G7 settled ledger.

    Reads real odds + status from data/bets/strategy_d_2026-05-27.csv,
    applies the per-stat thresholds, then proportionally caps all stakes
    in the single game ID to $200.
    """
    if not os.path.exists(FORWARD_CSV):
        return {"error": f"missing {FORWARD_CSV}"}
    sizing = cfg.get("sizing") or {}
    base_stake = float(sizing.get("base_stake", 100.0))
    bankroll = float((cfg.get("bankroll") or {}).get("amount", 10000.0))
    per_game_pct = float(sizing.get("max_per_game_pct", 6.0))
    per_game_cap = bankroll * (per_game_pct / 100.0)

    rows: List[dict] = []
    with open(FORWARD_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                edge = float(r["edge"])
                odds = int(r["odds"])
                status = r["status"].strip().upper()
            except Exception:
                continue
            ae = abs(edge)
            stat = r["stat"].lower()
            thr, op = _per_stat_threshold(cfg, stat)
            if not _passes_threshold(ae, thr, op):
                continue
            outcome = ("win" if status == "WIN"
                       else ("loss" if status == "LOSS" else "push"))
            pr = (odds / 100.0) if odds > 0 else (100.0 / abs(odds))
            rows.append({
                "player": r["player"], "stat": stat, "abs_edge": ae,
                "outcome": outcome, "profit_ratio": pr, "odds": odds,
                "status": status, "stake_pre_cap": base_stake,
                "game_id": r.get("game_id", "GAME"),
            })

    # group + cap
    by_game: Dict[str, List[dict]] = defaultdict(list)
    for b in rows:
        by_game[b["game_id"]].append(b)
    per_bet: List[dict] = []
    games_hit = 0
    for gid, lst in by_game.items():
        total_pre = sum(b["stake_pre_cap"] for b in lst)
        scale = 1.0
        if total_pre > per_game_cap:
            scale = per_game_cap / total_pre
            games_hit += 1
        for b in lst:
            stake = b["stake_pre_cap"] * scale
            pnl = _pnl(stake, b["outcome"], profit_ratio=b["profit_ratio"])
            per_bet.append({**b, "stake": round(stake, 2),
                            "pnl": round(pnl, 2)})
    nb = len(per_bet)
    wins = sum(1 for b in per_bet if b["outcome"] == "win")
    losses = sum(1 for b in per_bet if b["outcome"] == "loss")
    pushes = sum(1 for b in per_bet if b["outcome"] == "push")
    staked = sum(b["stake"] for b in per_bet)
    pnl = sum(b["pnl"] for b in per_bet)
    roi = (pnl / staked * 100.0) if staked > 0 else 0.0
    return {
        "n_bets": nb, "wins": wins, "losses": losses, "pushes": pushes,
        "total_staked": round(staked, 2), "total_pnl": round(pnl, 2),
        "roi_pct": round(roi, 2),
        "games_hit_cap": games_hit,
        "per_bet": per_bet,
    }


# ─────────────────────────────────────────────────────────────── main ──────
def _default_cfg_dict() -> dict:
    """Construct the iter-12 default config in memory for the comparison row.

    We do NOT modify the on-disk default. We mirror its semantics: edge_min
    0.50, operator '>=', per-game cap 6%, no per-stat overrides, flat $100,
    $10k bankroll, BLK/FG3M/STL.
    """
    return {
        "threshold": {
            "edge_min": 0.50, "edge_operator": ">=",
            "per_stat_overrides": {},
        },
        "sizing": {"mode": "flat", "base_stake": 100.0,
                   "max_per_bet_pct": 5.0, "max_per_game_pct": 6.0},
        "bankroll": {"amount": 10000.0},
        "stats_filter": list(STATS),
    }


def _no_cap_cfg_dict() -> dict:
    """The iter-18 sweep config: thr 0.35 flat $100, NO per-game cap."""
    return {
        "threshold": {
            "edge_min": 0.35, "edge_operator": ">",
            "per_stat_overrides": {},
        },
        "sizing": {"mode": "flat", "base_stake": 100.0,
                   "max_per_bet_pct": 5.0,
                   "max_per_game_pct": 1000.0},  # effectively no cap
        "bankroll": {"amount": 10000.0},
        "stats_filter": list(STATS),
    }


def run() -> dict:
    print("\n  iter-22 — backtest iter-18-proposed config (full 2024 playoffs)")
    proposed = _load_yaml_lite(CONFIG_PATH)
    print(f"  config:    {CONFIG_PATH}")
    print(f"             threshold.edge_min = "
          f"{proposed.get('threshold', {}).get('edge_min')} "
          f"op={proposed.get('threshold', {}).get('edge_operator')}")
    print(f"             per_stat_overrides = "
          f"{proposed.get('threshold', {}).get('per_stat_overrides')}")
    print(f"             max_per_game_pct   = "
          f"{proposed.get('sizing', {}).get('max_per_game_pct')}")

    preds = build_predictions()

    # Three simulations vs the same prediction pool
    default_cfg = _default_cfg_dict()
    no_cap_cfg = _no_cap_cfg_dict()
    res_default = simulate(preds, default_cfg, apply_cap=True)
    res_no_cap = simulate(preds, no_cap_cfg, apply_cap=False)
    res_proposed = simulate(preds, proposed, apply_cap=True)
    # also run proposed config WITHOUT the cap, for cap-attribution analysis
    res_proposed_uncapped = simulate(preds, proposed, apply_cap=False)

    fwd = forward_test_tonight(proposed)

    return {
        "n_preds": len(preds),
        "default": res_default,
        "no_cap_thr_035": res_no_cap,
        "proposed": res_proposed,
        "proposed_uncapped": res_proposed_uncapped,
        "forward_tonight": fwd,
        "config_proposed_dump": proposed,
    }


def save_report(out: dict) -> None:
    L: List[str] = []
    d, nc, p, pu = (out["default"], out["no_cap_thr_035"],
                    out["proposed"], out["proposed_uncapped"])
    L.append("# Iter-22 — iter-18-proposed config end-to-end OOS backtest\n")
    L.append(f"Pool: 2024 NBA playoffs canonical CSV (BLK / FG3M / STL only). "
             f"Total predictions: {out['n_preds']}. "
             f"Profit ratio @ -110: {PROFIT_RATIO_AT_M110:.4f}.\n")

    def _row(name: str, r: dict) -> str:
        return (f"| {name} | {r['n_bets']} | ${r['total_staked']:,.0f} | "
                f"${r['total_pnl']:+,.0f} | {r['roi_pct']:+.2f}% | "
                f"${r['maxdd_dollars']:,.0f} | "
                f"{(r['pnl_dd'] if r['pnl_dd'] is not None else float('inf')):.2f} |")

    L.append("## Per-config comparison\n")
    L.append("| Config | n_bets | total staked | PnL | ROI% | MaxDD | PnL/DD |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    L.append(_row("Default (thr 0.50 flat $100, cap 6%)", d))
    L.append(_row("Threshold-only (thr 0.35 flat $100, no cap)", nc))
    L.append(_row("iter-18-proposed (per-stat thr + $200 cap)", p))
    L.append(_row("iter-18-proposed config (UNCAPPED reference)", pu))
    L.append("")

    L.append("## Per-game cap impact (proposed config)\n")
    L.append(f"- Games with at least one bet: **{p['games_total']}**.")
    L.append(f"- Games where total candidate stake exceeded $200 cap: "
             f"**{p['games_hit_cap']}** "
             f"({p['cap_fraction']*100:.2f}% of games with bets).")
    L.append(f"- Total stake removed by cap: **${p['cap_lost_stake']:,.0f}**.")
    L.append(f"- On those capped games only — uncapped PnL would be "
             f"**${p['cap_uncapped_pnl_at_capped_games']:+,.0f}**, capped PnL "
             f"is **${p['cap_capped_pnl_at_capped_games']:+,.0f}**, delta "
             f"**${p['cap_pnl_delta_at_capped_games']:+,.0f}**.")
    L.append(f"- Whole-pool delta (capped minus uncapped): "
             f"**${p['total_pnl'] - pu['total_pnl']:+,.0f}**.\n")

    L.append("## Per-stat PnL contribution (proposed config, post-cap)\n")
    L.append("| Stat | n_bets | hit% | staked | PnL | ROI% |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for s in STATS:
        v = p["by_stat"].get(s)
        if not v:
            L.append(f"| {s.upper()} | 0 | - | $0 | $0 | - |")
            continue
        L.append(f"| {s.upper()} | {v['n']} | {v['hit_pct']:.2f}% | "
                 f"${v['staked']:,.0f} | ${v['pnl']:+,.0f} | "
                 f"{v['roi_pct']:+.2f}% |")
    L.append("")

    fwd = out["forward_tonight"]
    L.append("## Forward test — tonight's WCF G7 settled ledger (proposed cfg)\n")
    if fwd.get("error"):
        L.append(f"_({fwd['error']})_")
    else:
        L.append(f"- Bets surviving per-stat thresholds: **{fwd['n_bets']}**.")
        L.append(f"- Games hitting $200 cap: **{fwd['games_hit_cap']}**.")
        L.append(f"- Total staked: **${fwd['total_staked']:,.2f}**.")
        L.append(f"- W/L/P: **{fwd['wins']}/{fwd['losses']}/{fwd['pushes']}**.")
        L.append(f"- PnL: **${fwd['total_pnl']:+,.2f}** "
                 f"(ROI **{fwd['roi_pct']:+.2f}%**).\n")
        L.append("| Player | Stat | |edge| | Stake | Status | PnL |")
        L.append("|---|---|---:|---:|---|---:|")
        for b in fwd["per_bet"]:
            L.append(f"| {b['player']} | {b['stat'].upper()} | "
                     f"{b['abs_edge']:.2f} | ${b['stake']:.2f} | "
                     f"{b['status']} | ${b['pnl']:+,.2f} |")
        L.append("")

    L.append("## Notes\n")
    L.append("- Game grouping uses (date, venue, opp) — uniquely identifies "
             "a single game for the cap. Within a game, all candidate stakes "
             "scale proportionally when total > $200.")
    L.append("- ROI denominator is total staked (includes pushes at $0 PnL); "
             "hit% denominator excludes pushes.")
    L.append("- Comparison rows for 'Default' and 'Threshold-only' are "
             "re-simulated from the SAME prediction pool to avoid metric "
             "drift between scripts — header numbers in CALLBACK reflect "
             "iter-18's exact figures of $12,036 / $39,200 PnL.")
    L.append("- Leak safety: every per-(player,date) feature row built via "
             "iter-6 `_build_asof_row` strictly < game date.")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"\n  report -> {REPORT_PATH}")

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.utcnow().isoformat() + "Z",
                   **out}, fh, indent=2, default=str)
    print(f"  cache  -> {CACHE_PATH}")


def main() -> None:
    out = run()
    save_report(out)
    d, nc, p = out["default"], out["no_cap_thr_035"], out["proposed"]
    fwd = out["forward_tonight"]
    print("\n  ===== ITER-22 PROPOSED CONFIG E2E SUMMARY =====")
    print(f"  Default       : n={d['n_bets']}  PnL=${d['total_pnl']:+,.0f}  "
          f"ROI={d['roi_pct']:+.2f}%  DD=${d['maxdd_dollars']:,.0f}  "
          f"PnL/DD={d['pnl_dd']}")
    print(f"  Thr-only 0.35 : n={nc['n_bets']}  PnL=${nc['total_pnl']:+,.0f}  "
          f"ROI={nc['roi_pct']:+.2f}%  DD=${nc['maxdd_dollars']:,.0f}  "
          f"PnL/DD={nc['pnl_dd']}")
    print(f"  Proposed +cap : n={p['n_bets']}  PnL=${p['total_pnl']:+,.0f}  "
          f"ROI={p['roi_pct']:+.2f}%  DD=${p['maxdd_dollars']:,.0f}  "
          f"PnL/DD={p['pnl_dd']}")
    print(f"  Cap fraction  : {p['games_hit_cap']}/{p['games_total']} games "
          f"({p['cap_fraction']*100:.2f}%) hit cap, stake removed "
          f"${p['cap_lost_stake']:,.0f}")
    if not fwd.get("error"):
        print(f"  Tonight WCF G7: n={fwd['n_bets']}  W/L/P={fwd['wins']}/"
              f"{fwd['losses']}/{fwd['pushes']}  PnL=${fwd['total_pnl']:+,.2f}  "
              f"ROI={fwd['roi_pct']:+.2f}%")


if __name__ == "__main__":
    main()
