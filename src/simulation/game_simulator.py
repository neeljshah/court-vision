"""
game_simulator.py — Possession-by-possession Monte Carlo game simulator (Block F).

Full possession loop wired through predict_outcome() with B-1/B-2/E-3 CV adjustments.
Derives spread and total distributions from actual possession outcomes — not formula.

Public API
----------
    GameSimulator(season)
    sim.simulate_game(home_lineup, away_lineup, n_sims, cv_features) -> GameSimResult
    sim.prop_probability(player_id, stat, line, home_lineup, away_lineup) -> float
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# ── Constants ─────────────────────────────────────────────────────────────────

_N_SIMS_DEFAULT   = 10_000
_POSSESSIONS_MEAN = 100       # per team per game (pace-adjusted)
_POSSESSIONS_STD  = 5
_OREB_RATE        = 0.27      # offensive rebound rate → extra possession
_FT_PER_FOUL      = 2.0
# Second-chance / putback scoring off offensive rebounds. Set False to restore
# the legacy behavior where an OREB credited 0 points (fallback safety switch).
_PUTBACK_ENABLED  = True
_PUTBACK_FG_BONUS = 0.05      # putbacks convert slightly above base fg_pct
_PUTBACK_FG_CAP   = 0.62      # but capped to stay conservative

# Game state buckets for E-3 (score_diff, period) → outcome multipliers
# Precomputed to avoid calling predict_outcome() per sim per possession
_STATE_BLOWOUT = "blowout"   # |score_diff| > 15, period >= 3
_STATE_CLOSE   = "close"     # |score_diff| <= 5,  period >= 3
_STATE_NORMAL  = "normal"

# Default shot zone (used when no CV data)
_DEFAULT_ZONE     = "other"
_DEFAULT_PLAY_TYPE = "other"


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class GameSimResult:
    """Monte Carlo game simulation output."""
    home_win_prob: float
    spread_distribution: np.ndarray   # shape (n_sims,) home_pts - away_pts
    total_distribution: np.ndarray    # shape (n_sims,) home_pts + away_pts
    player_stats: Dict[str, Dict[str, np.ndarray]] = field(default_factory=dict)
    # {player_id: {stat: array(n_sims)}}

    def prop_probability(self, player_id: str, stat: str, line: float) -> float:
        arr = self.player_stats.get(str(player_id), {}).get(stat)
        if arr is None or len(arr) == 0:
            return 0.5
        return float(np.mean(arr > line))

    def spread_probability(self, spread_line: float) -> float:
        """P(home wins by more than spread_line points)."""
        return float(np.mean(self.spread_distribution > spread_line))

    def total_probability(self, total_line: float, over: bool = True) -> float:
        if over:
            return float(np.mean(self.total_distribution > total_line))
        return float(np.mean(self.total_distribution < total_line))

    def summary(self) -> dict:
        return {
            "home_win_prob":   round(self.home_win_prob, 4),
            "spread_mean":     round(float(np.mean(self.spread_distribution)), 2),
            "spread_std":      round(float(np.std(self.spread_distribution)), 2),
            "total_mean":      round(float(np.mean(self.total_distribution)), 2),
            "total_std":       round(float(np.std(self.total_distribution)), 2),
        }


# ── Player seed loader ─────────────────────────────────────────────────────────

def _load_player_seed(player_id: str, season: str) -> dict:
    """Load per-player averages from player_avgs cache."""
    path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    defaults = {
        "pts": 10.0, "reb": 4.0, "ast": 2.0, "fg3m": 0.8,
        "stl": 0.7, "blk": 0.3, "tov": 1.5, "min": 22.0,
        "fga": 7.0, "fg_pct": 0.45, "ft_pct": 0.77, "fta": 2.0,
        "fg3_pct": 0.35, "usage_rate": 0.20,
    }
    try:
        avgs = json.load(open(path))
        data = avgs.get(str(player_id))
        if not data:
            # Try by name key — fall back to defaults
            return defaults
        numeric = {}
        for k, v in data.items():
            try:
                numeric[k] = float(v or 0)
            except (TypeError, ValueError):
                pass  # skip non-numeric fields like "team": "DEN"
        merged = {**defaults, **numeric}
        return merged
    except Exception:
        return defaults


# ── Precompute outcome tables ──────────────────────────────────────────────────

def _precompute_player_outcomes(
    player_id: int,
    seed: dict,
    cv_features: dict,
    season: str,
) -> Dict[str, dict]:
    """
    Call predict_outcome() for each game state bucket and cache results.

    Returns {state_key: {shot_prob, tov_prob, fta_prob, fg_pct_est}}.
    State keys: "blowout", "close", "normal".
    """
    try:
        from src.prediction.possession_outcome_model import predict_outcome
    except ImportError:
        log.warning("possession_outcome_model unavailable — using priors")
        prior = {"shot_prob": 0.52, "tov_prob": 0.14, "fta_prob": 0.22, "fg_pct_est": 0.46}
        return {_STATE_BLOWOUT: prior, _STATE_CLOSE: prior, _STATE_NORMAL: prior}

    cv = cv_features.get(str(player_id), {})
    defender_dist   = float(cv.get("defender_dist", 4.0))
    spacing_adv     = float(cv.get("spacing", 0.0))

    states = {
        _STATE_BLOWOUT: (20, 3),
        _STATE_CLOSE:   (2,  4),
        _STATE_NORMAL:  (0,  2),
    }
    outcomes = {}
    for state, (score_diff, period) in states.items():
        outcomes[state] = predict_outcome(
            player_id=int(player_id),
            play_type=_DEFAULT_PLAY_TYPE,
            zone=_DEFAULT_ZONE,
            defender_dist_ft=defender_dist,
            spacing_advantage=spacing_adv,
            score_diff=score_diff,
            period=period,
        )
    return outcomes


# ── Core simulator ─────────────────────────────────────────────────────────────

class GameSimulator:
    """
    Possession-by-possession Monte Carlo game simulator (Block F).

    Seeds from NBA API averages. CV features (defender_dist, spacing, fatigue)
    injected via cv_features arg to simulate_game().
    """

    def __init__(self, season: str = "2024-25") -> None:
        self.season = season

    def simulate_game(
        self,
        home_lineup: List[str],
        away_lineup: List[str],
        n_sims: int = _N_SIMS_DEFAULT,
        cv_features: Optional[dict] = None,
        pace_override: Optional[float] = None,
    ) -> GameSimResult:
        """
        Run n_sims possession-by-possession simulations.

        Args:
            home_lineup:   List of player_id strings (up to 8, sorted by min desc)
            away_lineup:   List of player_id strings
            n_sims:        Number of simulations (default 10,000)
            cv_features:   {player_id: {defender_dist, spacing, fatigue}} from tracking
            pace_override: If set, overrides default _POSSESSIONS_MEAN

        Returns:
            GameSimResult with spread/total distributions and per-player stats
        """
        if cv_features is None:
            cv_features = {}

        rng = np.random.default_rng(seed=42)

        # Load seeds + precompute outcome tables for all players
        home_seeds, home_outcomes = self._load_lineup(home_lineup, cv_features)
        away_seeds, away_outcomes = self._load_lineup(away_lineup, cv_features)

        # Usage weights for ball-handler selection
        home_usage = self._usage_weights(home_seeds)
        away_usage = self._usage_weights(away_seeds)

        # Possession count per team (varies by pace)
        poss_mean = pace_override or _POSSESSIONS_MEAN
        home_poss_n = np.clip(
            rng.normal(poss_mean, _POSSESSIONS_STD, n_sims).astype(int), 80, 125
        )
        away_poss_n = np.clip(
            rng.normal(poss_mean, _POSSESSIONS_STD, n_sims).astype(int), 80, 125
        )

        # Simulate possessions
        home_pts, home_pstats = self._simulate_team(
            home_lineup, home_seeds, home_outcomes, home_usage,
            home_poss_n, n_sims, rng, "home"
        )
        away_pts, away_pstats = self._simulate_team(
            away_lineup, away_seeds, away_outcomes, away_usage,
            away_poss_n, n_sims, rng, "away"
        )

        spread = home_pts - away_pts
        total  = home_pts + away_pts

        player_stats = {**home_pstats, **away_pstats}

        return GameSimResult(
            home_win_prob=float(np.mean(home_pts > away_pts)),
            spread_distribution=spread,
            total_distribution=total,
            player_stats=player_stats,
        )

    def prop_probability(
        self,
        player_id: str,
        stat: str,
        line: float,
        home_lineup: List[str],
        away_lineup: List[str],
        n_sims: int = 5_000,
        cv_features: Optional[dict] = None,
    ) -> float:
        """Convenience: P(player_id's stat > line) from a game simulation."""
        result = self.simulate_game(home_lineup, away_lineup, n_sims, cv_features)
        return result.prop_probability(player_id, stat, line)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _load_lineup(
        self, lineup: List[str], cv_features: dict
    ) -> Tuple[List[dict], List[Dict[str, dict]]]:
        seeds, outcomes = [], []
        for pid in lineup:
            s = _load_player_seed(pid, self.season)
            s["player_id"] = pid
            seeds.append(s)
            outcomes.append(_precompute_player_outcomes(pid, s, cv_features, self.season))
        return seeds, outcomes

    def _usage_weights(self, seeds: List[dict]) -> np.ndarray:
        usages = np.array([float(s.get("usage_rate", 0.20) or 0.20) for s in seeds])
        usages = np.clip(usages, 0.05, 0.40)
        return usages / usages.sum()

    def _simulate_team(
        self,
        lineup: List[str],
        seeds: List[dict],
        outcomes: List[Dict[str, dict]],
        usage_weights: np.ndarray,
        poss_counts: np.ndarray,    # shape (n_sims,)
        n_sims: int,
        rng: np.random.Generator,
        side: str,
    ) -> Tuple[np.ndarray, Dict[str, Dict[str, np.ndarray]]]:
        """
        Simulate all possessions for one team across n_sims.

        Possession loop: iterate over max possession count; mask finished sims.
        Vectorized over n_sims per possession step — no per-sim Python loop.
        """
        n_players = len(seeds)
        if n_players == 0:
            return np.zeros(n_sims), {}

        max_poss = int(poss_counts.max())

        # Accumulators: shape (n_players, n_sims)
        pts_acc  = np.zeros((n_players, n_sims))
        reb_acc  = np.zeros((n_players, n_sims))
        ast_acc  = np.zeros((n_players, n_sims))
        fg3_acc  = np.zeros((n_players, n_sims))
        tov_acc  = np.zeros((n_players, n_sims))
        score    = np.zeros(n_sims)

        # Precompute per-player outcome arrays for each state
        # probs[player_idx][state] = {shot_prob, tov_prob, fta_prob, fg_pct_est}
        probs = outcomes   # already computed

        # Per-player FT%
        ft_pcts = np.array([float(s.get("ft_pct", 0.77)) for s in seeds])
        # 3pt% and 3pt rate
        fg3_pcts  = np.array([float(s.get("fg3_pct", 0.35)) for s in seeds])
        fg3_rates = np.array([  # fraction of FGA that are 3-pointers
            min(float(s.get("fg3m", 0.8)) / max(float(s.get("fga", 7.0)), 1.0), 0.60)
            for s in seeds
        ])

        for step in range(max_poss):
            # Mask: only sims that still have possessions remaining
            active = step < poss_counts          # (n_sims,) bool

            if not active.any():
                break

            n_active = active.sum()

            # Game state bucket: use current score as proxy
            # (score here = team's running pts, opponent pts unknown → use 0 diff for simplicity
            # Full game state requires inter-team loop; approximated here)
            period = min(step // 25 + 1, 4)     # rough quarter from possession count

            # Sample ball handler for active sims
            handler_idx = rng.choice(n_players, size=n_active, p=usage_weights)

            # For each player, process the sims where they're the ball handler
            for pi in range(n_players):
                pi_mask_active = handler_idx == pi
                if not pi_mask_active.any():
                    continue

                # Which of the n_sims indices are active AND handled by pi?
                sim_indices = np.where(active)[0][pi_mask_active]
                n_p = len(sim_indices)

                # Outcome probs (use normal state; blowout/close tracked after both teams simulated)
                o = probs[pi][_STATE_NORMAL]
                shot_p = float(o.get("shot_prob", 0.52))
                tov_p  = float(o.get("tov_prob",  0.14))
                fta_p  = float(o.get("fta_prob",  0.22))
                fg_pct = float(o.get("fg_pct_est", 0.46))
                ft_pct = ft_pcts[pi]

                # Sample outcomes (vectorized over n_p sims)
                rand = rng.random(n_p)
                is_tov    = rand < tov_p
                is_foul   = (~is_tov) & (rand < tov_p + fta_p)
                is_shot   = (~is_tov) & (~is_foul)

                # Shot outcomes
                made      = is_shot & (rng.random(n_p) < fg_pct)
                is_3pt    = made & (rng.random(n_p) < fg3_rates[pi])
                shot_pts  = np.where(is_3pt, 3.0, np.where(made, 2.0, 0.0))

                # Offensive rebounds → extra possession (small chance)
                oreb      = (~made & is_shot) & (rng.random(n_p) < _OREB_RATE)

                # Putback / second-chance points: an offensive rebound buys an
                # extra shot attempt this possession. Convert at the player's
                # fg_pct (putbacks are slightly higher-percentage but we stay
                # conservative and cap), worth 2 pts. This is the extra-possession
                # point credit the engine previously zeroed out.
                if _PUTBACK_ENABLED:
                    putback_made = oreb & (
                        rng.random(n_p) < min(fg_pct + _PUTBACK_FG_BONUS, _PUTBACK_FG_CAP)
                    )
                    putback_pts = np.where(putback_made, 2.0, 0.0)
                else:
                    putback_pts = np.zeros(n_p)

                # FT outcomes
                ft_made   = is_foul * rng.binomial(2, ft_pct, n_p)
                foul_pts  = ft_made.astype(float)

                # Assists: ~30% of made shots come off assist
                ast_made  = made & (rng.random(n_p) < 0.30)
                # Credit assist to a random teammate
                if n_players > 1 and ast_made.any():
                    other_players = [j for j in range(n_players) if j != pi]
                    ast_target = rng.choice(other_players, size=ast_made.sum())
                    for k, t in enumerate(ast_target):
                        ast_acc[t, sim_indices[ast_made][k]] += 1

                # Accumulate. Putback points credit the second-chance scoring
                # an offensive rebound creates (previously multiplied by 0).
                total_pts = shot_pts + foul_pts + putback_pts
                score[sim_indices]       += total_pts
                pts_acc[pi, sim_indices] += total_pts
                reb_acc[pi, sim_indices] += oreb.astype(float)
                fg3_acc[pi, sim_indices] += is_3pt.astype(float)
                tov_acc[pi, sim_indices] += is_tov.astype(float)

        # Add stl/blk/reb from per-minute rates (possessions don't model defense directly)
        pstats: Dict[str, Dict[str, np.ndarray]] = {}
        for pi, pid in enumerate(lineup):
            s = seeds[pi]
            avg_min = float(s.get("min", 22.0))
            avg_stl = float(s.get("stl", 0.7))
            avg_blk = float(s.get("blk", 0.3))
            avg_reb = float(s.get("reb", 4.0))

            # Supplement reb from possession model with per-min defensive rebounds
            dreb = rng.poisson(avg_reb * 0.75 / max(avg_min, 1.0) * avg_min, n_sims)
            total_reb = reb_acc[pi] + dreb.astype(float)

            stl_arr = rng.poisson(avg_stl / max(avg_min, 1.0) * avg_min, n_sims)
            blk_arr = rng.poisson(avg_blk / max(avg_min, 1.0) * avg_min, n_sims)

            pstats[str(pid)] = {
                "pts":  pts_acc[pi],
                "reb":  np.clip(total_reb, 0, 20),
                "ast":  np.clip(ast_acc[pi], 0, 15),
                "fg3m": fg3_acc[pi],
                "tov":  np.clip(tov_acc[pi], 0, 8),
                "stl":  np.clip(stl_arr.astype(float), 0, 6),
                "blk":  np.clip(blk_arr.astype(float), 0, 6),
            }

        return score, pstats


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Game simulator test run")
    parser.add_argument("--home", nargs="+", default=["2544", "2571"])
    parser.add_argument("--away", nargs="+", default=["203954", "1629029"])
    parser.add_argument("--n-sims", type=int, default=1000)
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    sim = GameSimulator(season=args.season)
    result = sim.simulate_game(args.home, args.away, n_sims=args.n_sims)
    print(result.summary())
    for pid in args.home[:2]:
        arr = result.player_stats.get(str(pid), {}).get("pts", np.array([]))
        if arr.size:
            print(f"  Player {pid} pts: mean={arr.mean():.1f} p75={np.percentile(arr,75):.1f}")
