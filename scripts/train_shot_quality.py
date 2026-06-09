"""
train_shot_quality.py — A1 xFG/xPTS retrain recipe (v2)

Architecture:
  - Data: per-game shot_log.csv (prefers shot_log_enriched.csv) from data/tracking/*/
  - Filter: made IN (0,1), court_zone NOT NULL, defender_dist_norm BETWEEN 0 AND 1,
            player_id NOT NULL, game has >=80 shots total
  - Feature engineering: uses defender_dist_norm*30 (feet), shot_clock, catch_and_shoot,
    shot_distance (feet), def_dist_sq
  - Per-zone models: 7 separate LogisticRegression keyed by court_zone
  - Walk-forward: 4 folds expanding window on lexically sorted game_id
  - Calibration: IsotonicRegression on 15% held-out slice within each WF fold
  - Saves: data/models/shot_quality_retrain_v2.pkl (per-zone dict format)
           data/models/shot_quality_benchmark_v2.json
           data/training/cv_shots_v2.csv

Ship gate:
  - >= 5/7 zones with POSITIVE defender_distance coefficient
  - log-loss improvement > 8% vs heuristic on LAST WF fold (not pooled)

Usage:
    C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe scripts/train_shot_quality.py
"""
from __future__ import annotations

import json
import logging
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
TRACKING_DIR   = ROOT / "data" / "tracking"
TRAINING_CSV   = ROOT / "data" / "training" / "cv_shots_v2.csv"
MODEL_V2_PATH  = ROOT / "data" / "models" / "shot_quality_retrain_v2.pkl"
OLD_MODEL_PATH = ROOT / "data" / "models" / "shot_quality.pkl"
BENCHMARK_PATH = ROOT / "data" / "models" / "shot_quality_benchmark_v2.json"

# ── constants ─────────────────────────────────────────────────────────────────
ZONE_BASELINE: Dict[str, float] = {
    "paint":            0.60,
    "mid_range":        0.40,
    "3pt_arc":          0.36,
    "corner_3":         0.39,
    "long_2":           0.34,
    "backcourt":        0.10,
    "other":            0.42,
    "restricted_area":  0.65,
}

# Zones that map to 3-point value
_3PT_ZONES = {"3pt_arc", "corner_3", "long_2"}

# Per-zone models only trained when zone has >= 100 labeled shots
MIN_ZONE_SHOTS = 100

# WF parameters
N_FOLDS      = 4
CALIB_FRAC   = 0.15   # fraction of train fold held out for isotonic calibration
MIN_CALIB_N  = 300    # skip calibration if slice < this

# Feature names (in order)
FEATURE_NAMES = ["def_dist_ft", "def_dist_sq", "shot_clock", "catch_and_shoot", "shot_distance_ft"]


# ── data loading ──────────────────────────────────────────────────────────────

def _load_shot_file(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, low_memory=False)
        df.columns = [c.strip().lower() for c in df.columns]
        if "court_zone" not in df.columns or "made" not in df.columns:
            return None
        return df
    except Exception as exc:
        log.debug("Skip %s: %s", path, exc)
        return None


def aggregate_shots() -> pd.DataFrame:
    """
    Walk data/tracking/<game_id>/ — prefer shot_log_enriched.csv over shot_log.csv.
    Keep only games with >= 80 total shots (Bug 39 guard: sparse games are ghost-slot artefacts).
    """
    game_dirs = sorted(TRACKING_DIR.glob("*/"))
    log.info("Scanning %d game dirs", len(game_dirs))

    frames: List[pd.DataFrame] = []
    skipped = 0
    sparse  = 0

    for gdir in game_dirs:
        if not gdir.is_dir():
            continue
        enriched = gdir / "shot_log_enriched.csv"
        plain    = gdir / "shot_log.csv"
        chosen   = enriched if enriched.exists() else (plain if plain.exists() else None)
        if chosen is None:
            skipped += 1
            continue
        df = _load_shot_file(chosen)
        if df is None:
            skipped += 1
            continue

        # Game-level gate: >= 10 total shots AND >= 5 labeled shots
        # (the >=80 total gate was too aggressive: median game has only 6 shots
        #  because most tracking dirs cover partial clips, not full games)
        n_labeled_game = df["made"].notna().sum() if "made" in df.columns else 0
        if len(df) < 10 or n_labeled_game < 5:
            sparse += 1
            continue

        df["_game_dir"] = gdir.name
        frames.append(df)

    log.info("Loaded %d games (%d skipped, %d too sparse)", len(frames), skipped, sparse)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def clean_and_filter(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Filter to labeled rows. Derive defender distance in feet from defender_dist_norm.
    """
    # ── coerce types ──────────────────────────────────────────────────────────
    raw["made"]             = pd.to_numeric(raw["made"],              errors="coerce")
    raw["shot_clock"]       = pd.to_numeric(raw.get("shot_clock",     pd.Series(np.nan, index=raw.index)), errors="coerce")
    raw["catch_and_shoot"]  = pd.to_numeric(raw.get("catch_and_shoot", pd.Series(0.0, index=raw.index)), errors="coerce").fillna(0)
    raw["shot_distance"]    = pd.to_numeric(raw.get("shot_distance",  pd.Series(np.nan, index=raw.index)), errors="coerce")

    # Defender distance: prefer defender_dist_norm (0-1 normalized), convert to feet
    # Fallback: clip raw defender_distance to plausible range and scale (> 50 = pixels)
    if "defender_dist_norm" in raw.columns:
        raw["defender_dist_norm"] = pd.to_numeric(raw["defender_dist_norm"], errors="coerce")
        raw["_dd_ft"] = raw["defender_dist_norm"].clip(0.0, 1.0) * 30.0
    elif "defender_distance" in raw.columns:
        dd = pd.to_numeric(raw["defender_distance"], errors="coerce")
        # If > 50, assume pixels (court ~1320px = 50ft -> 26.4px/ft)
        raw["_dd_ft"] = np.where(dd > 50, (dd / 26.4).clip(0, 30), dd.clip(0, 30))
    else:
        raw["_dd_ft"] = 5.0   # contested default

    # Fill missing
    raw["_dd_ft"]          = raw["_dd_ft"].fillna(5.0)
    raw["shot_clock"]      = raw["shot_clock"].fillna(12.0).clip(0, 24)
    raw["shot_distance"]   = raw["shot_distance"].fillna(15.0)

    # game_id normalization
    if "game_id" not in raw.columns:
        raw["game_id"] = raw["_game_dir"]
    raw["game_id"] = raw["game_id"].astype(str).str.strip()

    # player_id normalization
    if "player_id" not in raw.columns:
        raw["player_id"] = -1
    raw["player_id"] = pd.to_numeric(raw["player_id"], errors="coerce")

    # ── filter ────────────────────────────────────────────────────────────────
    labeled = raw[raw["made"].isin([0.0, 1.0])].copy()
    labeled = labeled[labeled["court_zone"].notna()].copy()
    labeled = labeled[labeled["player_id"].notna()].copy()
    labeled["court_zone"] = labeled["court_zone"].astype(str).str.strip()
    labeled = labeled[labeled["court_zone"] != ""].copy()
    labeled = labeled[labeled["court_zone"] != "nan"].copy()
    labeled = labeled[labeled["_dd_ft"].between(0.0, 30.0)].copy()

    log.info("Labeled + filtered shots: %d from %d total", len(labeled), len(raw))
    return labeled.reset_index(drop=True)


# ── feature building ──────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> np.ndarray:
    """
    Build X matrix: [def_dist_ft, def_dist_sq, shot_clock, catch_and_shoot, shot_distance_ft].
    """
    dd   = df["_dd_ft"].values.astype(float)
    sc   = df["shot_clock"].values.astype(float)
    cas  = df["catch_and_shoot"].values.astype(float)
    dist = df["shot_distance"].values.astype(float)
    return np.column_stack([dd, dd ** 2, sc, cas, dist])


# ── walk-forward split ────────────────────────────────────────────────────────

def make_wf_splits(games: List[str], n_folds: int = N_FOLDS) -> List[Tuple[List[str], List[str]]]:
    """
    Expanding-window walk-forward by lexically sorted game_id.
    Returns list of (train_games, test_games) tuples.
    Minimum 60% of games used in training for first fold.
    """
    games_sorted = sorted(set(games))
    n = len(games_sorted)
    if n < 4:
        raise ValueError(f"Too few games for WF: {n}")

    # Each fold: train on [0, train_end), test on [train_end, test_end)
    # We space them so test folds don't overlap and cover the last ~40%
    min_train = int(n * 0.60)
    test_window = max(1, (n - min_train) // n_folds)

    splits = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_window
        test_end  = train_end + test_window
        if test_end > n:
            test_end = n
        if train_end >= n:
            break
        train_games = games_sorted[:train_end]
        test_games  = games_sorted[train_end:test_end]
        if train_games and test_games:
            splits.append((train_games, test_games))

    if not splits:
        raise ValueError("Could not construct any WF folds")
    return splits


# ── per-zone model training ───────────────────────────────────────────────────

def train_per_zone(
    train_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Train one LR model per zone on train_df. Apply isotonic calibration
    on a 15% held-out slice from the training data.

    Returns dict keyed by zone: (lr_model, isotonic_or_None).
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.isotonic import IsotonicRegression

    per_zone: Dict[str, Any] = {}
    zones = train_df["court_zone"].unique()

    for zone in zones:
        zone_df = train_df[train_df["court_zone"] == zone].copy()
        n = len(zone_df)

        if n < MIN_ZONE_SHOTS:
            log.debug("Zone %s: only %d shots — using ZONE_BASELINE fallback", zone, n)
            per_zone[zone] = None   # signals fallback
            continue

        # Calibration split within training data
        n_calib = int(n * CALIB_FRAC)
        if n_calib >= MIN_CALIB_N:
            calib_df = zone_df.tail(n_calib).copy()
            fit_df   = zone_df.head(n - n_calib).copy()
        else:
            calib_df = None
            fit_df   = zone_df.copy()

        X_fit = build_features(fit_df)
        y_fit = fit_df["made"].astype(int).values

        if X_fit.shape[0] < 10 or len(np.unique(y_fit)) < 2:
            per_zone[zone] = None
            continue

        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("lr",     LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs")),
        ])
        try:
            pipe.fit(X_fit, y_fit)
        except Exception as exc:
            log.warning("Zone %s fit failed: %s", zone, exc)
            per_zone[zone] = None
            continue

        # Isotonic calibration
        iso: Optional[IsotonicRegression] = None
        if calib_df is not None and len(calib_df) >= MIN_CALIB_N:
            X_cal = build_features(calib_df)
            y_cal = calib_df["made"].astype(int).values
            raw_probs = pipe.predict_proba(X_cal)[:, 1]
            if len(np.unique(y_cal)) >= 2:
                iso = IsotonicRegression(out_of_bounds="clip")
                iso.fit(raw_probs, y_cal)

        per_zone[zone] = (pipe, iso)

    return per_zone


def predict_per_zone(
    per_zone: Dict[str, Any],
    df: pd.DataFrame,
) -> np.ndarray:
    """
    Predict xFG probabilities for each row in df using per-zone models.
    Falls back to ZONE_BASELINE for zones without a trained model.
    """
    probs = np.full(len(df), np.nan)
    for zone, model_tuple in per_zone.items():
        mask = (df["court_zone"] == zone).values
        if not mask.any():
            continue
        if model_tuple is None:
            probs[mask] = ZONE_BASELINE.get(zone, 0.42)
            continue
        pipe, iso = model_tuple
        X = build_features(df[mask])
        raw = pipe.predict_proba(X)[:, 1]
        if iso is not None:
            raw = iso.predict(raw)
        probs[mask] = raw

    # Any remaining NaN = unseen zone → heuristic
    nan_mask = np.isnan(probs)
    if nan_mask.any():
        for i in np.where(nan_mask)[0]:
            zone = str(df.iloc[i]["court_zone"])
            probs[i] = ZONE_BASELINE.get(zone, 0.42)
    return probs


# ── walk-forward evaluation ───────────────────────────────────────────────────

def run_walk_forward(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Run 4-fold WF evaluation. Return metrics per fold + the last fold's test set.
    """
    from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

    games = df["game_id"].unique().tolist()
    splits = make_wf_splits(games, n_folds=N_FOLDS)
    log.info("WF: %d folds over %d games", len(splits), len(games))

    fold_results = []
    last_test_df: Optional[pd.DataFrame] = None
    last_per_zone: Optional[Dict] = None

    for fold_idx, (train_games, test_games) in enumerate(splits):
        train_df = df[df["game_id"].isin(train_games)].copy()
        test_df  = df[df["game_id"].isin(test_games)].copy()

        if len(test_df) < 10 or len(train_df) < 50:
            log.warning("Fold %d: insufficient data (train=%d, test=%d)", fold_idx, len(train_df), len(test_df))
            continue

        per_zone = train_per_zone(train_df)

        # New model predictions on test
        y_true = test_df["made"].astype(int).values
        y_pred_new = predict_per_zone(per_zone, test_df)

        # Heuristic on test
        y_pred_heur = test_df["court_zone"].map(
            lambda z: ZONE_BASELINE.get(str(z), 0.42)
        ).values

        ll_new  = log_loss(y_true, y_pred_new)
        ll_heur = log_loss(y_true, y_pred_heur)
        brier   = brier_score_loss(y_true, y_pred_new)
        try:
            auc = roc_auc_score(y_true, y_pred_new)
        except Exception:
            auc = float("nan")

        ll_impr_pct = 100.0 * (ll_heur - ll_new) / ll_heur if ll_heur > 0 else 0.0

        fold_results.append({
            "fold":           fold_idx,
            "n_train":        len(train_df),
            "n_test":         len(test_df),
            "train_games":    len(train_games),
            "test_games":     len(test_games),
            "ll_new":         round(ll_new, 6),
            "ll_heuristic":   round(ll_heur, 6),
            "ll_impr_pct":    round(ll_impr_pct, 2),
            "brier":          round(brier, 6),
            "auc":            round(auc, 6),
        })
        log.info(
            "Fold %d: train=%d test=%d ll_new=%.4f ll_heur=%.4f impr=%.1f%%",
            fold_idx, len(train_df), len(test_df), ll_new, ll_heur, ll_impr_pct,
        )

        last_test_df  = test_df
        last_per_zone = per_zone

    return {
        "folds":          fold_results,
        "last_test_df":   last_test_df,
        "last_per_zone":  last_per_zone,
    }


# ── old model benchmark ───────────────────────────────────────────────────────

def predict_old_model(test_df: pd.DataFrame) -> np.ndarray:
    """
    Load data/models/shot_quality.pkl (old ShotQualityModel format) and predict.
    Returns ndarray of xFG probabilities; falls back to ZONE_BASELINE on error.
    """
    if not OLD_MODEL_PATH.exists():
        log.warning("Old model not found at %s — using ZONE_BASELINE as old-model proxy", OLD_MODEL_PATH)
        return test_df["court_zone"].map(lambda z: ZONE_BASELINE.get(str(z), 0.42)).values

    try:
        # Import the predict helper from shot_quality (PROTECTED, read-only)
        from src.prediction.shot_quality import ShotQualityModel, _build_features as _old_build

        with open(OLD_MODEL_PATH, "rb") as fh:
            state = pickle.load(fh)
        obj = ShotQualityModel()
        obj._model   = state["model"]
        obj._n_train = state.get("n_train", 0)
        obj._fitted  = obj._model is not None

        if not obj._fitted:
            raise ValueError("old model not fitted")

        # _build_features in old model uses raw defender_distance clipped to 30
        # But our test_df has _dd_ft already; build a compatible row
        compat = test_df.copy()
        compat["defender_distance"] = compat["_dd_ft"]   # already in feet
        X_old = _old_build(compat)
        probs = obj._model.predict_proba(X_old)[:, 1]
        return probs
    except Exception as exc:
        log.warning("Old model predict failed: %s — using ZONE_BASELINE", exc)
        return test_df["court_zone"].map(lambda z: ZONE_BASELINE.get(str(z), 0.42)).values


# ── metrics helpers ───────────────────────────────────────────────────────────

def compute_ece(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_pred >= bins[i]) & (y_pred < bins[i + 1])
        if mask.sum() == 0:
            continue
        avg_pred   = float(y_pred[mask].mean())
        avg_actual = float(y_true[mask].mean())
        ece       += mask.sum() * abs(avg_pred - avg_actual)
    return float(ece / max(len(y_true), 1))


def per_zone_log_loss(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    zones: np.ndarray,
) -> Dict[str, float]:
    """Compute log-loss per zone."""
    from sklearn.metrics import log_loss

    result = {}
    for zone in np.unique(zones):
        mask = zones == zone
        if mask.sum() < 2:
            continue
        try:
            result[zone] = round(log_loss(y_true[mask], y_pred[mask]), 6)
        except Exception:
            pass
    return result


# ── coefficient extraction ────────────────────────────────────────────────────

def extract_def_dist_coefs(per_zone: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Extract the def_dist_ft coefficient from each zone's LR model.
    FEATURE_NAMES[0] = def_dist_ft.
    Returns dict: zone -> coef (or None if fallback/no model).
    """
    coefs = {}
    for zone, model_tuple in per_zone.items():
        if model_tuple is None:
            coefs[zone] = None
            continue
        pipe, _ = model_tuple
        lr = pipe.named_steps["lr"]
        sc = pipe.named_steps["scaler"]
        # Raw LR coef is in scaled space; scale back to original units
        # coef_original = coef_scaled / scaler.scale_
        raw_coefs = lr.coef_[0]  # shape (n_features,)
        # def_dist_ft is feature index 0
        coef_raw   = float(raw_coefs[0])
        coef_unscaled = coef_raw / float(sc.scale_[0]) if sc.scale_[0] != 0 else coef_raw
        coefs[zone] = round(coef_unscaled, 5)
    return coefs


# ── three-way benchmark ───────────────────────────────────────────────────────

def three_way_benchmark(
    test_df: pd.DataFrame,
    last_per_zone: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare heuristic, old model, and new v2 on the last WF fold test set.
    """
    from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

    y_true = test_df["made"].astype(int).values
    zones  = test_df["court_zone"].values

    y_heur = test_df["court_zone"].map(lambda z: ZONE_BASELINE.get(str(z), 0.42)).values
    y_old  = predict_old_model(test_df)
    y_new  = predict_per_zone(last_per_zone, test_df)

    results = {}
    for name, y_pred in [("heuristic", y_heur), ("old_v1", y_old), ("new_v2", y_new)]:
        ll  = log_loss(y_true, y_pred)
        bs  = brier_score_loss(y_true, y_pred)
        try:
            auc = roc_auc_score(y_true, y_pred)
        except Exception:
            auc = float("nan")
        ece = compute_ece(y_true, y_pred)
        results[name] = {
            "log_loss":    round(ll, 6),
            "brier":       round(bs, 6),
            "auc":         round(auc, 6),
            "ece_10bin":   round(ece, 6),
        }

    # Log-loss improvement of new_v2 vs heuristic
    ll_heur = results["heuristic"]["log_loss"]
    ll_new  = results["new_v2"]["log_loss"]
    ll_impr_pct = 100.0 * (ll_heur - ll_new) / ll_heur if ll_heur > 0 else 0.0
    results["new_v2"]["ll_impr_vs_heuristic_pct"] = round(ll_impr_pct, 2)

    # Per-zone log-loss for new v2
    results["new_v2"]["per_zone_ll"] = per_zone_log_loss(y_true, y_new, zones)

    return results


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    from sklearn.metrics import log_loss

    # ── Step 1: data ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1 — DATA AGGREGATION")
    print("=" * 60)

    raw = aggregate_shots()
    if raw.empty:
        log.error("No data. Exiting.")
        sys.exit(1)

    labeled = clean_and_filter(raw)
    if len(labeled) < 100:
        log.error("Fewer than 100 labeled shots (%d). Cannot train.", len(labeled))
        sys.exit(1)

    print(f"Total labeled shots:  {len(labeled):,}")
    print(f"Games:                {labeled['game_id'].nunique():,}")
    print(f"Players:              {labeled['player_id'].nunique():,}")
    print(f"Overall FG%%:          {labeled['made'].mean():.3f}")
    print()
    print("Per-zone N and FG%:")
    for zone, grp in labeled.groupby("court_zone"):
        status = "OK" if len(grp) >= MIN_ZONE_SHOTS else "FALLBACK (<100)"
        print(f"  {zone:<18}: {len(grp):>5} shots  FG%={grp['made'].mean():.3f}  [{status}]")

    # Save training CSV
    TRAINING_CSV.parent.mkdir(parents=True, exist_ok=True)
    save_cols = [
        "game_id", "player_id", "court_zone", "_dd_ft", "shot_clock",
        "catch_and_shoot", "shot_distance", "made", "_game_dir",
    ]
    save_cols = [c for c in save_cols if c in labeled.columns]
    labeled[save_cols].to_csv(TRAINING_CSV, index=False)
    print(f"\nTraining data saved: {TRAINING_CSV} ({len(labeled):,} rows)")

    # ── Step 2: walk-forward evaluation ───────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2 — WALK-FORWARD EVALUATION (4 folds)")
    print("=" * 60)

    wf_results = run_walk_forward(labeled)
    fold_results    = wf_results["folds"]
    last_test_df    = wf_results["last_test_df"]
    last_per_zone   = wf_results["last_per_zone"]

    if not fold_results:
        log.error("No WF folds completed. Exiting.")
        sys.exit(1)

    print("\nFold summary:")
    print(f"  {'Fold':>4}  {'N_train':>8}  {'N_test':>7}  {'ll_new':>8}  {'ll_heur':>8}  {'impr%':>7}")
    print("  " + "-" * 52)
    for fr in fold_results:
        print(
            f"  {fr['fold']:>4}  {fr['n_train']:>8}  {fr['n_test']:>7}"
            f"  {fr['ll_new']:>8.4f}  {fr['ll_heuristic']:>8.4f}  {fr['ll_impr_pct']:>+7.1f}%"
        )

    last_fold = fold_results[-1]
    print(f"\nLAST FOLD (fold {last_fold['fold']}):")
    print(f"  log-loss new v2:   {last_fold['ll_new']:.4f}")
    print(f"  log-loss heuristic:{last_fold['ll_heuristic']:.4f}")
    print(f"  improvement:       {last_fold['ll_impr_pct']:+.1f}%")

    # ── Step 3: train final model on all data ─────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3 — FINAL TRAINING (all data)")
    print("=" * 60)

    final_per_zone = train_per_zone(labeled)
    trained_zones  = [z for z, m in final_per_zone.items() if m is not None]
    fallback_zones = [z for z, m in final_per_zone.items() if m is None]
    print(f"Trained zones ({len(trained_zones)}): {trained_zones}")
    print(f"Fallback zones ({len(fallback_zones)}): {fallback_zones}")

    # Def-dist coefficient check
    def_dist_coefs = extract_def_dist_coefs(final_per_zone)
    positive_zones = [z for z, c in def_dist_coefs.items() if c is not None and c > 0]
    negative_zones = [z for z, c in def_dist_coefs.items() if c is not None and c <= 0]

    print("\nDef-dist coefficient (scaled back to ft units):")
    print(f"  {'Zone':<18}  {'Coef':>10}  Sign")
    print("  " + "-" * 38)
    for zone in sorted(def_dist_coefs.keys()):
        c = def_dist_coefs[zone]
        if c is None:
            print(f"  {zone:<18}  {'N/A':>10}  (fallback)")
        else:
            sign = "POSITIVE" if c > 0 else "NEGATIVE"
            print(f"  {zone:<18}  {c:>+10.5f}  {sign}")

    n_trained_with_coef = len([z for z, c in def_dist_coefs.items() if c is not None])
    n_positive = len(positive_zones)
    ship_gate_coef = n_positive >= 5
    print(f"\nDef-dist positive zones: {n_positive}/{n_trained_with_coef} trained zones")
    print(f"Ship gate (>=5 positive): {'PASS' if ship_gate_coef else 'FAIL'}")

    # ── Step 4: three-way benchmark on last WF fold ───────────────────────────
    print("\n" + "=" * 60)
    print("STEP 4 — THREE-WAY BENCHMARK (last WF fold test set)")
    print("=" * 60)

    if last_test_df is None or last_per_zone is None:
        log.error("No last fold test data available. Skipping benchmark.")
        benchmark_data = {}
    else:
        bench = three_way_benchmark(last_test_df, last_per_zone)

        print(f"\n  {'Model':<12}  {'log-loss':>10}  {'brier':>8}  {'AUC':>7}  {'ECE':>7}")
        print("  " + "-" * 50)
        for model_name in ["heuristic", "old_v1", "new_v2"]:
            m = bench[model_name]
            extra = f"  (impr={m.get('ll_impr_vs_heuristic_pct', 0.0):+.1f}%)" if model_name == "new_v2" else ""
            print(
                f"  {model_name:<12}  {m['log_loss']:>10.4f}  {m['brier']:>8.4f}"
                f"  {m['auc']:>7.4f}  {m['ece_10bin']:>7.4f}{extra}"
            )

        print("\nPer-zone log-loss (new v2, last fold):")
        for zone, ll in sorted(bench["new_v2"].get("per_zone_ll", {}).items()):
            print(f"  {zone:<18}: {ll:.4f}")

        ll_impr_last = bench["new_v2"].get("ll_impr_vs_heuristic_pct", 0.0)
        ship_gate_ll = ll_impr_last > 8.0
        print(f"\nLog-loss improvement (last fold): {ll_impr_last:+.1f}%")
        print(f"Ship gate (>8% improvement):      {'PASS' if ship_gate_ll else 'FAIL'}")

        benchmark_data = bench

    # ── Step 5: save model ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 5 — SAVE v2 MODEL")
    print("=" * 60)

    MODEL_V2_PATH.parent.mkdir(parents=True, exist_ok=True)
    v2_payload = {
        "per_zone":     final_per_zone,
        "fallback":     ZONE_BASELINE,
        "feature_names": FEATURE_NAMES,
        "n_train":      len(labeled),
        "trained_zones": trained_zones,
        "fallback_zones": fallback_zones,
    }
    with open(MODEL_V2_PATH, "wb") as fh:
        pickle.dump(v2_payload, fh)
    print(f"Saved v2 model: {MODEL_V2_PATH} ({MODEL_V2_PATH.stat().st_size:,} bytes)")

    # ── Step 6: save benchmark JSON ───────────────────────────────────────────
    ll_impr_last_val = 0.0
    ship_gate_ll_val = False
    if benchmark_data:
        ll_impr_last_val = benchmark_data.get("new_v2", {}).get("ll_impr_vs_heuristic_pct", 0.0)
        ship_gate_ll_val = ll_impr_last_val > 8.0

    # Determine overall verdict
    if ship_gate_coef and ship_gate_ll_val:
        verdict = "PASS"
    elif ship_gate_coef and ll_impr_last_val > 0:
        verdict = "MARGINAL"
    else:
        verdict = "FAIL"

    benchmark_json = {
        "retrain_timestamp":      pd.Timestamp.now().isoformat(),
        "n_shots_labeled":        len(labeled),
        "n_games":                labeled["game_id"].nunique(),
        "per_zone_n": {
            zone: int((labeled["court_zone"] == zone).sum())
            for zone in labeled["court_zone"].unique()
        },
        "wf_folds":               fold_results,
        "last_fold_ll_new":       last_fold["ll_new"],
        "last_fold_ll_heuristic": last_fold["ll_heuristic"],
        "last_fold_ll_impr_pct":  last_fold["ll_impr_pct"],
        "three_way_benchmark":    benchmark_data,
        "def_dist_coefs":         def_dist_coefs,
        "n_positive_coef_zones":  n_positive,
        "trained_zones":          trained_zones,
        "fallback_zones":         fallback_zones,
        "ship_gate_coef_pass":    ship_gate_coef,
        "ship_gate_ll_pass":      ship_gate_ll_val,
        "verdict":                verdict,
    }

    with open(BENCHMARK_PATH, "w") as fh:
        json.dump(benchmark_json, fh, indent=2, default=str)
    print(f"Benchmark JSON:  {BENCHMARK_PATH}")

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Data: {len(labeled):,} shots, {labeled['game_id'].nunique()} games")
    print(f"Def-dist positive coefs: {n_positive}/{n_trained_with_coef}  "
          f"({'PASS' if ship_gate_coef else 'FAIL'} >= 5 gate)")
    print(f"Last-fold log-loss improvement vs heuristic: {last_fold['ll_impr_pct']:+.1f}%  "
          f"({'PASS' if last_fold['ll_impr_pct'] > 8 else 'FAIL'} >8% gate)")
    print(f"\nSHIP VERDICT: {verdict}")

    if verdict == "FAIL":
        print("\nFAIL reason analysis:")
        if not ship_gate_coef:
            print(f"  - Only {n_positive}/{n_trained_with_coef} zones have positive def_dist coef (need 5)")
            print(f"  - Negative zones: {negative_zones}")
            print("  - Likely cause: Bug 1 (defender_distance = teammate distance) not fully resolved")
            print("    in local data. Def_dist signal is still inverted or zero.")
        if not ship_gate_ll_val:
            print(f"  - Log-loss improvement {last_fold['ll_impr_pct']:+.1f}% < 8% threshold")
            print("  - Flat FG% across zones (no real differentiation) causes near-random predictions")
        print("\nDO NOT promote v2 pkl to shot_quality.pkl until bugs are resolved.")
    else:
        print("\nNOTE: v2 pkl written to data/models/shot_quality_retrain_v2.pkl")
        print("  NOT promoted to shot_quality.pkl (manual promotion required after review)")

    print("\nFiles written:")
    print(f"  {TRAINING_CSV}")
    print(f"  {MODEL_V2_PATH}")
    print(f"  {BENCHMARK_PATH}")


if __name__ == "__main__":
    main()
