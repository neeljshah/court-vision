"""
prop_holdout.py — Proper date-based holdout validation for prop models.

Train set  : games before 2025-02-01
Holdout set: games on/after 2025-02-01 (Feb–Apr 2025)

For each holdout game the feature vector is built from the player's
prior-game rolling stats (10-game window) so the model never sees
future data.  Features not derivable from game logs default to 0.0.

Usage
-----
    conda activate basketball_ai
    python scripts/validate/prop_holdout.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_VAULT_DIR  = os.path.join(PROJECT_DIR, "vault", "Validation")
_FEATS_JSON = os.path.join(PROJECT_DIR, "scripts", "validate", "_all_feats.json")

_CUTOFF  = datetime(2025, 2, 1)
_BAYES_K = 15
_ROLL_N  = 10
_PROP_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

_RETRAIN_THRESHOLD_R2 = 0.70
_REPORTED = {
    "pts":  {"mae": 0.310, "r2": 0.994},
    "reb":  {"mae": 0.115, "r2": 0.995},
    "ast":  {"mae": 0.091, "r2": 0.992},
    "fg3m": {"mae": 0.083, "r2": None},
    "stl":  {"mae": 0.066, "r2": None},
    "blk":  {"mae": 0.044, "r2": None},
    "tov":  {"mae": 0.078, "r2": None},
}


# ── Load feature list ─────────────────────────────────────────────────────────

def _load_all_feats() -> List[str]:
    """Load _ALL_FEATS from the pre-extracted JSON (avoids importing player_props)."""
    if os.path.exists(_FEATS_JSON):
        return json.load(open(_FEATS_JSON))
    # Fallback: parse from source directly
    import ast
    src_path = os.path.join(PROJECT_DIR, "src", "prediction", "player_props.py")
    src = open(src_path, encoding="utf-8").read()
    m = re.search(r"_ALL_FEATS\s*=\s*(\[.*?\])", src, re.DOTALL)
    if m:
        return ast.literal_eval(m.group(1))
    raise RuntimeError("Cannot find _ALL_FEATS in player_props.py")


# ── Date parser ───────────────────────────────────────────────────────────────

def _parse_date(s: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ── Load gamelogs ─────────────────────────────────────────────────────────────

def _load_gamelogs() -> Dict[int, List[dict]]:
    by_player: Dict[int, List[dict]] = defaultdict(list)
    pattern = os.path.join(_NBA_CACHE, "gamelog_full_*_2024-25.json")
    for fpath in glob.glob(pattern):
        m = re.search(r"gamelog_full_(\d+)_2024-25\.json", os.path.basename(fpath))
        if not m:
            continue
        pid = int(m.group(1))
        try:
            rows = json.load(open(fpath))
        except Exception:
            continue
        for r in rows:
            d = _parse_date(str(r.get("game_date", "")))
            if d is None:
                continue
            by_player[pid].append({**r, "_dt": d})
    for pid in by_player:
        by_player[pid].sort(key=lambda r: r["_dt"])
    return by_player


# ── Feature builder ───────────────────────────────────────────────────────────

def _avg(key: str, rows: List[dict]) -> float:
    vals = [float(r.get(key, 0) or 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _build_row(pid: int, prior: List[dict], all_feats: List[str]) -> dict:
    """Build one feature row from prior games; unknowns → 0.0."""
    n_all  = len(prior)
    n_roll = min(_ROLL_N, n_all)
    roll   = prior[-n_roll:] if n_roll > 0 else []

    def _bayes(rv: float, sv: float) -> float:
        n = float(n_roll)
        return round(n / (n + _BAYES_K) * rv + _BAYES_K / (n + _BAYES_K) * sv, 4)

    s = {k: _avg(k, prior) for k in ("pts","reb","ast","min","fg3m","stl","blk","tov")}
    r = {k: _avg(k, roll)  for k in ("pts","reb","ast","min","fg3m","stl","blk","tov")}

    fga_sum = sum(float(x.get("fga", 0) or 0) for x in prior)
    fgm_sum = sum(float(x.get("fgm", 0) or 0) for x in prior)
    fg_pct  = fgm_sum / fga_sum if fga_sum > 0 else 0.44

    home_g = [x for x in roll if "@" not in str(x.get("matchup", ""))]
    away_g = [x for x in roll if "@"     in str(x.get("matchup", ""))]

    # Group E expanded
    r_oreb = _avg("oreb",  roll); r_dreb = _avg("dreb", roll)
    r_pf   = _avg("pf",   roll)
    r_fga  = _avg("fga",  roll); r_fg3a = _avg("fg3a", roll)
    r_fta  = _avg("fta",  roll)
    r_pm   = _avg("plus_minus", roll)
    min_vals = [float(x.get("min", 0) or 0) for x in roll]
    min_var   = float(np.var(min_vals)) if len(min_vals) > 1 else 0.0
    fga_vals  = [float(x.get("fga", 0) or 0) for x in roll]
    fga_trend = (fga_vals[-1] - fga_vals[0]) / max(len(fga_vals)-1, 1) if len(fga_vals) > 1 else 0.0
    dd_rate   = sum(
        1 for x in roll
        if float(x.get("pts", 0) or 0) >= 10 and float(x.get("reb", 0) or 0) >= 10
    ) / max(n_roll, 1)

    # Start with all-zeros, then fill known features
    row = {f: 0.0 for f in all_feats}
    row.update({
        "season_pts": s["pts"], "season_reb": s["reb"], "season_ast": s["ast"],
        "season_min": s["min"], "season_fg3m": s["fg3m"], "season_stl": s["stl"],
        "season_blk": s["blk"], "season_tov": s["tov"],
        "pts_roll":  r["pts"],  "reb_roll":  r["reb"],
        "ast_roll":  r["ast"],  "min_roll":  r["min"],
        "pts_bayes":  _bayes(r["pts"],  s["pts"]),
        "reb_bayes":  _bayes(r["reb"],  s["reb"]),
        "ast_bayes":  _bayes(r["ast"],  s["ast"]),
        "fg3m_bayes": _bayes(r["fg3m"], s["fg3m"]),
        "stl_bayes":  _bayes(r["stl"],  s["stl"]),
        "blk_bayes":  _bayes(r["blk"],  s["blk"]),
        "tov_bayes":  _bayes(r["tov"],  s["tov"]),
        "fg_pct": fg_pct,
        "home_pts_avg": _avg("pts", home_g) if home_g else s["pts"],
        "away_pts_avg": _avg("pts", away_g) if away_g else s["pts"],
        "home_reb_avg": _avg("reb", home_g) if home_g else s["reb"],
        "away_reb_avg": _avg("reb", away_g) if away_g else s["reb"],
        "home_ast_avg": _avg("ast", home_g) if home_g else s["ast"],
        "away_ast_avg": _avg("ast", away_g) if away_g else s["ast"],
        "pts_vs_opp": s["pts"], "reb_vs_opp": s["reb"], "ast_vs_opp": s["ast"],
        "oreb_roll": r_oreb, "dreb_roll": r_dreb, "pf_roll": r_pf,
        "fga_roll": r_fga, "fg3a_roll": r_fg3a, "fta_roll": r_fta,
        "plus_minus_roll": r_pm, "min_variance": min_var,
        "fga_trend": fga_trend, "double_double_rate": dd_rate,
    })
    return row


# ── Load models ───────────────────────────────────────────────────────────────

def _load_models() -> Dict[str, xgb.XGBRegressor]:
    models: Dict[str, xgb.XGBRegressor] = {}
    for stat in _PROP_STATS:
        path = os.path.join(_MODEL_DIR, f"props_{stat}.json")
        if not os.path.exists(path):
            print(f"  [holdout] Model not found: {path}")
            continue
        m = xgb.XGBRegressor()
        m.load_model(path)
        models[stat] = m
    return models


# ── Run holdout ───────────────────────────────────────────────────────────────

def run_holdout() -> dict:
    print("[holdout] Loading feature list ...")
    all_feats = _load_all_feats()
    print(f"[holdout] {len(all_feats)} features")

    print("[holdout] Loading gamelogs ...")
    by_player = _load_gamelogs()
    print(f"[holdout] {len(by_player)} players")

    print("[holdout] Loading models ...")
    models = _load_models()
    if not models:
        print("[holdout] No models. Run train_props() first.")
        return {}
    print(f"[holdout] Models: {list(models.keys())}")

    # Build per-stat feature lists (exclude own season_ col)
    stat_feat_cols: Dict[str, List[str]] = {}
    for stat in _PROP_STATS:
        stat_feat_cols[stat] = [c for c in all_feats if c != f"season_{stat}"]

    # Accumulate rows across all players, then batch-predict
    rows_per_stat: Dict[str, List[dict]] = {s: [] for s in _PROP_STATS}
    actuals:       Dict[str, List[float]] = {s: [] for s in _PROP_STATS}
    n_holdout = 0

    for pid, games in by_player.items():
        train_games   = [g for g in games if g["_dt"] < _CUTOFF]
        holdout_games = [g for g in games if g["_dt"] >= _CUTOFF]
        if not holdout_games or len(train_games) < 5:
            continue

        for i, game in enumerate(holdout_games):
            prior = train_games + holdout_games[:i]
            if len(prior) < 3:
                continue
            feat_row = _build_row(pid, prior, all_feats)
            for stat in _PROP_STATS:
                actual = game.get(stat)
                if actual is None:
                    continue
                try:
                    actual = float(actual)
                except (TypeError, ValueError):
                    continue
                rows_per_stat[stat].append(feat_row)
                actuals[stat].append(actual)
            n_holdout += 1

    print(f"[holdout] Built {n_holdout} holdout rows — batch predicting ...")

    results = {}
    for stat in _PROP_STATS:
        if stat not in models or not rows_per_stat[stat]:
            continue
        cols = stat_feat_cols[stat]
        X = pd.DataFrame(rows_per_stat[stat])[cols]
        y_true = np.array(actuals[stat])
        y_pred = np.maximum(models[stat].predict(X), 0.0)

        mae  = mean_absolute_error(y_true, y_pred)
        r2   = r2_score(y_true, y_pred)
        hit  = float(np.mean(np.abs(y_true - y_pred) <= 1.5))
        over = float(np.mean(y_pred > y_true))
        under = float(np.mean(y_pred < y_true))
        results[stat] = {
            "n":           len(y_true),
            "mae":         round(mae, 3),
            "r2":          round(r2, 4),
            "hit_rate":    round(hit, 3),
            "over_rate":   round(over, 3),
            "under_rate":  round(under, 3),
            "mean_actual": round(float(np.mean(y_true)), 3),
            "mean_pred":   round(float(np.mean(y_pred)), 3),
        }

    return results


# ── Write report ──────────────────────────────────────────────────────────────

def write_report(results: dict) -> str:
    os.makedirs(_VAULT_DIR, exist_ok=True)
    report_path = os.path.join(_VAULT_DIR, "prop_holdout_report.md")

    lines = [
        "# Prop Model Holdout Validation Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Train cutoff:** 2025-02-01  ",
        f"**Holdout window:** 2025-02-01 → 2025-03-24  ",
        f"**Method:** Per-game rolling features (10-game window) from gamelog files  ",
        "",
        "## Summary",
        "",
        "| Stat | N | MAE | R² | Hit Rate (±1.5) | Over% | Under% | Reported MAE | Reported R² | Status |",
        "|------|---|-----|----|-----------------|----|------|------------|-----------|--------|",
    ]

    needs_retrain: List[str] = []
    for stat in _PROP_STATS:
        if stat not in results:
            lines.append(f"| {stat.upper()} | — | — | — | — | — | — | — | — | ⚠️ no data |")
            continue
        r = results[stat]
        rep_mae = _REPORTED.get(stat, {}).get("mae")
        rep_r2  = _REPORTED.get(stat, {}).get("r2")
        rep_mae_s = f"{rep_mae:.3f}" if rep_mae is not None else "—"
        rep_r2_s  = f"{rep_r2:.3f}"  if rep_r2  is not None else "—"
        if r["r2"] < _RETRAIN_THRESHOLD_R2:
            status = "🔴 NEEDS_RETRAIN"
            needs_retrain.append(stat)
        elif r["r2"] < 0.85:
            status = "🟡 MARGINAL"
        else:
            status = "✅ OK"
        lines.append(
            f"| {stat.upper()} | {r['n']} | {r['mae']:.3f} | {r['r2']:.4f} "
            f"| {r['hit_rate']:.1%} | {r['over_rate']:.1%} | {r['under_rate']:.1%} "
            f"| {rep_mae_s} | {rep_r2_s} | {status} |"
        )

    lines += [
        "",
        "## Key Findings",
        "",
        "### Why Reported R²=0.994 Is Inflated",
        "",
        "Training used simulated features: `roll = season_avg × (1 + noise_15%)`,",
        "target = `season_avg`. This is a near-identity function — the model learns to",
        "denoise a synthetic signal, not predict per-game outcomes from player form.",
        "Holdout R² above reflects true out-of-sample performance on real per-game data.",
        "",
        "### MAE Delta (Holdout − Reported)",
        "",
    ]
    for stat in _PROP_STATS:
        if stat not in results:
            continue
        r = results[stat]
        rep_mae = _REPORTED.get(stat, {}).get("mae")
        if rep_mae is not None:
            delta = r["mae"] - rep_mae
            lines.append(
                f"- **{stat.upper()}**: holdout MAE = {r['mae']:.3f} "
                f"(reported {rep_mae:.3f}, Δ = {delta:+.3f})"
            )

    lines += [
        "",
        "### Prediction Bias",
        "",
    ]
    for stat in _PROP_STATS:
        if stat not in results:
            continue
        r = results[stat]
        bias = r["mean_pred"] - r["mean_actual"]
        direction = "over-predicts" if bias > 0 else "under-predicts"
        lines.append(
            f"- **{stat.upper()}**: {direction} by {abs(bias):.3f} on average "
            f"(mean_pred={r['mean_pred']:.2f}, mean_actual={r['mean_actual']:.2f})"
        )

    lines += [
        "",
        "## CV Feature Lift (Phase 7)",
        "",
        "CV features (defender distance, contested shot rate, shot zone tendencies) are not yet",
        "in the training set — no full games have been processed through the tracker.",
        "After Phase G (10+ games), these features should add ~2–5% lift on pts/fg3m.",
        "",
        "## Action Items",
        "",
    ]
    if needs_retrain:
        lines.append(
            f"- 🔴 **Retrain required:** {', '.join(s.upper() for s in needs_retrain)} "
            f"— holdout R² < {_RETRAIN_THRESHOLD_R2}"
        )
    else:
        lines.append("- ✅ All models pass R² ≥ 0.70 threshold on holdout set")

    lines += [
        "- Current models trained on season-level aggregates with simulated noise.",
        "  For production: retrain on per-game rolling features from gamelogs.",
        "- After Phase G: add cv_features to training row → expect pts/fg3m lift.",
        "",
        "## Raw Results",
        "",
        "```json",
        json.dumps(results, indent=2),
        "```",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return report_path


# ── Registry update ───────────────────────────────────────────────────────────

def _update_registry(results: dict) -> None:
    reg_path = os.path.join(_MODEL_DIR, "model_registry.json")
    try:
        registry = json.load(open(reg_path)) if os.path.exists(reg_path) else {}
        for stat, r in results.items():
            key = f"props_{stat}"
            if key not in registry:
                registry[key] = {}
            registry[key].update({
                "holdout_mae":    r["mae"],
                "holdout_r2":     r["r2"],
                "holdout_n":      r["n"],
                "needs_retrain":  r["r2"] < _RETRAIN_THRESHOLD_R2,
            })
        json.dump(registry, open(reg_path, "w"), indent=2)
        print(f"[holdout] Registry updated → {reg_path}")
    except Exception as e:
        print(f"[holdout] Registry update failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    results = run_holdout()
    if not results:
        print("[holdout] No results.")
        return

    print("\n── Holdout Results ──────────────────────────────────────")
    for stat, r in results.items():
        print(
            f"  {stat.upper():4s}  n={r['n']:5d}  MAE={r['mae']:.3f}  "
            f"R²={r['r2']:.4f}  hit={r['hit_rate']:.1%}  "
            f"over={r['over_rate']:.1%}  under={r['under_rate']:.1%}"
        )
    print("─────────────────────────────────────────────────────────\n")

    report_path = write_report(results)
    print(f"[holdout] Report → {report_path}")
    _update_registry(results)


if __name__ == "__main__":
    main()
