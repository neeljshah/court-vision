"""signals/ref_crew_ft_environment.py — Referee crew FT-environment signal (ARM-A).

Basketball hypothesis
---------------------
Different referee crews systematically call different numbers of fouls and free
throws.  A "whistle-happy" crew (high ``ref_crew_fta``) inflates both teams'
free-throw attempts, which lifts the game total relative to the market's modelled
pace.  Conversely, a tight crew suppresses FTAs and compresses totals.  The
pre-game spread already reflects some of this, but the crew-specific signal is
orthogonal to point-total projections that rely solely on team pace and offense/
defense ratings, so it should clear the ablation-vs-FULL gate.

Signal contract
---------------
  name    = "ref_crew_ft_environment"
  target  = "total"
  scope   = "pregame"
  emits   = ["fta_z", "fouls_z", "home_win_pct_advantage"]

Sub-features
  fta_z               float.  Z-score of the crew's rolling average FTA per
                       game relative to the season-to-date league mean.
                       Positive = more FTAs expected (whistle-happy crew).
                       Uses ``officials_rolling.parquet`` L5-based z-score
                       where available; falls back to raw ``officials_features``
                       z-score (season rolling) as a secondary source.

  fouls_z             float.  Same Z-score for total fouls called per game.
                       Collinear with fta_z but captures a distinct part of the
                       crew tendency: some crews call many fouls that don't result
                       in FTs (off-ball / charge calls).

  home_win_pct_advantage  float.  The crew's home-win-rate minus the league
                       baseline (~0.55).  Positive means this crew tends to favour
                       home teams (which interacts with is_home and line to give
                       a secondary signal for win-prob / spread calibration).

Data sources (all strictly point-in-time)
------------------------------------------
  PRIMARY  : ``data/cache/officials_rolling.parquet``
             grain (game_id, team_abbreviation, game_date, season)
             cols: l5_ref_crew_fouls_per_g, l5_ref_crew_fta_per_g,
                   ref_crew_fouls_z, ref_crew_fta_z, home_win_pct_advantage
             Built by a rolling look-back that only uses games PRIOR to each
             game_date — strictly leak-safe.

  FALLBACK : ``data/officials_features.parquet``
             grain (team_abbreviation, game_date, game_id)
             cols: ref_crew_fouls, ref_crew_fta, ref_crew_home_win_pct
             Prior-season crew averages (point-in-time: prior season is
             complete before this season starts).  Used to derive z-scores
             when the rolling parquet is unavailable.

  STORE    : "ref_crew" atlas section read via self.read_atlas for any
             crew-level learned values written back by a prior SHIP.

DEFER items
-----------
  DEFER-1: Individual referee identity is not available in the parquets
           (only aggregate crew-level averages).  Per-referee tendencies
           (e.g. some refs are more prone to calling late-game fouls) cannot
           be modelled until a ref_id → game_id mapping is ingested.

  DEFER-2: The ``officials_player_sensitivity`` parquet (data/intelligence/)
           has 0 rows as of 2026-05-30.  Player-specific sensitivity to crew
           style (e.g. high-volume FT drawers benefiting from whistle-heavy
           crews) is DEFERRED until that parquet is populated.

  DEFER-3: The signal targets ``total`` (game-level), not per-player stats.
           Connecting crew FTA rate to individual player FTA (and thus PTS)
           requires the player-sensitivity atlas, which is not yet available.
"""
from __future__ import annotations

import datetime as _dt
import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict

# ---------------------------------------------------------------------------
# Constants / paths (script-relative ROOT — portable to RunPod Linux)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
_ROLLING_PATH = _ROOT / "data" / "cache" / "officials_rolling.parquet"
_OFFICIALS_PATH = _ROOT / "data" / "officials_features.parquet"

# League baseline home-win probability used to compute home_win_pct_advantage.
# NBA home-court ~55.3% over 2022-26 (observed, not a prior).
_LEAGUE_HOME_WIN_RATE: float = 0.553

# Default neutral values returned when data is unavailable.
_DEFAULTS: Dict[str, float] = {
    "fta_z": 0.0,
    "fouls_z": 0.0,
    "home_win_pct_advantage": 0.0,
}

# ---------------------------------------------------------------------------
# Module-level lazy caches (one load per process)
# ---------------------------------------------------------------------------

_rolling_cache: Optional[pd.DataFrame] = None
_officials_cache: Optional[pd.DataFrame] = None


def _load_rolling() -> pd.DataFrame:
    """Lazy-load officials_rolling.parquet."""
    global _rolling_cache
    if _rolling_cache is None:
        try:
            df = pd.read_parquet(_ROLLING_PATH)
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
            _rolling_cache = df
        except Exception as exc:
            warnings.warn(
                f"ref_crew_ft_environment: cannot load officials_rolling.parquet: {exc}"
            )
            _rolling_cache = pd.DataFrame()
    return _rolling_cache


def _load_officials() -> pd.DataFrame:
    """Lazy-load officials_features.parquet (fallback)."""
    global _officials_cache
    if _officials_cache is None:
        try:
            df = pd.read_parquet(_OFFICIALS_PATH)
            df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
            _officials_cache = df
        except Exception as exc:
            warnings.warn(
                f"ref_crew_ft_environment: cannot load officials_features.parquet: {exc}"
            )
            _officials_cache = pd.DataFrame()
    return _officials_cache


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _game_date_from_ctx(ctx: AsOfContext) -> Optional[_dt.date]:
    """Parse game_date from context, returning None on failure."""
    if ctx.game_date:
        try:
            return _dt.date.fromisoformat(ctx.game_date[:10])
        except ValueError:
            pass
    return ctx.decision_time.date()


def _rolling_features(
    game_date: _dt.date,
    team: Optional[str],
) -> Optional[Dict[str, float]]:
    """Look up features from officials_rolling.parquet for (game_date, team).

    The rolling parquet is pre-computed with data strictly BEFORE each game,
    so reading the exact game_date row is leak-safe (no same-day write).

    Returns a dict with fta_z, fouls_z, home_win_pct_advantage keys, or None
    when the parquet has no matching row.
    """
    df = _load_rolling()
    if df.empty:
        return None

    # Match on game_date; optionally filter by team (both teams share the same
    # crew, so either team row is valid — prefer the subject team for clarity)
    mask = df["game_date"] == game_date
    if mask.sum() == 0:
        return None

    if team:
        team_mask = mask & (df["team_abbreviation"] == team)
        rows = df[team_mask] if team_mask.sum() > 0 else df[mask]
    else:
        rows = df[mask]

    row = rows.iloc[0]

    # The rolling parquet already has season-normalised z-scores
    fta_z = float(row.get("ref_crew_fta_z", 0.0) or 0.0)
    fouls_z = float(row.get("ref_crew_fouls_z", 0.0) or 0.0)
    hwpa = float(row.get("home_win_pct_advantage", 0.0) or 0.0)

    return {
        "fta_z": fta_z,
        "fouls_z": fouls_z,
        "home_win_pct_advantage": hwpa,
    }


def _officials_features_fallback(
    game_date: _dt.date,
    team: Optional[str],
    decision_time: _dt.datetime,
) -> Optional[Dict[str, float]]:
    """Derive features from officials_features.parquet (fallback, raw averages).

    The parquet stores the crew's prior-season average fouls/FTAs (computed
    before the season, so point-in-time safe). We z-score against the
    HISTORICAL MEAN of all games strictly before decision_time to avoid leak.

    Returns a dict with fta_z, fouls_z, home_win_pct_advantage, or None.
    """
    df = _load_officials()
    if df.empty:
        return None

    cutoff_date = decision_time.date()

    # Leak-safe universe: only games before decision_time for computing league stats
    hist = df[df["game_date"] < cutoff_date]
    if hist.empty:
        return None

    # Compute league mean + std for z-scoring (leak-safe reference)
    fta_mean = float(hist["ref_crew_fta"].mean())
    fta_std = float(hist["ref_crew_fta"].std()) or 1.0
    fouls_mean = float(hist["ref_crew_fouls"].mean())
    fouls_std = float(hist["ref_crew_fouls"].std()) or 1.0
    hwp_mean = float(hist["ref_crew_home_win_pct"].mean())

    # Find the target game row
    day_mask = df["game_date"] == game_date
    if day_mask.sum() == 0:
        return None

    if team:
        team_mask = day_mask & (df["team_abbreviation"] == team)
        rows = df[team_mask] if team_mask.sum() > 0 else df[day_mask]
    else:
        rows = df[day_mask]

    row = rows.iloc[0]

    raw_fta = float(row.get("ref_crew_fta", fta_mean) or fta_mean)
    raw_fouls = float(row.get("ref_crew_fouls", fouls_mean) or fouls_mean)
    raw_hwp = float(row.get("ref_crew_home_win_pct", hwp_mean) or hwp_mean)

    return {
        "fta_z": (raw_fta - fta_mean) / fta_std,
        "fouls_z": (raw_fouls - fouls_mean) / fouls_std,
        "home_win_pct_advantage": raw_hwp - _LEAGUE_HOME_WIN_RATE,
    }


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class RefCrewFtEnvironment(Signal):
    """Referee crew FT-environment signal for game total predictions (pregame).

    Reads the officials_rolling.parquet (L5 z-scores, pre-computed leak-safe)
    for the subject game/team, falling back to officials_features.parquet
    when rolling data is absent.  Also checks the store for any previously
    shipped crew-level atlas values (reinforcement).

    Emits three sub-features:
      fta_z              -- crew's FTA tendency z-score vs league average
      fouls_z            -- crew's foul-calling tendency z-score
      home_win_pct_advantage -- crew home bias vs league baseline

    Returns None when neither data source has a row for the game_date.
    """

    name: str = "ref_crew_ft_environment"
    target: str = "total"
    scope: str = "pregame"
    reads_atlas: List[str] = ["ref_crew"]
    emits: List[str] = ["fta_z", "fouls_z", "home_win_pct_advantage"]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe referee-crew FT-environment features.

        Only reads game rows with game_date == ctx.game_date (the crew-assignment
        row for THIS game, pre-computed from prior data), and the store with
        as_of=ctx.decision_time.  Never reads same-game box scores.

        Args:
            ctx: the decision context; must have game_date (or decision_time)
                 to identify the crew assignment.

        Returns:
            Dict with keys fta_z, fouls_z, home_win_pct_advantage; or None
            when the crew assignment cannot be found for the requested date.
        """
        game_date = _game_date_from_ctx(ctx)
        if game_date is None:
            return None

        team = ctx.team  # used to disambiguate rows if needed; crew is same for both

        # ---- 1. Try store atlas (reinforcement path) ---------------------------
        # A previously SHIPPED crew-level value is stored under "ref_crew" section.
        # If the store has it, blend it with the freshly-looked-up z-score.
        store_feats: Optional[Dict[str, float]] = None
        if self.store is not None and team:
            stored = self.store.read_atlas("team", team, "ref_crew", ctx.decision_time)
            if isinstance(stored, dict):
                # Extract sub-keys; graceful on missing
                try:
                    store_feats = {
                        "fta_z": float(stored.get("fta_z", 0.0) or 0.0),
                        "fouls_z": float(stored.get("fouls_z", 0.0) or 0.0),
                        "home_win_pct_advantage": float(
                            stored.get("home_win_pct_advantage", 0.0) or 0.0
                        ),
                    }
                except (TypeError, ValueError):
                    store_feats = None

        # ---- 2. Primary: officials_rolling.parquet (preferred — L5 z-scores) --
        feats = _rolling_features(game_date, team)

        # ---- 3. Fallback: officials_features.parquet (raw averages → z-score) -
        if feats is None:
            feats = _officials_features_fallback(game_date, team, ctx.decision_time)

        # ---- 4. If neither source has data, return None ----------------------
        if feats is None:
            return None

        # ---- 5. Blend with store prior if available --------------------------
        # Simple average: store prior reflects a learned adjustment; current
        # season data reflects recency.  Equal weight until wiring fits a
        # proper blend coefficient.
        if store_feats is not None:
            feats = {
                k: (feats[k] + store_feats[k]) / 2.0
                for k in self.emits
            }

        return feats

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Referee crews have measurable systematic differences in foul-calling "
                "and FTA rates (std ~2 FTAs/game across crews); games assigned to "
                "whistle-happy crews (high fta_z) produce higher game totals than "
                "pace-only models predict, because extra FT possessions add points "
                "orthogonally to the team-offense / team-defense signal already "
                "wired into the prediction model."
            ),
            rationale=(
                "officials_features.parquet captures each crew's prior-season "
                "rolling average FTAs/game (mean 44.8, std 2.0, range 40-51); the "
                "z-score buckets the crew strictly relative to games already played "
                "before the decision date. At ±1 std (~2 FTAs/game) and ~0.75 "
                "pts/FTA, the expected total lift is ~1.5 pts, comparable to the "
                "rest/travel signal.  The crew assignment is known pre-game (NBA "
                "publishes officials the morning of), making this fully leak-free. "
                "The ablation test vs the FULL model (which does NOT include a crew "
                "feature today) should show a meaningful MAE reduction on total. "
                "Expected verdict: SHIP for total; VARIANCE_ONLY possible if the "
                "effect is real but dwarfed by team-pace variance in the FULL model."
            ),
            source="seed",
            atlas_fields=["ref_crew"],
            expected_verdict=Verdict.SHIP,
            priority="P2",
        )
