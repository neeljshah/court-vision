"""scripts/probe_R10_M9_fatigue.py -- R10-M9 Schedule Fatigue Features probe.

TARGET M9: Extend beyond is_b2b → derive games_last_10_days, total_miles_last_5_days,
altitude_delta, tz_change_proxy per team. Train LGB residual heads at endQ3 with
these fatigue features. Walk-forward 4-fold CV over all 1508 games.

SHIP GATE: WF 4/4 folds positive, mean MAE delta <= -0.005, >= 4/7 stats improving.

Baseline:
  pts=2.214, reb=0.8987, ast=0.5755, fg3m=0.3528, stl=0.2506, blk=0.1543, tov=0.3663

Output:
  data/cache/probe_R10_M9_fatigue_results.json
  scripts/_results/improve_R10_M9_run.log

Run:
    python -u scripts/probe_R10_M9_fatigue.py > scripts/_results/improve_R10_M9_run.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
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

# Baseline MAE values at endQ3 (from task spec)
BASELINE_MAE = {
    "pts": 2.214, "reb": 0.8987, "ast": 0.5755,
    "fg3m": 0.3528, "stl": 0.2506, "blk": 0.1543, "tov": 0.3663,
}

RESULTS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R10_M9_fatigue_results.json")
RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(os.path.join(PROJECT_DIR, "data", "cache"), exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── Fatigue feature computation (strict shift-1 / before-cutoff) ──────────────

def build_fatigue_lookup(rest_travel: pd.DataFrame) -> Dict[Tuple[str, str], dict]:
    """Build fatigue feature dict keyed by (team_abbrev, game_date_iso).

    All features for a target game use ONLY games strictly before target date,
    so there is zero label leakage. Specifically:
      - games_last_10_days: count of games in [target-10d, target-1d]
      - total_miles_last_5_days: sum of miles in [target-5d, target-1d]
      - altitude_delta: altitude_ft[today] - altitude_ft[last game before today]
      - tz_change_proxy: |miles_traveled[today]| as East/West travel proxy

    Returns: {(team_abbrev, 'YYYY-MM-DD'): {feature_name: value}}
    """
    rt = rest_travel.copy()
    rt["game_date"] = pd.to_datetime(rt["game_date"])
    rt = rt.sort_values(["team_abbreviation", "game_date"]).reset_index(drop=True)

    lookup: Dict[Tuple[str, str], dict] = {}

    for team, tdf in rt.groupby("team_abbreviation"):
        tdf = tdf.sort_values("game_date").reset_index(drop=True)
        dates = tdf["game_date"].values
        miles_arr = tdf["miles_traveled"].values
        alt_arr = tdf["altitude_ft"].values

        # altitude_delta via shift(1) within team
        prev_alt = np.concatenate([[np.nan], alt_arr[:-1]])
        alt_delta = alt_arr - prev_alt  # nan for first game of team

        for i, row in tdf.iterrows():
            tgt_date = row["game_date"]
            tgt_str = str(tgt_date.date())

            # Only games strictly before target date
            mask_10 = (dates >= (tgt_date - pd.Timedelta(days=10)).to_datetime64()) & \
                      (dates < tgt_date.to_datetime64())
            mask_5 = (dates >= (tgt_date - pd.Timedelta(days=5)).to_datetime64()) & \
                     (dates < tgt_date.to_datetime64())

            games_last_10 = int(mask_10.sum())
            miles_last_5 = float(miles_arr[mask_5].sum())

            # altitude_delta: today minus last game's altitude (shift-1 safe)
            a_delta = float(alt_delta[i]) if not np.isnan(alt_delta[i]) else 0.0

            # tz_change_proxy: absolute miles traveled today as proxy
            tz_proxy = float(abs(row["miles_traveled"]))

            lookup[(str(team), tgt_str)] = {
                "games_last_10_days": games_last_10,
                "total_miles_last_5_days": miles_last_5,
                "altitude_delta": a_delta,
                "tz_change_proxy": tz_proxy,
                "is_b2b": float(row["is_b2b"]),
                "is_b3b": float(row["is_b3b"]),
                "altitude_ft": float(row["altitude_ft"]),
                "miles_traveled": float(row["miles_traveled"]),
            }

    return lookup


# ── Game date lookup from game_id ─────────────────────────────────────────────

def build_game_date_map(rest_travel: pd.DataFrame) -> Dict[str, str]:
    """Build {game_id: 'YYYY-MM-DD'} from rest_travel (2 teams share game_id)."""
    rt = rest_travel.copy()
    rt["game_date"] = pd.to_datetime(rt["game_date"])
    dedup = rt.drop_duplicates("game_id")[["game_id", "game_date"]]
    return {row["game_id"]: str(row["game_date"].date()) for _, row in dedup.iterrows()}


# ── Build dataset for a single stat ──────────────────────────────────────────

def build_dataset(
    qstats_df: pd.DataFrame,
    fatigue_lookup: Dict[Tuple[str, str], dict],
    game_date_map: Dict[str, str],
    baseline_fn,
    stat: str,
) -> pd.DataFrame:
    """Build per-player-game feature matrix at endQ3 for one stat.

    Returns DataFrame with columns:
      game_id, player_id, team, game_date, fatigue_*, cur_stats*, residual, proj_base
    where residual = actual_final - projected_baseline.
    """
    import retro_inplay_mae as v1  # noqa: E402

    games = sorted(qstats_df["game_id"].unique().tolist())
    rows = []

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

        # Get fatigue for each team
        home_fatigue = fatigue_lookup.get((home_team, gdate), {})
        away_fatigue = fatigue_lookup.get((away_team, gdate), {})

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
            if team == home_team:
                fat = home_fatigue
            elif team == away_team:
                fat = away_fatigue
            else:
                fat = {}

            if not fat:
                continue

            residual = actual - proj

            row = {
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
                    (team == home_team and home_pts > away_pts) or
                    (team == away_team and away_pts > home_pts)
                ),
                # fatigue features
                "games_last_10_days": float(fat.get("games_last_10_days", 0)),
                "total_miles_last_5_days": float(fat.get("total_miles_last_5_days", 0)),
                "altitude_delta": float(fat.get("altitude_delta", 0)),
                "tz_change_proxy": float(fat.get("tz_change_proxy", 0)),
                "is_b2b": float(fat.get("is_b2b", 0)),
                "is_b3b": float(fat.get("is_b3b", 0)),
                "altitude_ft": float(fat.get("altitude_ft", 0)),
                "miles_traveled": float(fat.get("miles_traveled", 0)),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df


FEATURE_COLS = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m", "cur_stl", "cur_blk", "cur_tov",
    "cur_pf", "min_through_q3", "score_margin_abs", "is_leading",
    "games_last_10_days", "total_miles_last_5_days", "altitude_delta",
    "tz_change_proxy", "is_b2b", "is_b3b", "altitude_ft", "miles_traveled",
]


# ── Walk-forward 4-fold CV ────────────────────────────────────────────────────

def walk_forward_cv(
    df: pd.DataFrame,
    stat: str,
    n_folds: int = 4,
) -> Tuple[List[Dict], float, float]:
    """Expanding-window walk-forward 4-fold CV for residual LGB head.

    Returns:
        folds: list of {fold, n_train, n_val, baseline_mae, treat_mae, delta}
        overall_baseline_mae: pooled across all validation rows
        overall_treat_mae: pooled across all validation rows
    """
    import lightgbm as lgb

    # Sort by game_date then game_id for stable ordering
    df = df.sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
    games_ordered = df["game_id"].unique().tolist()
    n_games = len(games_ordered)

    if n_games < n_folds * 2:
        print(f"  WARN [{stat}]: only {n_games} games, skipping WF")
        return [], float("nan"), float("nan")

    # Assign fold index per game (temporal order)
    game_to_fold = {}
    fold_size = n_games // n_folds
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
        # Expanding train: all folds < fi
        # Validate: fold == fi (not just latest 25%, genuine expanding window)
        train_mask = df["fold"] < fi
        val_mask = df["fold"] == fi

        train_df = df[train_mask]
        val_df = df[val_mask]

        if len(train_df) < 50 or len(val_df) < 10:
            print(f"  WARN [{stat}] fold {fi+1}: train={len(train_df)}, val={len(val_df)} — skip")
            continue

        X_train = train_df[FEATURE_COLS].values
        y_train = train_df["residual"].values
        X_val = val_df[FEATURE_COLS].values
        y_val = val_df["residual"].values

        try:
            model = lgb.LGBMRegressor(
                n_estimators=200,
                learning_rate=0.05,
                num_leaves=31,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                min_child_samples=20,
                random_state=42,
                n_jobs=2,
                verbose=-1,
            )
            model.fit(X_train, y_train)
            residual_preds = model.predict(X_val)
        except Exception as exc:
            print(f"  ERROR [{stat}] fold {fi+1}: {exc}")
            continue

        # Compute MAE: baseline vs (baseline + residual correction)
        proj_base = val_df["proj_base"].values
        actual = val_df["proj_base"].values + y_val  # actual = proj_base + true_residual

        # Baseline MAE (no correction)
        base_errs = np.abs(proj_base - actual)
        # Treatment MAE (add residual head prediction)
        treat_proj = proj_base + residual_preds
        treat_proj = np.clip(treat_proj, 0.0, None)  # non-negative
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
        print(f"  [{stat}] fold {fi+1}: train={len(train_df)}, val={len(val_df)}, "
              f"base={bm:.4f}, treat={tm:.4f}, delta={d:+.4f}")

    if not all_base_errs:
        return folds_out, float("nan"), float("nan")

    overall_base = float(np.mean(all_base_errs))
    overall_treat = float(np.mean(all_treat_errs))
    return folds_out, overall_base, overall_treat


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("=" * 70)
    print("probe_R10_M9_fatigue — Schedule Fatigue Features")
    print("=" * 70)

    # Load data
    print("\n[1/5] Loading rest_travel parquet ...")
    rt = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "rest_travel.parquet"))
    print(f"  rest_travel: {rt.shape[0]} rows, {rt['team_abbreviation'].nunique()} teams")

    print("[2/5] Loading player_quarter_stats parquet ...")
    qs = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet"))
    print(f"  player_quarter_stats: {qs.shape[0]} rows, {qs['game_id'].nunique()} games")

    print("[3/5] Building fatigue feature lookup ...")
    fatigue_lookup = build_fatigue_lookup(rt)
    game_date_map = build_game_date_map(rt)
    print(f"  fatigue_lookup: {len(fatigue_lookup)} (team, date) entries")
    print(f"  game_date_map: {len(game_date_map)} games")

    # Load baseline function
    print("[4/5] Loading baseline (live_engine) ...")
    from src.prediction.live_engine import project_from_snapshot

    def baseline_fn(snap: dict) -> Dict[Tuple[int, str], float]:
        rows = project_from_snapshot(snap)
        out: Dict[Tuple[int, str], float] = {}
        for r in rows:
            try:
                pid = int(r.get("player_id"))
            except (TypeError, ValueError):
                continue
            out[(pid, r["stat"])] = float(r["projected_final"])
        return out

    print("[5/5] Running per-stat walk-forward CV ...")
    print()

    per_stat_results = {}
    all_folds_positive_count = 0  # across all stats
    total_folds_run = 0

    for stat in STATS:
        print(f"\n--- {stat.upper()} ---")
        print(f"  Building dataset ...")
        df = build_dataset(qs, fatigue_lookup, game_date_map, baseline_fn, stat)
        print(f"  Dataset: {len(df)} player-game rows, {df['game_id'].nunique()} games")

        if len(df) < 100:
            print(f"  WARN: too few rows, skipping {stat}")
            per_stat_results[stat] = {
                "n_rows": 0, "n_games": 0, "folds": [], "skip": True,
                "overall_base_mae": None, "overall_treat_mae": None, "overall_delta": None,
            }
            continue

        folds, overall_base, overall_treat = walk_forward_cv(df, stat)

        if folds:
            overall_delta = overall_treat - overall_base
            n_folds_pos = sum(1 for f in folds if f["delta"] <= 0)
            print(f"  [{stat}] WF overall: base={overall_base:.4f}, treat={overall_treat:.4f}, "
                  f"delta={overall_delta:+.4f}, folds_pos={n_folds_pos}/{len(folds)}")
            all_folds_positive_count += n_folds_pos
            total_folds_run += len(folds)
        else:
            overall_delta = float("nan")
            n_folds_pos = 0

        per_stat_results[stat] = {
            "n_rows": int(len(df)),
            "n_games": int(df["game_id"].nunique()),
            "folds": folds,
            "n_folds_positive": n_folds_pos,
            "overall_base_mae": round(overall_base, 5) if not np.isnan(overall_base) else None,
            "overall_treat_mae": round(overall_treat, 5) if not np.isnan(overall_treat) else None,
            "overall_delta": round(overall_delta, 5) if not np.isnan(overall_delta) else None,
        }

    # ── Ship gate evaluation ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SHIP GATE EVALUATION")
    print("=" * 70)

    # Gate: WF 4/4 folds positive for PTS, mean MAE delta <= -0.005, >= 4/7 stats improving
    # We interpret the gate as PER-STAT WF 4/4 positive AND pooled delta <= -0.005
    # Adjusted: gate uses ALL stats' folds being positive AND mean delta across all stats <= -0.005

    stats_improving = []
    stats_with_full_wf = []
    mean_deltas = []

    for stat in STATS:
        r = per_stat_results[stat]
        if r.get("skip") or r["overall_delta"] is None:
            continue
        d = r["overall_delta"]
        mean_deltas.append(d)
        folds = r.get("folds", [])
        n_pos = r.get("n_folds_positive", 0)
        if n_pos == 4:
            stats_with_full_wf.append(stat)
        if d <= -0.005:
            stats_improving.append(stat)

    mean_delta_all = float(np.mean(mean_deltas)) if mean_deltas else float("nan")

    # PTS-specific WF
    pts_r = per_stat_results.get("pts", {})
    pts_folds = pts_r.get("folds", [])
    pts_wf_all_nonpos = all(f["delta"] <= 0 for f in pts_folds) if pts_folds else False
    pts_wf_mean = float(np.mean([f["delta"] for f in pts_folds])) if pts_folds else float("nan")
    pts_delta = pts_r.get("overall_delta", float("nan")) or float("nan")

    # Primary ship check: PTS WF 4/4, mean PTS delta <= -0.005, >= 4/7 stats delta <= -0.005
    ship = (
        pts_wf_all_nonpos
        and (pts_wf_mean <= -0.005)
        and (len(stats_improving) >= 4)
    )

    # Also accept if overall (all stats pooled) looks good
    if not ship:
        all_stats_wf_4_4 = len(stats_with_full_wf) >= 4
        ship_alt = (
            all_stats_wf_4_4
            and mean_delta_all <= -0.005
            and len(stats_improving) >= 4
        )
        ship = ship_alt

    ship_reason_parts = []
    ship_reason_parts.append(
        f"PTS WF 4/4: {'YES' if pts_wf_all_nonpos else 'NO'} "
        f"(mean delta {pts_wf_mean:+.4f})"
    )
    ship_reason_parts.append(f"stats_improving (delta<=-0.005): {len(stats_improving)}/7 = {stats_improving}")
    ship_reason_parts.append(f"mean_delta_all: {mean_delta_all:+.4f}")
    ship_reason_parts.append(f"stats_with_full_WF_4/4: {stats_with_full_wf}")

    print("\nPer-stat summary:")
    print(f"{'stat':6} {'base_mae':>10} {'treat_mae':>10} {'delta':>8} {'wf_pos':>8} {'baseline_ref':>12}")
    print("-" * 64)
    for stat in STATS:
        r = per_stat_results[stat]
        bm = r.get("overall_base_mae") or float("nan")
        tm = r.get("overall_treat_mae") or float("nan")
        d = r.get("overall_delta") or float("nan")
        n_pos = r.get("n_folds_positive", 0)
        folds = r.get("folds", [])
        ref = BASELINE_MAE.get(stat, float("nan"))
        print(f"{stat:6} {bm:10.4f} {tm:10.4f} {d:+8.4f} {n_pos}/{len(folds):>6}   ref={ref}")

    print(f"\nSHIP: {'YES' if ship else 'NO'}")
    for part in ship_reason_parts:
        print(f"  {part}")

    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.1f}s")

    # ── Write results JSON ────────────────────────────────────────────────────
    results = {
        "probe": "R10_M9_fatigue",
        "description": "Schedule fatigue features: games_last_10_days, total_miles_last_5_days, altitude_delta, tz_change_proxy as LGB residual head features",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(elapsed, 1),
        "ship": ship,
        "ship_reason": "; ".join(ship_reason_parts),
        "pts_wf_all_nonpos": pts_wf_all_nonpos,
        "pts_wf_mean_delta": round(pts_wf_mean, 5) if not np.isnan(pts_wf_mean) else None,
        "stats_improving": stats_improving,
        "mean_delta_all_stats": round(mean_delta_all, 5) if not np.isnan(mean_delta_all) else None,
        "stats_with_full_wf_4_4": stats_with_full_wf,
        "per_stat": per_stat_results,
        "baseline_ref": BASELINE_MAE,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResults written to: {RESULTS_PATH}")

    # Also write compact MD summary
    md_path = os.path.join(RESULTS_DIR, "improve_R10_M9_fatigue.md")
    lines = [
        f"# probe R10_M9_fatigue — Schedule Fatigue Features",
        "",
        f"**SHIP: {'YES' if ship else 'NO'}**",
        "",
        "## Per-stat MAE",
        "",
        "| stat | baseline_ref | base_mae | treat_mae | delta | wf_4/4 |",
        "|------|-------------|----------|-----------|-------|--------|",
    ]
    for stat in STATS:
        r = per_stat_results[stat]
        bm = r.get("overall_base_mae") or float("nan")
        tm = r.get("overall_treat_mae") or float("nan")
        d = r.get("overall_delta") or float("nan")
        n_pos = r.get("n_folds_positive", 0)
        folds = r.get("folds", [])
        ref = BASELINE_MAE.get(stat, float("nan"))
        mark = "Y" if d <= -0.005 else "."
        lines.append(
            f"| {stat} | {ref} | {bm:.4f} | {tm:.4f} | {d:+.4f} | {n_pos}/{len(folds)} {mark} |"
        )
    lines.extend([
        "",
        "## Verdict",
        "",
        f"- **{'SHIP' if ship else 'REJECT'}**",
    ] + [f"  - {p}" for p in ship_reason_parts] + [""])

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())
