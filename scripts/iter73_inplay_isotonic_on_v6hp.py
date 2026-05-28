"""
Iter 73: Inplay Isotonic Calibration Overlay — RETRY on v6_hp baseline.

RETRY of Iter 62. Iter 62 fit isotonic against v1 raw predictions (production
.lgb at lr=0.05, num_leaves=31). Iter 68 then shipped v6_hp (lr=0.03,
num_leaves=15, plus the endQ3 quarter-feature additions) — a meaningfully
different prediction distribution. The Iter 62 isotonic joblibs at
data/models/inplay_isotonic_endq{1,2,3}.joblib are therefore MISCALIBRATED
against v6_hp. Refit isotonic on v6_hp OOS predictions and re-evaluate.

This script ONLY changes the base model — everything else (data construction,
WF splits, isotonic fitting protocol, ship gate logic) mirrors Iter 62.

Ship gate per snapshot:
  - >=3/4 folds improved
  - mean Brier delta <= -0.002 vs v6_hp single-model baseline

Baselines per snapshot (from v6_hp _meta.json wf_eval.mean_brier):
  endQ1 0.2120, endQ2 0.1771, endQ3 0.1250

DO NOT TOUCH:
  - data/models/inplay_winprob_endq{1,2,3}_v6_hp.lgb / _meta.json (READ-ONLY)
  - data/models/inplay_isotonic_endq{1,2,3}.joblib (Iter 62 — distinct
    filenames; we WRITE v6hp variants only)
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "iter73_inplay_isotonic_v6hp_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42

# v6_hp ship gate (per spec). Use v6_hp WF mean Brier from its _meta.json.
V6_HP_BASELINE: Dict[str, float] = {
    "endQ1": 0.2120,
    "endQ2": 0.1771,
    "endQ3": 0.1250,
}
SHIP_MIN_FOLDS_IMPROVED = 3
SHIP_MEAN_DELTA_MAX = -0.002


# ── data loaders (mirror iter68_inplay_hp_sweep.py exactly) ───────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    """Load v6_hp meta (NOT prod meta) — that's our base model spec."""
    path = os.path.join(
        MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_v6_hp_meta.json"
    )
    with open(path) as f:
        return json.load(f)


def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("rows", []):
            rows[r["game_id"]] = r
    return rows


def load_quarter_features_summaries() -> Dict[str, Dict[str, float]]:
    """Per (game_id, team_id) team-level aggregates from quarter_features.parquet.

    Mirrors iter68_inplay_hp_sweep.load_quarter_features_summaries.
    """
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print(f"  [WARN] {path} missing — endQ3 quarter features will be NaN",
              flush=True)
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    summaries: Dict[str, Dict[str, float]] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        key = f"{gid}_{int(tid)}"
        ttq4 = grp["trailing_team_q4_usg_concentration"]
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(ttq4.mean())
            if ttq4.notna().any() else float("nan"),
        }
    print(f"  quarter_features summaries: {len(summaries)} entries", flush=True)
    return summaries


def _pregame_wp_from_sg(sg: Dict) -> float:
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
    qf_summaries: Dict[str, Dict[str, float]],
) -> pd.DataFrame:
    """Mirrors iter68_inplay_hp_sweep.build_rows exactly."""
    records: List[Dict] = []
    required = ["home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4"]

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue
        if any(ls.get(k) is None for k in required):
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

        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

        for snap_idx, snapshot in enumerate(SNAPSHOTS):
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
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    # endQ3 filter ripple — same game set across all snapshots
    valid = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid)].copy()
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    return df


# ── WF split (matches iter62 / iter68) ────────────────────────────────────────

def wf_splits(n: int, n_folds: int = N_FOLDS) -> List[Tuple[int, int, int]]:
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds
    splits = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n
        splits.append((train_end, test_start, test_end))
    return splits


# ── reliability (10-bin) ──────────────────────────────────────────────────────

def reliability(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> List[Dict]:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        mean_pred = float(p[mask].mean()) if n > 0 else None
        actual_rate = float(y[mask].mean()) if n > 0 else None
        gap = (actual_rate - mean_pred) if (mean_pred is not None and actual_rate is not None) else None
        out.append({
            "bin": i, "lo": float(lo), "hi": float(hi), "n": n,
            "mean_pred": mean_pred, "actual_rate": actual_rate,
            "gap": gap,
        })
    return out


# ── per-snapshot evaluation ───────────────────────────────────────────────────

def evaluate_snapshot(snapshot: str, df: pd.DataFrame) -> Dict[str, Any]:
    print(f"\n=== Snapshot: {snapshot} ===", flush=True)
    meta = load_meta(snapshot)

    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    hp = dict(meta.get("hyperparams", {}))
    print(f"  v6_hp features ({len(feature_cols)}): {feature_cols}", flush=True)
    print(f"  v6_hp hyperparams: {hp}", flush=True)
    print(f"  v6_hp WF baseline mean Brier: {V6_HP_BASELINE[snapshot]:.4f}",
          flush=True)

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    X = sub[feature_cols].copy()
    y = sub["home_team_won"].astype(int)
    active_cats = [c for c in cat_cols if c in X.columns]
    for c in active_cats:
        X[c] = X[c].astype("category")

    n = len(X)
    print(f"  Rows: {n}, home_win_rate: {y.mean():.4f}", flush=True)

    splits = wf_splits(n)
    print(f"  WF splits: {[(s[0], s[1], s[2]) for s in splits]}", flush=True)

    fold_records: List[Dict[str, Any]] = []
    all_raw_preds: List[np.ndarray] = []
    all_labels: List[np.ndarray] = []

    for fold, (train_end, test_start, test_end) in enumerate(splits):
        if train_end < 30 or test_start >= n:
            print(f"  Fold {fold}: skip (insufficient data)", flush=True)
            continue
        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]
        if len(X_te) < 10:
            print(f"  Fold {fold}: skip (test={len(X_te)})", flush=True)
            continue

        # Train v6_hp from scratch on fold-train using v6_hp HPs (not prod HPs)
        model = lgb.LGBMClassifier(
            n_estimators=int(hp.get("n_estimators", 300)),
            learning_rate=float(hp["learning_rate"]),
            num_leaves=int(hp["num_leaves"]),
            min_child_samples=int(hp["min_child_samples"]),
            subsample=float(hp.get("subsample", 0.8)),
            colsample_bytree=float(hp.get("colsample_bytree", 0.8)),
            reg_alpha=float(hp.get("reg_alpha", 0.1)),
            reg_lambda=float(hp.get("reg_lambda", 1.0)),
            random_state=SEED,
            n_jobs=4,
            verbose=-1,
        )
        model.fit(
            X_tr, y_tr,
            categorical_feature=active_cats if active_cats else "auto",
        )
        raw_te = model.predict_proba(X_te)[:, 1]
        y_te_arr = y_te.values

        brier_raw = float(brier_score_loss(y_te_arr, raw_te))
        ll_raw = float(log_loss(y_te_arr, np.clip(raw_te, 1e-7, 1 - 1e-7)))

        # Cross-fold isotonic: fit on accumulated prior-folds' OOS preds
        if all_raw_preds:
            cal_train_p = np.concatenate(all_raw_preds)
            cal_train_y = np.concatenate(all_labels)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(cal_train_p, cal_train_y)
            cal_te = iso.transform(raw_te)
            cal_te = np.clip(cal_te, 1e-7, 1 - 1e-7)
            brier_cal = float(brier_score_loss(y_te_arr, cal_te))
            ll_cal = float(log_loss(y_te_arr, cal_te))
            cal_applied = True
            cal_train_n = int(len(cal_train_p))
        else:
            brier_cal = brier_raw
            ll_cal = ll_raw
            cal_te = raw_te.copy()
            cal_applied = False
            cal_train_n = 0

        delta = brier_cal - brier_raw
        improved = bool(delta < 0)
        rec = {
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "cal_applied": cal_applied,
            "cal_train_n": cal_train_n,
            "brier_raw": brier_raw,
            "brier_isotonic": brier_cal,
            "brier_delta": delta,
            "log_loss_raw": ll_raw,
            "log_loss_isotonic": ll_cal,
            "improved": improved,
            "reliability_raw": reliability(raw_te, y_te_arr),
            "reliability_isotonic": reliability(cal_te, y_te_arr),
        }
        fold_records.append(rec)
        print(f"  Fold {fold}: raw={brier_raw:.4f}, iso={brier_cal:.4f}, "
              f"delta={delta:+.4f}, cal_applied={cal_applied}, n_te={len(X_te)}",
              flush=True)

        all_raw_preds.append(raw_te)
        all_labels.append(y_te_arr)

    # Final isotonic — fit on ALL OOS predictions across folds (production overlay)
    final_p = np.concatenate(all_raw_preds) if all_raw_preds else np.array([])
    final_y = np.concatenate(all_labels) if all_labels else np.array([])
    final_iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(final_p) > 0:
        final_iso.fit(final_p, final_y)
    out_path = os.path.join(
        MODEL_DIR, f"inplay_isotonic_v6hp_{snapshot.lower()}.joblib"
    )
    # Only DUMP if snapshot ships — main() decides; here we always write
    # the artifact dict in memory but actual joblib.dump happens in main() so
    # we can gate by ship decision. Return the (path, payload) tuple.
    final_payload = {
        "isotonic": final_iso,
        "snapshot": snapshot,
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_oos_train": int(len(final_p)),
        "iter": "73",
        "base_model": f"inplay_winprob_{snapshot.lower()}_v6_hp.lgb",
        "v6_hp_hyperparams": hp,
        "note": "Per-snapshot isotonic overlay fit on accumulated WF OOS preds "
                "from v6_hp base model (Iter 68 HPs). RETRY of Iter 62 against "
                "the v6_hp baseline.",
    }

    # ── fold aggregates ──────────────────────────────────────────────────────
    cal_folds = [r for r in fold_records if r["cal_applied"]]
    mean_brier_raw_all = float(np.mean([r["brier_raw"] for r in fold_records])) if fold_records else None
    mean_brier_iso_all = float(np.mean([r["brier_isotonic"] for r in fold_records])) if fold_records else None
    mean_brier_raw_cal = float(np.mean([r["brier_raw"] for r in cal_folds])) if cal_folds else None
    mean_brier_iso_cal = float(np.mean([r["brier_isotonic"] for r in cal_folds])) if cal_folds else None
    n_improved_cal = int(sum(r["improved"] for r in cal_folds))
    n_cal = len(cal_folds)

    # Per-fold ship gate uses ALL FOLDS (cal+uncal) — fold 0 cannot improve so
    # it counts as a non-improvement. We need >=3/4 to ship.
    n_improved_all = int(sum(r["improved"] for r in fold_records))

    return {
        "snapshot": snapshot,
        "n_rows": int(n),
        "feature_cols": feature_cols,
        "categorical_cols": active_cats,
        "v6_hp_hyperparams": hp,
        "v6_hp_baseline_brier": V6_HP_BASELINE[snapshot],
        "n_folds_total": len(fold_records),
        "n_folds_cal_applied": n_cal,
        "n_folds_improved_cal": n_improved_cal,
        "n_folds_improved_all": n_improved_all,
        "mean_brier_raw_all_folds": mean_brier_raw_all,
        "mean_brier_iso_all_folds": mean_brier_iso_all,
        "mean_brier_delta_all_folds": (mean_brier_iso_all - mean_brier_raw_all)
            if (mean_brier_iso_all is not None and mean_brier_raw_all is not None) else None,
        "mean_brier_raw_cal_folds": mean_brier_raw_cal,
        "mean_brier_iso_cal_folds": mean_brier_iso_cal,
        "mean_brier_delta_cal_folds": (mean_brier_iso_cal - mean_brier_raw_cal)
            if (mean_brier_iso_cal is not None and mean_brier_raw_cal is not None) else None,
        "isotonic_overlay_path": out_path,
        "isotonic_payload": final_payload,
        "final_oos_n": int(len(final_p)),
        "fold_records": fold_records,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 73: Inplay Isotonic Overlay (on v6_hp baseline) ===",
          flush=True)
    print(f"  random_seed={SEED}", flush=True)
    print(f"  ship gate: >=3/4 folds improved AND mean delta <= -0.002 vs v6_hp",
          flush=True)

    print("\n[1] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"  linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[2] Building snapshot rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries)
    n_games = df["game_id"].nunique()
    print(f"  total rows: {len(df)} across {n_games} games", flush=True)

    print("\n[3] Per-snapshot evaluation ...", flush=True)
    snapshots_out: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        snapshots_out[snap] = evaluate_snapshot(snap, df)

    print("\n[4] Ship-gate evaluation ...", flush=True)
    ship_summary: Dict[str, Any] = {}
    saved_artifacts: Dict[str, Any] = {}
    for snap, res in snapshots_out.items():
        baseline = V6_HP_BASELINE[snap]
        # Compare to v6_hp WF baseline (per spec), NOT to fold-zero raw.
        # Mean delta vs v6_hp = mean(iso) - v6_hp_baseline_brier
        mean_iso = res["mean_brier_iso_all_folds"]
        delta_vs_v6hp = (mean_iso - baseline) if mean_iso is not None else None

        # Folds_improved: per spec "≥3/4 folds improved" — comparing iso fold
        # Brier vs the v6_hp WF baseline scalar. (Iter 62 used iso vs raw
        # per-fold; spec for Iter 73 says "vs v6_hp single-model baseline".)
        fold_improved_vs_v6hp = [
            r["brier_isotonic"] < baseline for r in res["fold_records"]
        ]
        n_imp_v6hp = int(sum(fold_improved_vs_v6hp))
        n_folds_total = len(res["fold_records"])

        folds_gate = n_imp_v6hp >= SHIP_MIN_FOLDS_IMPROVED
        delta_gate = (delta_vs_v6hp is not None
                      and delta_vs_v6hp <= SHIP_MEAN_DELTA_MAX)
        ship = folds_gate and delta_gate

        ship_summary[snap] = {
            "v6_hp_baseline_brier": baseline,
            "iso_mean_brier_all_folds": mean_iso,
            "mean_brier_delta_vs_v6hp": delta_vs_v6hp,
            "fold_improved_vs_v6hp": fold_improved_vs_v6hp,
            "n_folds_improved_vs_v6hp": n_imp_v6hp,
            "n_folds_total": n_folds_total,
            "folds_gate_passed": folds_gate,
            "delta_gate_passed": delta_gate,
            "ship": ship,
        }
        print(
            f"  {snap}: v6_hp_baseline={baseline:.4f} iso_mean={mean_iso:.4f} "
            f"delta={delta_vs_v6hp:+.4f} improved={n_imp_v6hp}/{n_folds_total} "
            f"ship={ship}", flush=True,
        )

        # SAVE only if shipping
        if ship:
            payload = res["isotonic_payload"]
            out_path = res["isotonic_overlay_path"]
            joblib.dump(payload, out_path)
            size_bytes = os.path.getsize(out_path)
            saved_artifacts[snap] = {
                "isotonic_overlay_path": out_path,
                "size_bytes": int(size_bytes),
            }
            print(f"    saved {out_path} ({size_bytes} bytes)", flush=True)
        else:
            # Confirm no joblib written — leave Iter 62's intact
            saved_artifacts[snap] = {"skipped_no_ship": True}

    # ── final summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 70, flush=True)
    print("ITER 73 — FINAL SUMMARY (isotonic overlay on v6_hp baseline)",
          flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'v6_hp':<9} {'iso_mean':<10} {'Delta':<10} "
          f"{'Folds':<7} {'Ship':<5}", flush=True)
    for snap in SNAPSHOTS:
        s = ship_summary[snap]
        print(
            f"  {snap:<7} {s['v6_hp_baseline_brier']:<9.4f} "
            f"{s['iso_mean_brier_all_folds']:<10.4f} "
            f"{s['mean_brier_delta_vs_v6hp']:<+10.4f} "
            f"{s['n_folds_improved_vs_v6hp']}/{s['n_folds_total']:<5} "
            f"{'YES' if s['ship'] else 'no':<5}", flush=True,
        )

    # Strip isotonic_payload from the JSON-dumped result (not serializable cleanly)
    snapshots_out_serializable: Dict[str, Any] = {}
    for k, v in snapshots_out.items():
        v2 = dict(v)
        v2.pop("isotonic_payload", None)
        snapshots_out_serializable[k] = v2

    result = {
        "iter": "73",
        "name": "inplay_isotonic_overlay_on_v6hp",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_models": (
            "data/models/inplay_winprob_endq{1,2,3}_v6_hp.lgb (READ-ONLY)"
        ),
        "iter62_isotonic_unchanged": (
            "data/models/inplay_isotonic_endq{1,2,3}.joblib (NOT MODIFIED)"
        ),
        "n_folds": N_FOLDS,
        "random_seed": SEED,
        "n_games_total": int(n_games),
        "v6_hp_baselines": V6_HP_BASELINE,
        "ship_gate": {
            "min_folds_improved_vs_v6hp": SHIP_MIN_FOLDS_IMPROVED,
            "max_mean_delta_vs_v6hp": SHIP_MEAN_DELTA_MAX,
        },
        "snapshots": snapshots_out_serializable,
        "ship_summary": ship_summary,
        "saved_artifacts": saved_artifacts,
        "elapsed_s": float(time.time() - t0),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[5] Results written to {OUT_JSON}", flush=True)
    print(f"  elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
