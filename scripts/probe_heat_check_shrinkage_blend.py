"""probe_heat_check_shrinkage_blend.py -- cycle 103b (loop 5).

Single-split + WF 4-fold probe of the V2 shrinkage residual vs cycle-88
heuristic on PTS at endQ3.

SHIP GATE:
  * heat_check PTS MAE improves by >= 0.10 vs cycle-88 heuristic
  * non_heat PTS MAE does NOT regress > 0.05 vs cycle-88 heuristic
  * WF 4/4 positive on heat_check stratum
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import numpy as np                                    # noqa: E402
import predict_in_game as pig                         # noqa: E402
import retro_inplay_mae as v1                         # noqa: E402
import train_minute_trajectory as tmt                 # noqa: E402
import train_heat_check_residual as thr               # noqa: E402
import train_heat_check_shrinkage_residual as ts      # noqa: E402
from src.prediction.heat_check_shrinkage_residual import (  # noqa: E402
    HeatCheckShrinkageResidualModel,
    apply_shrinkage_to_projection,
    heat_check_shrinkage_factor,
    in_heat_check_stratum,
)


def _num(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _heuristic_pts(snap_p, period, clock_rem):
    cur = _num(snap_p.get("pts"))
    cur_min = _num(snap_p.get("min"))
    period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
    bench_now = pig.is_bench_in_current_period(
        snap_p, period, period_elapsed_min=period_elapsed_min)
    player_basis = cur_min if bench_now else None
    return pig.project_final(
        cur, period, clock_rem,
        pace_factor=1.0, foul_factor=1.0, blow_factor=1.0,
        player_clock_played_min=player_basis,
    )


def _shrunk_pts(snap_p, period, clock_rem, model, pq, spm, lpm, pos_str):
    heur = _heuristic_pts(snap_p, period, clock_rem)
    cur = _num(snap_p.get("pts"))
    factor = heat_check_shrinkage_factor(
        residual_model=model,
        q1_pts=pq["q1_pts"], q2_pts=pq["q2_pts"], q3_pts=pq["q3_pts"],
        min_q1=pq["min_q1"], min_q2=pq["min_q2"], min_q3=pq["min_q3"],
        season_pts_per_min=spm, l5_pts_per_min=lpm,
        position_proxy=pos_str, score_margin_abs=0.0,
    )
    return apply_shrinkage_to_projection(heur, cur, factor), factor


def _per_player_q(gdf):
    out = {}
    for pid in gdf["player_id"].unique():
        pdf = gdf[gdf["player_id"] == pid]
        pq = {"q1_pts": 0.0, "q2_pts": 0.0, "q3_pts": 0.0,
              "min_q1": 0.0, "min_q2": 0.0, "min_q3": 0.0}
        for _, r in pdf.iterrows():
            p = int(r["period"])
            if p == 1:
                pq["q1_pts"] = float(r["pts"]); pq["min_q1"] = float(r["min"])
            elif p == 2:
                pq["q2_pts"] = float(r["pts"]); pq["min_q2"] = float(r["min"])
            elif p == 3:
                pq["q3_pts"] = float(r["pts"]); pq["min_q3"] = float(r["min"])
        out[int(pid)] = pq
    return out


def _evaluate(games, qstats_df, positions, prior_ppm, model):
    err_heur_strat, err_shrink_strat = [], []
    err_heur_non, err_shrink_non = [], []
    n_strat = n_non = 0
    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        gdf = qstats_df[qstats_df["game_id"] == gid]
        per_player = _per_player_q(gdf)
        pig._normalize_snapshot(snap)
        period = int(snap.get("period") or 4)
        clock_rem = pig.parse_clock(snap.get("clock"))
        for p in snap.get("players") or []:
            try:
                pid_i = int(p.get("player_id"))
            except (TypeError, ValueError):
                continue
            pq = per_player.get(pid_i)
            if not pq:
                continue
            if pq["min_q3"] <= 0.0 or (pq["min_q1"] + pq["min_q2"]) <= 0.0:
                continue
            q3_ppm = pq["q3_pts"] / pq["min_q3"]
            q12_ppm = (pq["q1_pts"] + pq["q2_pts"]) / (pq["min_q1"] + pq["min_q2"])
            in_strat = in_heat_check_stratum(q3_ppm, q12_ppm)
            actual = actuals.get((pid_i, "pts"))
            if actual is None:
                continue
            heur = _heuristic_pts(p, period, clock_rem)
            spm, lpm = prior_ppm.get((pid_i, gid), (float("nan"), float("nan")))
            pos_str = positions.get(pid_i)
            shrunk, _ = _shrunk_pts(p, period, clock_rem, model, pq,
                                     None if spm != spm else spm,
                                     None if lpm != lpm else lpm,
                                     pos_str)
            if in_strat:
                err_heur_strat.append(abs(heur - actual))
                err_shrink_strat.append(abs(shrunk - actual))
                n_strat += 1
            else:
                err_heur_non.append(abs(heur - actual))
                err_shrink_non.append(abs(shrunk - actual))
                n_non += 1

    def mae(xs):
        return (sum(xs) / len(xs)) if xs else float("nan")
    return {
        "heur_strat": mae(err_heur_strat),
        "shrink_strat": mae(err_shrink_strat),
        "heur_non": mae(err_heur_non),
        "shrink_non": mae(err_shrink_non),
        "n_strat": n_strat, "n_non": n_non,
    }


def run_wf(games, qstats_df, positions, prior_ppm):
    games = sorted(games)
    N = len(games)
    base = N // 5
    fold_bounds = []
    for k in range(4):
        train_end = (k + 1) * base
        test_end = (k + 2) * base if k < 3 else N
        fold_bounds.append((train_end, test_end))
    out = {"per_fold_delta": [], "heur": [], "shrink": [],
           "n_train": [], "n_test": []}
    for (train_end, test_end) in fold_bounds:
        train_games = set(games[:train_end])
        test_games = list(games[train_end:test_end])
        X_tr, y_tr = [], []
        for gid in train_games:
            X_g, y_g = _gid_shrink_rows(gid, qstats_df, positions, prior_ppm)
            X_tr.extend(X_g); y_tr.extend(y_g)
        if not X_tr:
            for k in ["per_fold_delta", "heur", "shrink", "n_train", "n_test"]:
                out[k].append(float("nan") if k != "n_train" else 0)
            continue
        model = HeatCheckShrinkageResidualModel()
        model.fit(X_tr, y_tr, num_boost_round=250,
                  learning_rate=0.04, num_leaves=15, min_data_in_leaf=15)
        ev = _evaluate(test_games, qstats_df, positions, prior_ppm, model)
        out["heur"].append(ev["heur_strat"])
        out["shrink"].append(ev["shrink_strat"])
        out["per_fold_delta"].append(ev["shrink_strat"] - ev["heur_strat"])
        out["n_train"].append(len(X_tr))
        out["n_test"].append(ev["n_strat"])
    return out


def _gid_shrink_rows(gid, qstats_df, positions, prior_ppm):
    from src.prediction.heat_check_shrinkage_residual import build_feature_row
    gdf = qstats_df[qstats_df["game_id"] == gid]
    X, y = [], []
    for pid in gdf["player_id"].unique():
        pdf = gdf[gdf["player_id"] == pid]
        min_by_q, pts_by_q = {}, {}
        for _, r in pdf.iterrows():
            p = int(r["period"])
            min_by_q[p] = float(r["min"]); pts_by_q[p] = float(r["pts"])
        m1 = min_by_q.get(1, 0.0); m2 = min_by_q.get(2, 0.0); m3 = min_by_q.get(3, 0.0)
        q1 = pts_by_q.get(1, 0.0); q2 = pts_by_q.get(2, 0.0); q3 = pts_by_q.get(3, 0.0)
        if m3 <= 0.0 or (m1 + m2) <= 0.0:
            continue
        q3_ppm = q3 / m3
        q12_ppm = (q1 + q2) / (m1 + m2)
        if not in_heat_check_stratum(q3_ppm, q12_ppm):
            continue
        q4_min = min_by_q.get(4, 0.0); q4_pts = pts_by_q.get(4, 0.0)
        if q4_min < 0.5:
            continue
        actual_q4_ppm = q4_pts / q4_min
        ratio = actual_q4_ppm / max(q3_ppm, 1e-6)
        spm, lpm = prior_ppm.get((int(pid), gid), (float("nan"), float("nan")))
        X.append(build_feature_row(
            q1_pts=q1, q2_pts=q2, q3_pts=q3,
            min_q1=m1, min_q2=m2, min_q3=m3,
            season_pts_per_min=spm, l5_pts_per_min=lpm,
            position_proxy=positions.get(int(pid)),
            score_margin_abs=0.0,
        ))
        y.append(float(ratio))
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    model = HeatCheckShrinkageResidualModel.load()
    if model is None:
        print("  ERROR: artifact missing -- run train_heat_check_shrinkage_residual.py first")
        return 2
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if args.max_games:
        games = games[:args.max_games]
    positions = tmt.load_positions()
    print(f"  {len(games)} games  {len(positions)} positions")
    print("  building prior PPM lookup...")
    prior_ppm = thr._build_prior_ppm_index(qstats_df)

    ev = _evaluate(games, qstats_df, positions, prior_ppm, model)
    strat_delta = ev["shrink_strat"] - ev["heur_strat"]
    non_delta = ev["shrink_non"] - ev["heur_non"]
    print(f"\n  heat_check  n={ev['n_strat']}  "
          f"heur={ev['heur_strat']:.4f}  shrink={ev['shrink_strat']:.4f}  "
          f"delta={strat_delta:+.4f}")
    print(f"  non_heat    n={ev['n_non']}    "
          f"heur={ev['heur_non']:.4f}  shrink={ev['shrink_non']:.4f}  "
          f"delta={non_delta:+.4f}")

    ship_single = strat_delta <= -0.10 and non_delta <= 0.05
    wf = None
    if ship_single and not args.skip_wf:
        print("\n  single-split PASSES -- running WF 4-fold...")
        wf = run_wf(games, qstats_df, positions, prior_ppm)
        for i, d in enumerate(wf["per_fold_delta"], 1):
            print(f"    fold {i}  n_train={wf['n_train'][i-1]}  "
                  f"n_test={wf['n_test'][i-1]}  "
                  f"heur={wf['heur'][i-1]:.4f}  "
                  f"shrink={wf['shrink'][i-1]:.4f}  delta={d:+.4f}")

    ship = ship_single and (wf is None or all(d < 0 for d in wf["per_fold_delta"]))

    lines = [
        "# heat_check shrinkage residual v2 -- cycle 103b (loop 5)",
        "",
        f"**Games:** {len(games)}  **heat_check n:** {ev['n_strat']}  "
        f"**non_heat n:** {ev['n_non']}",
        "",
        "## PTS MAE",
        "",
        "| slice | n | cycle-88 heuristic | + shrinkage v2 | delta |",
        "|-------|---|---------|-----------|-------|",
        f"| heat_check | {ev['n_strat']} | {ev['heur_strat']:.4f} | "
        f"{ev['shrink_strat']:.4f} | {strat_delta:+.4f} |",
        f"| non_heat | {ev['n_non']} | {ev['heur_non']:.4f} | "
        f"{ev['shrink_non']:.4f} | {non_delta:+.4f} |",
        "",
        "## Ship gate (single-split)",
        f"- heat_check delta vs heuristic: {strat_delta:+.4f}  (gate: <= -0.10)",
        f"- non_heat delta vs heuristic:   {non_delta:+.4f}  (gate: <= +0.05)",
    ]
    if wf is not None:
        lines += [
            "",
            "## WF 4-fold on heat_check stratum",
            "",
            "| fold | n_train | n_test | heur | shrink | delta |",
            "|-----:|--------:|-------:|-----:|-------:|------:|",
        ]
        for i, d in enumerate(wf["per_fold_delta"], 1):
            lines.append(
                f"| {i} | {wf['n_train'][i-1]} | {wf['n_test'][i-1]} | "
                f"{wf['heur'][i-1]:.4f} | {wf['shrink'][i-1]:.4f} | {d:+.4f} |"
            )
        wf_pass = sum(1 for d in wf["per_fold_delta"] if d < 0)
        lines.append(f"\n**WF:** {wf_pass}/4 folds beat heuristic.")
    lines.append("")
    lines.append(f"- **{'SHIP' if ship else 'REJECT'}**")
    out_path = os.path.join(
        PROJECT_DIR, "scripts", "_results", "heat_check_shrinkage_v2.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\n  wrote {out_path}")
    print(f"  SHIP={ship}")
    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())
