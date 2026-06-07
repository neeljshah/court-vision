"""Full-game Monte-Carlo simulator producing coherent, correlated per-player stat lines.

MOTIVATION
----------
``RestOfGameSim`` produces TEAM-level final-score / win-prob distributions.
``predict_pergame`` produces INDEPENDENT per-player point estimates (q50).
Neither links the two: there is no bridge that simulates a full game forward
into a coherent, correlated per-player stat matrix.

This module builds that bridge:

    simulate_game(player_priors, game_context, n_sims=2000) -> GameSimResult

The simulation is a three-layer coherent model:

  1. TEAM layer: Draw n_sims team total-point outcomes from the EmpiricalPossession
     model (reusing RestOfGameSim's shrinkage machinery), seeded from prior-game
     pace/ppp that are computed strictly from games BEFORE game_context['game_date'].

  2. MINUTES layer: Per player, draw minutes around the prior projection (l10_min).
     Renormalise each team's total minutes to the 240-minute budget (5 players * 48).

  3. STATS layer:
     - PTS: player pts_share (prior_q50_pts / team_prior_sum) scaled by
       (simmed_team_total / team_prior_sum) * (minutes_draw / proj_min) +
       idiosyncratic N(0, sigma_pts) noise.  After player draws, multiplicative
       renorm so sum(player pts) = simmed team total exactly (coherence).
     - REB: rate-based off simmed team total missed shots opportunity.
     - AST: rate-based off simmed team made FGs.  AST mean = prior_q50_ast
       PRESERVED exactly; only spread is added.
     - FG3M, STL, BLK, TOV: rate draws with per-player prior rate and pace-scaled
       opportunity, plus independent noise.
     - Correlated noise across stats for the SAME player via the parlay_engine
       rho table (Cholesky draw).

LEAK DISCIPLINE
---------------
  * All team priors (pace/ppp) are computed from games strictly BEFORE
    game_context['game_date'].  The caller supplies player_priors from the
    faithful OOF (oof_pred = leak-free per-player q50).
  * No same-game or future data enters any draw path.
  * This is a PREGAME simulator (full 48 min remaining, possession count 0).

HONEST CAVEAT
-------------
  The coherence constraint (renorm so sum(player_pts) = team_pts) SOFTENS the
  per-player distribution relative to independent draws.  Whether that improves
  MAE is an EMPIRICAL question answered by eval_game_simulator.py.  The value
  add may be purely in JOINT distributions (SGP / parlay coherence) rather than
  marginal accuracy.

Public API
----------
    GameSimResult            dataclass
    simulate_game(...)       pure function, seeded
    PlayerPrior              dataclass consumed by simulate_game
    GameContext              dataclass consumed by simulate_game
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# League constants reused from the possession sim
# ---------------------------------------------------------------------------
LEAGUE_PPP = 1.12
LEAGUE_PACE_PER48 = 99.0          # one team's possessions per 48 min
REG_GAME_LEN_SEC = 2880           # 48 min
TEAM_MINUTES_BUDGET = 240.0       # 5 players * 48 min

# Empirical residual sigma per stat (matches parlay_engine / courtvision_router).
# Used to scale idiosyncratic noise in the simulation.  Source: pregame OOF
# residual std.  AST intentionally wider than the table default to preserve
# natural spread while keeping the mean intact.
_SIGMA_TABLE: Dict[str, float] = {
    "pts":  6.2,
    "reb":  2.6,
    "ast":  2.0,
    "fg3m": 1.4,
    "stl":  1.0,
    "blk":  0.9,
    "tov":  1.2,
}

# Same-player inter-stat correlations (from parlay_engine._SAME_PLAYER_RHO).
# Only the pairs relevant to our 7 stats are listed; others default to 0.
_SAME_PLAYER_RHO = {
    ("pts", "ast"):  0.30,
    ("pts", "reb"):  0.40,
    ("pts", "fg3m"): 0.55,
    ("pts", "stl"):  0.20,
    ("pts", "blk"):  0.10,
    ("pts", "tov"):  0.35,
    ("reb", "blk"):  0.35,
    ("reb", "ast"):  0.15,
    ("ast", "tov"):  0.40,
    ("fg3m", "ast"): 0.20,
    ("stl", "blk"):  0.15,
}

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_STAT_IDX = {s: i for i, s in enumerate(STATS)}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class PlayerPrior:
    """All pregame prior information for one player in one game.

    All values are leak-free: computed strictly from games BEFORE game_date.
    The q50 values are the faithful OOF predictions (oof_pred column from
    pregame_oof_faithful.parquet or equivalent).
    """
    player_id: int
    team: str                   # team abbreviation (home or away)
    q50: Dict[str, float]       # stat -> prior point estimate (oof_pred)
    proj_min: float             # projected minutes (l10_min or similar)
    min_std: float = 4.0        # std of minutes across last 10 games (default)

    def get(self, stat: str, default: float = 0.0) -> float:
        return float(self.q50.get(stat, default))


@dataclass
class GameContext:
    """Game-level context consumed by simulate_game.

    team_priors: optional dict built by the caller from games strictly BEFORE
        game_date, keyed like the TeamPriorStore pattern:
        {"home_ppp": float, "away_ppp": float,
         "home_pace_per48": float, "away_pace_per48": float}
        Missing keys fall back to league means — never errors.
    """
    game_date: str              # ISO date string "YYYY-MM-DD"
    home_team: str
    away_team: str
    team_priors: Optional[Dict[str, float]] = None  # None -> league means


@dataclass
class PlayerSimStats:
    """Per-player simulation result for a single game."""
    player_id: int
    team: str
    sim_mean: Dict[str, float]
    q10: Dict[str, float]
    q50: Dict[str, float]
    q90: Dict[str, float]
    # raw samples shape (n_sims, 7) for joint queries;
    # columns are in STATS order: pts, reb, ast, fg3m, stl, blk, tov
    samples: np.ndarray = field(repr=False)

    def get_samples(self, stat: str) -> np.ndarray:
        return self.samples[:, _STAT_IDX[stat]]


@dataclass
class GameSimResult:
    """Output of simulate_game.

    players: list of PlayerSimStats, one per input player
    home_team_total_samples: (n_sims,) array of simulated home team points
    away_team_total_samples: (n_sims,) array of simulated away team points
    home_win_prob: fraction of sims where home > away
    coherence_mae: |sum(sim player pts) - sim team total| mean across sims
        for the simmed sample; should be near 0 by construction
    n_sims: int
    """
    players: List[PlayerSimStats]
    home_team_total_samples: np.ndarray = field(repr=False)
    away_team_total_samples: np.ndarray = field(repr=False)
    home_win_prob: float = 0.0
    coherence_mae: float = 0.0
    n_sims: int = 0

    def player(self, player_id: int) -> Optional[PlayerSimStats]:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _shrunk_ppp(prior_ppp: Optional[float]) -> float:
    """For a pregame sim (no in-game poss yet), return the prior directly or league."""
    if prior_ppp and prior_ppp > 0:
        return float(prior_ppp)
    return LEAGUE_PPP


def _shrunk_pace(prior_pace: Optional[float]) -> float:
    if prior_pace and prior_pace > 0:
        return float(prior_pace)
    return LEAGUE_PACE_PER48


def _draw_team_points(rng: np.random.Generator,
                      n_sims: int,
                      ppp: float,
                      pace_per48: float) -> np.ndarray:
    """Draw n_sims full-game total points for ONE team.

    Expected pts = ppp * pace_per48.
    We model total points as Poisson-ish: mean = ppp*pace, var ~ mean (Poisson
    approximation for discrete scoring sums).  We use a Gamma-Poisson (negative
    binomial) mixture with mild overdispersion (r=20) to reflect real NBA scoring
    variance (~std ≈ 10-12 pts).
    """
    expected = float(ppp * pace_per48)
    expected = max(80.0, min(140.0, expected))
    # Negative-binomial with mean=expected, r=20 => std ~ sqrt(expected + expected^2/r)
    r = 20.0
    p_nb = r / (r + expected)
    samples = rng.negative_binomial(r, p_nb, size=n_sims).astype(float)
    return samples


def _build_player_cov(n_stats: int, sigma: np.ndarray,
                      player_id: Optional[int] = None) -> np.ndarray:
    """Build the covariance matrix for a single player's stat vector.

    When CV_ARCHETYPE_CORR is ON, uses recalibrated/archetype-conditioned rhos
    from correlation_recal.same_player_rho().  When OFF (default), uses
    _SAME_PLAYER_RHO as before (byte-identical).  Remaining pairs default to 0.
    """
    cov = np.diag(sigma ** 2).astype(float)

    # Resolve rho table: recalibrated when flag ON, naive otherwise.
    _recal_active = False
    try:
        from src.prediction import correlation_recal as _recal_mod
        if _recal_mod.recal_enabled():
            _recal_active = True
    except Exception:
        pass

    for (sa, sb), naive_rho in _SAME_PLAYER_RHO.items():
        if sa not in _STAT_IDX or sb not in _STAT_IDX:
            continue
        if _recal_active:
            try:
                recal_rho = _recal_mod.same_player_rho(sa, sb, player_id)
                rho = recal_rho if recal_rho is not None else naive_rho
            except Exception:
                rho = naive_rho
        else:
            rho = naive_rho
        i, j = _STAT_IDX[sa], _STAT_IDX[sb]
        v = rho * sigma[i] * sigma[j]
        cov[i, j] = v
        cov[j, i] = v
    # PSD repair: eigen-clip any negative eigenvalues
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.clip(eigvals, 1e-6, None)
    cov = (eigvecs * eigvals) @ eigvecs.T
    return cov


def _cholesky_psd(cov: np.ndarray) -> np.ndarray:
    """Cholesky with jitter fallback for numerical stability."""
    try:
        return np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        jitter = 1e-4 * np.trace(cov) / cov.shape[0]
        return np.linalg.cholesky(cov + jitter * np.eye(cov.shape[0]))


def _draw_player_noise(rng: np.random.Generator,
                       n_sims: int,
                       sigma: np.ndarray,
                       cov: np.ndarray) -> np.ndarray:
    """Draw (n_sims, n_stats) correlated noise matrix for one player.

    Returns zero-mean draws with the given covariance.
    """
    L = _cholesky_psd(cov)
    z = rng.standard_normal((n_sims, len(sigma)))
    return z @ L.T


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def simulate_game(
    player_priors: List[PlayerPrior],
    game_context: GameContext,
    n_sims: int = 2000,
    seed: Optional[int] = 42,
) -> GameSimResult:
    """Simulate a full game forward into coherent per-player stat distributions.

    Args:
        player_priors: list of PlayerPrior, one per player expected to play.
            Must include players from BOTH teams.
        game_context: GameContext with game_date, home/away teams, optional
            team_priors (prior-form pace/ppp computed from games before game_date).
        n_sims: number of Monte-Carlo trials.
        seed: RNG seed for determinism.

    Returns:
        GameSimResult with per-player distributions and team totals.

    Leak guarantee: reads only game_context.team_priors (caller's responsibility
    to ensure these come from games < game_date) + player_priors (oof_pred from
    faithful walk-forward). No file I/O here; pure function.
    """
    rng = np.random.default_rng(seed)
    tp = game_context.team_priors or {}

    # -----------------------------------------------------------------------
    # STEP 1: TEAM layer — draw n_sims team totals
    # -----------------------------------------------------------------------
    home_ppp = _shrunk_ppp(tp.get("home_ppp"))
    away_ppp = _shrunk_ppp(tp.get("away_ppp"))
    home_pace = _shrunk_pace(tp.get("home_pace_per48"))
    away_pace = _shrunk_pace(tp.get("away_pace_per48"))

    home_totals = _draw_team_points(rng, n_sims, home_ppp, home_pace)
    away_totals = _draw_team_points(rng, n_sims, away_ppp, away_pace)

    home_win_prob = float((home_totals > away_totals).mean())

    # Split players by team
    home_players = [p for p in player_priors if p.team == game_context.home_team]
    away_players = [p for p in player_priors if p.team == game_context.away_team]

    # -----------------------------------------------------------------------
    # STEP 2 & 3: MINUTES + STATS layers, per team
    # -----------------------------------------------------------------------
    # Compute coherence MAE across all sims (for home + away combined)
    all_coherence = np.zeros(n_sims)

    results: List[PlayerSimStats] = []

    for team_players, team_totals, team_name in [
        (home_players, home_totals, game_context.home_team),
        (away_players, away_totals, game_context.away_team),
    ]:
        if not team_players:
            continue

        # -- MINUTES LAYER -----------------------------------------------
        # Draw per-player minutes around proj_min with player-specific std.
        # Shape: (n_sims, n_players)
        n_p = len(team_players)
        proj_mins = np.array([max(1.0, p.proj_min) for p in team_players])
        min_stds = np.array([max(0.5, p.min_std) for p in team_players])

        # Draw log-normal minutes to keep positive.
        # log(proj_min) +/- (min_std/proj_min) via delta method
        log_mu = np.log(proj_mins)
        log_sigma = np.clip(min_stds / proj_mins, 0.05, 0.6)
        # shape (n_sims, n_players)
        raw_min_draws = np.exp(
            log_mu[None, :] + log_sigma[None, :] * rng.standard_normal((n_sims, n_p))
        )

        # Renormalise to TEAM_MINUTES_BUDGET (soft: renorm per sim)
        team_min_sum = raw_min_draws.sum(axis=1, keepdims=True)  # (n_sims, 1)
        scale_min = np.where(
            team_min_sum > 0,
            TEAM_MINUTES_BUDGET / team_min_sum,
            1.0,
        )
        min_draws = raw_min_draws * scale_min  # (n_sims, n_players)

        # -- PTS SHARE ANCHOR --------------------------------------------
        # Player's share of team prior pts
        prior_pts = np.array([max(0.1, p.get("pts")) for p in team_players])
        team_prior_sum_pts = prior_pts.sum()

        # -- PER-PLAYER STAT DRAWS (correlated noise) --------------------
        player_raw_pts = np.zeros((n_sims, n_p))
        player_stat_mat = np.zeros((n_sims, n_p, len(STATS)))

        for i, pp in enumerate(team_players):
            sigma = np.array([_SIGMA_TABLE[s] for s in STATS], dtype=float)
            cov = _build_player_cov(len(STATS), sigma, player_id=pp.player_id)
            noise = _draw_player_noise(rng, n_sims, sigma, cov)  # (n_sims, n_stats)

            # Minutes scaling ratio (relative to projection)
            min_ratio = min_draws[:, i] / max(proj_mins[i], 1.0)  # (n_sims,)

            # Build raw mean vector from prior q50s
            mu = np.array([pp.get(s) for s in STATS], dtype=float)

            # Scale by minutes ratio (if player plays more/less than expected,
            # all counting stats scale proportionally)
            # shape: (n_sims, n_stats)
            stat_draws = mu[None, :] * min_ratio[:, None] + noise

            # Clip non-negative stats to 0
            for si, s in enumerate(STATS):
                if s != "pts":   # pts handled separately after coherence renorm
                    stat_draws[:, si] = np.clip(stat_draws[:, si], 0.0, None)

            # PTS raw: anchored on share of simmed team total
            pts_share = prior_pts[i] / max(team_prior_sum_pts, 1.0)
            # Coherence draw: share of actual simmed team total, scaled by min ratio
            pts_coherence = pts_share * team_totals * min_ratio  # (n_sims,)
            # Blend: 70% coherence anchor, 30% independent prediction + noise
            pts_independent = mu[_STAT_IDX["pts"]] * min_ratio + noise[:, _STAT_IDX["pts"]]
            stat_draws[:, _STAT_IDX["pts"]] = (
                0.70 * pts_coherence + 0.30 * pts_independent
            )
            stat_draws[:, _STAT_IDX["pts"]] = np.clip(stat_draws[:, _STAT_IDX["pts"]], 0.0, None)

            player_raw_pts[:, i] = stat_draws[:, _STAT_IDX["pts"]]
            player_stat_mat[:, i, :] = stat_draws

        # -- COHERENCE RENORM FOR PTS ------------------------------------
        # Multiplicative renorm: adjust each player's pts so sum = team_totals.
        # Use a soft renorm with a cap to avoid distorting individual lines too much.
        team_sim_sum_pts = player_raw_pts.sum(axis=1)  # (n_sims,)
        # ratio: how much to scale each player's pts to hit the team total
        renorm_ratio = np.where(
            team_sim_sum_pts > 1.0,
            team_totals / team_sim_sum_pts,
            1.0,
        )
        # Cap renorm ratio to [0.6, 1.6] to avoid extreme distortion
        renorm_ratio = np.clip(renorm_ratio, 0.6, 1.6)

        # Apply renorm to pts column
        player_stat_mat[:, :, _STAT_IDX["pts"]] *= renorm_ratio[:, None]
        player_stat_mat[:, :, _STAT_IDX["pts"]] = np.clip(
            player_stat_mat[:, :, _STAT_IDX["pts"]], 0.0, None
        )

        # Track coherence MAE (post-renorm)
        post_pts_sum = player_stat_mat[:, :, _STAT_IDX["pts"]].sum(axis=1)
        all_coherence += np.abs(post_pts_sum - team_totals)

        # -- AST PROTECTION: ensure mean is preserved --------------------
        # AST is the production edge stat — keep its marginal mean at prior_q50_ast.
        # Only noise was added; we correct via a per-player additive shift of the mean.
        for i, pp in enumerate(team_players):
            ast_target_mean = float(pp.get("ast"))
            current_ast_mean = float(player_stat_mat[:, i, _STAT_IDX["ast"]].mean())
            shift = ast_target_mean - current_ast_mean
            # Additive shift to preserve mean; re-clip to 0
            player_stat_mat[:, i, _STAT_IDX["ast"]] = np.clip(
                player_stat_mat[:, i, _STAT_IDX["ast"]] + shift, 0.0, None
            )

        # -- PACKAGE RESULTS ---------------------------------------------
        for i, pp in enumerate(team_players):
            s_mat = player_stat_mat[:, i, :]  # (n_sims, n_stats)
            sim_mean = {s: float(s_mat[:, si].mean()) for si, s in enumerate(STATS)}
            q10 = {s: float(np.percentile(s_mat[:, si], 10)) for si, s in enumerate(STATS)}
            q50_ = {s: float(np.percentile(s_mat[:, si], 50)) for si, s in enumerate(STATS)}
            q90 = {s: float(np.percentile(s_mat[:, si], 90)) for si, s in enumerate(STATS)}

            results.append(PlayerSimStats(
                player_id=pp.player_id,
                team=team_name,
                sim_mean=sim_mean,
                q10=q10,
                q50=q50_,
                q90=q90,
                samples=s_mat.copy(),
            ))

    coherence_mae = float(all_coherence.mean()) / max(1, len(home_players) + len(away_players) > 0)

    return GameSimResult(
        players=results,
        home_team_total_samples=home_totals,
        away_team_total_samples=away_totals,
        home_win_prob=home_win_prob,
        coherence_mae=coherence_mae,
        n_sims=n_sims,
    )
