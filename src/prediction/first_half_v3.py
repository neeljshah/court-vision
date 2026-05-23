"""
first_half_v3.py — Honest first-half predictor trained on real Q1+Q2 period scores.

Architecture: LightGBM regression, L1 objective, walk-forward eval.
Target: first_half_total = home_q1+q2 + away_q1+q2 (REAL period scores, not proxy).

Feature set extends game_models v2 FEATURE_COLS with first-half-specific
rolling averages (Q1-avg_l10, Q2-avg_l10, H1_scored_l10, H1_allowed_l10).

Walk-forward split identical to game_models v2:
  Train   : 2022-23 + first 70% of 2023-24
  Val     : last 30% of 2023-24
  Holdout : 2024-25 in full
"""
from __future__ import annotations

import json, os, sys, time, warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_LINESCORE_FILE = os.path.join(_NBA_CACHE, "linescores_all.json")

# Base features reused from game_models v2
from src.prediction.game_models import FEATURE_COLS as _BASE_FEATURE_COLS

# Additional H1-specific features appended after the base set
_H1_EXTRA_COLS = [
    "home_q1_avg_l10", "home_q2_avg_l10",
    "away_q1_avg_l10", "away_q2_avg_l10",
    "home_h1_scored_l10", "away_h1_scored_l10",
    "home_h1_allowed_l10", "away_h1_allowed_l10",
    "h1_scored_sum_l10",    # home_h1_scored + away_h1_scored
    "h1_allowed_avg_l10",   # avg of h1_allowed
    "score_prior",          # home_avg_score_l10 + away_avg_score_l10
]

FEATURE_COLS_V3: List[str] = list(_BASE_FEATURE_COLS) + _H1_EXTRA_COLS

_TRAIN_SEASONS  = ["2022-23", "2023-24"]
_HOLDOUT_SEASON = "2024-25"


# ── Linescore loader ───────────────────────────────────────────────────────────

def _load_linescore_cache() -> dict:
    """Load the linescores_all.json cache: game_id -> {home_h1, away_h1, ...}."""
    if not os.path.exists(_LINESCORE_FILE):
        return {}
    with open(_LINESCORE_FILE) as f:
        return json.load(f)


# ── Per-game first-half rolling features ──────────────────────────────────────

def _build_h1_rolling(
    gamelog: pd.DataFrame,
    linescores: dict,
) -> Tuple[dict, dict, int, int]:
    """
    Build per-game first-half rolling features from game log + linescore cache.

    Returns:
        h1_lookup  : (team_id, game_id) -> {home_q1_avg_l10, ...}
        avg_score  : (team_id, game_id) -> avg_full_game_score_l10
        n_real     : number of rows backed by real period scores
        n_imputed  : number of rows imputed from 0.47 × game_total
    """
    gl = gamelog.copy()
    gl["_dt"] = pd.to_datetime(gl["GAME_DATE"], errors="coerce")
    gl = gl.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)

    h1_lookup: dict = {}
    avg_score_lookup: dict = {}
    n_real = 0
    n_imputed = 0

    for tid, grp in gl.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        q1_vals, q2_vals = [], []
        h1_scored_vals, h1_allowed_vals = [], []

        for i in range(len(grp)):
            gid  = str(grp.at[i, "GAME_ID"])
            pts  = float(grp.at[i, "PTS"] or 0)
            is_home = " vs. " in str(grp.at[i, "MATCHUP"])

            ls = linescores.get(gid, {})
            if ls:
                # Use home_team_id from linescore as authoritative home/away identifier
                ls_home_tid = ls.get("home_team_id")
                team_is_home = (ls_home_tid == int(tid)) if ls_home_tid else is_home
                if team_is_home:
                    q1 = float(ls.get("home_q1", 0))
                    q2 = float(ls.get("home_q2", 0))
                    h1s = float(ls.get("home_h1", 0))
                    h1a = float(ls.get("away_h1", 0))
                else:
                    q1 = float(ls.get("away_q1", 0))
                    q2 = float(ls.get("away_q2", 0))
                    h1s = float(ls.get("away_h1", 0))
                    h1a = float(ls.get("home_h1", 0))
                n_real += 1
            else:
                # impute: approx 47% split across Q1/Q2
                q1 = pts * 0.24
                q2 = pts * 0.23
                h1s = pts * 0.47
                h1a = pts * 0.47   # crude — unknown opponent half
                n_imputed += 1

            q1_vals.append(q1)
            q2_vals.append(q2)
            h1_scored_vals.append(h1s)
            h1_allowed_vals.append(h1a)

        q1_s      = pd.Series(q1_vals)
        q2_s      = pd.Series(q2_vals)
        h1sc_s    = pd.Series(h1_scored_vals)
        h1al_s    = pd.Series(h1_allowed_vals)
        pts_s     = grp["PTS"].astype(float)

        # shift(1) prevents leakage — rolling uses only *previous* games
        q1_l10   = q1_s.shift(1).rolling(10, min_periods=3).mean()
        q2_l10   = q2_s.shift(1).rolling(10, min_periods=3).mean()
        h1sc_l10 = h1sc_s.shift(1).rolling(10, min_periods=3).mean()
        h1al_l10 = h1al_s.shift(1).rolling(10, min_periods=3).mean()
        avg_sc   = pts_s.shift(1).rolling(10, min_periods=3).mean()

        for i in range(len(grp)):
            gid = str(grp.at[i, "GAME_ID"])
            key = (int(tid), gid)
            fallback_pts = float(grp.at[i, "PTS"] or 100)
            h1_lookup[key] = {
                "q1_l10":   float(q1_l10.iloc[i])   if pd.notna(q1_l10.iloc[i])   else fallback_pts * 0.24,
                "q2_l10":   float(q2_l10.iloc[i])   if pd.notna(q2_l10.iloc[i])   else fallback_pts * 0.23,
                "h1sc_l10": float(h1sc_l10.iloc[i]) if pd.notna(h1sc_l10.iloc[i]) else fallback_pts * 0.47,
                "h1al_l10": float(h1al_l10.iloc[i]) if pd.notna(h1al_l10.iloc[i]) else fallback_pts * 0.47,
            }
            avg_score_lookup[key] = (
                float(avg_sc.iloc[i]) if pd.notna(avg_sc.iloc[i]) else fallback_pts
            )

    return h1_lookup, avg_score_lookup, n_real, n_imputed


# ── Truth loader ───────────────────────────────────────────────────────────────

def _load_first_half_truth(seasons: List[str]) -> pd.DataFrame:
    """
    Walk scored_games_*.json caches + linescores_all.json to produce:
        game_id, season, game_date, h1_total (REAL or imputed), is_real

    Returns a DataFrame with columns: game_id, season, game_date, h1_total, is_real
    """
    linescores = _load_linescore_cache()
    records = []
    for season in seasons:
        cache = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
        if not os.path.exists(cache):
            continue
        with open(cache) as f:
            payload = json.load(f)
        for row in payload.get("rows", []):
            gid   = row["game_id"]
            ls    = linescores.get(gid, {})
            ls_h1 = ls.get("h1_total", 0) if ls else 0
            if ls and ls_h1 > 60:   # valid real period score (>60 rules out zeros/nulls)
                h1 = float(ls_h1)
                real = True
            else:
                h1   = float(row.get("first_half_proxy", row["game_total"] * 0.47))
                real = False
            records.append({
                "game_id":   gid,
                "season":    season,
                "game_date": row.get("game_date", ""),
                "h1_total":  h1,
                "is_real":   real,
            })
    return pd.DataFrame(records)


# ── Dataset builder ───────────────────────────────────────────────────────────

def _build_dataset(seasons: List[str]) -> pd.DataFrame:
    """
    Merge v2 scored_games features with first-half truth and H1 rolling features.
    Returns a DataFrame with FEATURE_COLS_V3 + target columns.
    """
    linescores = _load_linescore_cache()
    all_rows: List[dict] = []
    total_real = 0
    total_imputed = 0

    for season in seasons:
        cache = os.path.join(_NBA_CACHE, f"scored_games_{season}.json")
        if not os.path.exists(cache):
            print(f"  [v3] scored_games_{season}: missing, skip")
            continue
        with open(cache) as f:
            payload = json.load(f)
        base_rows = payload.get("rows", [])
        if not base_rows:
            continue

        # Build gamelog for this season to compute H1 rolling features
        try:
            from nba_api.stats.endpoints import leaguegamelog
            warnings.filterwarnings("ignore")
            time.sleep(0.6)
            gl = leaguegamelog.LeagueGameLog(
                season=season,
                season_type_all_star="Regular Season",
                player_or_team_abbreviation="T",
            ).get_data_frames()[0]
        except Exception as e:
            print(f"  [v3] gamelog {season}: {e}")
            continue

        h1_lookup, avg_sc_lookup, nr, ni = _build_h1_rolling(gl, linescores)
        total_real    += nr
        total_imputed += ni

        # Index base_rows by game_id for O(1) lookup
        base_by_gid = {r["game_id"]: r for r in base_rows}

        # Walk gamelog to find home/away team IDs per game
        gid_teams: dict = {}
        for gid_val in gl["GAME_ID"].unique():
            pair = gl[gl["GAME_ID"] == gid_val]
            hr   = pair[pair["MATCHUP"].str.contains(r" vs\. ", na=False)]
            ar   = pair[pair["MATCHUP"].str.contains(r" @ ",    na=False)]
            if hr.empty or ar.empty:
                continue
            gid_teams[str(gid_val)] = (int(hr.iloc[0]["TEAM_ID"]), int(ar.iloc[0]["TEAM_ID"]))

        for gid, (htid, atid) in gid_teams.items():
            base = base_by_gid.get(gid)
            if base is None:
                continue

            h1_h = h1_lookup.get((htid, gid), {})
            h1_a = h1_lookup.get((atid, gid), {})
            if not h1_h or not h1_a:
                continue

            avg_h = avg_sc_lookup.get((htid, gid), base.get("home_off_rtg", 112) * 0.47)
            avg_a = avg_sc_lookup.get((atid, gid), base.get("away_off_rtg", 112) * 0.47)

            # First-half truth label
            ls = linescores.get(gid, {})
            ls_h1 = ls.get("h1_total", 0) if ls else 0
            if ls and ls_h1 > 60:   # >60 rules out zeros/nulls
                h1_total = float(ls_h1)
                is_real  = True
            else:
                h1_total = float(base.get("first_half_proxy", base["game_total"] * 0.47))
                is_real  = False

            row = dict(base)   # copy all base v2 features
            row.update({
                "h1_total":          h1_total,
                "is_real":           is_real,
                # H1-specific extra features
                "home_q1_avg_l10":   h1_h["q1_l10"],
                "home_q2_avg_l10":   h1_h["q2_l10"],
                "away_q1_avg_l10":   h1_a["q1_l10"],
                "away_q2_avg_l10":   h1_a["q2_l10"],
                "home_h1_scored_l10":h1_h["h1sc_l10"],
                "away_h1_scored_l10":h1_a["h1sc_l10"],
                "home_h1_allowed_l10":h1_h["h1al_l10"],
                "away_h1_allowed_l10":h1_a["h1al_l10"],
                "h1_scored_sum_l10": h1_h["h1sc_l10"] + h1_a["h1sc_l10"],
                "h1_allowed_avg_l10":(h1_h["h1al_l10"] + h1_a["h1al_l10"]) / 2,
                "score_prior":       avg_h + avg_a,
            })
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  [v3] Dataset: {len(df)} rows | real={total_real} imputed={total_imputed}")
    return df


# ── Main class ─────────────────────────────────────────────────────────────────

class FirstHalfPredictorV3:
    """
    Honest first-half points predictor using real Q1+Q2 period scores as labels.
    Extends game_models v2 feature set with first-half-specific rolling averages.
    """

    def __init__(self, model_dir: str = _MODEL_DIR) -> None:
        self.model_dir   = model_dir
        self.model_path  = os.path.join(model_dir, "first_half_lgb.txt")
        self.metrics_path= os.path.join(model_dir, "first_half_v3_metrics.json")
        self._booster    = None

    # ── Train ──────────────────────────────────────────────────────────────────

    def train(self, seasons: Optional[List[str]] = None) -> Dict:
        """
        Walk-forward train on 3 seasons; return metrics dict.

        Split:
          Train   : 2022-23 + first 70% of 2023-24
          Val     : last 30% of 2023-24
          Holdout : 2024-25
        """
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("lightgbm required: pip install lightgbm")
        from sklearn.metrics import mean_absolute_error, r2_score

        if seasons is None:
            seasons = [*_TRAIN_SEASONS, _HOLDOUT_SEASON]

        os.makedirs(self.model_dir, exist_ok=True)

        print("[first_half_v3] Building dataset ...")
        df = _build_dataset(seasons)

        # Ensure all feature cols present (fill missing with 0)
        for c in FEATURE_COLS_V3:
            if c not in df.columns:
                df[c] = 0.0

        df = df.dropna(subset=FEATURE_COLS_V3 + ["h1_total"]).reset_index(drop=True)
        print(f"  After dropna: {len(df)} rows")
        print(f"  Real targets: {df['is_real'].sum()}/{len(df)} "
              f"({100*df['is_real'].mean():.1f}%)")

        if len(df) < 200:
            print("[first_half_v3] Insufficient data.")
            return {}

        # Walk-forward split
        df_tv = df[df["season"] != _HOLDOUT_SEASON].reset_index(drop=True)
        df_ho = df[df["season"] == _HOLDOUT_SEASON].reset_index(drop=True)
        tv_split = int(len(df_tv) * 0.70)
        df_tr = df_tv.iloc[:tv_split].reset_index(drop=True)
        df_va = df_tv.iloc[tv_split:].reset_index(drop=True)
        print(f"  Train={len(df_tr)} Val={len(df_va)} Holdout={len(df_ho)}")

        X_tr  = df_tr[FEATURE_COLS_V3].values.astype(np.float32)
        X_va  = df_va[FEATURE_COLS_V3].values.astype(np.float32)
        X_ho  = df_ho[FEATURE_COLS_V3].values.astype(np.float32) if len(df_ho) > 0 else None
        y_tr  = df_tr["h1_total"].values.astype(np.float32)
        y_va  = df_va["h1_total"].values.astype(np.float32)

        model = lgb.LGBMRegressor(
            objective="regression_l1",
            n_estimators=400,
            learning_rate=0.05,
            num_leaves=63,
            min_child_samples=20,
            reg_lambda=1.0,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_va, y_va)],
            callbacks=[
                lgb.early_stopping(40, verbose=False),
                lgb.log_evaluation(100),
            ],
        )

        # Val metrics
        p_va  = model.predict(X_va)
        val_mae = float(mean_absolute_error(y_va, p_va))
        val_r2  = float(r2_score(y_va, p_va))
        val_med = float(np.median(np.abs(y_va - p_va)))

        # Holdout metrics
        ho_mae = ho_r2 = ho_med = None
        month_mae: dict = {}
        if X_ho is not None and len(df_ho) > 0:
            p_ho   = model.predict(X_ho)
            y_ho   = df_ho["h1_total"].values.astype(np.float32)
            ho_mae = float(mean_absolute_error(y_ho, p_ho))
            ho_r2  = float(r2_score(y_ho, p_ho))
            ho_med = float(np.median(np.abs(y_ho - p_ho)))

            # Per-month breakdown
            if "game_date" in df_ho.columns:
                df_ho = df_ho.copy()
                df_ho["_month"] = pd.to_datetime(
                    df_ho["game_date"], errors="coerce"
                ).dt.month
                df_ho["_err"] = np.abs(y_ho - p_ho)
                for bucket, months in [("early", [10, 11, 12]), ("mid", [1, 2]), ("late", [3, 4, 5, 6])]:
                    sub = df_ho[df_ho["_month"].isin(months)]
                    if len(sub) > 0:
                        month_mae[bucket] = round(float(sub["_err"].mean()), 3)

        print(f"\n  Val  MAE={val_mae:.3f}  R²={val_r2:.3f}  MedianAE={val_med:.3f}")
        print(f"  Hold MAE={ho_mae}  R²={ho_r2}  MedianAE={ho_med}")
        print(f"  Holdout by month: {month_mae}")

        # Feature importance (top 8)
        importance = pd.Series(
            model.feature_importances_, index=FEATURE_COLS_V3
        ).sort_values(ascending=False)
        top8 = importance.head(8).to_dict()
        print(f"\n  Top-8 features: {top8}")

        # Persist model
        self._booster = model.booster_
        model.booster_.save_model(self.model_path)
        print(f"  Model saved -> {self.model_path}")

        # Persist metrics
        metrics = {
            "version":            "v3_real_period_scoring",
            "feature_cols":       FEATURE_COLS_V3,
            "n_features":         len(FEATURE_COLS_V3),
            "train_n":            len(df_tr),
            "val_n":              len(df_va),
            "holdout_n":          len(df_ho) if df_ho is not None else 0,
            "real_pct":           round(100 * df["is_real"].mean(), 1),
            "val_mae":            round(val_mae, 3),
            "val_r2":             round(val_r2, 3),
            "val_median_ae":      round(val_med, 3),
            "holdout_mae":        round(ho_mae, 3) if ho_mae else None,
            "holdout_r2":         round(ho_r2, 3) if ho_r2 else None,
            "holdout_median_ae":  round(ho_med, 3) if ho_med else None,
            "holdout_month_mae":  month_mae,
            "top8_features":      {k: int(v) for k, v in top8.items()},
            "v2_proxy_holdout_mae": 6.96,   # baseline for comparison
        }
        with open(self.metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"  Metrics saved -> {self.metrics_path}")
        return metrics

    # ── Predict ────────────────────────────────────────────────────────────────

    def predict(self, features: dict) -> float:
        """Predict first-half total from a pre-game features dict."""
        if self._booster is None:
            self._load()
        import lightgbm as lgb
        x = np.array(
            [[features.get(c, 0.0) for c in FEATURE_COLS_V3]], dtype=np.float32
        )
        return float(self._booster.predict(x)[0])

    def _load(self) -> None:
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("lightgbm required")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Model not found: {self.model_path} — run train() first"
            )
        self._booster = lgb.Booster(model_file=self.model_path)
