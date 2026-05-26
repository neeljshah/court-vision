"""probe_R10_M7_ref_features.py — M7 Referee Tendency Features (loop 5, R10).

WHY: data/officials_features.parquet has crew-level priors (ref_crew_fouls,
ref_crew_fta, ref_crew_home_win_pct). Cycle 15 attempted these and regressed
on WF. This retry uses them as RESIDUAL HEAD features (additive on top of
live_engine baseline) with stricter per-stat WF discipline.

The parquet stores the same crew priors for both teams in a game (verified:
same values across teammates), suggesting these are CAREER/PRIOR crew stats,
not target-game outcomes — so they're safe from direct label leakage.

SHIP GATE: WF 4/4 folds positive per stat, mean delta <= -0.005, >= 4/7 stats
improving.

Run:
    python -u scripts/probe_R10_M7_ref_features.py > scripts/_results/improve_R10_M7_run.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
BASELINES = {
    "pts": 2.214, "reb": 0.8987, "ast": 0.5755, "fg3m": 0.3528,
    "stl": 0.2506, "blk": 0.1543, "tov": 0.3663,
}

_RESULTS_JSON = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R10_M7_ref_features_results.json"
)


def build_ref_lookup(parq_path: str) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], Dict[str, str]]:
    """Build (team, game_date) -> ref features lookup and game_id -> game_date map."""
    df = pd.read_parquet(parq_path)
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    game_dates: Dict[str, str] = {}
    for _, row in df.iterrows():
        team = str(row["team_abbreviation"])
        date = str(row["game_date"])
        gid = str(row["game_id"])
        lookup[(team, date)] = {
            "ref_crew_fouls": float(row["ref_crew_fouls"]),
            "ref_crew_fta": float(row["ref_crew_fta"]),
            "ref_crew_home_win_pct": float(row["ref_crew_home_win_pct"]),
        }
        game_dates[gid] = date
    return lookup, game_dates


def build_dataset(
    qstats_df: pd.DataFrame,
    ref_lookup: Dict[Tuple[str, str], Dict[str, float]],
    game_date_map: Dict[str, str],
    baseline_fn,
    stat: str,
) -> pd.DataFrame:
    import retro_inplay_mae as v1

    games = sorted(qstats_df["game_id"].unique().tolist())
    rows: List[dict] = []

    for gid in games:
        gdate = game_date_map.get(gid)
        if gdate is None:
            continue
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        try:
            base_projs = baseline_fn(snap)
        except Exception:
            continue

        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))
        home_ref = ref_lookup.get((home_team, gdate), {})
        away_ref = ref_lookup.get((away_team, gdate), {})
        if not home_ref and not away_ref:
            continue

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue
            actual = actuals.get((pid, stat))
            proj = base_projs.get((pid, stat))
            if actual is None or proj is None:
                continue
            team = str(player.get("team", ""))
            ref = home_ref if team == home_team else (away_ref if team == away_team else {})
            if not ref:
                continue
            residual = actual - proj
            rows.append({
                "game_id": gid,
                "player_id": pid,
                "team": team,
                "game_date": gdate,
                "proj_base": float(proj),
                "residual": float(residual),
                "cur_pts": float(player.get("pts", 0)),
                "cur_reb": float(player.get("reb", 0)),
                "cur_ast": float(player.get("ast", 0)),
                "cur_fg3m": float(player.get("fg3m", 0)),
                "cur_stl": float(player.get("stl", 0)),
                "cur_blk": float(player.get("blk", 0)),
                "cur_tov": float(player.get("tov", 0)),
                "cur_pf": float(player.get("pf", 0)),
                "min_through_q3": float(player.get("min", 0)),
                "score_margin_abs": float(margin),
                "is_leading": float(
                    (team == home_team and home_pts > away_pts)
                    or (team == away_team and away_pts > home_pts)
                ),
                "ref_crew_fouls": ref["ref_crew_fouls"],
                "ref_crew_fta": ref["ref_crew_fta"],
                "ref_crew_home_win_pct": ref["ref_crew_home_win_pct"],
            })
    return pd.DataFrame(rows)


FEATURE_COLS_BASE = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m", "cur_stl", "cur_blk", "cur_tov",
    "cur_pf", "min_through_q3", "score_margin_abs", "is_leading",
]
FEATURE_COLS_AUG = FEATURE_COLS_BASE + [
    "ref_crew_fouls", "ref_crew_fta", "ref_crew_home_win_pct",
]


def walk_forward_cv(df: pd.DataFrame, stat: str, n_folds: int = 4):
    import lightgbm as lgb

    df = df.sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
    games_ordered = df["game_id"].unique().tolist()
    n_games = len(games_ordered)
    if n_games < n_folds * 2:
        return [], float("nan"), float("nan")

    fold_size = n_games // n_folds
    game_to_fold = {}
    for fi in range(n_folds):
        lo = fi * fold_size
        hi = n_games if fi == n_folds - 1 else (fi + 1) * fold_size
        for g in games_ordered[lo:hi]:
            game_to_fold[g] = fi
    df["fold"] = df["game_id"].map(game_to_fold)

    all_base_errs: List[float] = []
    all_treat_errs: List[float] = []
    folds_out = []

    for fi in range(n_folds):
        train_mask = df["fold"] < fi
        val_mask = df["fold"] == fi
        train_df = df[train_mask]
        val_df = df[val_mask]
        if len(train_df) < 50 or len(val_df) < 10:
            continue

        # CONTROL: same model architecture, base features only
        X_train_base = train_df[FEATURE_COLS_BASE].values
        X_val_base = val_df[FEATURE_COLS_BASE].values
        # TREATMENT: base + ref features
        X_train_aug = train_df[FEATURE_COLS_AUG].values
        X_val_aug = val_df[FEATURE_COLS_AUG].values
        y_train = train_df["residual"].values
        y_val = val_df["residual"].values

        def _fit_predict(X_tr, X_va):
            m = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
                random_state=42, n_jobs=2, verbose=-1,
            )
            m.fit(X_tr, y_train)
            return m.predict(X_va)

        try:
            preds_base = _fit_predict(X_train_base, X_val_base)
            preds_aug = _fit_predict(X_train_aug, X_val_aug)
        except Exception as exc:
            print(f"  ERROR [{stat}] fold {fi+1}: {exc}")
            continue

        proj_base = val_df["proj_base"].values
        actual = proj_base + y_val
        # baseline = control head (no ref features), treatment = aug head
        base_proj = np.clip(proj_base + preds_base, 0.0, None)
        treat_proj = np.clip(proj_base + preds_aug, 0.0, None)
        base_errs = np.abs(base_proj - actual)
        treat_errs = np.abs(treat_proj - actual)

        bm = float(np.mean(base_errs))
        tm = float(np.mean(treat_errs))
        d = tm - bm
        all_base_errs.extend(base_errs.tolist())
        all_treat_errs.extend(treat_errs.tolist())
        folds_out.append({
            "fold": fi + 1,
            "n_train": int(len(train_df)),
            "n_val": int(len(val_df)),
            "baseline_mae": round(bm, 5),
            "treat_mae": round(tm, 5),
            "delta": round(d, 5),
        })
        print(f"  [{stat}] fold {fi+1}: n_tr={len(train_df)} n_va={len(val_df)} "
              f"base={bm:.4f} aug={tm:.4f} delta={d:+.4f}", flush=True)

    if not all_base_errs:
        return folds_out, float("nan"), float("nan")
    return folds_out, float(np.mean(all_base_errs)), float(np.mean(all_treat_errs))


def main():
    t0 = time.time()
    print("=" * 70)
    print("probe_R10_M7_ref_features — Referee Tendency Features")
    print("=" * 70, flush=True)

    parq = os.path.join(PROJECT_DIR, "data", "officials_features.parquet")
    if not os.path.exists(parq):
        raise SystemExit(f"missing parquet: {parq}")
    print("[1/4] Loading officials_features parquet ...")
    ref_lookup, game_dates_from_ref = build_ref_lookup(parq)
    print(f"  ref_lookup: {len(ref_lookup)} (team, date) entries", flush=True)

    print("[2/4] Loading player_quarter_stats parquet ...")
    qs = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet"))
    print(f"  player_quarter_stats: {qs.shape[0]} rows, {qs['game_id'].nunique()} games", flush=True)

    # Build comprehensive game_date_map (rest_travel or officials)
    game_date_map = dict(game_dates_from_ref)
    rt_path = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    if os.path.exists(rt_path):
        rt = pd.read_parquet(rt_path)
        for _, r in rt.iterrows():
            gid = str(r["game_id"])
            if gid not in game_date_map:
                game_date_map[gid] = str(r["game_date"])
    print(f"  game_date_map: {len(game_date_map)} entries", flush=True)

    print("[3/4] Loading live_engine baseline ...", flush=True)
    from src.prediction.live_engine import project_from_snapshot

    def baseline_fn(snap):
        rows = project_from_snapshot(snap)
        out = {}
        for r in rows:
            try:
                pid = int(r.get("player_id"))
            except (TypeError, ValueError):
                continue
            out[(pid, r["stat"])] = float(r["projected_final"])
        return out

    print("[4/4] Per-stat walk-forward CV ...", flush=True)
    per_stat = {}
    for stat in STATS:
        print(f"\n--- {stat.upper()} ---", flush=True)
        df = build_dataset(qs, ref_lookup, game_date_map, baseline_fn, stat)
        print(f"  dataset: {len(df)} rows, {df['game_id'].nunique()} games", flush=True)
        if len(df) < 100:
            per_stat[stat] = {"skip": True, "overall_delta": None}
            continue
        folds, base, treat = walk_forward_cv(df, stat)
        if folds:
            delta = treat - base
            n_pos = sum(1 for f in folds if f["delta"] <= 0)
            print(f"  [{stat}] OVERALL: base={base:.4f} aug={treat:.4f} delta={delta:+.4f} "
                  f"folds_pos={n_pos}/{len(folds)}", flush=True)
        else:
            delta = float("nan")
            n_pos = 0
        per_stat[stat] = {
            "n_rows": int(len(df)),
            "n_games": int(df["game_id"].nunique()),
            "folds": folds,
            "n_folds_positive": n_pos,
            "overall_base_mae": round(base, 5) if not np.isnan(base) else None,
            "overall_treat_mae": round(treat, 5) if not np.isnan(treat) else None,
            "overall_delta": round(delta, 5) if not np.isnan(delta) else None,
        }

    # Ship gate
    valid_stats = [s for s in STATS if not per_stat[s].get("skip") and per_stat[s].get("overall_delta") is not None]
    n_improving = sum(1 for s in valid_stats if per_stat[s]["overall_delta"] < 0)
    mean_delta = float(np.mean([per_stat[s]["overall_delta"] for s in valid_stats])) if valid_stats else float("nan")
    all_folds_4of4 = all(
        per_stat[s]["n_folds_positive"] == len(per_stat[s].get("folds", [])) and len(per_stat[s].get("folds", [])) == 4
        for s in valid_stats
    )

    gate_4of4 = bool(all_folds_4of4)
    gate_mean = mean_delta <= -0.005
    gate_4of7 = n_improving >= 4
    ship = gate_4of4 and gate_mean and gate_4of7

    ship_reason = (
        f"gate_4of4_per_stat={'PASS' if gate_4of4 else 'FAIL'} "
        f"gate_mean_delta<=-0.005={'PASS' if gate_mean else 'FAIL'}(mean={mean_delta:.5f}) "
        f"gate_4of7_improving={'PASS' if gate_4of7 else 'FAIL'}(n={n_improving}/7)"
    )
    status = "SHIP" if ship else "REJECT"

    out = {
        "probe": "R10_M7_ref_features",
        "status": status,
        "ship_reason": ship_reason,
        "per_stat": per_stat,
        "n_improving": n_improving,
        "mean_delta": round(mean_delta, 6) if not np.isnan(mean_delta) else None,
        "elapsed_seconds": round(time.time() - t0, 1),
        "feature_set_base": FEATURE_COLS_BASE,
        "feature_set_aug": FEATURE_COLS_AUG,
    }
    os.makedirs(os.path.dirname(_RESULTS_JSON), exist_ok=True)
    with open(_RESULTS_JSON, "w") as fh:
        json.dump(out, fh, indent=2)
    print("\n" + "=" * 70)
    print(f"[R10_M7_ref_features] {status} — {ship_reason}", flush=True)
    print(f"  results → {_RESULTS_JSON}", flush=True)


if __name__ == "__main__":
    main()
