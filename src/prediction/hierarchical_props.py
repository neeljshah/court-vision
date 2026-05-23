"""
hierarchical_props.py — Empirical Bayes hierarchical prop model + legacy D-3/D-4 blend.

New (HierarchicalPropModel):
  Full 3-level normal-normal empirical Bayes with closed-form posteriors.
  Hierarchy: league → position → player.  No MCMC required.
  Returns posterior mean + 80%/95% credible intervals + posterior samples.

Legacy (D-3/D-4 — preserved for backward compatibility):
  blend_prediction(xgb_pred, player_id, stat, games_played) -> float
  compute_optimal_lookback(player_id, stat) -> int
  get_archetype_prior(player_id, stat) -> float

Bayesian library: numpy empirical Bayes (PyMC/cmdstanpy/bambi unavailable).
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODELS_DIR  = os.path.join(_PROJECT_DIR, "data", "models")
_NBA_DIR     = os.path.join(_PROJECT_DIR, "data", "nba")


# ── HierarchicalPropModel ────────────────────────────────────────────────────

class HierarchicalPropModel:
    """
    3-level empirical Bayes hierarchical model for a single stat.

    Hierarchy:
      league_mean -> position_mean[pos] -> player_mean[player]

    Closed-form normal-normal posterior:
      posterior_mean[i] = (n_i * x_bar_i / sigma^2 + mu_pos / tau^2)
                          / (n_i / sigma^2 + 1 / tau^2)
      posterior_var[i]  = 1 / (n_i / sigma^2 + 1 / tau^2)

    where sigma^2 = within-player game variance (estimated from data),
          tau^2   = between-player variance (EB estimate per position group).
    """

    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

    def __init__(self, stat: str, model_dir: str = _MODELS_DIR) -> None:
        if stat not in self.STATS:
            raise ValueError(f"stat must be one of {self.STATS}, got {stat!r}")
        self.stat       = stat
        self.model_dir  = model_dir
        # Fitted parameters (set by fit())
        self._league_mean:   float = 0.0
        self._sigma2:        float = 1.0      # within-player variance
        self._pos_means:     Dict[str, float] = {}   # position -> mean
        self._pos_tau2:      Dict[str, float] = {}   # position -> between-player var
        self._player_stats:  Dict[int, Dict]  = {}   # player_id -> {n, x_bar, pos}
        self._fitted:        bool = False

    # ── Position inference ────────────────────────────────────────────────────

    @staticmethod
    def _infer_position(player_id: int, player_base: Dict[int, dict]) -> str:
        """Rule-based position from stat profile: G (high ast), C (high blk), F (else)."""
        row = player_base.get(player_id, {})
        blk = float(row.get("blk", 0) or 0)
        ast = float(row.get("ast", 0) or 0)
        if blk >= 0.9:
            return "C"
        if ast >= 4.0:
            return "G"
        return "F"

    @staticmethod
    def _load_player_base() -> Dict[int, dict]:
        """Load data/nba/player_base_2024-25.json as {player_id: row}."""
        path = os.path.join(_NBA_DIR, "player_base_2024-25.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                raw = json.load(f)
            # Dict keyed by player name -> {player_id, ...}
            if isinstance(raw, dict):
                return {int(v["player_id"]): v for v in raw.values() if "player_id" in v}
            if isinstance(raw, list):
                return {int(r["player_id"]): r for r in raw if "player_id" in r}
        except Exception as e:
            log.debug("_load_player_base failed: %s", e)
        return {}

    # ── EB estimation helpers ─────────────────────────────────────────────────

    @staticmethod
    def _estimate_eb_params(
        player_vals: Dict[int, List[float]]
    ) -> Tuple[float, float, float]:
        """
        Method-of-moments EB for normal-normal model.

        Returns (mu_pop, sigma2, tau2):
          mu_pop  = grand mean of per-player means
          sigma2  = mean within-player variance (pooled)
          tau2    = between-player variance (must be >= 0)
        """
        n_players = len(player_vals)
        if n_players == 0:
            return 0.0, 1.0, 0.0

        player_ns    = np.array([len(v) for v in player_vals.values()], dtype=float)
        player_means = np.array([np.mean(v) for v in player_vals.values()], dtype=float)
        player_vars  = np.array(
            [np.var(v, ddof=1) if len(v) > 1 else 1.0 for v in player_vals.values()],
            dtype=float,
        )

        mu_pop  = float(np.mean(player_means))
        sigma2  = float(np.mean(player_vars))          # within-player pooled
        sigma2  = max(sigma2, 1e-6)

        # Between-player variance via MOM: Var(x_bar_i) = tau2 + sigma2/n_i
        observed_var = float(np.var(player_means, ddof=1)) if n_players > 1 else 0.0
        avg_sigma2_over_n = float(np.mean(sigma2 / np.maximum(player_ns, 1)))
        tau2 = max(0.0, observed_var - avg_sigma2_over_n)

        return mu_pop, sigma2, tau2

    # ── fit ───────────────────────────────────────────────────────────────────

    def fit(self, training_data, n_iter: int = 1000) -> Dict:
        """
        Fit empirical Bayes hierarchical model from training_data.

        training_data: pd.DataFrame OR list-of-dicts with columns/keys:
          player_id (int), actual (float), [pos (str, optional)]

        n_iter: ignored for EB (kept for API compatibility with MCMC version).

        Returns: {"stat", "n_players", "n_obs", "league_mean", "sigma2",
                  "positions", "fitted"}
        """
        import pandas as pd

        if isinstance(training_data, list):
            df = pd.DataFrame(training_data)
        else:
            df = training_data.copy()

        if "actual" not in df.columns and self.stat in df.columns:
            df = df.rename(columns={self.stat: "actual"})

        df = df[df["actual"].notna()].copy()
        df["actual"] = df["actual"].astype(float)

        # Load positions
        player_base = self._load_player_base()

        if "pos" not in df.columns:
            df["pos"] = df["player_id"].apply(
                lambda pid: self._infer_position(int(pid), player_base)
            )

        positions = df["pos"].unique().tolist()
        self._pos_means = {}
        self._pos_tau2  = {}
        self._player_stats = {}

        # ── League-level EB ───────────────────────────────────────────────────
        all_vals: Dict[int, List[float]] = {}
        for pid, grp in df.groupby("player_id"):
            all_vals[int(pid)] = grp["actual"].tolist()

        self._league_mean, self._sigma2, league_tau2 = self._estimate_eb_params(all_vals)

        # ── Position-level EB ─────────────────────────────────────────────────
        for pos in positions:
            pos_df = df[df["pos"] == pos]
            pos_vals: Dict[int, List[float]] = {}
            for pid, grp in pos_df.groupby("player_id"):
                pos_vals[int(pid)] = grp["actual"].tolist()
            pos_mean, _, pos_tau2 = self._estimate_eb_params(pos_vals)
            self._pos_means[pos] = pos_mean
            self._pos_tau2[pos]  = max(pos_tau2, 1e-6)   # guard zero

        # ── Player-level posteriors ────────────────────────────────────────────
        for pid, grp in df.groupby("player_id"):
            pos = grp["pos"].iloc[0]
            vals = grp["actual"].tolist()
            n   = len(vals)
            x_bar = float(np.mean(vals))
            self._player_stats[int(pid)] = {
                "n": n, "x_bar": x_bar, "pos": pos,
                "vals": vals,
            }

        self._fitted = True
        log.info(
            "HierarchicalPropModel[%s] fitted: %d players, %d obs, "
            "league_mean=%.3f, sigma2=%.4f",
            self.stat, len(self._player_stats), len(df),
            self._league_mean, self._sigma2,
        )
        return {
            "stat":        self.stat,
            "n_players":   len(self._player_stats),
            "n_obs":       len(df),
            "league_mean": round(self._league_mean, 4),
            "sigma2":      round(self._sigma2, 4),
            "positions":   {p: {"mean": round(m, 4), "tau2": round(self._pos_tau2.get(p, 0), 6)}
                            for p, m in self._pos_means.items()},
            "fitted":      True,
        }

    # ── predict ───────────────────────────────────────────────────────────────

    def predict(self, player_id: int, game_features: dict) -> Dict[str, float]:
        """
        Return posterior predictive distribution for player_id.

        game_features: dict (currently unused in EB; reserved for future
          covariates like opp_def_rating, is_home when game logs are wired).

        Returns dict with keys:
          mean, lo_80, hi_80, lo_95, hi_95, posterior_samples (np.ndarray)
        """
        if not self._fitted:
            raise RuntimeError("Call fit() before predict()")

        player_base = self._load_player_base()

        if player_id in self._player_stats:
            ps  = self._player_stats[player_id]
            n   = ps["n"]
            x_bar = ps["x_bar"]
            pos = ps["pos"]
        else:
            # Unseen player: use position prior
            pos   = self._infer_position(player_id, player_base)
            n     = 0
            x_bar = self._pos_means.get(pos, self._league_mean)

        mu_pos  = self._pos_means.get(pos, self._league_mean)
        tau2    = self._pos_tau2.get(pos, self._sigma2)
        sigma2  = self._sigma2

        # Closed-form normal-normal posterior
        if n > 0 and tau2 > 0 and sigma2 > 0:
            precision_data  = n / sigma2
            precision_prior = 1.0 / tau2
            post_prec = precision_data + precision_prior
            post_mean = (precision_data * x_bar + precision_prior * mu_pos) / post_prec
            post_var  = 1.0 / post_prec
        else:
            post_mean = mu_pos
            post_var  = tau2 if tau2 > 0 else sigma2

        post_std = max(float(np.sqrt(post_var)), 1e-6)
        post_mean = max(0.0, float(post_mean))   # stats are non-negative

        # Predictive uncertainty includes within-player noise
        pred_var = post_var + sigma2
        pred_std = float(np.sqrt(pred_var))

        # Credible intervals (Gaussian approx)
        z80, z95 = 1.2816, 1.9600
        samples = np.random.normal(post_mean, pred_std, size=500)
        samples = np.maximum(samples, 0.0)

        return {
            "mean":             round(post_mean, 4),
            "lo_80":            round(max(0.0, post_mean - z80 * pred_std), 4),
            "hi_80":            round(post_mean + z80 * pred_std, 4),
            "lo_95":            round(max(0.0, post_mean - z95 * pred_std), 4),
            "hi_95":            round(post_mean + z95 * pred_std, 4),
            "posterior_std":    round(post_std, 4),
            "shrinkage_weight": round(1.0 / (1.0 + n * tau2 / sigma2) if sigma2 > 0 and tau2 > 0 else 1.0, 4),
            "n_games":          n,
            "position":         pos,
            "posterior_samples": samples,
        }

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        path = path or os.path.join(self.model_dir, f"hierarchical_{self.stat}.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "stat":           self.stat,
            "league_mean":    self._league_mean,
            "sigma2":         self._sigma2,
            "pos_means":      self._pos_means,
            "pos_tau2":       self._pos_tau2,
            "player_stats":   self._player_stats,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f)
        return path

    def load(self, path: Optional[str] = None) -> "HierarchicalPropModel":
        path = path or os.path.join(self.model_dir, f"hierarchical_{self.stat}.pkl")
        with open(path, "rb") as f:
            payload = pickle.load(f)
        self._league_mean  = payload["league_mean"]
        self._sigma2       = payload["sigma2"]
        self._pos_means    = payload["pos_means"]
        self._pos_tau2     = payload["pos_tau2"]
        self._player_stats = payload["player_stats"]
        self._fitted       = True
        return self

_NBA_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "nba",
)

# D-3: Position-archetype priors (league-average per position per stat)
ARCHETYPES = {
    "PG_handler":  {"pts": 18.5, "reb": 3.8, "ast": 6.2, "fg3m": 2.1, "stl": 1.3, "blk": 0.3, "tov": 2.8},
    "SG_scorer":   {"pts": 16.2, "reb": 3.5, "ast": 2.8, "fg3m": 2.0, "stl": 1.0, "blk": 0.4, "tov": 1.9},
    "SF_wing":     {"pts": 14.8, "reb": 5.2, "ast": 2.4, "fg3m": 1.4, "stl": 1.0, "blk": 0.6, "tov": 1.6},
    "PF_stretch":  {"pts": 13.1, "reb": 6.8, "ast": 1.9, "fg3m": 1.2, "stl": 0.7, "blk": 0.9, "tov": 1.4},
    "C_rim":       {"pts": 12.4, "reb": 9.1, "ast": 1.4, "fg3m": 0.3, "stl": 0.6, "blk": 1.8, "tov": 1.7},
}

# Fallback league average (across all positions)
_LEAGUE_AVG = {
    stat: round(np.mean([v[stat] for v in ARCHETYPES.values()]), 2)
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
}

# Position → archetype mapping (NBA position abbreviations)
_POS_TO_ARCHETYPE = {
    "PG": "PG_handler", "G": "PG_handler",
    "SG": "SG_scorer",
    "SF": "SF_wing",  "F": "SF_wing",
    "PF": "PF_stretch",
    "C":  "C_rim",    "FC": "C_rim",
}

# D-4: AR-order → lookback window mapping
_AR_TO_WINDOW = {1: 5, 2: 8, 3: 12, 4: 15, 5: 20}

# Module-level cache for optimal lookback (recompute monthly in production)
_LOOKBACK_CACHE: dict = {}


def get_archetype_prior(player_id: int, stat: str) -> float:
    """
    D-3: Return position-archetype prior for a player/stat.

    Loads player position from data/nba/player_bio.json.
    Falls back to league average if position unknown.
    """
    try:
        bio_path = os.path.join(_NBA_CACHE, "player_bio.json")
        if not os.path.exists(bio_path):
            return _LEAGUE_AVG.get(stat, 10.0)
        bios = json.load(open(bio_path))
        # Bio files may be list or dict keyed by player_id
        if isinstance(bios, list):
            pid_map = {int(r.get("id", r.get("player_id", 0))): r for r in bios}
        else:
            pid_map = {int(k): v for k, v in bios.items()}

        bio = pid_map.get(int(player_id), {})
        position = str(bio.get("position", bio.get("pos", ""))).strip().upper()

        # Normalise common position strings
        for pos_key in _POS_TO_ARCHETYPE:
            if pos_key in position:
                archetype = _POS_TO_ARCHETYPE[pos_key]
                return float(ARCHETYPES[archetype].get(stat, _LEAGUE_AVG.get(stat, 10.0)))
    except Exception:
        pass
    return _LEAGUE_AVG.get(stat, 10.0)


def blend_prediction(
    xgb_pred: float,
    player_id: int,
    stat: str,
    games_played: int,
) -> float:
    """
    D-3: Bayesian hierarchical blend of XGBoost prediction with archetype prior.

    season_weight ramps from 0 (0 games) to 1.0 (25+ games):
      Games 0-5:   ~20% season, ~80% archetype
      Games 11-25: ~50% season, ~50% archetype
      Games 25+:   100% season (no blending)

    Args:
        xgb_pred:     XGBoost model prediction.
        player_id:    NBA player ID.
        stat:         Prop stat name.
        games_played: Number of season games played so far.

    Returns:
        Blended prediction float.
    """
    season_weight = min(float(max(games_played, 0)) / 25.0, 1.0)
    archetype_prior = get_archetype_prior(player_id, stat)
    return round(season_weight * xgb_pred + (1.0 - season_weight) * archetype_prior, 3)


# ── D-4: Optimal lookback ─────────────────────────────────────────────────────

def compute_optimal_lookback(player_id: int, stat: str) -> int:
    """
    D-4: Select optimal rolling lookback window using AR(p) AIC minimisation.

    Fits AR(1) through AR(5) on player's last 50 game values.
    Returns lookback in [5, 30] games mapped from optimal AR order.

    Results cached in module-level dict.
    """
    cache_key = (int(player_id), stat.lower())
    if cache_key in _LOOKBACK_CACHE:
        return _LOOKBACK_CACHE[cache_key]

    _default = 10  # median lookback when undetermined

    try:
        season = "2024-25"
        gamelog_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
        if not os.path.exists(gamelog_path):
            return _default

        rows = json.load(open(gamelog_path))
        col_map = {"pts": "PTS", "reb": "REB", "ast": "AST",
                   "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
        col = col_map.get(stat.lower(), stat.upper())
        series = np.array([float(r.get(col, 0) or 0) for r in rows
                           if r.get(col) is not None], dtype=float)[-50:]

        if len(series) < 10:
            return _default

        best_p, best_aic = 1, float("inf")
        for p in range(1, 6):
            if len(series) <= p + 1:
                continue
            try:
                aic = _aic_ar(series, p)
                if aic < best_aic:
                    best_aic = aic
                    best_p = p
            except Exception:
                continue

        window = int(np.clip(_AR_TO_WINDOW.get(best_p, 10), 5, 30))
        _LOOKBACK_CACHE[cache_key] = window
        return window
    except Exception:
        return _default


def _aic_ar(series: np.ndarray, p: int) -> float:
    """Compute AIC for AR(p) model via OLS."""
    n = len(series)
    y = series[p:]
    X = np.column_stack([series[p - i - 1: n - i - 1] for i in range(p)])
    # OLS: theta = (X'X)^{-1} X'y
    try:
        theta, residuals, _, _ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return float("inf")
    if len(residuals) == 0:
        resid = y - X @ theta
        sse = float(np.sum(resid ** 2))
    else:
        sse = float(residuals[0])
    if sse <= 0:
        return float("inf")
    n_eff = len(y)
    log_lik = -0.5 * n_eff * (1.0 + np.log(2 * np.pi * sse / n_eff))
    return float(-2.0 * log_lik + 2.0 * (p + 1))
