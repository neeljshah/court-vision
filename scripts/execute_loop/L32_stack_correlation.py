"""L32_stack_correlation.py — Stack Correlation Engine (BUILD L32).

Identifies correlated player stacks within a DFS slate and recommends
bet overlays for high-correlation lineups.

Public API
----------
    compute_team_stack_correlations(team, fpts_data, *, min_correlation) -> StackCorrelation | None
    identify_game_stacks(slate, fpts_data, min_correlation) -> list[StackCorrelation]
    recommend_stack_bets(stack, current_lines) -> list[dict]

CLI
---
    python L32_stack_correlation.py analyze --slate path.json --fpts path.json
    python L32_stack_correlation.py recommend --team LAL --lines path.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parent.parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_N_SAMPLES: int = 1000
_MIN_TEAM_SIZE: int = 5
_TOP_N_PLAYERS: int = 3
_RNG_SEED: int = 42

# Default pairwise correlations between stat types (team-level stacking signal).
# Diagonal (same-stat pairs) represent within-team stat covariance.
_DEFAULT_CORR: Dict[tuple, float] = {
    ("PTS", "PTS"): 0.45,
    ("PTS", "AST"): 0.30,
    ("AST", "PTS"): 0.30,
    ("REB", "REB"): 0.25,
    ("STL", "STL"): 0.10,
}

# Cholesky target correlation for PTS-PTS player pairs (main sampling signal)
_PTS_PTS_CORR: float = _DEFAULT_CORR[("PTS", "PTS")]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class StackCorrelation:
    """Encapsulates a correlated player stack for a single team."""

    stack_key: str                   # e.g. "LAL_high_pace_lineup"
    players: List[str]               # player names in the stack
    correlated_stats: List[str]      # e.g. ["PTS", "AST", "REB"]
    correlation_matrix: np.ndarray   # n_players x n_players Pearson matrix
    expected_lift: float             # avg off-diagonal correlation * 100 (%)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_correlated_samples(
    means: List[float],
    stds: List[float],
    target_corr: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return (N_SAMPLES x n_players) array with Cholesky-injected correlation.

    All player-pairs share the same target_corr off-diagonal.  Diagonal is 1.0.
    The Cholesky decomposition is clamped to ensure PSD even for extreme inputs.

    Parameters
    ----------
    means       : Per-player PTS mean (Gaussian assumption).
    stds        : Per-player PTS std.
    target_corr : Desired Pearson correlation between all player pairs.
    rng         : Seeded numpy Generator.

    Returns
    -------
    np.ndarray shape (N_SAMPLES, n_players) — correlated stat draws.
    """
    n = len(means)
    # Build correlation matrix: 1 on diagonal, target_corr off-diagonal
    corr_mat = np.full((n, n), target_corr, dtype=float)
    np.fill_diagonal(corr_mat, 1.0)

    # Clamp to ensure PSD: eigenvalue floor at 1e-8
    eigvals, eigvecs = np.linalg.eigh(corr_mat)
    eigvals = np.maximum(eigvals, 1e-8)
    corr_mat = eigvecs @ np.diag(eigvals) @ eigvecs.T

    # Cholesky factor
    L = np.linalg.cholesky(corr_mat)

    # Draw independent standard normals → apply Cholesky → scale to each player
    z = rng.standard_normal(size=(_N_SAMPLES, n))
    correlated_z = z @ L.T  # (N_SAMPLES, n)

    means_arr = np.array(means, dtype=float)
    stds_arr = np.array(stds, dtype=float)
    stds_arr = np.maximum(stds_arr, 1e-6)  # guard zero-std

    return correlated_z * stds_arr[None, :] + means_arr[None, :]


def _pearson_matrix(samples: np.ndarray) -> np.ndarray:
    """Compute n_players x n_players Pearson correlation from (N, n) sample matrix.

    NaN values are coerced to 0.0; diagonal is forced to 1.0.
    """
    n = samples.shape[1]
    mat = np.corrcoef(samples.T)  # (n, n)
    if mat.ndim < 2:
        mat = np.eye(n)
    mat = np.where(np.isnan(mat), 0.0, mat)
    np.fill_diagonal(mat, 1.0)
    return mat


def _avg_off_diagonal(mat: np.ndarray) -> float:
    """Return mean of strictly off-diagonal elements."""
    n = mat.shape[0]
    if n < 2:
        return 0.0
    mask = ~np.eye(n, dtype=bool)
    return float(np.mean(mat[mask]))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_team_stack_correlations(
    team: str,
    fpts_data: Dict[str, dict],
    *,
    min_correlation: float = 0.3,
) -> Optional[StackCorrelation]:
    """Compute stack correlations for all players on a given team.

    Uses Cholesky-based correlated Gaussian draws (N=1000) for PTS, then
    computes empirical Pearson correlation across the player pool.

    Parameters
    ----------
    team            : Team abbreviation (e.g. "LAL").
    fpts_data       : {player_name: {"mean": float, "std": float, "team": str}}.
    min_correlation : Minimum avg off-diagonal correlation to return a stack.

    Returns
    -------
    StackCorrelation or None if team has <5 players or avg corr < min_correlation.
    """
    # Filter to team
    team_players = {
        name: info
        for name, info in fpts_data.items()
        if str(info.get("team", "")).upper() == team.upper()
    }

    if len(team_players) < _MIN_TEAM_SIZE:
        log.debug(
            "Team %s has %d players (< %d) — skipping stack.",
            team, len(team_players), _MIN_TEAM_SIZE,
        )
        return None

    names = list(team_players.keys())
    means: List[float] = []
    stds: List[float] = []

    for name in names:
        info = team_players[name]
        means.append(float(info.get("mean", 20.0)))
        stds.append(float(info.get("std", 5.0)))

    rng = np.random.default_rng(_RNG_SEED)
    samples = _build_correlated_samples(means, stds, _PTS_PTS_CORR, rng)
    corr_mat = _pearson_matrix(samples)
    avg_off_diag = _avg_off_diagonal(corr_mat)

    if avg_off_diag < min_correlation:
        log.debug(
            "Team %s avg_off_diag=%.3f < min_correlation=%.3f — no stack.",
            team, avg_off_diag, min_correlation,
        )
        return None

    expected_lift = avg_off_diag * 100.0
    correlated_stats = _infer_correlated_stats(avg_off_diag)

    log.info(
        "Stack found: %s | players=%d | avg_corr=%.3f | lift=%.1f%%",
        team, len(names), avg_off_diag, expected_lift,
    )

    return StackCorrelation(
        stack_key=f"{team}_high_pace_lineup",
        players=names,
        correlated_stats=correlated_stats,
        correlation_matrix=corr_mat,
        expected_lift=expected_lift,
    )


def _infer_correlated_stats(avg_corr: float) -> List[str]:
    """Return stat labels whose _DEFAULT_CORR same-stat value exceeds avg_corr."""
    stats: List[str] = []
    seen: set = set()
    for (s1, s2), v in _DEFAULT_CORR.items():
        if s1 == s2 and v >= avg_corr and s1 not in seen:
            stats.append(s1)
            seen.add(s1)
    # Always include PTS as the primary stacking stat
    if "PTS" not in seen:
        stats.insert(0, "PTS")
    return stats


def identify_game_stacks(
    slate: dict,
    fpts_data: Dict[str, dict],
    min_correlation: float = 0.3,
) -> List[StackCorrelation]:
    """Identify stacks for every team appearing in a slate.

    Parameters
    ----------
    slate           : {"games": [{"home": "LAL", "away": "DEN"}], "teams": [...]}
    fpts_data       : {player_name: {"mean": float, "std": float, "team": str}}
    min_correlation : Passed through to compute_team_stack_correlations.

    Returns
    -------
    List of StackCorrelation objects (one per qualifying team).
    """
    teams: List[str] = []

    # Collect teams from slate["teams"] first
    if "teams" in slate:
        teams.extend(str(t) for t in slate["teams"])

    # Also harvest home/away from games in case "teams" key is absent
    for game in slate.get("games", []):
        for side in ("home", "away"):
            t = str(game.get(side, ""))
            if t and t not in teams:
                teams.append(t)

    # Deduplicate while preserving order
    seen: set = set()
    unique_teams: List[str] = []
    for t in teams:
        if t not in seen:
            seen.add(t)
            unique_teams.append(t)

    stacks: List[StackCorrelation] = []
    for team in unique_teams:
        stack = compute_team_stack_correlations(
            team, fpts_data, min_correlation=min_correlation
        )
        if stack is not None:
            stacks.append(stack)

    log.info(
        "identify_game_stacks: checked %d teams → %d stacks found.",
        len(unique_teams), len(stacks),
    )
    return stacks


def recommend_stack_bets(
    stack: StackCorrelation,
    current_lines: Dict[str, dict],
) -> List[dict]:
    """Generate OVER bet recommendations for top players in a stack.

    Ranks stack.players by their PTS mean from fpts_data context embedded
    in the stack_key metadata.  Since StackCorrelation doesn't carry raw
    means, the caller passes current_lines which maps player → stat → line.
    Top-3 players (by order in stack.players, already sorted by caller if desired)
    are selected; players missing from current_lines are skipped.

    Parameters
    ----------
    stack         : StackCorrelation produced by compute_team_stack_correlations.
    current_lines : {player_name: {"PTS": float, "AST": float, ...}}

    Returns
    -------
    List of dicts, one per recommended bet::

        {
            "player": str,
            "stat": "PTS",
            "side": "OVER",
            "line": float,
            "stack_key": str,
            "correlation_boost": float,   # expected_lift / 100
        }

    At most _TOP_N_PLAYERS (3) recommendations are returned.
    """
    correlation_boost = stack.expected_lift / 100.0
    recommendations: List[dict] = []

    for player in stack.players:
        if len(recommendations) >= _TOP_N_PLAYERS:
            break
        lines = current_lines.get(player)
        if lines is None:
            log.debug("Player %r not in current_lines — skipping.", player)
            continue
        pts_line = lines.get("PTS")
        if pts_line is None:
            log.debug("Player %r has no PTS line — skipping.", player)
            continue

        recommendations.append(
            {
                "player": player,
                "stat": "PTS",
                "side": "OVER",
                "line": float(pts_line),
                "stack_key": stack.stack_key,
                "correlation_boost": correlation_boost,
            }
        )

    log.info(
        "recommend_stack_bets: %s → %d bet recs (boost=%.3f).",
        stack.stack_key, len(recommendations), correlation_boost,
    )
    return recommendations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_analyze(args: argparse.Namespace) -> None:
    slate_path = Path(args.slate)
    fpts_path = Path(args.fpts)

    if not slate_path.exists():
        log.error("Slate file not found: %s", slate_path)
        sys.exit(1)
    if not fpts_path.exists():
        log.error("FPTS file not found: %s", fpts_path)
        sys.exit(1)

    slate = json.loads(slate_path.read_text(encoding="utf-8"))
    fpts_data = json.loads(fpts_path.read_text(encoding="utf-8"))

    stacks = identify_game_stacks(slate, fpts_data, min_correlation=args.min_correlation)
    if not stacks:
        print("No qualifying stacks found.")
        return

    for s in stacks:
        print(
            f"{s.stack_key} | players={len(s.players)} "
            f"| lift={s.expected_lift:.1f}% | stats={s.correlated_stats}"
        )


def _cmd_recommend(args: argparse.Namespace) -> None:
    lines_path = Path(args.lines)
    if not lines_path.exists():
        log.error("Lines file not found: %s", lines_path)
        sys.exit(1)

    current_lines = json.loads(lines_path.read_text(encoding="utf-8"))

    # Build a synthetic fpts_data for the named team from the lines file if needed
    fpts_data: Dict[str, dict] = {}
    for player, stats in current_lines.items():
        pts_line = float(stats.get("PTS", 20.0))
        fpts_data[player] = {"mean": pts_line, "std": max(pts_line * 0.25, 3.0), "team": args.team}

    stack = compute_team_stack_correlations(args.team, fpts_data, min_correlation=0.3)
    if stack is None:
        print(f"No stack found for team {args.team}.")
        return

    recs = recommend_stack_bets(stack, current_lines)
    if not recs:
        print("No bet recommendations (players missing from lines).")
        return

    for rec in recs:
        print(
            f"{rec['player']} | {rec['stat']} OVER {rec['line']} "
            f"| boost={rec['correlation_boost']:.3f} | {rec['stack_key']}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="L32_stack_correlation",
        description="Stack Correlation Engine — identify and bet correlated DFS stacks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Find stacks across a full slate.")
    p_analyze.add_argument("--slate", required=True, help="Path to slate JSON.")
    p_analyze.add_argument("--fpts", required=True, help="Path to fpts_data JSON.")
    p_analyze.add_argument(
        "--min-correlation", type=float, default=0.3,
        dest="min_correlation",
        help="Minimum avg Pearson correlation to qualify as a stack (default 0.3).",
    )

    # recommend
    p_rec = sub.add_parser("recommend", help="Recommend bets for a single team stack.")
    p_rec.add_argument("--team", required=True, help="Team abbreviation (e.g. LAL).")
    p_rec.add_argument("--lines", required=True, help="Path to current_lines JSON.")

    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        _cmd_analyze(args)
    elif args.command == "recommend":
        _cmd_recommend(args)
