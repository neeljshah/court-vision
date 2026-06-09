"""
probe_quarter_features_endq1q2_wf.py — Walk-forward probe for endQ1 + endQ2 quarter features.

Replicates Iter 20's endQ3 expansion (probe_quarter_features_wf.py) for the
endQ1 and endQ2 snapshots.

LEAKAGE RULES (enforced):
  endQ1: only Q1 data from quarter_features.parquet
    Safe:   q1_usg_avg (team's avg Q1 usage rate)
    Leak:   halftime_pace_shift (uses Q3+Q4), trailing_team_q4_usg_concentration (Q4),
            q2_pts, q3_pts, q4_pts, second_half_share_min, fourth_quarter_share_pts

  endQ2: Q1 + Q2 data only
    Safe:   q1_usg_avg, q1_pts_share_h1 (Q1 pts / Q1+Q2 pts — did team start hot?)
    Leak:   halftime_pace_shift (uses Q3+Q4), trailing_team_q4_usg_concentration (Q4),
            q3_pts, q4_pts, second_half_share_min, fourth_quarter_share_pts

SHIP gate: 3+/4 walk-forward folds show strictly lower Brier vs baseline.

Results saved to data/cache/probe_quarter_features_endq1q2_wf_results.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
OUT_JSON = os.path.join(DATA_CACHE, "probe_quarter_features_endq1q2_wf_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)


# ── data loaders ─────────────────────────────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def load_quarter_features_summaries() -> Dict[str, Dict]:
    """Load quarter_features parquet; produce per-game per-team summaries.

    Returns dict keyed by "{game_id}_{team_id}" with only LEAK-SAFE fields:
        q1_usg_avg              — team-avg player Q1 usage rate (Q1 data only)
        q1_pts_share_h1         — Q1 pts / (Q1+Q2 pts) for team (Q1+Q2 data only)

    halftime_pace_shift and trailing_team_q4_usg_concentration are NOT included
    here because they require Q3/Q4 data (leakage for endQ1/endQ2).
    """
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print("  [WARN] quarter_features.parquet missing", flush=True)
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")

    summaries: Dict[str, Dict] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        q1_pts_sum = float(grp["q1_pts"].sum())
        q2_pts_sum = float(grp["q2_pts"].sum())
        h1_pts = q1_pts_sum + q2_pts_sum
        q1_pts_share_h1 = q1_pts_sum / h1_pts if h1_pts > 0 else np.nan
        key = f"{gid}_{int(tid)}"
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            # Q1 share of H1 scoring — reveals if team started hot or finished H1 strong
            "q1_pts_share_h1": q1_pts_share_h1,
        }
    print(f"  quarter_features summaries: {len(summaries)} entries", flush=True)
    return summaries


MINUTES_PER_QUARTER = 12.0


def _pregame_wp_from_sg(sg: Dict) -> float:
    """ELO-based pregame WP proxy (mirrors the training script)."""
    wp = sg.get("sim_win_prob")
    if wp is not None:
        return float(wp)
    hca = 65.0
    home_elo = sg.get("home_elo")
    away_elo = sg.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


def build_rows(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict,
) -> pd.DataFrame:
    """Build one row per (game_id, snapshot) with base + leak-safe quarter features."""
    records: List[Dict] = []

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue

        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]

        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)

        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = _pregame_wp_from_sg(sg)

        # Quarter-feature lookup (NaN if game not in parquet)
        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        q1_pts_share_h1 = qf_row.get("q1_pts_share_h1", np.nan)

        for snap_idx, snapshot in enumerate(["endQ1", "endQ2", "endQ3"]):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER

            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum

            if snapshot == "endQ3" and total_pts < 60:
                continue

            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played

            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            records.append({
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
                # Leak-safe quarter features (NaN for unmatched games)
                "q1_usg_avg": q1_usg_avg,
                # q1_pts_share_h1 is Q1+Q2 data only (safe from endQ2 onward)
                "q1_pts_share_h1": q1_pts_share_h1,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  Built {len(df)} snapshot rows from {df['game_id'].nunique()} games",
          flush=True)
    return df


# ── feature schemas ───────────────────────────────────────────────────────────

# endQ1 baseline (current production schema)
BASE_FEATURES_ENDQ1 = [
    "score_margin", "total_pts", "pace_so_far", "q1_delta",
    "last_q_margin", "pregame_win_prob", "home_team_id", "season",
]
# endQ1 expanded: add q1_usg_avg only (only Q1 data available at this snapshot)
EXPANDED_FEATURES_ENDQ1 = BASE_FEATURES_ENDQ1 + ["q1_usg_avg"]

# endQ2 baseline (current production schema)
BASE_FEATURES_ENDQ2 = [
    "score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
    "last_q_margin", "pregame_win_prob", "home_team_id", "season",
]
# endQ2 expanded: q1_usg_avg + q1_pts_share_h1 (both safe — only Q1/Q2 data)
EXPANDED_FEATURES_ENDQ2 = BASE_FEATURES_ENDQ2 + ["q1_usg_avg", "q1_pts_share_h1"]

CAT_COLS = ["home_team_id", "season"]


# ── walk-forward CV ───────────────────────────────────────────────────────────

def walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_folds: int = 4,
    label: str = "",
) -> List[Dict]:
    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

    n = len(X)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    fold_results = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

        if train_end < 30 or test_start >= n:
            continue

        X_tr = X.iloc[:train_end].copy()
        y_tr = y.iloc[:train_end]
        X_te = X.iloc[test_start:test_end].copy()
        y_te = y.iloc[test_start:test_end]

        if len(X_te) < 10:
            continue

        cat_cols = [c for c in CAT_COLS if c in X_tr.columns]
        for c in cat_cols:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=4,
            verbose=-1,
        )
        model.fit(X_tr, y_tr,
                  categorical_feature=cat_cols if cat_cols else "auto")

        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        fr = {
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_te, probs)),
            "accuracy": float(accuracy_score(y_te, preds)),
            "auc": float(roc_auc_score(y_te, probs)),
        }
        fold_results.append(fr)
        print(f"    {label} fold {fold}: train={len(X_tr)}, test={len(X_te)}, "
              f"Brier={fr['brier']:.4f}, Acc={fr['accuracy']:.4f}", flush=True)

    return fold_results


def run_wf_for_snapshot(
    df: pd.DataFrame,
    snapshot: str,
    base_features: List[str],
    expanded_features: List[str],
) -> Dict:
    """Run PRE vs POST WF comparison for a given snapshot. Returns result dict."""
    sub = df[df["snapshot"] == snapshot].copy()
    y = sub["home_team_won"].copy()
    n_rows = len(sub)
    home_win_rate = float(y.mean())
    print(f"\n  {snapshot}: {n_rows} rows, home_win_rate={home_win_rate:.3f}",
          flush=True)

    # Coverage of new features
    new_feat = [f for f in expanded_features if f not in base_features]
    for nf in new_feat:
        if nf in sub.columns:
            coverage = sub[nf].notna().sum()
            print(f"    {nf} coverage: {coverage}/{n_rows} ({100*coverage/n_rows:.1f}%)",
                  flush=True)

    print(f"\n  [PRE] {snapshot} baseline ({len(base_features)} features):", flush=True)
    pre_folds = walk_forward_cv(
        sub[base_features].copy(), y, n_folds=4, label=f"PRE-{snapshot}"
    )

    print(f"\n  [POST] {snapshot} expanded ({len(expanded_features)} features):", flush=True)
    post_folds = walk_forward_cv(
        sub[expanded_features].copy(), y, n_folds=4, label=f"POST-{snapshot}"
    )

    pre_briers = [r["brier"] for r in pre_folds]
    post_briers = [r["brier"] for r in post_folds]
    deltas = [post_briers[i] - pre_briers[i] for i in range(len(pre_briers))]
    improved = sum(1 for d in deltas if d < 0)
    n_folds = len(pre_briers)
    ship = improved >= 3

    print(f"\n  {'='*55}", flush=True)
    print(f"  {snapshot} Comparison", flush=True)
    print(f"  {'Fold':<6} {'PRE Brier':<12} {'POST Brier':<12} {'Delta':<10} Result",
          flush=True)
    for i, (pre, post, delta) in enumerate(zip(pre_briers, post_briers, deltas)):
        result = "IMPROVE" if delta < 0 else "REGRESS"
        print(f"  {i:<6} {pre:<12.4f} {post:<12.4f} {delta:+.4f}    {result}",
              flush=True)
    print(f"\n  PRE  mean Brier: {np.mean(pre_briers):.4f}", flush=True)
    print(f"  POST mean Brier: {np.mean(post_briers):.4f}", flush=True)
    print(f"  Mean delta:      {np.mean(deltas):+.4f}", flush=True)
    print(f"  Folds improved:  {improved}/{n_folds}", flush=True)
    print(f"\n  DECISION ({snapshot}): {'SHIP' if ship else 'REVERT'}", flush=True)

    return {
        "snapshot": snapshot,
        "decision": "SHIP" if ship else "REVERT",
        "folds_improved": improved,
        "n_folds": n_folds,
        "pre_briers": pre_briers,
        "post_briers": post_briers,
        "deltas": deltas,
        "pre_mean_brier": float(np.mean(pre_briers)),
        "post_mean_brier": float(np.mean(post_briers)),
        "mean_delta": float(np.mean(deltas)),
        "base_features": base_features,
        "expanded_features": expanded_features,
        "new_features": [f for f in expanded_features if f not in base_features],
        "n_rows": n_rows,
        "home_win_rate": home_win_rate,
        "pre_folds_detail": pre_folds,
        "post_folds_detail": post_folds,
    }


def main() -> None:
    t0 = time.time()
    print("=== probe_quarter_features_endq1q2_wf: endQ1+endQ2 expansion ===",
          flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"  linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[2] Building rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries)

    # Filter to games that have endQ3 (same as training script — consistent game set)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    print(f"  After endQ3-gate filter: {len(df)} rows, "
          f"{df['game_id'].nunique()} games", flush=True)

    print("\n[3] endQ1 probe ...", flush=True)
    result_q1 = run_wf_for_snapshot(
        df, "endQ1", BASE_FEATURES_ENDQ1, EXPANDED_FEATURES_ENDQ1
    )

    print("\n[4] endQ2 probe ...", flush=True)
    result_q2 = run_wf_for_snapshot(
        df, "endQ2", BASE_FEATURES_ENDQ2, EXPANDED_FEATURES_ENDQ2
    )

    elapsed = time.time() - t0

    combined = {
        "probe": "quarter_features_expansion_endq1q2",
        "elapsed_s": float(elapsed),
        "endQ1": result_q1,
        "endQ2": result_q2,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)

    # Final summary
    print("\n" + "=" * 60, flush=True)
    print("FINAL SUMMARY", flush=True)
    for snap, res in [("endQ1", result_q1), ("endQ2", result_q2)]:
        print(f"  {snap}: {res['decision']} "
              f"({res['folds_improved']}/{res['n_folds']} folds improved, "
              f"mean delta={res['mean_delta']:+.4f})", flush=True)
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
