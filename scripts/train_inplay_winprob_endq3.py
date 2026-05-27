"""
train_inplay_winprob_endq3.py — production trainer for R10_M5 in-play winprob.

Trains LightGBM binary classifiers on FULL data (not walk-forward) for
endQ1, endQ2, endQ3 snapshots and persists native LightGBM Booster files
under data/models/inplay_winprob_<snap>.lgb.

Feature spec mirrors scripts/probe_R10_M5_inplay_winprob.py exactly so the
walk-forward Brier/AUC numbers from the probe carry over. When the probe's
upstream artifact `data/nba/linescores_all.json` is missing, this trainer
rebuilds it on the fly from the per-quarter boxscore cache at
``data/cache/quarter_box/``.

Usage:
    python scripts/train_inplay_winprob_endq3.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
QUARTER_BOX_DIR = os.path.join(DATA_CACHE, "quarter_box")
LINESCORES_PATH = os.path.join(NBA_CACHE, "linescores_all.json")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
os.makedirs(MODEL_DIR, exist_ok=True)


# ── linescores builder (filesystem fallback) ──────────────────────────────────

def _build_linescores_from_quarter_box() -> Dict[str, Dict]:
    """Rebuild linescores_all.json schema from data/cache/quarter_box/ shards.

    Each shard is data/cache/quarter_box/<gid>_q<n>.json and contains a
    ``teams`` list with per-team ``pts`` (NBA boxscoreplayertrackv3-equivalent).
    The schema produced here matches what probe_R10_M5_inplay_winprob.py
    expects: ``home_q1..q4``, ``away_q1..q4``, ``home_team_id``.

    Returns the dict keyed by game_id. Persists to disk if non-empty.
    """
    if os.path.exists(LINESCORES_PATH):
        with open(LINESCORES_PATH) as f:
            data = json.load(f)
        if data:
            print(f"  loaded cached linescores ({len(data)} games)", flush=True)
            return data

    print("  cache miss — rebuilding linescores from quarter_box ...", flush=True)
    gids: Dict[str, Dict[int, Dict]] = {}
    for path in glob.glob(os.path.join(QUARTER_BOX_DIR, "*_q*.json")):
        base = os.path.basename(path)
        try:
            gid, q_tag = base.rsplit("_q", 1)
            q = int(q_tag.replace(".json", ""))
        except (ValueError, IndexError):
            continue
        if q not in (1, 2, 3, 4):
            continue
        try:
            with open(path) as f:
                shard = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        teams = shard.get("teams") or []
        if len(teams) != 2:
            continue
        gids.setdefault(gid, {})[q] = {
            "teams": teams,
            "home_team_id": shard.get("home_team_id"),
        }

    # season_games tells us which team is home; we cross-reference.
    season_games_full = _load_season_games_full()

    linescores: Dict[str, Dict] = {}
    for gid, qmap in gids.items():
        if set(qmap.keys()) < {1, 2, 3, 4}:
            continue
        sg = season_games_full.get(gid)
        if sg is None:
            continue
        home_abbrev = sg.get("home_team")
        if not home_abbrev:
            continue
        row: Dict = {"home_team_id": None}
        ok = True
        for q in (1, 2, 3, 4):
            teams = qmap[q]["teams"]
            home_t = next((t for t in teams
                           if t.get("team_abbreviation") == home_abbrev), None)
            away_t = next((t for t in teams
                           if t.get("team_abbreviation") != home_abbrev), None)
            if home_t is None or away_t is None:
                ok = False
                break
            row[f"home_q{q}"] = home_t.get("pts")
            row[f"away_q{q}"] = away_t.get("pts")
            if row["home_team_id"] is None:
                row["home_team_id"] = home_t.get("team_id")
        if not ok:
            continue
        if any(row.get(f"home_q{q}") is None or row.get(f"away_q{q}") is None
               for q in (1, 2, 3, 4)):
            continue
        linescores[gid] = row

    if linescores:
        os.makedirs(NBA_CACHE, exist_ok=True)
        with open(LINESCORES_PATH, "w") as f:
            json.dump(linescores, f)
        print(f"  built linescores from {len(linescores)} games "
              f"-> {LINESCORES_PATH}", flush=True)
    return linescores


def _load_season_games_full() -> Dict[str, Dict]:
    """Load 2022-23, 2023-24, 2024-25 season_games into gid -> row dict."""
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


# ── pregame WP fallback ───────────────────────────────────────────────────────

def _pregame_wp_from_features(row: Dict) -> float:
    """Closed-form pregame WP proxy from elo + home advantage.

    Used when ``sim_win_prob`` is absent from season_games_*.json (the
    common case on the current RunPod box). Mirrors the standard Elo
    logistic: P(home) = 1 / (1 + 10^((away_elo - home_elo - HCA) / 400)).
    Falls back to 0.55 (league-average home edge) if Elo is missing.
    """
    hca = 65.0  # home-court advantage in Elo points (~3pt spread)
    home_elo = row.get("home_elo")
    away_elo = row.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


# ── quarter features loader ───────────────────────────────────────────────────

QUARTER_FEATURES_PATH = os.path.join(DATA_CACHE, "quarter_features.parquet")


def _load_quarter_features_team_summary() -> Dict:
    """Load quarter_features parquet and aggregate to team-level summaries per game.

    Returns dict keyed by "{game_id}_{team_id}" -> {q1_usg_avg, halftime_pace_shift,
    trailing_team_q4_usg_hhi}.
    """
    import math
    if not os.path.exists(QUARTER_FEATURES_PATH):
        print(f"  [WARN] {QUARTER_FEATURES_PATH} missing — endQ3 quarter features will be NaN",
              flush=True)
        return {}
    df = pd.read_parquet(QUARTER_FEATURES_PATH)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")

    summaries: Dict = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        ttq4 = grp["trailing_team_q4_usg_concentration"]
        summaries[f"{gid}_{int(tid)}"] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(ttq4.mean())
            if ttq4.notna().any() else float("nan"),
        }
    print(f"  quarter_features team summaries: {len(summaries)} entries", flush=True)
    return summaries


# ── feature builder (matches probe spec exactly) ──────────────────────────────

MINUTES_PER_QUARTER = 12.0


def build_rows(linescores: Dict, season_games: Dict,
               quarter_summaries: Optional[Dict] = None) -> pd.DataFrame:
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

        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = _pregame_wp_from_features(sg)

        # Quarter features lookup (NaN if not in parquet)
        qs = quarter_summaries or {}
        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qs.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

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
                # quarter features (NaN for games not in quarter_features parquet)
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    return df


# ── trainer ───────────────────────────────────────────────────────────────────

SNAP_FEATURES: Dict[str, List[str]] = {
    "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id", "season",
              "q1_usg_avg", "halftime_pace_shift", "trailing_team_q4_usg_hhi"],
}

CAT_COLS = ["home_team_id", "season"]


def train_snapshot(df: pd.DataFrame, snapshot: str) -> Dict:
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, brier_score_loss, log_loss, roc_auc_score,
    )

    sub = df[df["snapshot"] == snapshot].copy()
    feat_cols = SNAP_FEATURES[snapshot]
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].astype(int).copy()

    for c in CAT_COLS:
        if c in X.columns:
            X[c] = X[c].astype("category")

    print(f"\n[train] {snapshot}: n_rows={len(X)}, "
          f"home_win_rate={y.mean():.3f}", flush=True)

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
    cat_in_X = [c for c in CAT_COLS if c in X.columns]
    model.fit(X, y, categorical_feature=cat_in_X if cat_in_X else "auto")

    probs = model.predict_proba(X)[:, 1]
    preds = (probs >= 0.5).astype(int)
    in_sample = {
        "auc": float(roc_auc_score(y, probs)),
        "brier": float(brier_score_loss(y, probs)),
        "log_loss": float(log_loss(y, probs)),
        "accuracy": float(accuracy_score(y, preds)),
    }
    print(f"  in-sample AUC={in_sample['auc']:.4f} "
          f"Brier={in_sample['brier']:.4f} "
          f"Acc={in_sample['accuracy']:.4f}", flush=True)

    out_path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}.lgb")
    model.booster_.save_model(out_path)
    print(f"  saved booster -> {out_path} "
          f"({os.path.getsize(out_path)} bytes)", flush=True)

    meta_path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")
    meta = {
        "snapshot": snapshot,
        "feature_cols": feat_cols,
        "categorical_cols": cat_in_X,
        "n_train_rows": int(len(X)),
        "home_win_rate": float(y.mean()),
        "in_sample": in_sample,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe": "R10_M5_inplay_winprob",
        "hyperparams": {
            "n_estimators": 300, "learning_rate": 0.05, "num_leaves": 31,
            "min_child_samples": 20, "subsample": 0.8, "colsample_bytree": 0.8,
            "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
        },
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def main() -> None:
    t0 = time.time()
    print("=== Train R10_M5 in-play winprob (production) ===", flush=True)

    print("[1] Loading linescores + season_games ...", flush=True)
    linescores = _build_linescores_from_quarter_box()
    season_games = _load_season_games_full()
    print(f"  linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)
    if not linescores:
        raise RuntimeError(
            "No linescores available — populate data/cache/quarter_box/ or "
            "ship data/nba/linescores_all.json before training."
        )

    print("[2] Loading quarter features ...", flush=True)
    quarter_summaries = _load_quarter_features_team_summary()

    print("[3] Building snapshot rows ...", flush=True)
    df = build_rows(linescores, season_games, quarter_summaries)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    print(f"  rows={len(df)}, games={len(valid_games)}", flush=True)

    all_meta = {}
    for snap in ["endQ1", "endQ2", "endQ3"]:
        all_meta[snap] = train_snapshot(df, snap)

    elapsed = time.time() - t0
    print(f"\nTotal elapsed: {elapsed:.1f}s", flush=True)
    print("Artifacts:", flush=True)
    for snap in all_meta:
        p = os.path.join(MODEL_DIR, f"inplay_winprob_{snap.lower()}.lgb")
        print(f"  {snap}: {p} ({os.path.getsize(p)} bytes)", flush=True)


if __name__ == "__main__":
    main()
