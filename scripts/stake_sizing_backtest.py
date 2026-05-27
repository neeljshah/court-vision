"""stake_sizing_backtest.py - iter-10 stake sizing comparison.

Reuses the iter-9 OOS predict paths to enumerate every (player, date, stat)
bet on the 2024 playoff canonical slate, then applies FOUR alternative stake
sizing strategies on top of the same bet set:

  A) Flat $100/bet (iter-9 baseline).
  B) Fractional Kelly @ -110 (0.25x Kelly, capped at 5% of bankroll).
  C) Bucket-weighted flat - INVERSE of confidence:
        |edge| in [0.50,0.75): $200
        |edge| in [0.75,1.00): $100
        |edge| in [1.00,1.50): $50
        |edge| >= 1.50      : $25
  D) Stat-filtered flat $100 - only BLK / FG3M / STL.

For each strategy: total staked, n_bets, total PnL, ROI%, max drawdown.
Also emits per-date equity curve JSON to data/cache/stake_sizing_curves.json.

Bankroll: $10,000. Strategies B uses a running bankroll (re-staking based on
current equity); A, C, D are flat (independent of running PnL) per the brief.

Report: vault/Reports/stake_sizing_backtest.md
"""
from __future__ import annotations

import csv
import json
import os
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
    _build_asof_row,
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _recommend,
    _odds_to_decimal_profit,
)
from src.prediction.prop_pergame import (  # noqa: E402
    feature_columns,
    apply_garbage_time_haircut,
)
from src.prediction.prop_quantiles import _inverse  # noqa: E402

try:
    from src.prediction.pregame_residual_heads import apply_residual_correction  # noqa: E402
except Exception:
    def apply_residual_correction(pred, row, stat, model_dir=None):
        return pred


CSV_PATH = os.path.join(PROJECT_DIR, "data", "external", "historical_lines",
                        "playoffs_2024_canonical.csv")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "stake_sizing_backtest.md")
CURVES_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                           "stake_sizing_curves.json")

THRESHOLD = 0.5
BANKROLL_START = 10_000.0
PROFIT_RATIO_AT_M110 = _odds_to_decimal_profit(-110)  # 0.9091
# Fractional Kelly tuning
KELLY_FRACTION = 0.25
KELLY_CAP_PCT = 0.05  # max 5% of (starting) bankroll per bet

QSTAT_XGB = {"blk", "fg3m", "stl", "tov"}
QSTAT_LGB = {"reb"}
VALIDATED_STATS = {"blk", "fg3m", "stl"}  # strategy D filter

# Stake table for strategy C (inverse confidence)
def _stake_C(abs_edge: float) -> float:
    if abs_edge < 0.75:
        return 200.0
    if abs_edge < 1.00:
        return 100.0
    if abs_edge < 1.50:
        return 50.0
    return 25.0


# ---------- Artifact loaders (mirrors aggregate_oos_backtest.py) ----------

def _load_qstat_model(stat: str):
    if stat in QSTAT_LGB:
        import joblib
        path = os.path.join(OOS_DIR, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            return None
        return joblib.load(path)
    if stat in QSTAT_XGB:
        import xgboost as xgb
        path = os.path.join(OOS_DIR, f"quantile_pergame_{stat}_q50.json")
        if not os.path.exists(path):
            return None
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m
    return None


def _load_blend_artifacts(stat: str):
    """Load the PTS-style 3-way blend (xgb sqrt + lgb sqrt + mlp scaled sqrt).
    Used for PTS and (if present) AST."""
    import joblib
    import xgboost as xgb_lib
    xgb_path = os.path.join(OOS_DIR, f"props_pg_{stat}.json")
    lgb_path = os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl")
    mlp_path = os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl")
    sca_path = os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl")
    cal_path = os.path.join(OOS_DIR, f"calibration_pergame_{stat}.joblib")
    wts_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    a = {}
    if os.path.exists(xgb_path):
        m = xgb_lib.XGBRegressor()
        m.load_model(xgb_path)
        a["xgb"] = m
    else:
        a["xgb"] = None
    a["lgb"] = joblib.load(lgb_path) if os.path.exists(lgb_path) else None
    a["mlp"] = joblib.load(mlp_path) if os.path.exists(mlp_path) else None
    a["mlp_scaler"] = joblib.load(sca_path) if os.path.exists(sca_path) else None
    a["cal"] = joblib.load(cal_path) if os.path.exists(cal_path) else None
    weights = None
    if os.path.exists(wts_path):
        try:
            weights_all = json.load(open(wts_path, encoding="utf-8"))
            weights = weights_all.get(stat)
        except Exception:
            weights = None
    a["weights"] = weights
    return a


# ---------- Prediction helpers ----------

def _predict_qstat(stat: str, model, feat_row: Dict[str, float]) -> float:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    pred_t = float(model.predict(X)[0])
    pred = float(_inverse(stat, np.array([pred_t]))[0])
    return max(0.0, pred)


def _inv_sqrt(v: float) -> float:
    return max(0.0, float(v)) ** 2


def _predict_blend(stat: str, artifacts: dict,
                   feat_row: Dict[str, float],
                   apply_haircut: bool = False) -> Optional[float]:
    cols = feature_columns()
    X = np.array([[float(feat_row.get(c, 0.0) or 0.0) for c in cols]],
                 dtype=float)
    weights = artifacts.get("weights")
    if not weights:
        return None
    w_xgb = float(weights.get("w_xgb", 0.0))
    w_lgb = float(weights.get("w_lgb", 0.0))
    w_mlp = float(weights.get("w_mlp", 0.0))
    parts: List[float] = []
    if artifacts.get("xgb") is not None and w_xgb > 0:
        parts.append(w_xgb * _inv_sqrt(float(artifacts["xgb"].predict(X)[0])))
    if artifacts.get("lgb") is not None and w_lgb > 0:
        parts.append(w_lgb * _inv_sqrt(float(artifacts["lgb"].predict(X)[0])))
    if (artifacts.get("mlp") is not None
            and artifacts.get("mlp_scaler") is not None
            and w_mlp > 0):
        Xs = artifacts["mlp_scaler"].transform(X)
        parts.append(w_mlp * _inv_sqrt(float(artifacts["mlp"].predict(Xs)[0])))
    if not parts:
        return None
    pred = float(sum(parts))
    cal = artifacts.get("cal")
    if cal is not None:
        try:
            pred = float(cal.predict([pred])[0])
        except Exception:
            pass
    pred = max(pred, 0.0)
    if apply_haircut:
        hs_raw = feat_row.get("home_spread")
        try:
            pred = float(apply_garbage_time_haircut(pred, stat, hs_raw))
        except Exception:
            pass
        try:
            pred = float(apply_residual_correction(pred, feat_row, stat,
                                                   model_dir=OOS_DIR))
        except Exception:
            pass
    return round(pred, 2)


# ---------- Model_prob proxy ----------

def _model_prob_from_edge(edge_signed: float, rec: str) -> float:
    """Stand-in model_prob = 0.5 + clip(edge_in_rec_direction / 5.0, -0.45, 0.45).
    rec is 'OVER' or 'UNDER'. For OVER, signed edge>0 is favorable; for UNDER, <0 is favorable.
    """
    if rec == "OVER":
        signed = edge_signed
    else:  # UNDER
        signed = -edge_signed
    return 0.5 + max(-0.45, min(0.45, signed / 5.0))


# ---------- Strategy stake calculators ----------

def _stake_kelly(model_prob: float, current_bankroll: float) -> float:
    """Fractional Kelly at -110.
        kelly_fraction = (p*(1/b) - (1-p)) / (1/b), b = profit_ratio
    Effectively kelly = p - (1-p)/b. We multiply by KELLY_FRACTION and cap.
    """
    b = PROFIT_RATIO_AT_M110
    kelly_full = (model_prob * (1.0 / b) - (1.0 - model_prob)) / (1.0 / b)
    if kelly_full <= 0:
        return 0.0
    stake = KELLY_FRACTION * kelly_full * current_bankroll
    cap = KELLY_CAP_PCT * BANKROLL_START
    return float(min(stake, cap))


# ---------- Drawdown helper ----------

def _max_drawdown(curve: List[float]) -> float:
    """Max peak-to-trough drop on a cumulative PnL curve."""
    if not curve:
        return 0.0
    peak = curve[0]
    dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = min(dd, v - peak)
    return float(-dd)


# ---------- Main ----------

def run() -> dict:
    print("\n  iter-10 stake-sizing backtest")
    print(f"  csv:       {CSV_PATH}")
    print(f"  oos_dir:   {OOS_DIR}")
    print(f"  threshold: |edge| > {THRESHOLD}")
    print(f"  bankroll:  ${BANKROLL_START:,.0f}")

    # Load models
    models: Dict[str, object] = {}
    have_pts_art = _load_blend_artifacts("pts")
    if (have_pts_art["xgb"] is not None and have_pts_art["lgb"] is not None
            and have_pts_art["weights"] is not None):
        models["pts"] = ("blend", have_pts_art)
        print(f"  pts blend ready: weights={have_pts_art['weights']}")
    have_ast_art = _load_blend_artifacts("ast")
    if (have_ast_art["xgb"] is not None and have_ast_art["lgb"] is not None
            and have_ast_art["weights"] is not None):
        models["ast"] = ("blend", have_ast_art)
        print(f"  ast blend ready: weights={have_ast_art['weights']}")
    else:
        print("  ast blend NOT ready - excluded")
    for s in ("blk", "fg3m", "reb", "stl", "tov"):
        m = _load_qstat_model(s)
        if m is not None:
            models[s] = ("qstat", m)
            print(f"  loaded {s} q50 model")
        else:
            print(f"  missing {s} q50 model")

    # Load CSV
    all_rows: List[dict] = []
    with open(CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            stat = r.get("stat", "").lower()
            if stat in models:
                all_rows.append(r)
    print(f"  CSV rows we can predict: {len(all_rows)}")

    # Resolve player ids
    unique_names = sorted({r["player"] for r in all_rows})
    name2pid: Dict[str, Optional[int]] = {nm: _resolve_player_id(nm)
                                          for nm in unique_names}
    n_resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  resolved {n_resolved}/{len(unique_names)} players")

    # Enumerate bets
    bets: List[dict] = []
    skips = defaultdict(int)
    row_cache: Dict[Tuple, Optional[Dict[str, float]]] = {}
    t0 = time.time()
    for i, r in enumerate(all_rows):
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
            kind, art = models[stat]
            if kind == "blend":
                # apply haircut only for PTS (matches production)
                pred = _predict_blend(stat, art, feat, apply_haircut=(stat == "pts"))
                if pred is None:
                    skips[f"{stat}_pred_none"] += 1
                    continue
            else:
                pred = _predict_qstat(stat, art, feat)
        except Exception as e:
            skips[f"{stat}_err:{type(e).__name__}"] += 1
            continue

        edge = pred - line  # signed
        rec = _recommend(edge, THRESHOLD)
        if rec == "NO_BET":
            continue

        actual_result = _classify_result(actual, line)
        if actual_result == "PUSH":
            # we treat push as 0 stake outcome: keep in record but as push
            outcome = "push"
        else:
            outcome = "win" if rec == actual_result else "loss"

        abs_edge = abs(edge)
        mprob = _model_prob_from_edge(edge, rec)

        bets.append({
            "date": r["date"],
            "player": r["player"],
            "stat": stat,
            "line": line,
            "actual": actual,
            "pred": pred,
            "edge": edge,
            "abs_edge": abs_edge,
            "rec": rec,
            "outcome": outcome,
            "model_prob": mprob,
        })
        if (i + 1) % 1000 == 0:
            print(f"   ...{i+1}/{len(all_rows)} ({time.time()-t0:.1f}s) bets so far: {len(bets)}")

    elapsed = time.time() - t0
    print(f"\n  Done predicting in {elapsed:.1f}s. n_bets total: {len(bets)}")
    print(f"  skips: {dict(skips)}")

    # Sort bets by date (then arbitrary) for equity curve
    bets.sort(key=lambda x: (x["date"], x["stat"], x["player"]))

    # ---------- Apply strategies ----------
    strategies = ["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"]
    state = {
        s: {"staked": 0.0, "pnl": 0.0, "n_bets": 0, "wins": 0, "losses": 0,
            "pushes": 0, "curve": [], "dates": [], "bankroll": BANKROLL_START,
            "half1_bets": 0, "half1_wins": 0, "half2_bets": 0, "half2_wins": 0}
        for s in strategies
    }
    n_total = len(bets)
    half_idx = n_total // 2

    daily_pnl: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {s: 0.0 for s in strategies}
    )

    for idx, bet in enumerate(bets):
        ae = bet["abs_edge"]
        stat = bet["stat"]
        outcome = bet["outcome"]
        mprob = bet["model_prob"]
        date = bet["date"]
        in_first_half = idx < half_idx

        # Strategy A: flat $100
        stake_A = 100.0
        # Strategy B: fractional Kelly using current bankroll
        stake_B = _stake_kelly(mprob, state["B_kelly025"]["bankroll"])
        # Strategy C: inverse-confidence flat
        stake_C = _stake_C(ae)
        # Strategy D: stat filter
        stake_D = 100.0 if stat in VALIDATED_STATS else 0.0

        def _pnl(stake: float, outcome: str) -> float:
            if stake <= 0:
                return 0.0
            if outcome == "win":
                return stake * PROFIT_RATIO_AT_M110
            if outcome == "loss":
                return -stake
            return 0.0  # push

        for sname, stake in zip(strategies, [stake_A, stake_B, stake_C, stake_D]):
            if stake <= 0:
                continue
            p = _pnl(stake, outcome)
            st = state[sname]
            st["staked"] += stake
            st["pnl"] += p
            st["n_bets"] += 1
            if outcome == "win":
                st["wins"] += 1
                if in_first_half:
                    st["half1_wins"] += 1
                else:
                    st["half2_wins"] += 1
            elif outcome == "loss":
                st["losses"] += 1
            else:
                st["pushes"] += 1
            if in_first_half:
                st["half1_bets"] += 1
            else:
                st["half2_bets"] += 1
            if sname == "B_kelly025":
                st["bankroll"] += p
            daily_pnl[date][sname] += p

    # Build daily cumulative curves (sorted by date)
    all_dates = sorted(daily_pnl.keys())
    cumulative: Dict[str, List[float]] = {s: [] for s in strategies}
    cum_running = {s: 0.0 for s in strategies}
    curves_json: Dict[str, List[dict]] = {s: [] for s in strategies}
    for d in all_dates:
        for s in strategies:
            cum_running[s] += daily_pnl[d][s]
            cumulative[s].append(cum_running[s])
            curves_json[s].append({"date": d, "cum_pnl": round(cum_running[s], 2)})

    # Strategy summaries
    summary = {}
    for s in strategies:
        st = state[s]
        roi_pct = (st["pnl"] / st["staked"] * 100.0) if st["staked"] > 0 else 0.0
        dd = _max_drawdown(cumulative[s])
        h1 = (st["half1_wins"] / st["half1_bets"]) if st["half1_bets"] else 0.0
        h2 = (st["half2_wins"] / st["half2_bets"]) if st["half2_bets"] else 0.0
        max_v = max(cumulative[s]) if cumulative[s] else 0.0
        min_v = min(cumulative[s]) if cumulative[s] else 0.0
        # find dates of max/min
        max_d = all_dates[cumulative[s].index(max_v)] if cumulative[s] else "-"
        min_d = all_dates[cumulative[s].index(min_v)] if cumulative[s] else "-"
        summary[s] = {
            "total_staked": st["staked"],
            "n_bets": st["n_bets"],
            "wins": st["wins"],
            "losses": st["losses"],
            "pushes": st["pushes"],
            "total_pnl": st["pnl"],
            "roi_pct": roi_pct,
            "max_drawdown": dd,
            "pnl_per_dd": (st["pnl"] / dd) if dd > 0 else float("inf"),
            "half1_hit": h1,
            "half2_hit": h2,
            "half_diff_pp": abs(h1 - h2) * 100.0,
            "curve_start": cumulative[s][0] if cumulative[s] else 0.0,
            "curve_end": cumulative[s][-1] if cumulative[s] else 0.0,
            "curve_max": max_v,
            "curve_min": min_v,
            "curve_max_date": max_d,
            "curve_min_date": min_d,
            "first_date": all_dates[0] if all_dates else "-",
            "last_date": all_dates[-1] if all_dates else "-",
        }

    # Persist curves
    os.makedirs(os.path.dirname(CURVES_PATH), exist_ok=True)
    with open(CURVES_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "bankroll_start": BANKROLL_START,
            "strategies": curves_json,
            "summary": summary,
        }, fh, indent=2)
    print(f"  curves -> {CURVES_PATH}")

    return {
        "bets": bets,
        "summary": summary,
        "all_dates": all_dates,
        "curves": cumulative,
        "elapsed_sec": elapsed,
        "skips": dict(skips),
    }


# ---------- Report ----------

LABELS = {
    "A_flat100": "A) Flat $100",
    "B_kelly025": "B) 0.25x Kelly (cap 5%)",
    "C_inverse_conf": "C) Inverse-confidence flat",
    "D_stat_filter": "D) BLK/FG3M/STL only ($100)",
}


def save_report(result: dict) -> None:
    summary = result["summary"]
    L: List[str] = []
    L.append("# Stake-Sizing Backtest - iter-10\n")
    L.append("Same OOS bet set as iter-9, four staking strategies applied. "
             "Bankroll $10,000. Threshold |edge| > 0.5. Odds -110 (profit ratio 0.9091).\n")

    # Comparison table
    L.append("## Strategy comparison")
    L.append("| Strategy | Total Staked | n_bets | wins | Total PnL | ROI% | Max Drawdown | PnL/DD |")
    L.append("|----------|------------:|------:|----:|---------:|-----:|-------------:|------:|")
    for s in ["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"]:
        d = summary[s]
        pnl_dd = d["pnl_per_dd"]
        pnl_dd_str = f"{pnl_dd:.2f}" if pnl_dd != float("inf") else "inf"
        L.append(
            f"| {LABELS[s]} | ${d['total_staked']:,.0f} | {d['n_bets']} | {d['wins']} | "
            f"${d['total_pnl']:+,.0f} | {d['roi_pct']:+.2f}% | "
            f"${d['max_drawdown']:,.0f} | {pnl_dd_str} |"
        )
    L.append("")

    # Equity curve summary
    L.append("## Equity curve summary (cumulative PnL over time)")
    L.append("| Strategy | First Date | Last Date | End PnL | Peak PnL (date) | Trough PnL (date) |")
    L.append("|----------|:----------:|:---------:|-------:|:------------------|:-------------------|")
    for s in ["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"]:
        d = summary[s]
        L.append(
            f"| {LABELS[s]} | {d['first_date']} | {d['last_date']} | "
            f"${d['curve_end']:+,.0f} | ${d['curve_max']:+,.0f} ({d['curve_max_date']}) | "
            f"${d['curve_min']:+,.0f} ({d['curve_min_date']}) |"
        )
    L.append("")

    # Stability (split-half)
    L.append("## Robustness (first-half vs second-half hit rate)")
    L.append("| Strategy | Half1 hit% | Half2 hit% | |diff| pp |")
    L.append("|----------|----------:|----------:|---------:|")
    for s in ["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"]:
        d = summary[s]
        L.append(
            f"| {LABELS[s]} | {d['half1_hit']*100:.2f}% | "
            f"{d['half2_hit']*100:.2f}% | {d['half_diff_pp']:.2f} |"
        )
    L.append("")

    # Recommendation
    best_risk = max(["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"],
                    key=lambda s: (summary[s]["pnl_per_dd"]
                                   if summary[s]["pnl_per_dd"] != float("inf")
                                   else 1e9))
    best_pnl = max(["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"],
                   key=lambda s: summary[s]["total_pnl"])
    most_stable = min(["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"],
                      key=lambda s: summary[s]["half_diff_pp"])
    L.append("## Recommendation")
    L.append(f"- **Best risk-adjusted (highest PnL/MaxDD):** {LABELS[best_risk]} "
             f"(PnL=${summary[best_risk]['total_pnl']:+,.0f}, "
             f"MaxDD=${summary[best_risk]['max_drawdown']:,.0f}).")
    L.append(f"- **Best raw PnL:** {LABELS[best_pnl]} "
             f"(${summary[best_pnl]['total_pnl']:+,.0f} on "
             f"${summary[best_pnl]['total_staked']:,.0f} staked).")
    L.append(f"- **Most stable across the slate (smallest half1/half2 hit-rate gap):** "
             f"{LABELS[most_stable]} (gap={summary[most_stable]['half_diff_pp']:.2f}pp).")
    L.append("")

    # Quirks / caveats
    L.append("## Quirks / caveats")
    L.append("- `model_prob` is a stand-in: `0.5 + clip(edge/5.0, -0.45, 0.45)` in the "
             "rec direction. Real Kelly sizing needs full q10/q50/q90 OOS quantiles "
             "to derive a probability from the quantile spread - those aren't on disk "
             "for iter-10. Strategy B is therefore an upper-bound estimate of what "
             "proper-Kelly could do; the proxy under-disperses for skill-driven bets.")
    L.append("- AST OOS blend artifacts (`props_pg_ast.json` + lgb + mlp + meta_weights) "
             "are present in iter-10, so AST is INCLUDED here vs iter-9 where it was "
             "excluded. AST blend uses the same sqrt+Huber + NNLS-3way stack as PTS, "
             "without the cycle-96a garbage-time haircut (the haircut is PTS-specific).")
    L.append("- Strategy A baseline PnL on iter-10 (with AST in) may differ slightly "
             "from iter-9's $13,182, which excluded AST and used the same PTS path.")
    L.append("- Strategies A, C, D use flat sizing on a notional $10k bankroll (no "
             "compounding). Strategy B re-stakes off the running bankroll. Drawdown "
             "is on cumulative PnL (running peak-to-trough).")
    L.append("- Half-split robustness uses bet-index halves (sorted by date), not date "
             "halves; close enough given the dense 2024 playoff window.")
    L.append(f"- Skips during prediction: {result['skips']}")
    L.append("")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  report -> {REPORT_PATH}")


def main() -> None:
    result = run()
    # Print summary table
    print("\n  STAKE SIZING COMPARISON")
    print(f"  {'Strategy':<32} {'Staked':>12} {'n':>6} {'PnL':>12} {'ROI%':>8} {'MaxDD':>10} {'PnL/DD':>8}")
    for s in ["A_flat100", "B_kelly025", "C_inverse_conf", "D_stat_filter"]:
        d = result["summary"][s]
        pnl_dd = d["pnl_per_dd"]
        pnl_dd_str = f"{pnl_dd:.2f}" if pnl_dd != float("inf") else "inf"
        print(f"  {LABELS[s]:<32} ${d['total_staked']:>10,.0f} {d['n_bets']:>6} "
              f"${d['total_pnl']:>+10,.0f} {d['roi_pct']:>+7.2f}% "
              f"${d['max_drawdown']:>8,.0f} {pnl_dd_str:>8}")
    save_report(result)


if __name__ == "__main__":
    main()
