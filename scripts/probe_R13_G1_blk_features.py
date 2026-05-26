"""probe_R13_G1_blk_features.py -- R13_G1 BLK-specific feature engineering.

WHY: BLK is the strongest signal in the loop -- M16 streak hit -34% MAE on
fold-1; F3 cross-stat hit -54% mean on the 0.527 pregame base; F4 PrizePicks
shows BLK is overpriced by z=5.7 (would be profitable bet at scale). Go deeper
on what makes BLK predictable by adding BLK-specific features on TOP of the
F3 cross-stat head (R12_F3 already shipped).

APPROACH (mirrors probe_R12_F3_cross_stat_covariance.py):
  Pregame OOF parquet -> per (player_id, game_id) row, build:

    BASELINE features (already shipped in F3):
      xstat_z_<stat>     -- L5 cross-stat residual z, target's own EXCLUDED
      n_prior_xstat      -- coverage counter

    NEW BLK-specific features (this probe):
      OPP TEAM DEFENSIVE CONTEXT (Hypothesis 1 proxy):
        opp_efg_l5         -- opp team's L5 rolling efg_pct (low = bricks)
        opp_pace_l5        -- opp team's L5 rolling pace (more possessions)
        opp_oreb_pct_l5    -- opp team's L5 rolling oreb_pct
        opp_ts_pct_l5      -- opp team's L5 rolling ts_pct
      Mapping: (player_id, game_id) -> matchup via gamelog_full_<pid>_*.json
              -> opp tricode -> team_advanced_stats lookup -> L5 shift(1).

      PLAYER DEFENSIVE FORM (Hypothesis 4 spirit):
        own_def_rtg_l5     -- player's L5 shift(1) defensiverating mean
        own_dreb_pct_l5    -- player's L5 shift(1) defensivereboundpercentage
        own_reb_pct_l5     -- player's L5 shift(1) reboundpercentage
        own_pie_l5         -- player's L5 shift(1) PIE (player impact)
        own_min_l5         -- player's L5 shift(1) minutes
      Source: data/player_adv_stats.parquet (71% OOF coverage with >=5 prior).

      POSITION/HEIGHT (Hypothesis 2 covariate, 100% coverage):
        is_center          -- 1 if position contains "Center"
        height_inches      -- raw player height
      Source: data/player_positions.parquet.

  Train residual head with ALL features (xstat + BLK-specific).

SHIP GATE (BLK only):
  Per-fold mean_delta vs F3-only baseline <= -0.020 on 4/4 walk-forward folds.
  Compose ON TOP of F3 -- both heads use the same OOF, the new head INCLUDES
  the F3 xstat features so it cannot be net-negative if BLK signal is real.

LEAKAGE INVARIANTS:
  - xstat_z_blk EXCLUDED from features (same rule as F3).
  - All L5 rolling features use strict shift(1) on (id, game_date) ordering.
  - team_advanced_stats lookup uses opp team's *prior* games strictly before
    the current game_date.
  - player_adv_stats L5 uses strict shift(1) on player's chronology.

Run:
    python -u scripts/probe_R13_G1_blk_features.py \\
        > scripts/_results/improve_R13_G1_run.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    import lightgbm as lgb
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"lightgbm import failed: {exc}")

# ── constants ────────────────────────────────────────────────────────────────

STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
TARGET_STAT = "blk"
_L5 = 5

_OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_ADV_PATH = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")
_TEAM_ADV_PATH = os.path.join(
    PROJECT_DIR, "data", "team_advanced_stats.parquet"
)
_POS_PATH = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
_CACHE_OUT = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R13_G1_blk_features_results.json"
)
_HEADS_OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

# Operative "production" BLK baseline after M16+F3 chain (per user spec).
BLK_PROD_BASELINE = 0.154

XSTAT_Z_NAMES: Tuple[str, ...] = tuple(f"xstat_z_{s}" for s in STATS)

BLK_NEW_FEATURES: Tuple[str, ...] = (
    "opp_efg_l5",
    "opp_pace_l5",
    "opp_oreb_pct_l5",
    "opp_ts_pct_l5",
    "own_def_rtg_l5",
    "own_dreb_pct_l5",
    "own_reb_pct_l5",
    "own_pie_l5",
    "own_min_l5",
    "is_center",
    "height_inches",
)


def _lgb_params() -> Dict:
    """Match F3 / M16 LGB_PARAMS for apples-to-apples comparison."""
    return {
        "n_estimators":      200,
        "learning_rate":     0.03,
        "num_leaves":        15,
        "min_child_samples": 80,
        "objective":         "regression_l1",
        "random_state":      42,
        "verbosity":         -1,
        "n_jobs":            -1,
    }


# ── F3 cross-stat z builder (copied for stand-alone reuse) ───────────────────


def compute_xstat_z_matrix(
    oof_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Compute (player_id, game_id) -> {xstat_z_<stat>, n_prior_xstat}.

    Same logic as probe_R12_F3_cross_stat_covariance.compute_xstat_z_matrix.
    """
    print("  pivoting OOF wide for xstat ...", flush=True)
    wide = oof_df.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values=["actual", "oof_pred"],
        aggfunc="first",
    ).reset_index()
    wide.columns = [f"{a}_{b}" if b else a for a, b in wide.columns]
    wide["game_date"] = pd.to_datetime(wide["game_date"])
    wide = wide.sort_values(
        ["player_id", "game_date", "game_id"]
    ).reset_index(drop=True)

    sigmas: Dict[str, float] = {}
    for s in STATS:
        col = f"actual_{s}"
        sigmas[s] = (
            max(float(wide[col].dropna().std()), 1e-6)
            if col in wide.columns
            else 1.0
        )

    for s in STATS:
        a, p = f"actual_{s}", f"oof_pred_{s}"
        if a in wide.columns and p in wide.columns:
            wide[f"z_{s}"] = (wide[a] - wide[p]) / sigmas[s]
        else:
            wide[f"z_{s}"] = np.nan

    for s in STATS:
        zcol = f"z_{s}"
        shifted = wide.groupby("player_id", sort=False)[zcol].shift(1)
        wide[f"xstat_z_{s}"] = (
            shifted.groupby(wide["player_id"], sort=False)
            .rolling(window=_L5, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    wide["_has_data"] = (
        wide[[f"z_{s}" for s in STATS]].notna().any(axis=1).astype(int)
    )
    wide["n_prior_xstat"] = (
        wide.groupby("player_id", sort=False)["_has_data"]
        .cumsum()
        .sub(wide["_has_data"])
        .astype(float)
    )

    keep = ["player_id", "game_id", "n_prior_xstat"] + list(XSTAT_Z_NAMES)
    out = wide[keep].copy()
    for col in XSTAT_Z_NAMES:
        out[col] = out[col].fillna(0.0)
    print(
        f"  built {len(out):,} (pid, gid) rows w/ xstat features",
        flush=True,
    )
    return out, sigmas


# ── matchup / opponent linkage from gamelog_full_*.json ──────────────────────


def build_matchup_index(nba_cache: str = _NBA_CACHE) -> pd.DataFrame:
    """Build a (player_id, game_id, own_team, opp_team) lookup table from
    data/nba/gamelog_full_*.json files.

    Returns DataFrame with columns: player_id, game_id, own_team, opp_team.
    """
    print(f"  scanning {nba_cache} for gamelog_full_*.json ...", flush=True)
    rows: List[Dict] = []
    n_files = 0
    for fname in os.listdir(nba_cache):
        if not fname.startswith("gamelog_full_") or not fname.endswith(".json"):
            continue
        n_files += 1
        try:
            with open(os.path.join(nba_cache, fname), encoding="utf-8") as fh:
                logs = json.load(fh)
        except Exception:
            continue
        if not isinstance(logs, list):
            continue
        for g in logs:
            try:
                pid = int(g.get("player_id"))
                gid = str(g.get("game_id"))
                m = str(g.get("matchup", ""))
            except (TypeError, ValueError):
                continue
            if not pid or not gid or not m:
                continue
            if " vs. " in m:
                parts = m.split(" vs. ", 1)
                home_marker = True
            elif " @ " in m:
                parts = m.split(" @ ", 1)
                home_marker = False
            else:
                continue
            if len(parts) != 2:
                continue
            own = parts[0].strip()
            opp = parts[1].strip()
            if len(own) > 4 or len(opp) > 4:
                continue
            rows.append({
                "player_id": pid,
                "game_id":   gid,
                "own_team":  own,
                "opp_team":  opp,
                "is_home":   1 if home_marker else 0,
            })
    print(
        f"  scanned {n_files} files, parsed {len(rows):,} (pid, gid, opp) rows",
        flush=True,
    )
    df = pd.DataFrame(rows).drop_duplicates(
        subset=["player_id", "game_id"], keep="first"
    )
    return df


# ── opponent team L5 rolling stats from team_advanced_stats ──────────────────


def build_team_l5_features(
    team_adv_path: str = _TEAM_ADV_PATH,
) -> pd.DataFrame:
    """For each (team_tricode, game_id, game_date), compute the team's L5
    shift(1) rolling mean of (efg_pct, pace, oreb_pct, ts_pct).

    These are the OPPONENT-team contextual features the BLK head will see.
    """
    print(f"  loading {team_adv_path} ...", flush=True)
    df = pd.read_parquet(team_adv_path)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(
        ["team_tricode", "game_date", "game_id"]
    ).reset_index(drop=True)

    cols_in = ("efg_pct", "pace", "oreb_pct", "ts_pct")
    cols_out = ("opp_efg_l5", "opp_pace_l5", "opp_oreb_pct_l5", "opp_ts_pct_l5")
    for cin, cout in zip(cols_in, cols_out):
        shifted = df.groupby("team_tricode", sort=False)[cin].shift(1)
        df[cout] = (
            shifted.groupby(df["team_tricode"], sort=False)
            .rolling(window=_L5, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    keep = ["team_tricode", "game_id"] + list(cols_out)
    print(
        f"  built team L5 rolling for {df['team_tricode'].nunique()} teams "
        f"({len(df):,} team-games)",
        flush=True,
    )
    return df[keep]


# ── player own-form L5 rolling from player_adv_stats ─────────────────────────


def build_player_adv_l5(adv_path: str = _ADV_PATH) -> pd.DataFrame:
    """For each (player_id, game_id), compute L5 shift(1) rolling means of
    defensiverating, defensivereboundpercentage, reboundpercentage, pie,
    minutes.
    """
    print(f"  loading {adv_path} ...", flush=True)
    df = pd.read_parquet(adv_path)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values(
        ["player_id", "game_date", "game_id"]
    ).reset_index(drop=True)

    cols_in = (
        "defensiverating",
        "defensivereboundpercentage",
        "reboundpercentage",
        "pie",
        "minutes",
    )
    cols_out = (
        "own_def_rtg_l5",
        "own_dreb_pct_l5",
        "own_reb_pct_l5",
        "own_pie_l5",
        "own_min_l5",
    )
    for cin, cout in zip(cols_in, cols_out):
        shifted = df.groupby("player_id", sort=False)[cin].shift(1)
        df[cout] = (
            shifted.groupby(df["player_id"], sort=False)
            .rolling(window=_L5, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    keep = ["player_id", "game_id"] + list(cols_out)
    print(
        f"  built player L5 adv features for "
        f"{df['player_id'].nunique()} players ({len(df):,} player-games)",
        flush=True,
    )
    return df[keep]


# ── position / height static lookup ──────────────────────────────────────────


def build_position_features(pos_path: str = _POS_PATH) -> pd.DataFrame:
    print(f"  loading {pos_path} ...", flush=True)
    df = pd.read_parquet(pos_path)
    df["is_center"] = df["position"].astype(str).str.contains(
        "Center", case=False, na=False
    ).astype(int)
    df["height_inches"] = df["height_inches"].astype(float).fillna(0.0)
    keep = ["player_id", "is_center", "height_inches"]
    return df[keep]


# ── assemble feature matrix for BLK only ─────────────────────────────────────


def assemble_blk_features(
    oof_df: pd.DataFrame,
    xstat_df: pd.DataFrame,
    matchup_df: pd.DataFrame,
    team_l5_df: pd.DataFrame,
    player_l5_df: pd.DataFrame,
    pos_df: pd.DataFrame,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str], int, int]:
    """Returns (X_full, oof_pred, actual, folds, feat_names_full,
    n_with_opp_join, n_with_adv_join).

    X_full has 17 columns:
      [6 xstat_z_<stat-except-blk>, n_prior_xstat,
       opp_efg_l5, opp_pace_l5, opp_oreb_pct_l5, opp_ts_pct_l5,
       own_def_rtg_l5, own_dreb_pct_l5, own_reb_pct_l5, own_pie_l5,
       own_min_l5, is_center, height_inches]
    """
    sub = oof_df[oof_df["stat"] == TARGET_STAT][
        ["player_id", "game_id", "oof_pred", "actual", "fold"]
    ].copy()
    sub["player_id"] = sub["player_id"].astype(int)
    sub["game_id"] = sub["game_id"].astype(str)

    # 1) Join xstat features.
    sub = sub.merge(xstat_df, on=["player_id", "game_id"], how="left")

    # 2) Join matchup -> opp_team.
    sub = sub.merge(matchup_df, on=["player_id", "game_id"], how="left")

    # 3) Join opp team L5 features via (opp_team, game_id) -> team_adv keyed
    #    by (team_tricode, game_id).
    team_l5_renamed = team_l5_df.rename(columns={"team_tricode": "opp_team"})
    pre_opp = len(sub)
    sub = sub.merge(team_l5_renamed, on=["opp_team", "game_id"], how="left")
    n_with_opp = int(sub["opp_efg_l5"].notna().sum())

    # 4) Join player's own L5 adv features.
    sub = sub.merge(player_l5_df, on=["player_id", "game_id"], how="left")
    n_with_adv = int(sub["own_def_rtg_l5"].notna().sum())

    # 5) Join position/height.
    sub = sub.merge(pos_df, on=["player_id"], how="left")

    # Feature schema -- exclude target stat's own xstat z.
    xstat_feats = [f"xstat_z_{s}" for s in STATS if s != TARGET_STAT]
    feat_names_full = xstat_feats + ["n_prior_xstat"] + list(BLK_NEW_FEATURES)

    for col in feat_names_full:
        if col not in sub.columns:
            sub[col] = 0.0
        sub[col] = pd.to_numeric(sub[col], errors="coerce").fillna(0.0)

    X = sub[feat_names_full].to_numpy(dtype=np.float32)
    oof_pred = sub["oof_pred"].to_numpy(dtype=np.float32)
    actual = sub["actual"].to_numpy(dtype=np.float32)
    folds = sub["fold"].to_numpy(dtype=np.int32)
    print(
        f"  assembled BLK matrix: n={len(sub):,} "
        f"opp_join_cov={n_with_opp}/{len(sub)} "
        f"adv_join_cov={n_with_adv}/{len(sub)}",
        flush=True,
    )
    return X, oof_pred, actual, folds, feat_names_full, n_with_opp, n_with_adv


# ── walk-forward evaluation ──────────────────────────────────────────────────


def _feature_indices(feat_names: List[str], select: List[str]) -> List[int]:
    return [i for i, n in enumerate(feat_names) if n in select]


def wf_eval_compose(
    X_full: np.ndarray,
    folds: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    feat_names_full: List[str],
) -> Dict:
    """Per-fold walk-forward train/eval.

    For each fold k:
      - Train F3-only head on (xstat_z_*, n_prior_xstat) of train-folds.
      - Train G1 head on FULL feature set of train-folds.
      - Predict residuals on val (fold==k).
      - Compute:
          mae_oof   = MAE(oof_pred, actual)              -- pregame raw
          mae_f3    = MAE(oof_pred + resid_f3, actual)   -- F3-adjusted base
          mae_g1    = MAE(oof_pred + resid_g1, actual)   -- G1-adjusted
          delta_g1_vs_f3 = mae_g1 - mae_f3               -- target metric
    """
    params = _lgb_params()
    f3_idx = _feature_indices(
        feat_names_full,
        list(XSTAT_Z_NAMES[:0])  # placeholder
        + [f"xstat_z_{s}" for s in STATS if s != TARGET_STAT]
        + ["n_prior_xstat"],
    )
    fold_records: List[Dict] = []
    fold_wins = 0
    deltas: List[float] = []
    abs_deltas_vs_oof: List[float] = []

    for k in (1, 2, 3, 4):
        tr_mask = folds != k
        va_mask = folds == k
        if tr_mask.sum() < 200 or va_mask.sum() < 10:
            fold_records.append({"fold": k, "skip": True})
            continue

        y_resid_tr = actual[tr_mask] - oof_pred[tr_mask]
        X_tr_full = X_full[tr_mask]
        X_tr_f3 = X_tr_full[:, f3_idx]
        X_va_full = X_full[va_mask]
        X_va_f3 = X_va_full[:, f3_idx]

        # F3-only head (baseline).
        m_f3 = lgb.LGBMRegressor(**params)
        m_f3.fit(
            X_tr_f3,
            y_resid_tr,
            feature_name=[feat_names_full[i] for i in f3_idx],
        )
        resid_f3 = m_f3.predict(X_va_f3)

        # G1 head (xstat + new BLK features).
        m_g1 = lgb.LGBMRegressor(**params)
        m_g1.fit(X_tr_full, y_resid_tr, feature_name=feat_names_full)
        resid_g1 = m_g1.predict(X_va_full)

        y_va = actual[va_mask]
        op_va = oof_pred[va_mask]
        mae_oof = float(np.mean(np.abs(op_va - y_va)))
        mae_f3 = float(np.mean(np.abs(op_va + resid_f3 - y_va)))
        mae_g1 = float(np.mean(np.abs(op_va + resid_g1 - y_va)))
        delta_g1_vs_f3 = mae_g1 - mae_f3
        delta_g1_vs_oof = mae_g1 - mae_oof

        deltas.append(delta_g1_vs_f3)
        abs_deltas_vs_oof.append(delta_g1_vs_oof)
        win = delta_g1_vs_f3 <= -0.020
        if win:
            fold_wins += 1

        fold_records.append({
            "fold":            k,
            "n":               int(va_mask.sum()),
            "mae_oof":         round(mae_oof, 6),
            "mae_f3":          round(mae_f3, 6),
            "mae_g1":          round(mae_g1, 6),
            "delta_g1_vs_f3":  round(delta_g1_vs_f3, 6),
            "delta_g1_vs_oof": round(delta_g1_vs_oof, 6),
            "win":             bool(win),
        })
        print(
            f"    [blk] fold {k}: oof={mae_oof:.5f} f3={mae_f3:.5f} "
            f"g1={mae_g1:.5f} d_g1_vs_f3={delta_g1_vs_f3:+.5f} "
            f"{'WIN' if win else 'loss'}",
            flush=True,
        )

    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    return {
        "fold_wins":        fold_wins,
        "mean_delta_g1_vs_f3": round(mean_delta, 6),
        "mean_delta_g1_vs_oof": round(
            float(np.mean(abs_deltas_vs_oof)) if abs_deltas_vs_oof else 0.0, 6
        ),
        "folds":            fold_records,
    }


def train_and_save_final(
    X_full: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    feat_names_full: List[str],
    eval_summary: Dict,
) -> bool:
    """Fit G1 head on full data and save."""
    y = actual - oof_pred
    model = lgb.LGBMRegressor(**_lgb_params())
    model.fit(X_full, y, feature_name=feat_names_full)
    out_path = os.path.join(_HEADS_OUT_DIR, f"{TARGET_STAT}_g1.lgb")
    model.booster_.save_model(out_path)
    meta_path = os.path.join(_HEADS_OUT_DIR, f"{TARGET_STAT}_g1_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "stat":           TARGET_STAT,
                "probe":          "R13_G1_blk_features",
                "features":       feat_names_full,
                "fold_wins":      eval_summary["fold_wins"],
                "mean_delta_g1_vs_f3":  eval_summary["mean_delta_g1_vs_f3"],
                "mean_delta_g1_vs_oof": eval_summary["mean_delta_g1_vs_oof"],
                "folds":          eval_summary["folds"],
                "lgb_params":     _lgb_params(),
                "trained_at":     datetime.utcnow().isoformat(),
                "n_rows":         int(len(y)),
                "compose_note": (
                    "Composes on top of R12_F3 cross-stat head: the G1 model "
                    "includes the F3 xstat features as a subset and adds 11 "
                    "BLK-specific features (4 opp-team L5, 5 player adv L5, "
                    "is_center, height_inches)."
                ),
                "leak_audit":     f"target z xstat_z_{TARGET_STAT} EXCLUDED",
            },
            fh,
            indent=2,
        )
    print(f"  [blk] SHIPPED -> {out_path}", flush=True)
    return True


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="R13_G1 BLK-specific feature engineering probe."
    )
    ap.add_argument(
        "--max-games", type=int, default=None,
        help="Cap unique games for quick smoke.",
    )
    args = ap.parse_args()

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    os.makedirs(_HEADS_OUT_DIR, exist_ok=True)
    t0 = time.time()

    print("=" * 65, flush=True)
    print("probe_R13_G1_blk_features", flush=True)
    print("=" * 65, flush=True)

    print("\nStep 1/6: load OOF parquet ...", flush=True)
    oof_df = pd.read_parquet(_OOF_PATH)
    print(f"  OOF shape: {oof_df.shape}", flush=True)
    if args.max_games:
        keep_games = sorted(oof_df["game_id"].unique())[:args.max_games]
        oof_df = oof_df[oof_df["game_id"].isin(keep_games)].copy()
        print(f"  capped to {oof_df['game_id'].nunique()} games", flush=True)

    print("\nStep 2/6: build cross-stat z residuals (F3 backbone) ...",
          flush=True)
    xstat_df, sigmas = compute_xstat_z_matrix(oof_df)

    print("\nStep 3/6: build matchup -> opp_team index ...", flush=True)
    matchup_df = build_matchup_index()

    print("\nStep 4/6: build opponent team L5 features ...", flush=True)
    team_l5_df = build_team_l5_features()

    print("\nStep 5/6: build player own adv L5 + position features ...",
          flush=True)
    player_l5_df = build_player_adv_l5()
    pos_df = build_position_features()

    print("\nStep 6/6: assemble BLK matrix + walk-forward eval ...",
          flush=True)
    X_full, oof_pred, actual, folds, feat_names_full, n_opp, n_adv = (
        assemble_blk_features(
            oof_df, xstat_df, matchup_df, team_l5_df, player_l5_df, pos_df,
        )
    )
    if X_full.shape[0] < 200:
        print(f"  [blk] SKIP (only {X_full.shape[0]} rows)", flush=True)
        return 1

    eval_res = wf_eval_compose(
        X_full, folds, oof_pred, actual, feat_names_full,
    )

    # Ship gate: 4/4 WF folds with delta_g1_vs_f3 <= -0.020.
    ship = (
        eval_res["fold_wins"] == 4
        and eval_res["mean_delta_g1_vs_f3"] <= -0.020
    )

    saved = False
    if ship:
        saved = train_and_save_final(
            X_full, oof_pred, actual, feat_names_full, eval_res,
        )
    else:
        print(
            f"  [blk] REJECT (fold_wins={eval_res['fold_wins']}/4 "
            f"mean_delta_vs_f3={eval_res['mean_delta_g1_vs_f3']:+.5f}, "
            f"required: 4/4 AND mean<=-0.020)",
            flush=True,
        )

    elapsed = time.time() - t0
    print("\n" + "=" * 65, flush=True)
    print("GATE SUMMARY", flush=True)
    print(
        f"  fold_wins (delta_g1_vs_f3 <= -0.020): "
        f"{eval_res['fold_wins']}/4",
        flush=True,
    )
    print(
        f"  mean_delta_g1_vs_f3:  {eval_res['mean_delta_g1_vs_f3']:+.5f}",
        flush=True,
    )
    print(
        f"  mean_delta_g1_vs_oof: {eval_res['mean_delta_g1_vs_oof']:+.5f}",
        flush=True,
    )
    print(f"  SHIP: {'YES' if ship else 'NO'}", flush=True)
    print(f"  elapsed: {elapsed:.1f}s", flush=True)

    out = {
        "probe":              "R13_G1_blk_features",
        "timestamp":          datetime.utcnow().isoformat(),
        "elapsed_s":          round(elapsed, 1),
        "ship":               bool(ship),
        "saved":              bool(saved),
        "stat":               TARGET_STAT,
        "fold_wins":          eval_res["fold_wins"],
        "mean_delta_g1_vs_f3":  eval_res["mean_delta_g1_vs_f3"],
        "mean_delta_g1_vs_oof": eval_res["mean_delta_g1_vs_oof"],
        "folds":              eval_res["folds"],
        "feature_names":      feat_names_full,
        "n_features":         len(feat_names_full),
        "n_rows":             int(X_full.shape[0]),
        "n_with_opp_join":    int(n_opp),
        "n_with_adv_join":    int(n_adv),
        "ship_gate": {
            "rule":      "4/4 WF folds with delta_g1_vs_f3 <= -0.020",
            "baseline":  "F3-adjusted OOF (R12_F3 cross-stat head)",
            "operative_prod_baseline_mae": BLK_PROD_BASELINE,
        },
        "compose_note": (
            "G1 includes xstat features as a subset; baseline is F3-only "
            "residual head trained per-fold for apples-to-apples."
        ),
        "lgb_params":         _lgb_params(),
        "leak_audit": (
            "xstat_z_blk EXCLUDED; all L5 features use strict shift(1) on "
            "(id, game_date); opp team features shift on team's own history."
        ),
        "sigmas":             {k: round(v, 6) for k, v in sigmas.items()},
    }
    with open(_CACHE_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nWrote: {_CACHE_OUT}", flush=True)

    return 0 if ship else 1


if __name__ == "__main__":
    sys.exit(main())
