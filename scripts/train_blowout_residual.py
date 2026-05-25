"""train_blowout_residual.py -- cycle 102a (loop 5).

Trains :class:`src.prediction.blowout_residual.BlowoutResidualModel` on the
BLOWOUT_FLIP subset of the 550-game per-quarter parquet. Cycle 95b decomposed
endQ3 MAE and surfaced blowout_flip as a distinct failure mode that the
cycle-88 heuristic blowout_factor handles poorly (it ONLY fires post-fact
on observed margin, never proactively). The residual REPLACES the heuristic
on the blowout_flip stratum via stratified dispatch.

Stratum gate (matches `in_blowout_flip_stratum`):
    (|Q3 margin| <= 18 AND |final margin| >= 20)
    OR (|Q3 margin| <= 12 AND |final margin| >= 18)

Chronological 80/20 split: earliest 80 % of game_ids train, latest 20 %
validate. Writes ``data/models/blowout_residual.lgb`` plus meta JSON.

Usage:
    python scripts/train_blowout_residual.py
    python scripts/train_blowout_residual.py --max-games 100  (debug)
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

import train_minute_trajectory as tmt  # noqa: E402
import retro_inplay_mae as v1          # noqa: E402
from src.prediction.blowout_residual import (  # noqa: E402
    BlowoutResidualModel,
    build_feature_row,
    in_blowout_flip_stratum,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def _team_q_margins(game_df, pid_to_team) -> Tuple[Dict[str, Dict[int, float]],
                                                    Dict[int, str]]:
    """Return ({team_abbrev: {period: team_pts}}, pid_to_team).

    Q-by-Q team scoring totals — used to compute the Q1+Q2 / Q3 / final
    margin from this player's POV.
    """
    teams: Dict[str, Dict[int, float]] = {}
    for _, r in game_df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError):
            continue
        team = pid_to_team.get(pid, "")
        if not team:
            continue
        per = int(r["period"])
        teams.setdefault(team, {}).setdefault(per, 0.0)
        teams[team][per] += float(r["pts"])
    return teams, pid_to_team


def build_blowout_corpus(max_games: Optional[int] = None) -> Tuple[
        List[List[float]], List[float], List[str], Dict[str, int]]:
    """Walk the per-quarter parquet and emit (X_row, y) for blowout_flip rows."""
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows: List[List[float]] = []
    y: List[float] = []
    gids_out: List[str] = []
    stats = {
        "rows_total": 0,
        "rows_in_stratum": 0,
        "games_w_team_map": 0,
        "games_processed": 0,
    }

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        stats["games_processed"] += 1
        target_date = tmt.find_game_date_for_game(gid, df, pid_log_index)

        # Need team map to compute per-team margins.
        pid_to_team, home_abbrev, away_abbrev = v1.load_team_map(gid)
        if not pid_to_team:
            continue
        stats["games_w_team_map"] += 1

        # Per-team Q-by-Q points.
        team_q_pts, _ = _team_q_margins(gdf, pid_to_team)
        teams = list(team_q_pts.keys())
        if len(teams) < 2:
            continue

        # Helper: compute (q3_margin_signed_from_team_POV, q2_margin, final_margin).
        def margins_for_team(team: str) -> Tuple[float, float, float]:
            opp_candidates = [t for t in teams if t != team]
            if not opp_candidates:
                return 0.0, 0.0, 0.0
            opp = opp_candidates[0]
            my_q = team_q_pts.get(team, {})
            op_q = team_q_pts.get(opp, {})
            q3_margin = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0)
                            for q in (1, 2, 3))
            q2_margin = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0)
                            for q in (1, 2))
            # Final margin: include Q4 + any OT.
            all_q = set(my_q.keys()) | set(op_q.keys())
            final_margin = sum(my_q.get(q, 0.0) - op_q.get(q, 0.0)
                               for q in all_q)
            return q3_margin, q2_margin, final_margin

        for pid in gdf["player_id"].unique():
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                continue
            team = pid_to_team.get(pid_i, "")
            if not team:
                continue
            pdf = gdf[gdf["player_id"] == pid]
            min_by_q: Dict[int, float] = {}
            pf_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pf_by_q[p] = float(r["pf"])

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            min_through = min_q1 + min_q2 + min_q3
            if min_through <= 0.5:
                continue

            q3_pf = pf_by_q.get(3, 0.0)
            pf_through = (pf_by_q.get(1, 0.0)
                          + pf_by_q.get(2, 0.0)
                          + pf_by_q.get(3, 0.0))

            stats["rows_total"] += 1

            q3_signed, q2_signed, final_signed = margins_for_team(team)
            q3_abs = abs(q3_signed)
            final_abs = abs(final_signed)

            if not in_blowout_flip_stratum(
                    q3_margin_abs=q3_abs, final_margin_abs=final_abs):
                continue
            stats["rows_in_stratum"] += 1

            score_velocity = q3_signed - q2_signed
            team_is_leading = 1 if q3_signed > 0 else 0

            # Target: Q4 + OT minutes.
            rem_min = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) >= 4:
                    rem_min += float(r["min"])

            pos_str = positions.get(pid_i)
            l20 = tmt.rolling_mean_min(pid_i, target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(pid_i, target_date, 5, pid_log_index)

            row = build_feature_row(
                pf_through_q3=pf_through,
                q3_pf=q3_pf,
                min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
                period=3,
                score_margin_abs=q3_abs,
                score_margin_signed_q3=q3_signed,
                score_velocity_q3=score_velocity,
                is_leading_team=team_is_leading,
                position_proxy=pos_str,
                l20_min=l20, l5_min=l5,
            )
            X_rows.append(row)
            y.append(float(rem_min))
            gids_out.append(gid)

    return X_rows, y, gids_out, stats


def chronological_split(X: List[List[float]], y: List[float],
                        game_id_rows: List[str], val_frac: float = 0.2) -> Tuple[
                            List[List[float]], List[float],
                            List[List[float]], List[float]]:
    games_order = sorted(set(game_id_rows))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, gid in zip(X, y, game_id_rows):
        if gid in train_games:
            X_tr.append(x)
            y_tr.append(yi)
        else:
            X_val.append(x)
            y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  loading + building blowout_flip training corpus...")
    X, y, gids, stats = build_blowout_corpus(max_games=args.max_games)
    print(f"  games processed:            {stats['games_processed']}")
    print(f"  games with team map:        {stats['games_w_team_map']}")
    print(f"  total endQ3 rows seen:      {stats['rows_total']}")
    print(f"  blowout_flip stratum rows:  {stats['rows_in_stratum']}")
    print(f"  unique games in stratum:    {len(set(gids))}")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2
    if len(X) < 200:
        print(f"  WARN: n={len(X)} < 200 (stability bar). Proceeding anyway.")

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, val_frac=0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    model = BlowoutResidualModel()
    model.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
              num_boost_round=300, learning_rate=0.04,
              num_leaves=15, min_data_in_leaf=20, seed=42)

    import numpy as np
    pred_val = model.predict(X_val) if X_val else np.array([])
    val_mae = (float(np.mean(np.abs(pred_val - np.asarray(y_val))))
               if len(pred_val) else float("nan"))
    pred_tr = model.predict(X_tr)
    tr_mae = float(np.mean(np.abs(pred_tr - np.asarray(y_tr))))
    print(f"  train MAE: {tr_mae:.4f}  val MAE: {val_mae:.4f}")
    print(f"  fallback (train mean y): {model.fallback_mean:.4f}")
    if len(y_val):
        mean_pred = float(np.mean(y_tr))
        baseline_val_mae = float(np.mean(np.abs(np.asarray(y_val) - mean_pred)))
        print(f"  baseline (mean-pred) val MAE: {baseline_val_mae:.4f}  "
              f"(improvement: {baseline_val_mae - val_mae:+.4f})")

    model.save()
    print(f"  saved -> data/models/blowout_residual.lgb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
