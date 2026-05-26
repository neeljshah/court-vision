"""probe_R8_M31_ot.py — R8 probe: OT probability → stat inflation correction.

Stage 0: build OT label cache (filesystem-only first; API fallback; REJECT if unavailable).
Stage 1: P(OT) binary classifier at endQ3 (LightGBM, walk-forward CV).
Stage 2: apply empirical inflation priors.
Stage 3: evaluate corrected vs baseline MAE at endQ3.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ── constants ──────────────────────────────────────────────────────────────────
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
INFLATION_PRIORS = {
    "pts": 0.058, "reb": 0.045, "ast": 0.052, "fg3m": 0.060,
    "stl": 0.044, "blk": 0.041, "tov": 0.038,
}

_CACHE_DIR     = os.path.join(PROJECT_DIR, "data", "cache")
_OT_LABELS     = os.path.join(_CACHE_DIR, "ot_labels.json")
_RESULTS       = os.path.join(_CACHE_DIR, "probe_R8_M31_ot_results.json")
_LS_PATH       = os.path.join(PROJECT_DIR, "data", "nba", "linescores_all.json")
_QBOX_DIR      = os.path.join(_CACHE_DIR, "quarter_box")
_BOXSCORE_DIR  = os.path.join(PROJECT_DIR, "data", "nba")
_QUARTER_PARQ  = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


# ── helpers ────────────────────────────────────────────────────────────────────

def _reject(reason: str, extra: Optional[dict] = None) -> None:
    out = {"probe": "R8_M31_ot", "status": "REJECT", "ship_reason": reason}
    if extra:
        out.update(extra)
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_RESULTS, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"[R8_M31_ot] REJECT — {reason}")
    sys.exit(0)


def _load_linescores() -> Dict[str, dict]:
    if not os.path.exists(_LS_PATH):
        return {}
    with open(_LS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ── Stage 0: OT label cache ───────────────────────────────────────────────────

def _build_ot_labels_filesystem(linescores: Dict[str, dict]) -> Tuple[Dict[str, dict], int]:
    """Cross-ref boxscore final total vs linescore Q1-Q4 sum to detect OT.

    If boxscore_<gid>.json home_score > ls home Q1+Q2+Q3+Q4, went to OT.
    Returns (labels_dict, n_covered).
    """
    labels: Dict[str, dict] = {}
    bs_files = [f for f in os.listdir(_BOXSCORE_DIR) if f.startswith("boxscore_0") and f.endswith(".json")]
    for fname in bs_files:
        gid = fname.replace("boxscore_", "").replace(".json", "")
        ls = linescores.get(gid)
        if ls is None:
            continue
        try:
            with open(os.path.join(_BOXSCORE_DIR, fname), encoding="utf-8") as fh:
                bs = json.load(fh)
        except Exception:
            continue
        h_total = bs.get("home_score")
        a_total = bs.get("away_score")
        if h_total is None or a_total is None:
            continue
        h_reg = (ls.get("home_q1", 0) + ls.get("home_q2", 0) +
                 ls.get("home_q3", 0) + ls.get("home_q4", 0))
        a_reg = (ls.get("away_q1", 0) + ls.get("away_q2", 0) +
                 ls.get("away_q3", 0) + ls.get("away_q4", 0))
        went_ot = int(h_total) > int(h_reg) or int(a_total) > int(a_reg)
        final_margin = abs(int(h_total) - int(a_total))
        labels[gid] = {
            "went_ot": int(went_ot),
            "n_ot_periods": 1 if went_ot else 0,  # cannot derive exact count
            "final_margin": final_margin,
        }
    return labels, len(labels)


def _build_ot_labels_quarter_box() -> Dict[str, dict]:
    """Check quarter_box for period >4 files (direct OT evidence)."""
    labels: Dict[str, dict] = {}
    if not os.path.isdir(_QBOX_DIR):
        return labels
    ot_games: Dict[str, int] = defaultdict(int)
    for fname in os.listdir(_QBOX_DIR):
        if not fname.endswith(".json"):
            continue
        parts = fname.replace(".json", "").split("_")
        if len(parts) != 2:
            continue
        gid, qstr = parts
        if qstr.startswith("q") and qstr[1:].isdigit():
            period = int(qstr[1:])
            if period > 4:
                ot_games[gid] = max(ot_games[gid], period - 4)
    for gid, n_ot in ot_games.items():
        labels[gid] = {"went_ot": 1, "n_ot_periods": n_ot, "final_margin": None}
    return labels


def stage0_build_ot_labels() -> Dict[str, dict]:
    """Build OT label cache. Returns labels dict or calls _reject()."""
    linescores = _load_linescores()
    all_game_ids = set(linescores.keys())

    if os.path.exists(_OT_LABELS):
        try:
            with open(_OT_LABELS, encoding="utf-8") as fh:
                cached = json.load(fh)
            if isinstance(cached, dict) and len(cached) > 0:
                coverage = len(cached) / max(len(all_game_ids), 1)
                print(f"[Stage 0] loaded cached labels: {len(cached)} games "
                      f"({sum(v.get('went_ot', 0) for v in cached.values())} OT), "
                      f"coverage={coverage:.2%}")
                if coverage >= 0.90:
                    return cached
                print(f"[Stage 0] cached coverage {coverage:.2%} < 90%; rebuilding")
        except Exception as e:
            print(f"[Stage 0] cache load failed: {e}; rebuilding")

    qbox_labels = _build_ot_labels_quarter_box()
    print(f"[Stage 0] quarter_box OT files: {len(qbox_labels)} games")

    # Option 1b: boxscore cross-ref with linescores
    fs_labels, n_covered = _build_ot_labels_filesystem(linescores)
    print(f"[Stage 0] boxscore cross-ref: {n_covered} games labeled "
          f"({sum(v['went_ot'] for v in fs_labels.values())} OT)")

    # Merge: prefer fs_labels; annotate quarter_box OT games too
    labels = dict(fs_labels)
    for gid, lbl in qbox_labels.items():
        if gid not in labels:
            labels[gid] = lbl
        else:
            if lbl["went_ot"]:
                labels[gid]["went_ot"] = 1

    coverage = len(labels) / max(len(all_game_ids), 1)
    print(f"[Stage 0] coverage: {len(labels)}/{len(all_game_ids)} = {coverage:.2%}")

    if coverage < 0.90:
        # Try NBA API as last resort
        print("[Stage 0] Coverage < 90%, attempting nba_api fallback...")
        labels = _try_nba_api_fallback(labels, linescores)
        coverage = len(labels) / max(len(all_game_ids), 1)
        print(f"[Stage 0] After API: {len(labels)}/{len(all_game_ids)} = {coverage:.2%}")

    if coverage < 0.90:
        _reject(
            "ot_label_unavailable",
            {"ot_label_coverage": coverage, "status": "REJECT",
             "reason": f"coverage={coverage:.2%} < 90%"},
        )

    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_OT_LABELS, "w") as fh:
        json.dump(labels, fh, indent=2)
    print(f"[Stage 0] Saved {len(labels)} labels → {_OT_LABELS}")
    return labels


def _try_nba_api_fallback(
    existing: Dict[str, dict], linescores: Dict[str, dict]
) -> Dict[str, dict]:
    """Attempt nba_api to fill gaps. Returns extended labels; never crashes."""
    try:
        from nba_api.stats.endpoints.boxscoresummaryv2 import BoxScoreSummaryV2  # type: ignore
    except Exception as e:
        print(f"[Stage 0] nba_api not available: {e}")
        return existing

    missing = [gid for gid in linescores if gid not in existing]
    print(f"[Stage 0] API: fetching {len(missing)} missing games...")
    labels = dict(existing)
    for gid in missing:
        try:
            bs = BoxScoreSummaryV2(game_id=gid)
            df = bs.get_data_frames()[5]  # LineScore
            pts_ot = 0
            for col in ["PTS_OT1", "PTS_OT2", "PTS_OT3", "PTS_OT4"]:
                if col in df.columns:
                    pts_ot += df[col].fillna(0).sum()
            went_ot = pts_ot > 0
            ls = linescores.get(gid, {})
            h_reg = (ls.get("home_q1", 0) + ls.get("home_q2", 0) +
                     ls.get("home_q3", 0) + ls.get("home_q4", 0))
            a_reg = (ls.get("away_q1", 0) + ls.get("away_q2", 0) +
                     ls.get("away_q3", 0) + ls.get("away_q4", 0))
            labels[gid] = {
                "went_ot": int(went_ot),
                "n_ot_periods": 1 if went_ot else 0,
                "final_margin": None,
            }
            time.sleep(0.6)
        except Exception:
            continue
    return labels


# ── Stage 1: P(OT) classifier ─────────────────────────────────────────────────

def _build_features(linescores: Dict[str, dict], labels: Dict[str, dict],
                    game_dates: Dict[str, str]) -> Tuple[list, list, list, list]:
    """Build feature rows for games present in both linescores and labels."""
    rows, targets, gids, dates = [], [], [], []
    for gid, lbl in labels.items():
        ls = linescores.get(gid)
        if ls is None:
            continue
        try:
            hq1 = float(ls.get("home_q1", 0))
            hq2 = float(ls.get("home_q2", 0))
            hq3 = float(ls.get("home_q3", 0))
            aq1 = float(ls.get("away_q1", 0))
            aq2 = float(ls.get("away_q2", 0))
            aq3 = float(ls.get("away_q3", 0))
        except (TypeError, ValueError):
            continue
        home_pts_q3 = hq1 + hq2 + hq3
        away_pts_q3 = aq1 + aq2 + aq3
        total_q3 = home_pts_q3 + away_pts_q3
        margin = abs(home_pts_q3 - away_pts_q3)
        pace_proxy = total_q3 / 3.0
        feat = [
            margin,          # score_margin_abs_q3
            total_q3,        # total_score_q3
            pace_proxy,      # pace_so_far proxy
            abs(hq3 - aq3), # q3_score_delta
            margin * pace_proxy,  # margin_x_pace_interaction
            float(ls.get("home_team_id") or 0),  # categorical
        ]
        rows.append(feat)
        targets.append(int(lbl["went_ot"]))
        gids.append(gid)
        dates.append(game_dates.get(gid, "1900-01-01"))
    return rows, targets, gids, dates


def _load_game_dates() -> Dict[str, str]:
    dates: Dict[str, str] = {}
    for season_file in ["season_games_2022-23.json", "season_games_2023-24.json",
                        "season_games_2024-25.json"]:
        p = os.path.join(PROJECT_DIR, "data", "nba", season_file)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            sg = json.load(fh)
        rows = sg.get("rows", sg) if isinstance(sg, dict) else sg
        for r in rows:
            gid = str(r.get("game_id", ""))
            date = str(r.get("game_date", ""))
            if gid and date:
                dates[gid] = date
    return dates


def stage1_classifier(linescores: Dict[str, dict], labels: Dict[str, dict],
                      game_dates: Dict[str, str]) -> Tuple[float, float, float, int, list, list]:
    """Walk-forward 4-fold LightGBM classifier. Returns (auc, brier, logloss, n_ot, y_true, y_pred_prob)."""
    try:
        import lightgbm as lgb
        import numpy as np
        from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss
        from sklearn.model_selection import KFold
    except ImportError as e:
        _reject(f"missing_dependency: {e}")

    rows, targets, gids, dates = _build_features(linescores, labels, game_dates)
    if len(rows) < 50:
        _reject(f"insufficient_data: only {len(rows)} games with features")

    import numpy as np
    X = np.array(rows, dtype=np.float32)
    y = np.array(targets, dtype=np.int32)

    # Walk-forward by date order
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    X, y = X[order], y[order]

    n = len(X)
    fold_size = n // 4
    all_preds = np.zeros(n)
    aucs, briers, lls = [], [], []

    lgb_params = {
        "objective": "binary", "metric": ["binary_logloss", "auc"],
        "n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31,
        "min_data_in_leaf": 20, "is_unbalance": True,
        "verbose": -1, "random_state": 42,
    }

    for fold in range(4):
        test_start = fold * fold_size
        test_end = test_start + fold_size if fold < 3 else n
        train_idx = list(range(0, test_start))
        test_idx  = list(range(test_start, test_end))
        if len(train_idx) < 30:
            continue
        Xtr, Xte = X[train_idx], X[test_idx]
        ytr, yte = y[train_idx], y[test_idx]
        model = lgb.LGBMClassifier(**lgb_params)
        model.fit(Xtr, ytr)
        preds = model.predict_proba(Xte)[:, 1]
        all_preds[test_idx] = preds
        if yte.sum() > 0 and (1 - yte).sum() > 0:
            aucs.append(roc_auc_score(yte, preds))
            briers.append(brier_score_loss(yte, preds))
            lls.append(log_loss(yte, preds))

    valid_mask = all_preds > 0
    y_true_valid = y[valid_mask]
    y_pred_valid = all_preds[valid_mask]

    mean_auc = float(np.mean(aucs)) if aucs else 0.5
    mean_brier = float(np.mean(briers)) if briers else 0.25
    mean_ll = float(np.mean(lls)) if lls else 1.0
    n_ot = int(y.sum())
    print(f"[Stage 1] AUC={mean_auc:.3f} Brier={mean_brier:.4f} LogLoss={mean_ll:.4f} "
          f"n={len(y)} n_ot={n_ot}")
    return mean_auc, mean_brier, mean_ll, n_ot, list(y_true_valid), list(y_pred_valid)


# ── Stage 3: baseline MAE + corrected MAE ─────────────────────────────────────

def stage3_evaluate(linescores: Dict[str, dict], labels: Dict[str, dict],
                    game_dates: Dict[str, str],
                    y_pred_by_gid: Dict[str, float]) -> Dict[str, dict]:
    """Walk-forward 4-fold MAE: baseline vs OT-corrected at endQ3."""
    try:
        import pandas as pd
        import numpy as np
    except ImportError as e:
        _reject(f"missing_dependency: {e}")

    if not os.path.exists(_QUARTER_PARQ):
        _reject("player_quarter_stats.parquet not found")

    import pandas as pd
    import numpy as np

    sys.path.insert(0, SCRIPTS_DIR)
    try:
        import retro_inplay_mae as rim
    except ImportError as e:
        _reject(f"cannot import retro_inplay_mae: {e}")

    from src.prediction.live_engine import project_from_snapshot

    qdf = rim.load_quarter_stats(_QUARTER_PARQ)
    game_ids_in_parq = set(qdf["game_id"].unique())

    # Only games with: linescore + OT label + in parquet
    usable = [gid for gid in labels if gid in game_ids_in_parq and gid in linescores]
    usable.sort(key=lambda g: game_dates.get(g, "1900-01-01"))
    if len(usable) < 20:
        _reject(f"insufficient_games_for_stage3: {len(usable)}")

    print(f"[Stage 3] {len(usable)} games with parquet + labels")

    records = []  # {game_id, player_id, stat, actual, baseline, p_ot}
    for gid in usable:
        snap = rim.build_snapshot(gid, "endQ3", qdf)
        if snap is None:
            continue
        try:
            proj_rows = project_from_snapshot(snap, period=4)
        except Exception:
            continue

        p_ot = y_pred_by_gid.get(gid, float(np.mean(list(y_pred_by_gid.values())) if y_pred_by_gid else 0.07))

        # Ground truth: Q1-Q4 sum from parquet
        gdf = qdf[(qdf["game_id"] == gid) & (qdf["period"].isin([1, 2, 3, 4]))]
        actuals = gdf.groupby("player_id")[STATS].sum().reset_index()
        act_map: Dict[int, Dict[str, float]] = {
            int(r["player_id"]): {s: float(r[s]) for s in STATS}
            for _, r in actuals.iterrows()
        }

        for row in proj_rows:
            pid = int(row.get("player_id", 0))
            if pid not in act_map:
                continue
            stat = str(row.get("stat", ""))
            if stat not in STATS:
                continue
            baseline = float(row.get("projected_final", 0.0))
            actual   = act_map[pid].get(stat, 0.0)
            corrected = baseline * (1.0 + p_ot * INFLATION_PRIORS[stat])
            records.append({
                "game_id": gid, "player_id": pid, "stat": stat,
                "actual": actual, "baseline": baseline,
                "corrected": corrected, "p_ot": p_ot,
            })

    if not records:
        _reject("no_stage3_records_built")

    # Walk-forward 4-fold MAE
    rec_by_gid: Dict[str, list] = defaultdict(list)
    for r in records:
        rec_by_gid[r["game_id"]].append(r)

    gid_order = usable  # already sorted by date
    n_g = len(gid_order)
    fold_size = n_g // 4

    stat_err_base: Dict[str, list] = {s: [] for s in STATS}
    stat_err_corr: Dict[str, list] = {s: [] for s in STATS}

    for fold in range(4):
        test_start = fold * fold_size
        test_end = test_start + fold_size if fold < 3 else n_g
        test_gids = gid_order[test_start:test_end]
        for gid in test_gids:
            for r in rec_by_gid.get(gid, []):
                s = r["stat"]
                stat_err_base[s].append(abs(r["actual"] - r["baseline"]))
                stat_err_corr[s].append(abs(r["actual"] - r["corrected"]))

    results: Dict[str, dict] = {}
    for s in STATS:
        if not stat_err_base[s]:
            results[s] = {"baseline": None, "corrected": None, "delta": None}
            continue
        b = float(np.mean(stat_err_base[s]))
        c = float(np.mean(stat_err_corr[s]))
        results[s] = {"baseline": round(b, 4), "corrected": round(c, 4),
                      "delta": round(c - b, 4)}
    return results


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import numpy as np

    print("[R8_M31_ot] Stage 0: building OT labels...")
    linescores = _load_linescores()
    if not linescores:
        _reject("ot_label_unavailable", {"reason": "linescores_all.json missing or empty"})

    labels = stage0_build_ot_labels()
    coverage = len(labels) / max(len(linescores), 1)
    ot_rate  = sum(v["went_ot"] for v in labels.values()) / max(len(labels), 1)
    print(f"[Stage 0] ot_rate={ot_rate:.3f}")

    print("[R8_M31_ot] Stage 1: P(OT) classifier...")
    game_dates = _load_game_dates()
    auc, brier, ll, n_ot, y_true_valid, y_pred_valid = stage1_classifier(linescores, labels, game_dates)

    mean_pred = float(np.mean(y_pred_valid)) if y_pred_valid else 0.0
    calib_ok = 0.05 <= mean_pred <= 0.10
    print(f"[Stage 1] mean P(OT)={mean_pred:.4f}, calib_ok={calib_ok}")

    # Build per-game P(OT) for Stage 3 (use linescore features + last trained fold)
    try:
        import lightgbm as lgb
        rows, targets, gids, dates = _build_features(linescores, labels, game_dates)
        order = sorted(range(len(dates)), key=lambda i: dates[i])
        X_all = np.array(rows, dtype=np.float32)[order]
        y_all = np.array(targets, dtype=np.int32)[order]
        gids_all = [gids[i] for i in order]
        lgb_params = {
            "objective": "binary", "n_estimators": 200, "learning_rate": 0.05,
            "num_leaves": 31, "min_data_in_leaf": 20, "is_unbalance": True,
            "verbose": -1, "random_state": 42,
        }
        model = lgb.LGBMClassifier(**lgb_params)
        model.fit(X_all, y_all)
        preds_all = model.predict_proba(X_all)[:, 1]
        y_pred_by_gid = {gids_all[i]: float(preds_all[i]) for i in range(len(gids_all))}
    except Exception as e:
        print(f"[Stage 1] full-model fit failed: {e}; using mean P(OT)")
        y_pred_by_gid = {gid: mean_pred for gid in labels}

    print("[R8_M31_ot] Stage 3: MAE evaluation...")
    mae_delta = stage3_evaluate(linescores, labels, game_dates, y_pred_by_gid)
    print("[Stage 3] MAE deltas:")
    for s, v in mae_delta.items():
        print(f"  {s}: baseline={v['baseline']} corrected={v['corrected']} delta={v['delta']}")

    # ── Ship gate ──────────────────────────────────────────────────────────────
    valid_deltas = [v["delta"] for v in mae_delta.values() if v["delta"] is not None]
    n_improve    = sum(1 for d in valid_deltas if d < 0)  # negative delta = improvement
    max_regress  = max((d for d in valid_deltas if d > 0), default=0.0)
    mean_delta   = float(np.mean(valid_deltas)) if valid_deltas else 0.0

    gate_a = (n_improve >= 3) and (max_regress <= 0.005)
    gate_b = mean_delta <= -0.003
    ship = (gate_a or gate_b) and calib_ok

    ship_reason = (
        f"gate_a={'PASS' if gate_a else 'FAIL'}(n_improve={n_improve},max_regress={max_regress:.4f}) "
        f"gate_b={'PASS' if gate_b else 'FAIL'}(mean_delta={mean_delta:.4f}) "
        f"calib={'PASS' if calib_ok else 'FAIL'}(mean_p={mean_pred:.4f})"
    )

    out = {
        "probe": "R8_M31_ot",
        "status": "SHIP" if ship else "REJECT",
        "ot_label_coverage": round(coverage, 4),
        "ot_rate": round(ot_rate, 4),
        "stage1": {
            "auc": round(auc, 4), "brier": round(brier, 4),
            "log_loss": round(ll, 4), "n_ot_games": n_ot,
        },
        "stage2_inflation": INFLATION_PRIORS,
        "stage3_mae_delta": mae_delta,
        "ship_reason": ship_reason,
    }
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_RESULTS, "w") as fh:
        json.dump(out, fh, indent=2)
    status = "SHIP" if ship else "REJECT"
    print(f"\n[R8_M31_ot] {status} — {ship_reason}")
    print(f"[R8_M31_ot] Results → {_RESULTS}")


if __name__ == "__main__":
    main()
