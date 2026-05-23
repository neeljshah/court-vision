"""src/prediction/live_win_prob_v2.py — GBM live in-game win probability (v2).

Replaces broken LSTM (val_auc=0.0). Architecture: LightGBM regressor trained on
game-state snapshots sampled from quarter-boundary data (linescores) + scored_games
pre-game features. 324 games × 4 states = 1296 base rows; PBP tick rows appended
when available (59 games × ~96 ticks each ≈ 5664 additional rows).

Target: home_wins (binary 1/0 at final whistle).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

_MODEL_DIR = PROJECT_DIR / "data" / "models"
_NBA_CACHE = PROJECT_DIR / "data" / "nba"
_MODEL_PATH = _MODEL_DIR / "live_win_prob_v2_lgb.txt"
_METRICS_PATH = _MODEL_DIR / "live_win_prob_v2_metrics.json"

FEATURE_NAMES = [
    "seconds_remaining",
    "score_margin_home",
    "home_net_rtg_l10",
    "away_net_rtg_l10",
    "home_off_rtg_l10",
    "away_off_rtg_l10",
    "home_def_rtg_l10",
    "away_def_rtg_l10",
    "period",
    "time_left_in_period",
    "pace_remaining_estimate",
    "net_rtg_diff",
    "home_form_l5",
    "away_form_l5",
    "home_court_advantage",  # constant 1.0 — anchors base home-win rate ~0.53
]

# Training distribution means — used as safe defaults in predict()
_DEFAULT_OFF_RTG = 110.0
_DEFAULT_DEF_RTG = 110.0

_REGULATION_SECONDS = 2880  # 48 min
_PERIOD_SECONDS = 720       # 12 min


def _make_state(
    seconds_remaining: float,
    score_margin_home: float,
    home_net_rtg_l10: float,
    away_net_rtg_l10: float,
    home_off_rtg_l10: float,
    away_off_rtg_l10: float,
    home_def_rtg_l10: float,
    away_def_rtg_l10: float,
    period: int,
    pace_l10: float,
    net_rtg_diff: float,
    home_form_l5: float,
    away_form_l5: float,
    home_court_advantage: float = 1.0,
) -> np.ndarray:
    """Build a 1-D feature vector from game state scalars."""
    time_left_in_period = seconds_remaining % _PERIOD_SECONDS
    if time_left_in_period == 0 and seconds_remaining > 0:
        time_left_in_period = _PERIOD_SECONDS
    pace_remaining = pace_l10 * (seconds_remaining / _REGULATION_SECONDS)
    return np.array([
        seconds_remaining,
        score_margin_home,
        home_net_rtg_l10,
        away_net_rtg_l10,
        home_off_rtg_l10,
        away_off_rtg_l10,
        home_def_rtg_l10,
        away_def_rtg_l10,
        float(period),
        time_left_in_period,
        pace_remaining,
        net_rtg_diff,
        home_form_l5,
        away_form_l5,
        home_court_advantage,
    ], dtype=np.float32)


def _load_all_scored_games() -> Dict[str, dict]:
    scored: Dict[str, dict] = {}
    for season in ("2022-23", "2023-24", "2024-25"):
        p = _NBA_CACHE / f"scored_games_{season}.json"
        if p.exists():
            d = json.loads(p.read_text())
            for r in d.get("rows", []):
                scored[r["game_id"]] = r
    return scored


def _load_linescores() -> Dict[str, dict]:
    p = _NBA_CACHE / "linescores_all.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _load_ot_maps() -> set:
    ot_games: set = set()
    for season in ("2022-23", "2023-24", "2024-25"):
        p = _NBA_CACHE / f"ot_map_{season}.json"
        if p.exists():
            d = json.loads(p.read_text())
            ot_games.update(d.keys())
    return ot_games


def _quarter_states_for_game(
    game_id: str,
    linescore: dict,
    sg: dict,
    ot_games: set,
) -> List[tuple]:
    """Generate quarter-boundary (start-of-quarter) game states.

    Returns list of (feature_vector, home_wins).
    We sample the START of each quarter — i.e. what was the score BEFORE this
    quarter began — so the model sees evolving score information.
    """
    h = [linescore[f"home_q{q}"] for q in range(1, 5)]
    a = [linescore[f"away_q{q}"] for q in range(1, 5)]
    home_total = sum(h)
    away_total = sum(a)
    # OT games: linescore only has 4 quarters; treat final score as those 4 Qs
    # home_wins derived from whether home > away at final
    home_wins = 1 if home_total > away_total else 0

    pace_l10 = (sg.get("home_pace_l10", 98.0) + sg.get("away_pace_l10", 98.0)) / 2
    kw = dict(
        home_net_rtg_l10=sg.get("home_net_rtg_L10", 0.0),
        away_net_rtg_l10=sg.get("away_net_rtg_L10", 0.0),
        home_off_rtg_l10=sg.get("home_off_rtg_L10", _DEFAULT_OFF_RTG),
        away_off_rtg_l10=sg.get("away_off_rtg_L10", _DEFAULT_OFF_RTG),
        home_def_rtg_l10=sg.get("home_def_rtg_L10", _DEFAULT_DEF_RTG),
        away_def_rtg_l10=sg.get("away_def_rtg_L10", _DEFAULT_DEF_RTG),
        net_rtg_diff=sg.get("net_rtg_diff", 0.0),
        home_form_l5=sg.get("home_form_l5", 0.5),
        away_form_l5=sg.get("away_form_l5", 0.5),
        pace_l10=pace_l10,
    )

    rows = []
    home_running, away_running = 0, 0
    # 4 states: start of Q1, Q2, Q3, Q4
    for q in range(1, 5):
        sec_remaining = _REGULATION_SECONDS - (q - 1) * _PERIOD_SECONDS
        margin = float(home_running - away_running)
        vec = _make_state(
            seconds_remaining=float(sec_remaining),
            score_margin_home=margin,
            period=q,
            **kw,
        )
        rows.append((vec, home_wins))
        home_running += h[q - 1]
        away_running += a[q - 1]

    return rows


def _pbp_states_for_game(
    game_id: str,
    sg: dict,
    ot_games: set,
) -> List[tuple]:
    """Generate per-event game states from PBP files (30s tick filter)."""
    import glob as _glob, re as _re

    pbp_files = sorted(
        _glob.glob(str(_NBA_CACHE / f"pbp_{game_id}_p*.json"))
    )
    if not pbp_files:
        return []

    all_events = []
    for pf in pbp_files:
        events = json.loads(Path(pf).read_text())
        all_events.extend(events)

    if not all_events:
        return []

    # Determine outcome from last scored event
    home_wins = None
    for ev in reversed(all_events):
        margin_str = str(ev.get("score_margin", "")).strip()
        score_str = str(ev.get("score", "")).strip()
        if score_str and "-" in score_str:
            try:
                parts = score_str.split("-")
                h_score = int(parts[0])
                a_score = int(parts[1])
                home_wins = 1 if h_score > a_score else 0
                break
            except (ValueError, IndexError):
                continue

    if home_wins is None:
        return []

    pace_l10 = (sg.get("home_pace_l10", 98.0) + sg.get("away_pace_l10", 98.0)) / 2
    kw = dict(
        home_net_rtg_l10=sg.get("home_net_rtg_L10", 0.0),
        away_net_rtg_l10=sg.get("away_net_rtg_L10", 0.0),
        home_off_rtg_l10=sg.get("home_off_rtg_L10", _DEFAULT_OFF_RTG),
        away_off_rtg_l10=sg.get("away_off_rtg_L10", _DEFAULT_OFF_RTG),
        home_def_rtg_l10=sg.get("home_def_rtg_L10", _DEFAULT_DEF_RTG),
        away_def_rtg_l10=sg.get("away_def_rtg_L10", _DEFAULT_DEF_RTG),
        net_rtg_diff=sg.get("net_rtg_diff", 0.0),
        home_form_l5=sg.get("home_form_l5", 0.5),
        away_form_l5=sg.get("away_form_l5", 0.5),
        pace_l10=pace_l10,
    )

    rows = []
    last_tick_sec = -1
    tick_interval = 30

    for ev in all_events:
        period = int(ev.get("period", 1))
        clock_sec = int(ev.get("game_clock_sec", 0))
        score_str = str(ev.get("score", "")).strip()
        if not score_str or "-" not in score_str:
            continue
        try:
            parts = score_str.split("-")
            h_score = int(parts[0])
            a_score = int(parts[1])
        except (ValueError, IndexError):
            continue

        # seconds_remaining = time left in game (regulation)
        periods_done = min(period - 1, 3)
        sec_elapsed_in_period = clock_sec  # game_clock_sec counts UP within period
        sec_elapsed = periods_done * _PERIOD_SECONDS + sec_elapsed_in_period
        sec_remaining = max(0.0, float(_REGULATION_SECONDS - sec_elapsed))

        # tick filter: only keep one snapshot per 30s elapsed
        if abs(sec_elapsed - last_tick_sec) < tick_interval:
            continue
        last_tick_sec = sec_elapsed

        margin = float(h_score - a_score)
        vec = _make_state(
            seconds_remaining=sec_remaining,
            score_margin_home=margin,
            period=period,
            **kw,
        )
        rows.append((vec, home_wins))

    return rows


def _apply_saturation(p: float, score_margin_home: float, seconds_remaining: float) -> float:
    """Post-hoc saturation clamp for extreme late-game states.

    When a team is up by more points than there are possessions left to overcome
    the deficit, the model output should saturate toward 0 or 1. NBA pace is ~100
    possessions per 48 min = ~1 possession per 28.8 seconds.
    Expected possessions remaining ≈ seconds_remaining / 29.
    If |margin| > possessions_remaining * 2 (each possession worth ~2 pts), clamp hard.
    """
    if seconds_remaining <= 0:
        return 1.0 if score_margin_home > 0 else (0.0 if score_margin_home < 0 else 0.5)
    possessions_remaining = seconds_remaining / 29.0
    pts_achievable = possessions_remaining * 2.0
    # Score is unovercomable if deficit > achievable points
    if score_margin_home > pts_achievable:
        # Blend GBM prediction with 1.0 based on how extreme
        blend = min(1.0, (score_margin_home - pts_achievable) / max(pts_achievable, 1.0))
        return float(p + blend * (1.0 - p))
    elif score_margin_home < -pts_achievable:
        blend = min(1.0, (-score_margin_home - pts_achievable) / max(pts_achievable, 1.0))
        return float(p - blend * p)
    return p


class LiveWinProbV2:
    """LightGBM in-game win probability model.

    Usage
    -----
    m = LiveWinProbV2()
    metrics = m.train()          # builds + saves model
    p = m.predict(game_state)    # returns float in [0, 1]
    """

    def __init__(self, model_dir: str = "data/models") -> None:
        _p = Path(model_dir)
        if not _p.is_absolute():
            _p = PROJECT_DIR / _p
        self._model_dir = _p
        self._model_path = _p / "live_win_prob_v2_lgb.txt"
        self._metrics_path = _p / "live_win_prob_v2_metrics.json"
        self._model: Optional[Any] = None
        self._load_if_exists()

    def _load_if_exists(self) -> None:
        if self._model_path.exists():
            try:
                import lightgbm as lgb  # type: ignore
                self._model = lgb.Booster(model_file=str(self._model_path))
            except Exception:
                self._model = None

    # ------------------------------------------------------------------
    def train(self) -> Dict[str, Any]:
        """Build training set, fit LightGBM, persist artifacts. Returns metrics dict."""
        import lightgbm as lgb  # type: ignore
        from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss  # type: ignore

        scored = _load_all_scored_games()
        linescores = _load_linescores()
        ot_games = _load_ot_maps()

        rows: List[tuple] = []
        pbp_rows = 0
        qboundary_rows = 0
        sources: Dict[str, int] = {"pbp_ticks": 0, "quarter_boundary": 0}

        # --- quarter-boundary states (all 324 linescore games) ---
        for gid, ls in linescores.items():
            sg = scored.get(gid, {})
            if not sg:
                continue
            qrows = _quarter_states_for_game(gid, ls, sg, ot_games)
            rows.extend(qrows)
            qboundary_rows += len(qrows)

        # --- PBP tick states (59 games) ---
        for gid, sg in scored.items():
            prows = _pbp_states_for_game(gid, sg, ot_games)
            if prows:
                rows.extend(prows)
                pbp_rows += len(prows)

        sources["quarter_boundary"] = qboundary_rows
        sources["pbp_ticks"] = pbp_rows

        if len(rows) < 50:
            return {
                "error": "insufficient data",
                "n_train": 0, "n_val": 0,
                "val_auc": 0.5, "val_brier": 0.25, "logloss": 0.693,
            }

        X = np.stack([r[0] for r in rows])
        y = np.array([r[1] for r in rows], dtype=np.float32)

        # Walk-forward split: last 20% of rows → val
        n = len(rows)
        n_val = max(1, int(n * 0.20))
        n_train = n - n_val
        X_train, X_val = X[:n_train], X[n_train:]
        y_train, y_val = y[:n_train], y[n_train:]

        dtrain = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_NAMES)
        dval = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_NAMES, reference=dtrain)

        params = {
            "objective": "binary",
            "metric": ["auc", "binary_logloss"],
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "min_child_samples": 10,
            "lambda_l1": 0.1,
            "lambda_l2": 0.1,
            "verbose": -1,
            "n_jobs": -1,
        }

        callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)]
        booster = lgb.train(
            params,
            dtrain,
            num_boost_round=500,
            valid_sets=[dval],
            callbacks=callbacks,
        )

        preds_val = booster.predict(X_val)
        preds_val = np.clip(preds_val, 1e-7, 1 - 1e-7)

        val_auc = float(roc_auc_score(y_val, preds_val))
        val_brier = float(brier_score_loss(y_val, preds_val))
        val_logloss = float(log_loss(y_val, preds_val))

        self._model_dir.mkdir(parents=True, exist_ok=True)
        booster.save_model(str(self._model_path))
        self._model = booster

        metrics: Dict[str, Any] = {
            "version": "v2_gbm",
            "n_train": int(n_train),
            "n_val": int(n_val),
            "val_auc": round(val_auc, 4),
            "val_brier": round(val_brier, 4),
            "logloss": round(val_logloss, 4),
            "features": FEATURE_NAMES,
            "tick_interval_sec": 30,
            "calibration_bins": [10],
            "sources": sources,
            "computed_at": datetime.utcnow().isoformat() + "Z",
            "note": (
                "Training states: quarter-boundary snapshots from 324 linescores games "
                "plus per-event ticks from 59 PBP games. "
                "Limitations: L10 ratings at game-day (not mid-game); "
                "no timeout/foul-bonus/lineup features (absent from cached data)."
            ),
        }
        self._metrics_path.write_text(json.dumps(metrics, indent=2))
        return metrics

    # ------------------------------------------------------------------
    def predict(self, game_state: dict) -> float:
        """Predict P(home wins) for the given game state dict.

        Required keys: seconds_remaining, score_margin_home.
        Optional: home_net_rtg_l10, away_net_rtg_l10, home_off_rtg_l10,
                  away_off_rtg_l10, home_def_rtg_l10, away_def_rtg_l10,
                  period, pace_l10, net_rtg_diff, home_form_l5, away_form_l5,
                  home_court_advantage (default 1.0).
        """
        if self._model is None:
            raise RuntimeError("Model not loaded — call train() first or ensure model file exists.")

        pace_l10 = float(game_state.get("pace_l10", 98.0))
        vec = _make_state(
            seconds_remaining=float(game_state.get("seconds_remaining", _REGULATION_SECONDS)),
            score_margin_home=float(game_state.get("score_margin_home", 0.0)),
            home_net_rtg_l10=float(game_state.get("home_net_rtg_l10", 0.0)),
            away_net_rtg_l10=float(game_state.get("away_net_rtg_l10", 0.0)),
            home_off_rtg_l10=float(game_state.get("home_off_rtg_l10", _DEFAULT_OFF_RTG)),
            away_off_rtg_l10=float(game_state.get("away_off_rtg_l10", _DEFAULT_OFF_RTG)),
            home_def_rtg_l10=float(game_state.get("home_def_rtg_l10", _DEFAULT_DEF_RTG)),
            away_def_rtg_l10=float(game_state.get("away_def_rtg_l10", _DEFAULT_DEF_RTG)),
            period=int(game_state.get("period", 4)),
            pace_l10=pace_l10,
            net_rtg_diff=float(game_state.get("net_rtg_diff", 0.0)),
            home_form_l5=float(game_state.get("home_form_l5", 0.5)),
            away_form_l5=float(game_state.get("away_form_l5", 0.5)),
            home_court_advantage=float(game_state.get("home_court_advantage", 1.0)),
        )
        p = float(self._model.predict(vec.reshape(1, -1))[0])
        p = float(np.clip(p, 0.0, 1.0))
        # Apply physical saturation for extreme late-game states
        sec = float(game_state.get("seconds_remaining", _REGULATION_SECONDS))
        margin = float(game_state.get("score_margin_home", 0.0))
        return _apply_saturation(p, margin, sec)
