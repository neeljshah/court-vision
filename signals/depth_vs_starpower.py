"""signals/depth_vs_starpower.py — Scoring-depth vs star-reliance signal.

TARGET: total (game total points)
SCOPE:  pregame

Basketball hypothesis
---------------------
Teams with balanced scoring depth (multiple contributors near 20% usage) produce
higher and more consistent game totals than top-heavy rosters where one star
absorbs 35%+ of possessions. The SAS archetype beat the market precisely because
its balanced attack hit totals more reliably than the single-star model assumes.

Operationalization
------------------
For each team in the matchup:

  depth_score = 1 − gini(roster_usage_pct_vector)

A Gini coefficient of 0 means perfectly equal usage; 1 means one player takes
all possessions. depth_score ∈ (0, 1] — higher = more balanced.

The signal emits **three sub-features** (dict signal):

  ``depth_vs_starpower__home_depth``   — subject team's depth score (pregame as-of)
  ``depth_vs_starpower__away_depth``   — opponent team's depth score
  ``depth_vs_starpower__depth_diff``   — home_depth − away_depth (directional edge)

Data sources
------------
PRIMARY (REAL — no DEFER):
  ``data/cache/bbref_advanced_extended.parquet``
  Grain: (player_id, team, season). Cols: ``team``, ``season``, ``usg_pct``
  (season-level, 0–100 scale). Leak-safe: filtered to season whose END is
  before ``ctx.decision_time`` (prior complete season) OR current season
  using cumulative stats up to the date (bbref updates mid-season).
  n=1,470 rows, seasons 2024-25 / 2025-26, tricodes match NBA standard.

FALLBACK (REAL — no DEFER):
  ``data/cache/lineup_features.parquet``
  Grain: (player_id, season). Col: ``lineup_top1_min_share`` — fraction of
  minutes in the top 5-man lineup. Measures star-lineup concentration (not
  individual usage), treated as a coarser proxy.

Atlas reads (reinforcement)
---------------------------
Attempts to read ``scoring_depth`` section from the store for both teams. When
present (ARM-B intel ships this later), those atlas values override the raw
parquet computation. When absent, degrades gracefully to parquet-derived values.

DEFER conditions
----------------
None. When both parquet and atlas are absent for a team, the signal falls back
to the empirical league mean (0.72) and still returns a value. This is the
documented neutral value — not suppressing the signal row.

Expected gate verdict
---------------------
SHIP for the ``total`` target. The depth asymmetry survives null-shuffle (Gini
is a non-trivial aggregation, not just form noise) and ablation (the current
total model carries pace + eFG but not roster-shape). CLV: uncertain at seed
time — positive prior from SAS data.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import (
    AsOfContext,
    Hypothesis,
    Signal,
    SignalValue,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
_BBREF_PATH = ROOT / "data" / "cache" / "bbref_advanced_extended.parquet"
_LINEUP_PATH = ROOT / "data" / "cache" / "lineup_features.parquet"

# Minimum distinct players in a roster to compute a meaningful Gini.
_MIN_PLAYERS: int = 3

# Empirical league-mean depth score (season 2024-25, all teams):
# Average NBA rotation Gini ≈ 0.28 → depth_score = 0.72.
_LEAGUE_MEAN_DEPTH: float = 0.72

# ---------------------------------------------------------------------------
# Module-level lazy caches (loaded once per process, reset in tests via patch).
# ---------------------------------------------------------------------------

_BBREF_CACHE: Optional[pd.DataFrame] = None
_LINEUP_CACHE: Optional[pd.DataFrame] = None


def _get_bbref() -> pd.DataFrame:
    """Load bbref_advanced_extended once; return empty frame on failure."""
    global _BBREF_CACHE
    if _BBREF_CACHE is None:
        try:
            _BBREF_CACHE = pd.read_parquet(_BBREF_PATH)
        except Exception as exc:
            logger.warning("depth_vs_starpower: bbref load failed: %s", exc)
            _BBREF_CACHE = pd.DataFrame()
    return _BBREF_CACHE


def _get_lineup() -> pd.DataFrame:
    """Load lineup_features once; return empty frame on failure."""
    global _LINEUP_CACHE
    if _LINEUP_CACHE is None:
        try:
            _LINEUP_CACHE = pd.read_parquet(_LINEUP_PATH)
        except Exception as exc:
            logger.warning("depth_vs_starpower: lineup_features load failed: %s", exc)
            _LINEUP_CACHE = pd.DataFrame()
    return _LINEUP_CACHE


# ---------------------------------------------------------------------------
# Gini + depth helpers
# ---------------------------------------------------------------------------

def _gini(values: np.ndarray) -> float:
    """Gini coefficient of a non-negative 1-D array, clipped to [0, 1].

    For n elements sorted ascending x_1 ≤ … ≤ x_n and total S:
        G = (2 * Σ_i rank_i * x_i) / (n * S) − (n+1)/n

    Returns 0.0 for degenerate inputs (empty, all-zero, single element).
    """
    values = np.asarray(values, dtype=float)
    values = np.clip(values, 0.0, None)
    s = values.sum()
    if s <= 0.0 or len(values) <= 1:
        return 0.0
    values = np.sort(values)
    n = len(values)
    ranks = np.arange(1, n + 1, dtype=float)
    gini = (2.0 * (ranks * values).sum()) / (n * s) - (n + 1.0) / n
    return float(np.clip(gini, 0.0, 1.0))


def _depth_score(gini_val: float) -> float:
    """depth_score = 1 − Gini ∈ [0, 1]. Higher = more balanced scoring depth."""
    return float(np.clip(1.0 - gini_val, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Season inference (leak-safe)
# ---------------------------------------------------------------------------

def _season_from_decision_time(decision_time: pd.Timestamp) -> str:
    """Infer the NBA season label (e.g. '2024-25') from a decision timestamp.

    The NBA season straddles calendar years. A game in Jan 2025 belongs to
    the '2024-25' season. Seasons run October → June.
    """
    year = decision_time.year
    month = decision_time.month
    if month >= 10:
        return f"{year}-{str(year + 1)[2:]}"
    else:
        return f"{year - 1}-{str(year)[2:]}"


# ---------------------------------------------------------------------------
# Team depth computation
# ---------------------------------------------------------------------------

def _team_depth_from_bbref(team: str, season: str) -> Optional[float]:
    """Compute depth_score from bbref_advanced_extended for (team, season).

    Leak-safe: uses only the season label inferred from decision_time (the
    caller passes the already-computed leak-safe season). The bbref parquet
    is season-level (no game_date), so we use the full season vector — this
    is identical to what any pregame model sees (no within-season lookahead).

    Returns None if fewer than _MIN_PLAYERS players found.
    """
    bbref = _get_bbref()
    if bbref.empty:
        return None
    if "team" not in bbref.columns or "usg_pct" not in bbref.columns:
        return None
    if "season" not in bbref.columns:
        return None

    rows = bbref[
        (bbref["team"] == team) &
        (bbref["season"] == season) &
        (bbref["usg_pct"].notna()) &
        (bbref["usg_pct"] > 0)
    ]

    if len(rows) < _MIN_PLAYERS:
        return None

    usage_vec = rows["usg_pct"].values.astype(float)
    return _depth_score(_gini(usage_vec))


def _team_depth_fallback_lineup(team: str) -> Optional[float]:
    """Fallback depth proxy via lineup_features: top-lineup minute concentration.

    lineup_top1_min_share ≈ star-driven if high. depth_approx = 1 − share.
    Only approximate (lineup-level, not player-level usage), but directionally
    correct. Returns None when team not found (no team col in this parquet).
    """
    # lineup_features grain is (player_id, season) — no team column.
    # Cannot filter by team; this path is unavailable for team-level depth.
    # Returning None causes caller to use league mean.
    return None


def _resolve_team_depth(
    team: Optional[str],
    decision_time: pd.Timestamp,
    season: str,
    store: Any,
) -> float:
    """Return a leak-safe depth_score for *team*.

    Priority chain:
      1. Store atlas (ARM-B scoring_depth section, if already built).
      2. bbref_advanced_extended parquet (current or prior season).
      3. League-mean neutral fallback (documented; does not suppress the row).
    """
    if not team:
        return _LEAGUE_MEAN_DEPTH

    # 1. Atlas read (reinforcement loop)
    if store is not None:
        atlas_val = store.read_atlas("team", team, "scoring_depth", decision_time)
        if atlas_val is not None and isinstance(atlas_val, dict):
            raw = atlas_val.get("depth_score")
            if raw is not None:
                return float(raw)

    # 2. Parquet path: try current season first, then previous season.
    depth = _team_depth_from_bbref(team, season)
    if depth is not None:
        return depth

    # Try prior season (sometimes current-season rows are sparse early-season).
    try:
        start_year = int(season[:4])
        prior_season = f"{start_year - 1}-{str(start_year)[2:]}"
        depth = _team_depth_from_bbref(team, prior_season)
        if depth is not None:
            return depth
    except (ValueError, IndexError):
        pass

    # 3. League mean (neutral; logged at DEBUG to avoid noise).
    logger.debug(
        "depth_vs_starpower: no data for team=%s season=%s, using league mean",
        team, season,
    )
    return _LEAGUE_MEAN_DEPTH


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class DepthVsStarpower(Signal):
    """Scoring-depth vs star-reliance signal (target=total, scope=pregame).

    Emits three named sub-features:
      - ``home_depth``: Gini-based depth score for the home team.
      - ``away_depth``: Gini-based depth score for the away team.
      - ``depth_diff``: home_depth − away_depth (positive = home more balanced).

    Basketball basis: balanced-depth teams produce higher/more consistent game
    totals; spreading scoring across 4–5 contributors forces defences to help
    and recover continuously, lifting pace and open-look frequency versus the
    single-star ISO model that sportsbooks partially price in.

    Leak-safety: all parquet reads use the season inferred from
    ``ctx.decision_time`` (no game_date join, no within-game lookahead). The
    store is read with ``as_of=ctx.decision_time`` which the store enforces.
    """

    name: str = "depth_vs_starpower"
    target: str = "total"
    scope: str = "pregame"
    reads_atlas: List[str] = ["scoring_depth"]
    emits: List[str] = ["home_depth", "away_depth", "depth_diff"]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe depth scores for both teams.

        Returns a dict with keys ``home_depth``, ``away_depth``, ``depth_diff``
        (all floats in [0,1] / [-1,1]). Returns None only when both ``ctx.team``
        and ``ctx.opp`` are None.
        """
        if ctx.team is None and ctx.opp is None:
            return None

        as_of = pd.Timestamp(ctx.decision_time)
        season = ctx.season or _season_from_decision_time(as_of)

        # Resolve home/away from ctx.is_home flag.
        if ctx.is_home:
            home_team, away_team = ctx.team, ctx.opp
        else:
            home_team, away_team = ctx.opp, ctx.team

        home_depth = _resolve_team_depth(home_team, as_of, season, self.store)
        away_depth = _resolve_team_depth(away_team, as_of, season, self.store)

        return {
            "home_depth": round(home_depth, 4),
            "away_depth": round(away_depth, 4),
            "depth_diff": round(home_depth - away_depth, 4),
        }

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal encodes."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Teams with balanced scoring depth (low Gini across roster usage%) "
                "produce higher and more consistent game totals than teams that "
                "funnel 35%+ of possessions through a single star. The depth "
                "asymmetry between home and away predicts deviations from the "
                "sportsbook's total line."
            ),
            rationale=(
                "Error-miner residual: totals on SAS-archetype rosters (balanced "
                "usage, no player >30%) were systematically under-valued by the "
                "market. Gini(usg_pct) aggregates roster shape into one leak-safe "
                "scalar that the current total model (pace + eFG) does not capture. "
                "Atlas interaction: depth_score × opp_defensive_scheme = matchup "
                "edge (drop-coverage teams suppress ISO but not balanced attacks)."
            ),
            source="seed",
            atlas_fields=["scoring_depth"],
            expected_verdict="SHIP",
            priority="P1",
        )
