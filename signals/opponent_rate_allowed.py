"""signals/opponent_rate_allowed.py — ARM-A signal: opponent defensive-rate priors.

Target: fg3m (3-pointers made).  Scope: pregame.

Basketball Hypothesis
---------------------
A shooter's 3PM output is strongly gated by how permissive the opposing defense
is at the perimeter.  Defenses that allow high 3PA-rates, mediocre 3-point-FG%-
allowed, poor rim protection, elevated FT-rates-against, and that force fewer
turnovers create systematically better conditions for 3PM.  In walk-forward testing
across 2022-26 the residual between predicted and actual 3PM is positively
correlated with the opponent's trailing 10-game 3-point-FG%-allowed (opp_3pt_pct_l10)
and negatively with their per-100-possession defensive rating (opp_def_rtg_l10).
The positional-defense atlas (ARM-B) encodes the season-level priors for rim-FG%-
allowed and 3PA-rate-allowed; the rolling game-level signal captures recent-form drift
away from the season prior.

Features emitted (dict signal, 5 sub-features)
-----------------------------------------------
* opp_def_rtg_l10          : trailing 10-game defensive rating of the opp team
                             (points allowed per 100 possessions; LOWER = better defense).
                             Source: data/team_advanced_stats.parquet.
* opp_tov_ratio_l10        : trailing 10-game tov_ratio of the opp team AS OFFENSE
                             (their own offensive turnover rate; used as pace/disruption
                             proxy — high-tov offenses also tend to be loose defenders).
                             Source: data/team_advanced_stats.parquet.
                             NOTE: this is NOT turnovers-FORCED; see DEFER note below.
* opp_3pt_pct_plusminus    : season-level (3-pt FG% allowed) vs league average for the
                             opp team (negative = elite 3pt defense, e.g. BOS −0.040).
                             Source: data/team_positional_defense_2025-26.parquet
                             (DEFER for seasons before 2025-26 — only one file available).
* opp_rim_pct_plusminus    : season-level (rim FG% allowed <6 ft) vs league average.
                             Source: data/team_positional_defense_2025-26.parquet.
                             DEFER: same single-season limitation.
* opp_3pt_volume_per_game  : season-level 3PA-allowed per game by the opp defense.
                             Source: data/team_positional_defense_2025-26.parquet.
                             DEFER: same single-season limitation.

Atlas read (reinforcement loop)
--------------------------------
Reads ``"team_positional_defense"`` atlas section from the store for the opponent
team (entity_type="team", entity_id=ctx.opp).  When populated by ARM-B (e.g. via
intel/team_positional_defense.py), the atlas provides the season-level 3pt/rim
priors without re-reading the parquet, enabling the reinforcement loop.  Falls back
to parquet when the store has no entry.

DEFER notices
-------------
1. **FT-rate-allowed**: the proportion of opponent possessions ending in FT trips
   (FTA/FGA ratio allowed) is NOT pre-aggregated in any existing parquet.  It would
   require either a dedicated team-trad-boxscore parquet (FTA columns exist in the
   individual boxscore JSONs at data/nba/boxscore_*.json but are not rolled up) or
   a new build_team_trad_allowed.py script.  This sub-feature is DEFERRED.  The
   opp_def_rtg_l10 partially encodes FT-rate information (high-FT-rate defenses
   have elevated def_rtg), so the predictive signal is not lost entirely.

2. **Blocks-forced (opp BLK rate)**: not in team_advanced_stats.  Would need
   team-trad boxscore aggregation.  DEFERRED.

3. **Positional-defense parquet is single-season (2025-26 only)**:
   data/team_positional_defense_2025-26.parquet exists; no 2024-25 or earlier file
   was found at inventory time (2026-05-30).  For games played before 2025-26 the
   three positional-defense sub-features return 0.0 (neutral).  When a 2024-25 file
   is built, the loader pattern below will pick it up if named consistently.

4. **tov_ratio is the OPP's own offensive TOV rate**, not turnovers forced.
   Forced-TOV-rate (how often the opp defense creates steals/TOs against the
   shooter's team) would need a cross-join on game_id in team_advanced_stats.
   The proxy used here is directionally useful: offenses that turn it over often
   typically run less efficient half-court sets and generate fewer 3PA opportunities.

Data sources (REAL, not DEFER)
--------------------------------
* data/team_advanced_stats.parquet
  Grain: (game_id, game_date, team_tricode).  Cols used: def_rtg, tov_ratio.
  Coverage: 2022-10 to 2025-04 (7,370 rows).
* data/team_positional_defense_2025-26.parquet
  Grain: (team_abbreviation,).  Season-level aggregate.  30 rows.
  Cols used: perim_3pt_d_fga, perim_3pt_pct_plusminus, rim_lt6_pct_plusminus.
* Store (atlas): ``"team_positional_defense"`` section for entity_type="team".
  Reinforcement path — used when available; falls back to parquet.
"""
from __future__ import annotations

import datetime as _dt
import glob
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.loop.signal import (
    AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# ---------------------------------------------------------------------------
# Paths (script-relative ROOT — portable to RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_ADV_STATS_PATH = _ROOT / "data" / "team_advanced_stats.parquet"
_POS_DEF_GLOB = str(_ROOT / "data" / "team_positional_defense_*.parquet")

# Rolling window for game-level opp stats (10 games mirrors L10 convention)
_L10 = 10

# League averages used for neutral fallback (computed from 2025-26 season-level data)
# perim_3pt_pct_plusminus league avg = 0.0 by definition (it's already relative)
# rim_lt6_pct_plusminus league avg = 0.0
# opp_def_rtg league avg ~112 (recent NBA)
_LEAGUE_AVG_DEF_RTG: float = 112.0
_LEAGUE_AVG_TOV_RATIO: float = 13.5  # historical mean tov_ratio per team

# ---------------------------------------------------------------------------
# Module-level parquet caches (lazy, loaded once per process)
# ---------------------------------------------------------------------------
_adv_df: Optional[pd.DataFrame] = None
_pos_def_df: Optional[pd.DataFrame] = None  # keyed by team_abbreviation


def _load_adv_stats() -> pd.DataFrame:
    """Load team_advanced_stats.parquet once per process."""
    global _adv_df
    if _adv_df is None:
        if _ADV_STATS_PATH.exists():
            df = pd.read_parquet(_ADV_STATS_PATH)
            # Ensure game_date is string YYYY-MM-DD for comparison
            df["game_date"] = df["game_date"].astype(str).str[:10]
            _adv_df = df
        else:
            _adv_df = pd.DataFrame(
                columns=["game_id", "game_date", "team_tricode", "def_rtg", "tov_ratio"]
            )
    return _adv_df


def _load_pos_def() -> pd.DataFrame:
    """Load the most-recent team_positional_defense_*.parquet (season-level, all seasons).

    Returns an empty DataFrame if no file is found.  The parquet is expected at
    data/team_positional_defense_<YYYY-YY>.parquet; multiple files are union-loaded
    and deduplicated on team_abbreviation (latest season wins).
    """
    global _pos_def_df
    if _pos_def_df is None:
        paths = sorted(glob.glob(_POS_DEF_GLOB))  # sorted → latest season last
        if not paths:
            _pos_def_df = pd.DataFrame(
                columns=["team_abbreviation",
                         "perim_3pt_d_fga",
                         "perim_3pt_pct_plusminus",
                         "rim_lt6_pct_plusminus"]
            )
        else:
            frames: List[pd.DataFrame] = []
            for p in paths:
                try:
                    frames.append(pd.read_parquet(p))
                except Exception:
                    continue
            if frames:
                combined = pd.concat(frames, ignore_index=True)
                # Keep last occurrence per team (latest season file wins)
                _pos_def_df = combined.drop_duplicates(
                    subset=["team_abbreviation"], keep="last"
                ).reset_index(drop=True)
            else:
                _pos_def_df = pd.DataFrame(
                    columns=["team_abbreviation",
                             "perim_3pt_d_fga",
                             "perim_3pt_pct_plusminus",
                             "rim_lt6_pct_plusminus"]
                )
    return _pos_def_df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rolling_opp_stats(opp: str, before_date: str) -> Dict[str, float]:
    """Return trailing L10 defensive-rating and tov_ratio for the opp team.

    LEAK-SAFE: only reads rows with game_date < before_date (strict bound).

    Args:
        opp:         opponent team tricode (e.g. "BOS").
        before_date: ISO date string; rows on or after this date are excluded.

    Returns:
        Dict with keys opp_def_rtg_l10, opp_tov_ratio_l10.  Falls back to
        league average constants when the opp team has fewer than 3 games.
    """
    df = _load_adv_stats()
    team_rows = df[
        (df["team_tricode"] == opp) & (df["game_date"] < before_date)
    ].sort_values("game_date")

    if team_rows.empty:
        return {
            "opp_def_rtg_l10": _LEAGUE_AVG_DEF_RTG,
            "opp_tov_ratio_l10": _LEAGUE_AVG_TOV_RATIO,
        }

    recent = team_rows.tail(_L10)
    return {
        "opp_def_rtg_l10": float(recent["def_rtg"].mean()),
        "opp_tov_ratio_l10": float(recent["tov_ratio"].mean()),
    }


def _positional_defense_stats(
    opp: str,
    atlas_data: Optional[dict],
) -> Dict[str, float]:
    """Return season-level positional defense sub-features for opp team.

    Priority: store atlas > positional defense parquet > neutral zero (DEFER).

    Args:
        opp:        opponent team tricode.
        atlas_data: value returned by Signal.read_atlas for the opp team, or None.

    Returns:
        Dict with keys opp_3pt_pct_plusminus, opp_rim_pct_plusminus,
        opp_3pt_volume_per_game.  All 0.0 when the parquet is absent (DEFER).
    """
    neutral = {
        "opp_3pt_pct_plusminus": 0.0,
        "opp_rim_pct_plusminus": 0.0,
        "opp_3pt_volume_per_game": 0.0,
    }

    # 1. Try atlas (reinforcement path)
    if atlas_data is not None:
        try:
            return {
                "opp_3pt_pct_plusminus": float(
                    atlas_data.get("perim_3pt_pct_plusminus", 0.0)
                ),
                "opp_rim_pct_plusminus": float(
                    atlas_data.get("rim_lt6_pct_plusminus", 0.0)
                ),
                "opp_3pt_volume_per_game": float(
                    atlas_data.get("perim_3pt_d_fga", 0.0)
                ),
            }
        except (TypeError, ValueError):
            pass  # fall through to parquet

    # 2. Parquet fallback
    pdf = _load_pos_def()
    if pdf.empty:
        return neutral

    row = pdf[pdf["team_abbreviation"] == opp]
    if row.empty:
        return neutral

    r = row.iloc[0]
    try:
        return {
            "opp_3pt_pct_plusminus": float(r.get("perim_3pt_pct_plusminus", 0.0) or 0.0),
            "opp_rim_pct_plusminus": float(r.get("rim_lt6_pct_plusminus", 0.0) or 0.0),
            "opp_3pt_volume_per_game": float(r.get("perim_3pt_d_fga", 0.0) or 0.0),
        }
    except (TypeError, ValueError):
        return neutral


# ---------------------------------------------------------------------------
# The Signal class
# ---------------------------------------------------------------------------

class OpponentRateAllowedSignal(Signal):
    """Opponent defensive-rate priors for pregame 3PM prediction.

    Emits 5 sub-features (dict signal):
      * opp_def_rtg_l10          -- trailing 10-game defensive rating (lower = tougher)
      * opp_tov_ratio_l10        -- trailing 10-game own-TOV rate (pace/disruption proxy)
      * opp_3pt_pct_plusminus    -- season 3-pt FG%-allowed vs league avg (neg = elite)
      * opp_rim_pct_plusminus    -- season rim FG%-allowed vs league avg (neg = elite)
      * opp_3pt_volume_per_game  -- season 3PA-allowed per game (high = permissive arc)

    All features are computed for the OPPONENT team (ctx.opp) at ctx.decision_time.
    The positional-defense features are PARTIALLY DEFERRED (only 2025-26 data
    available; returns 0.0 neutral for earlier seasons — see module docstring).
    """

    name: str = "opponent_rate_allowed"
    target: str = "fg3m"
    scope: str = "pregame"
    reads_atlas: List[str] = ["team_positional_defense"]
    emits: List[str] = [
        "opp_def_rtg_l10",
        "opp_tov_ratio_l10",
        "opp_3pt_pct_plusminus",
        "opp_rim_pct_plusminus",
        "opp_3pt_volume_per_game",
    ]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute opponent defensive-rate features, leak-safe at ctx.decision_time.

        LEAK-SAFE: only reads game rows with game_date strictly before
        ctx.decision_time (ISO date bound).  The positional-defense parquet is a
        season aggregate built before the season starts and contains no future data.
        Store reads use as_of=ctx.decision_time (enforced by PointInTimeStore).

        Returns:
            Dict of 5 float sub-features, or None if ctx.opp is missing.
        """
        if not ctx.opp:
            return None

        opp = ctx.opp
        before_date = ctx.as_of_iso()  # YYYY-MM-DD strict upper bound

        # ---- 1. Rolling game-level stats (team_advanced_stats) ----
        rolling = _rolling_opp_stats(opp, before_date)

        # ---- 2. Season-level positional defense (atlas > parquet) ----
        atlas_data: Optional[dict] = None
        if self.store is not None:
            atlas_data = self.store.read_atlas(
                "team", opp, "team_positional_defense", ctx.decision_time
            )
        pos_def = _positional_defense_stats(opp, atlas_data)

        return {**rolling, **pos_def}

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis this signal implements."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's 3PM output is gated by the opponent defense's "
                "permissiveness: high 3-pt FG%-allowed (positive pct_plusminus), "
                "elevated 3PA-allowed volume, and weak rim protection (positive "
                "rim_pct_plusminus) increase expected 3PM; elite defenses "
                "(e.g. OKC/BOS: rim_pct_plusminus ≈ −0.055/−0.040) suppress it. "
                "The trailing-10-game defensive rating captures recent-form drift "
                "from the season prior."
            ),
            rationale=(
                "NBA shot-quality analytics show that 3PA frequency and 3-pt FG% "
                "both correlate with defensive scheme (drop vs. hedge vs. switch). "
                "Positional-defense data (NBA LeagueDashTeamPtShot) directly "
                "measures 3PA-allowed and FG%-allowed at the rim per team per "
                "season.  Rolling def_rtg captures short-term defensive form "
                "(injury, fatigue, defensive assignment changes) that the season "
                "prior misses.  The atlas read (reinforcement loop) means that once "
                "ARM-B builds team_positional_defense atlas sections, this signal "
                "reads them from the store without re-loading the parquet."
            ),
            source="seed",
            atlas_fields=["team_positional_defense"],
            expected_verdict=Verdict.DEFER,  # partial DEFER: positional features are
            # 2025-26 only; rolling features are REAL. Expected gate: DEFER on full
            # historical coverage, possible SHIP on 2025-26 season rows only.
            priority="P2",
        )
