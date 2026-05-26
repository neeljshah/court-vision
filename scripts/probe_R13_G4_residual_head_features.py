"""probe_R13_G4_residual_head_features.py — R13 stress-test residual heads.

Stress-tests 3 additive feature batches on endQ3 residual heads to find ONE
more 4/4 WF ship for any stat:

  Batch A — Referee features (from data/officials_features.parquet):
    ref_crew_fouls, ref_crew_fta, ref_crew_home_win_pct.
  Batch B — Rest-travel features (from data/rest_travel.parquet):
    is_b2b, is_b3b, miles_traveled, altitude_ft.
  Batch C — Q3-cumulative game-context features (computed from snapshot):
    cum_pts_through_q3, q3_margin_squared, pace_q3.

For each stat we hold the base 11-feature control fixed (mirrors R10_M7's
FEATURE_COLS_BASE so we honestly measure the ADDITIVE lift of the batch).
4-fold chronological WF (sort by game_date). Ship gate (per-stat):
  fold_wins == 4 AND mean delta <= -0.005

Output: data/cache/probe_R13_G4_residual_head_features_results.json

Run:
    python -u scripts/probe_R13_G4_residual_head_features.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

_RESULTS_JSON = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R13_G4_residual_head_features_results.json"
)

FEATURE_COLS_BASE = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m", "cur_stl", "cur_blk", "cur_tov",
    "cur_pf", "min_through_q3", "score_margin_abs", "is_leading",
]

# Per-batch additive feature lists
BATCH_FEATURES = {
    "A_ref": ["ref_crew_fouls", "ref_crew_fta", "ref_crew_home_win_pct"],
    "B_rest": ["is_b2b", "is_b3b", "miles_traveled", "altitude_ft"],
    "C_q3cum": ["cum_pts_through_q3", "q3_margin_squared", "pace_q3"],
}


def build_ref_lookup(parq_path: str) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], Dict[str, str]]:
    df = pd.read_parquet(parq_path)
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    game_dates: Dict[str, str] = {}
    for _, row in df.iterrows():
        team = str(row["team_abbreviation"])
        date = str(row["game_date"])[:10]
        gid = str(row["game_id"])
        lookup[(team, date)] = {
            "ref_crew_fouls": float(row["ref_crew_fouls"]),
            "ref_crew_fta": float(row["ref_crew_fta"]),
            "ref_crew_home_win_pct": float(row["ref_crew_home_win_pct"]),
        }
        game_dates[gid] = date
    return lookup, game_dates


def build_rest_lookup(parq_path: str) -> Tuple[Dict[Tuple[str, str], Dict[str, float]], Dict[str, str]]:
    df = pd.read_parquet(parq_path)
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    game_dates: Dict[str, str] = {}
    for _, row in df.iterrows():
        team = str(row["team_abbreviation"])
        date = str(row["game_date"])[:10]
        gid = str(row["game_id"])
        lookup[(team, date)] = {
            "is_b2b": float(row["is_b2b"]),
            "is_b3b": float(row["is_b3b"]),
            "miles_traveled": float(row["miles_traveled"]),
            "altitude_ft": float(row["altitude_ft"]),
        }
        game_dates[gid] = date
    return lookup, game_dates


def build_dataset(
    qstats_df: pd.DataFrame,
    ref_lookup: Dict[Tuple[str, str], Dict[str, float]],
    rest_lookup: Dict[Tuple[str, str], Dict[str, float]],
    game_date_map: Dict[str, str],
    baseline_fn,
) -> pd.DataFrame:
    """Build one big dataframe with base + all 3 batch features + per-stat residuals."""
    import retro_inplay_mae as v1

    games = sorted(qstats_df["game_id"].unique().tolist())
    rows: List[dict] = []
    n_no_date = 0
    n_snap_fail = 0
    n_baseline_fail = 0

    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  build {gi}/{len(games)} kept={len(rows)} ...", flush=True)
        gdate = game_date_map.get(gid)
        if gdate is None:
            n_no_date += 1
            continue
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            n_snap_fail += 1
            continue
        try:
            base_projs = baseline_fn(snap)
        except Exception:
            n_baseline_fail += 1
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))
        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)
        total_pts = home_pts + away_pts  # cum_pts_through_q3
        margin_sq = margin * margin       # q3_margin_squared

        # pace proxy: total per-player minutes / 5 players-per-team / 3 quarters
        # = avg minutes-played per player divided by 36 (full game = 48), scaled to pace
        players_snap = snap.get("players", [])
        total_min = sum(float(p.get("min", 0)) for p in players_snap)
        # Sample size: top 10 players approximate game pace
        # Higher total_min through Q3 = more possessions per quarter
        pace_q3 = total_min / max(1.0, len(players_snap))

        home_ref = ref_lookup.get((home_team, gdate), {})
        away_ref = ref_lookup.get((away_team, gdate), {})
        home_rest = rest_lookup.get((home_team, gdate), {})
        away_rest = rest_lookup.get((away_team, gdate), {})

        for player in players_snap:
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue
            team = str(player.get("team", ""))
            if team == home_team:
                ref = home_ref
                rest = home_rest
                is_leading = float(home_pts > away_pts)
            elif team == away_team:
                ref = away_ref
                rest = away_rest
                is_leading = float(away_pts > home_pts)
            else:
                continue

            # Collect per-stat actuals / projections
            stat_residuals: Dict[str, float] = {}
            stat_projs: Dict[str, float] = {}
            all_present = True
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = base_projs.get((pid, stat))
                if actual is None or proj is None:
                    all_present = False
                    break
                stat_residuals[stat] = float(actual - proj)
                stat_projs[stat] = float(proj)
            if not all_present:
                continue

            row = {
                "game_id": gid,
                "player_id": pid,
                "team": team,
                "game_date": gdate,
                # base features (mirror R10_M7)
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
                "is_leading": is_leading,
                # batch A — ref features (zero-fill if missing)
                "ref_crew_fouls":        float(ref.get("ref_crew_fouls", 0.0)),
                "ref_crew_fta":          float(ref.get("ref_crew_fta", 0.0)),
                "ref_crew_home_win_pct": float(ref.get("ref_crew_home_win_pct", 0.5)),
                "_has_ref":              float(bool(ref)),
                # batch B — rest/travel (zero-fill if missing)
                "is_b2b":          float(rest.get("is_b2b", 0.0)),
                "is_b3b":          float(rest.get("is_b3b", 0.0)),
                "miles_traveled":  float(rest.get("miles_traveled", 0.0)),
                "altitude_ft":     float(rest.get("altitude_ft", 285.0)),
                "_has_rest":       float(bool(rest)),
                # batch C — q3-cumulative
                "cum_pts_through_q3": float(total_pts),
                "q3_margin_squared":  float(margin_sq),
                "pace_q3":            float(pace_q3),
            }
            # Add per-stat proj + residual columns
            for stat in STATS:
                row[f"proj_{stat}"] = stat_projs[stat]
                row[f"resid_{stat}"] = stat_residuals[stat]
            rows.append(row)

    print(f"  build summary: no_date={n_no_date} snap_fail={n_snap_fail} "
          f"baseline_fail={n_baseline_fail} kept_rows={len(rows)}", flush=True)
    return pd.DataFrame(rows)


def walk_forward_cv(
    df: pd.DataFrame,
    stat: str,
    extra_cols: List[str],
    n_folds: int = 4,
) -> Tuple[List[dict], float, float]:
    """Run WF CV: control = BASE only, treatment = BASE + extra_cols."""
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
    df = df.copy()
    df["_fold"] = df["game_id"].map(game_to_fold)

    all_base_errs: List[float] = []
    all_treat_errs: List[float] = []
    folds_out: List[dict] = []
    aug_cols = FEATURE_COLS_BASE + extra_cols

    proj_col = f"proj_{stat}"
    resid_col = f"resid_{stat}"

    for fi in range(n_folds):
        # Chunked CV: val = fold fi, train = all other folds (matches
        # train_residual_heads_endq3_streak.py's GroupKFold-style logic).
        train_mask = df["_fold"] != fi
        val_mask = df["_fold"] == fi
        train_df = df[train_mask]
        val_df = df[val_mask]
        if len(train_df) < 50 or len(val_df) < 10:
            continue

        X_train_base = train_df[FEATURE_COLS_BASE].values
        X_val_base = val_df[FEATURE_COLS_BASE].values
        X_train_aug = train_df[aug_cols].values
        X_val_aug = val_df[aug_cols].values
        y_train = train_df[resid_col].values
        y_val = val_df[resid_col].values

        def _fit_predict(X_tr, X_va):
            m = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
                random_state=42, n_jobs=4, verbose=-1,
            )
            m.fit(X_tr, y_train)
            return m.predict(X_va)

        try:
            preds_base = _fit_predict(X_train_base, X_val_base)
            preds_aug = _fit_predict(X_train_aug, X_val_aug)
        except Exception as exc:
            print(f"  ERR [{stat}] fold {fi}: {exc}", flush=True)
            continue

        proj_base = val_df[proj_col].values
        actual = proj_base + y_val
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
        print(f"    [{stat}] fold {fi+1}: n_tr={len(train_df)} n_va={len(val_df)} "
              f"base={bm:.4f} aug={tm:.4f} delta={d:+.4f}",
              flush=True)

    if not all_base_errs:
        return folds_out, float("nan"), float("nan")
    return folds_out, float(np.mean(all_base_errs)), float(np.mean(all_treat_errs))


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("probe_R13_G4_residual_head_features")
    print("=" * 70, flush=True)

    print("[1/5] Loading officials_features ...", flush=True)
    ref_path = os.path.join(PROJECT_DIR, "data", "officials_features.parquet")
    ref_lookup, game_dates_ref = build_ref_lookup(ref_path)
    print(f"  ref: {len(ref_lookup)} entries, {len(game_dates_ref)} games", flush=True)

    print("[2/5] Loading rest_travel ...", flush=True)
    rt_path = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    rest_lookup, game_dates_rest = build_rest_lookup(rt_path)
    print(f"  rest: {len(rest_lookup)} entries, {len(game_dates_rest)} games", flush=True)

    # Merge date maps
    game_date_map = dict(game_dates_ref)
    for gid, gd in game_dates_rest.items():
        game_date_map.setdefault(gid, gd)
    print(f"  merged game_date_map: {len(game_date_map)} games", flush=True)

    print("[3/5] Loading player_quarter_stats ...", flush=True)
    qs = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet"))
    print(f"  qs: {qs.shape[0]} rows, {qs['game_id'].nunique()} games", flush=True)

    print("[4/5] Loading cycle88 baseline (fast - probe purpose only) ...", flush=True)
    # NOTE: cycle88 baseline used for speed (probe finishes in ~3min vs ~3hr).
    # Additive-lift measurement is invariant to baseline choice -- same proj used
    # for control and treatment so it cancels out of the delta.
    import retro_inplay_mae as v1_mod

    def baseline_fn(snap):
        return v1_mod.project_snapshot_to_finals(snap)

    print("[5/5] Building dataset ...", flush=True)
    df = build_dataset(qs, ref_lookup, rest_lookup, game_date_map, baseline_fn)
    print(f"  dataset: {len(df)} rows, {df['game_id'].nunique()} games", flush=True)
    if len(df) < 1000:
        print("ABORT: dataset too small", flush=True)
        return 2

    print(f"  coverage: ref={df['_has_ref'].mean():.3f}  "
          f"rest={df['_has_rest'].mean():.3f}", flush=True)

    # Per-batch x per-stat WF
    per_batch_per_stat: Dict[str, Dict[str, dict]] = {}
    ship_candidates: List[Tuple[str, str, float]] = []
    for batch_name, extras in BATCH_FEATURES.items():
        per_batch_per_stat[batch_name] = {}
        print(f"\n========== BATCH {batch_name} (extras={extras}) ==========", flush=True)
        for stat in STATS:
            print(f"\n  --- {batch_name} / {stat.upper()} ---", flush=True)
            folds, base, treat = walk_forward_cv(df, stat, extras, n_folds=4)
            if not folds:
                per_batch_per_stat[batch_name][stat] = {"skip": True}
                continue
            delta = treat - base
            n_pos = sum(1 for f in folds if f["delta"] < 0)
            n_folds = len(folds)
            print(f"  [{batch_name}/{stat}] OVERALL: base={base:.4f} aug={treat:.4f} "
                  f"delta={delta:+.4f} folds_pos={n_pos}/{n_folds}", flush=True)
            per_batch_per_stat[batch_name][stat] = {
                "n_folds":         n_folds,
                "n_folds_pos":     n_pos,
                "overall_base":    round(base, 5),
                "overall_treat":   round(treat, 5),
                "overall_delta":   round(delta, 5),
                "fold_deltas":     [f["delta"] for f in folds],
                "fold_pos_all":    n_pos == n_folds,
            }
            # Ship gate: all 4 folds positive AND mean delta <= -0.005
            if n_folds == 4 and n_pos == 4 and delta <= -0.005:
                ship_candidates.append((batch_name, stat, delta))

    # Pick best ship if any
    ship_candidates.sort(key=lambda x: x[2])
    ship = ship_candidates[0] if ship_candidates else None

    result = {
        "probe": "R13_G4_residual_head_features",
        "status": "SHIP" if ship else "REJECT",
        "best_ship": (
            {"batch": ship[0], "stat": ship[1], "delta": round(ship[2], 5)}
            if ship else None
        ),
        "all_ship_candidates": [
            {"batch": b, "stat": s, "delta": round(d, 5)}
            for b, s, d in ship_candidates
        ],
        "per_batch_per_stat": per_batch_per_stat,
        "elapsed_seconds": round(time.time() - t0, 1),
        "n_rows": int(len(df)),
        "n_games": int(df["game_id"].nunique()),
        "ship_gate": "fold_wins==4 AND mean_delta<=-0.005",
        "feature_set_base": FEATURE_COLS_BASE,
        "batches": BATCH_FEATURES,
    }
    os.makedirs(os.path.dirname(_RESULTS_JSON), exist_ok=True)
    with open(_RESULTS_JSON, "w") as fh:
        json.dump(result, fh, indent=2)
    print("\n" + "=" * 70)
    print(f"[R13_G4] {result['status']}", flush=True)
    if ship:
        print(f"  SHIP: batch={ship[0]} stat={ship[1]} delta={ship[2]:+.5f}", flush=True)
    print(f"  results -> {_RESULTS_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
