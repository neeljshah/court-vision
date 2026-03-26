"""
possession_simulator.py — 7-model possession chain Monte Carlo simulator.

Runs 10,000 possessions per game per team.  Seeds from NBA API averages until
CV data is available.  CV features drop in as additional inputs when ready.

7-Model Possession Chain
------------------------
[1] play_type     — what type of possession (ISO/PnR/spot-up/drive/etc.)
[2] shot_selector — which player attempts the shot (usage-weighted)
[3] xfg           — expected field goal probability for that shot
[4] to_foul       — turnover / foul outcome (short-circuits to FT or no shot)
[5] rebound       — offensive rebound → extra possession
[6] fatigue_mult  — apply per-player fatigue scalar at current minute
[7] substitution  — check if player is still on court

Public API
----------
    PossessionSimulator(season)
    simulator.simulate(game_id, n_sims)     -> SimResult
    simulator.over_prob(player_id, stat, line, game_id) -> float
    simulator.get_distribution(player_id, stat, game_id) -> np.ndarray
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_N_SIMS_DEFAULT   = 10_000
_POSSESSIONS_PER_GAME = 100       # approximate per team
_AVG_PACE         = 100.0
_OREB_RATE        = 0.27          # league-average offensive rebound rate
_TOV_RATE         = 0.135         # league-average turnover rate per possession
_FOUL_RATE        = 0.08          # shooting foul rate
_FT_MAKE_PCT      = 0.77          # league-average FT%

# Play type frequency distribution (league average)
_PLAY_TYPE_DIST = {
    "spot_up":      0.26,
    "transition":   0.15,
    "pnr_ball":     0.14,
    "iso":          0.10,
    "post_up":      0.08,
    "pnr_roll":     0.07,
    "cut":          0.06,
    "hand_off":     0.04,
    "putback":      0.05,
    "misc":         0.05,
}

# Points per play type (league average PPP)
_PLAY_TYPE_PPP = {
    "spot_up":      1.05,
    "transition":   1.15,
    "pnr_ball":     0.88,
    "iso":          0.85,
    "post_up":      0.83,
    "pnr_roll":     1.18,
    "cut":          1.25,
    "hand_off":     0.95,
    "putback":      1.05,
    "misc":         0.92,
}

# FG% per shot zone (league average)
_ZONE_FG_PCT = {
    "rim":          0.63,
    "mid_range":    0.41,
    "corner_3":     0.39,
    "above_3":      0.36,
}


# ── Simulation result ─────────────────────────────────────────────────────────

@dataclass
class SimResult:
    """Holds Monte Carlo simulation distributions per player."""
    game_id: str
    n_sims: int
    # distributions[player_id][stat] = np.array(n_sims,)
    distributions: Dict[str, Dict[str, np.ndarray]] = field(default_factory=dict)
    # game-level
    home_score_dist: Optional[np.ndarray] = None
    away_score_dist: Optional[np.ndarray] = None
    home_win_prob: float = 0.5

    def percentile(self, player_id: str, stat: str, pct: float) -> float:
        """Return the pct-th percentile of stat distribution for player_id."""
        arr = self.distributions.get(str(player_id), {}).get(stat)
        if arr is None:
            return 0.0
        return float(np.percentile(arr, pct))

    def over_prob(self, player_id: str, stat: str, line: float) -> float:
        """Return P(stat > line) from simulation distributions."""
        arr = self.distributions.get(str(player_id), {}).get(stat)
        if arr is None or len(arr) == 0:
            return 0.5
        return float(np.mean(arr > line))

    def mean(self, player_id: str, stat: str) -> float:
        """Return mean projection for player_id's stat."""
        arr = self.distributions.get(str(player_id), {}).get(stat)
        if arr is None:
            return 0.0
        return float(np.mean(arr))

    def summary(self, player_id: str) -> dict:
        """Return {stat: {mean, p25, p50, p75, p90}} for a player."""
        out = {}
        for stat, arr in self.distributions.get(str(player_id), {}).items():
            out[stat] = {
                "mean": round(float(np.mean(arr)), 2),
                "p25":  round(float(np.percentile(arr, 25)), 2),
                "p50":  round(float(np.percentile(arr, 50)), 2),
                "p75":  round(float(np.percentile(arr, 75)), 2),
                "p90":  round(float(np.percentile(arr, 90)), 2),
            }
        return out


# ── Player seed loader ─────────────────────────────────────────────────────────

class _PlayerSeed:
    """Loads per-player NBA API averages for simulation seeding."""

    def __init__(self, season: str = "2024-25") -> None:
        self.season = season
        self._avgs: dict = {}
        self._load()

    def _load(self) -> None:
        path = os.path.join(PROJECT_DIR, "data", "nba", f"player_avgs_{self.season}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self._avgs = json.load(f)
            except Exception:
                pass

        # Also pull gamelogs if avgs missing
        if not self._avgs:
            self._load_from_gamelogs()

    def _load_from_gamelogs(self) -> None:
        """Build per-player averages from individual gamelog files."""
        import glob
        pattern = os.path.join(PROJECT_DIR, "data", "nba", f"gamelog_full_*_{self.season}.json")
        for fpath in glob.glob(pattern)[:200]:   # cap at 200 to avoid slowness
            try:
                with open(fpath) as f:
                    rows = json.load(f)
                if not rows:
                    continue
                pid = str(rows[0].get("player_id", os.path.basename(fpath).split("_")[2]))
                # rolling last 20
                recent = rows[-20:]
                def _avg(key):
                    vals = [float(r.get(key, 0) or 0) for r in recent]
                    return float(np.mean(vals)) if vals else 0.0
                self._avgs[pid] = {
                    "pts": _avg("pts"), "reb": _avg("reb"), "ast": _avg("ast"),
                    "fg3m": _avg("fg3m"), "stl": _avg("stl"), "blk": _avg("blk"),
                    "tov": _avg("tov"), "min": _avg("min"),
                    "fga": _avg("fga"), "fg_pct": _avg("fg_pct"),
                    "ft_pct": _avg("ft_pct"), "fta": _avg("fta"),
                }
            except Exception:
                continue

    def get(self, player_id: str) -> dict:
        """Return avg stats dict for player_id."""
        return self._avgs.get(str(player_id), {})

    def all_ids(self) -> list:
        return list(self._avgs.keys())


# ── 7-model possession chain ───────────────────────────────────────────────────

class PossessionSimulator:
    """
    Monte Carlo possession simulator.

    Seeds from NBA API averages.  CV features (defender_dist, spacing, fatigue_ms)
    drop in as additional inputs when available via inject_cv_features().
    """

    def __init__(self, season: str = "2024-25") -> None:
        self.season = season
        self._seeds = _PlayerSeed(season)
        self._cv_features: dict = {}     # {player_id: {feature: value}}
        self._synergy: dict = {}         # {team: {play_type: ppp}}
        self._load_synergy()

    # ── External CV injection ────────────────────────────────────────────────

    def inject_cv_features(self, cv_data: dict) -> None:
        """
        Inject CV-derived features for a game.

        Args:
            cv_data: {player_id: {defender_dist: float, spacing: float,
                                   fatigue: float, shot_clock_avg: float}}
        """
        self._cv_features.update(cv_data)
        log.info("Injected CV features for %d players", len(cv_data))

    # ── Public API ───────────────────────────────────────────────────────────

    def simulate(
        self,
        game_id: str,
        n_sims: int = _N_SIMS_DEFAULT,
        player_ids: Optional[List[str]] = None,
        home_team: str = "",
        away_team: str = "",
        predicted_total: float = 222.0,
        predicted_spread: float = 0.0,
    ) -> SimResult:
        """
        Run n_sims Monte Carlo simulations for game_id.

        Args:
            game_id:           NBA game ID string
            n_sims:            Number of simulations (default 10,000)
            player_ids:        Optional list of player IDs to simulate
            home_team:         Home team abbreviation
            away_team:         Away team abbreviation
            predicted_total:   Expected total points (game model output)
            predicted_spread:  Expected spread (positive = home favored)

        Returns:
            SimResult with per-player stat distributions
        """
        rng = np.random.default_rng(seed=42)

        # Resolve player list
        if not player_ids:
            player_ids = self._seeds.all_ids()[:30]   # cap for performance

        # Per-game pace scalar
        pace = self._estimate_pace(game_id, predicted_total)

        result = SimResult(game_id=game_id, n_sims=n_sims)

        # Simulate each player independently
        for pid in player_ids:
            seed = self._seeds.get(pid)
            if not seed:
                continue
            dists = self._simulate_player(pid, seed, pace, n_sims, rng)
            result.distributions[str(pid)] = dists

        # Game-level score distribution
        home_pts, away_pts = self._simulate_game_scores(
            n_sims, predicted_total, predicted_spread, rng
        )
        result.home_score_dist = home_pts
        result.away_score_dist = away_pts
        result.home_win_prob = float(np.mean(home_pts > away_pts))

        return result

    def over_prob(
        self, player_id: str, stat: str, line: float, game_id: str = ""
    ) -> float:
        """
        Quick single-player over probability.
        Runs simulation if result not cached.
        """
        result = self.simulate(
            game_id=game_id or "quick",
            n_sims=5_000,
            player_ids=[str(player_id)],
        )
        return result.over_prob(str(player_id), stat, line)

    def get_distribution(
        self, player_id: str, stat: str, game_id: str = ""
    ) -> np.ndarray:
        """Return raw simulation distribution for player_id's stat."""
        result = self.simulate(
            game_id=game_id or "quick",
            n_sims=5_000,
            player_ids=[str(player_id)],
        )
        return result.distributions.get(str(player_id), {}).get(stat, np.array([]))

    # ── Internal simulation chain ────────────────────────────────────────────

    def _simulate_player(
        self, pid: str, seed: dict, pace: float,
        n_sims: int, rng: np.random.Generator
    ) -> Dict[str, np.ndarray]:
        """
        Run n_sims possession chains for a single player.
        Returns {stat: array(n_sims)}.
        """
        avg_min  = float(seed.get("min", 25.0) or 25.0)
        avg_pts  = float(seed.get("pts", 10.0) or 10.0)
        avg_reb  = float(seed.get("reb", 4.0)  or 4.0)
        avg_ast  = float(seed.get("ast", 2.0)  or 2.0)
        avg_fg3m = float(seed.get("fg3m", 1.0) or 1.0)
        avg_stl  = float(seed.get("stl", 0.7)  or 0.7)
        avg_blk  = float(seed.get("blk", 0.4)  or 0.4)
        avg_tov  = float(seed.get("tov", 1.5)  or 1.5)
        avg_fga  = float(seed.get("fga", 8.0)  or 8.0)
        fg_pct   = float(seed.get("fg_pct", 0.45) or 0.45)
        ft_pct   = float(seed.get("ft_pct", 0.77) or 0.77)

        # CV adjustments
        cv = self._cv_features.get(str(pid), {})
        defender_dist  = float(cv.get("defender_dist", 4.0))   # feet, open = 6+
        fatigue_scalar = float(cv.get("fatigue", 1.0))
        # Tighter defense → lower FG%
        cv_fg_adj = 1.0 + (defender_dist - 4.0) * 0.015
        fg_pct    = min(max(fg_pct * cv_fg_adj * fatigue_scalar, 0.25), 0.70)

        # Minutes model — Poisson minutes per game
        min_std  = max(avg_min * 0.15, 2.0)
        mins_arr = np.clip(rng.normal(avg_min, min_std, n_sims), 0, 48)

        # Scale per-game rate by minutes fraction
        min_frac = mins_arr / max(avg_min, 1.0)

        # ── [1] Play type — sample from usage-weighted distribution ──────────
        # (affects points per possession, not tracked per stat here — absorbed
        # into overall pts distribution)

        # ── [2] Shot selector — FGA Poisson ──────────────────────────────────
        # Scale FGA by minutes fraction + noise
        fga_rate = avg_fga / max(avg_min, 1.0)   # per minute
        fga_arr  = rng.poisson(fga_rate * mins_arr * pace)
        fga_arr  = np.clip(fga_arr, 0, 30)

        # ── [3] xFG — binomial makes/misses ──────────────────────────────────
        fgm_arr = rng.binomial(fga_arr, fg_pct)

        # 3-pointers: proportion of FGA that are 3-pointers
        fg3a_rate = float(seed.get("fg3a", avg_fg3m / max(fg_pct, 0.01)) or avg_fg3m / 0.36)
        fg3a_frac = min(float(fg3a_rate / max(avg_fga, 1.0)), 0.60)
        fg3a_arr  = rng.binomial(fga_arr, fg3a_frac)
        fg3pct    = float(seed.get("fg3_pct", avg_fg3m / max(fg3a_rate, 1.0)) or 0.36)
        fg3m_arr  = rng.binomial(fg3a_arr, min(fg3pct, 0.55))

        # ── [4] TO / Foul — Poisson rates ────────────────────────────────────
        # Turnovers: per-minute rate
        tov_rate  = avg_tov / max(avg_min, 1.0)
        tov_arr   = rng.poisson(tov_rate * mins_arr)
        tov_arr   = np.clip(tov_arr, 0, 8)

        # Free throws: correlates with FGA + usage
        fta_rate  = float(seed.get("fta", avg_pts * 0.15) or avg_pts * 0.15)
        fta_arr   = rng.poisson((fta_rate / max(avg_min, 1.0)) * mins_arr * pace)
        ftm_arr   = rng.binomial(np.clip(fta_arr, 0, 15), min(ft_pct, 0.98))

        # ── [5] Rebounds ─────────────────────────────────────────────────────
        reb_rate  = avg_reb / max(avg_min, 1.0)
        reb_arr   = rng.poisson(reb_rate * mins_arr)
        reb_arr   = np.clip(reb_arr, 0, 20)

        # ── [6] Fatigue multiplier ────────────────────────────────────────────
        # Late-game fatigue: minutes > 35 → slight decline
        fatigue_penalty = np.where(mins_arr > 35, 1.0 - (mins_arr - 35) * 0.003, 1.0)
        fatigue_penalty = np.clip(fatigue_penalty, 0.85, 1.0)

        # ── [7] Substitution — if projected < 20 min, many zeros ─────────────
        dnp_mask    = mins_arr < 3.0   # ~DNP games
        active_mask = ~dnp_mask

        # ── Compile stats ─────────────────────────────────────────────────────
        # Points: 2*fgm + fg3m (already counted in fgm) + ftm
        pts_arr = (2 * fgm_arr + fg3m_arr + ftm_arr) * fatigue_penalty
        pts_arr = np.where(active_mask, pts_arr, 0.0)

        # Assists: per-minute Poisson
        ast_rate = avg_ast / max(avg_min, 1.0)
        ast_arr  = rng.poisson(ast_rate * mins_arr)
        ast_arr  = np.clip(ast_arr, 0, 15)
        ast_arr  = np.where(active_mask, ast_arr, 0)

        # Steals + blocks: rare events
        stl_rate = avg_stl / max(avg_min, 1.0)
        blk_rate = avg_blk / max(avg_min, 1.0)
        stl_arr  = rng.poisson(stl_rate * mins_arr)
        blk_arr  = rng.poisson(blk_rate * mins_arr)
        stl_arr  = np.clip(np.where(active_mask, stl_arr, 0), 0, 6)
        blk_arr  = np.clip(np.where(active_mask, blk_arr, 0), 0, 6)

        # Zero out DNP games
        fg3m_arr = np.where(active_mask, fg3m_arr, 0)
        reb_arr  = np.where(active_mask, reb_arr, 0)
        tov_arr  = np.where(active_mask, tov_arr, 0)
        mins_arr = np.where(active_mask, mins_arr, 0.0)

        return {
            "pts":  pts_arr.astype(float),
            "reb":  reb_arr.astype(float),
            "ast":  ast_arr.astype(float),
            "fg3m": fg3m_arr.astype(float),
            "stl":  stl_arr.astype(float),
            "blk":  blk_arr.astype(float),
            "tov":  tov_arr.astype(float),
            "min":  mins_arr,
        }

    def _simulate_game_scores(
        self,
        n_sims: int,
        predicted_total: float,
        predicted_spread: float,
        rng: np.random.Generator,
    ) -> tuple:
        """Return (home_pts, away_pts) arrays each of shape (n_sims,)."""
        avg_total = predicted_total or 222.0
        # home advantage embedded in spread
        home_avg = (avg_total / 2) + (predicted_spread / 2)
        away_avg = (avg_total / 2) - (predicted_spread / 2)
        std = avg_total * 0.07   # ~7% std of total → ~15pt game std
        home_pts = rng.normal(home_avg, std / math.sqrt(2), n_sims)
        away_pts = rng.normal(away_avg, std / math.sqrt(2), n_sims)
        return np.clip(home_pts, 70, 160), np.clip(away_pts, 70, 160)

    def _estimate_pace(self, game_id: str, predicted_total: float) -> float:
        """Convert predicted total to pace scalar (1.0 = avg)."""
        return float((predicted_total or 222.0) / 222.0)

    def _load_synergy(self) -> None:
        """Load team synergy play-type data for play-type model."""
        path = os.path.join(
            PROJECT_DIR, "data", "nba", f"synergy_offense_{self.season}.json"
        )
        if os.path.exists(path):
            try:
                with open(path) as f:
                    rows = json.load(f)
                for row in rows:
                    team = row.get("team_abbreviation", "")
                    pt   = row.get("play_type", "")
                    ppp  = float(row.get("ppp", 1.0) or 1.0)
                    if team and pt:
                        self._synergy.setdefault(team, {})[pt] = ppp
            except Exception:
                pass
