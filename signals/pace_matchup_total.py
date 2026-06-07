"""signals/pace_matchup_total.py — ARM-A signal: combined-pace adjustment to game total.

Basketball hypothesis
---------------------
When both teams in a matchup share a high-pace profile (FAST / VERY_FAST labels from
the ``pace_identity`` atlas), the expected number of possessions per game is higher
than a league-average game, and the over/under line should be adjusted upward.
Conversely, a slow-vs-slow matchup suppresses possessions and pushes the projection
downward.  The combined-pace adjustment captures this matchup-pace interaction that a
simple per-team average misses.

The signal emits three sub-features:
  ``combined_pace``
      (home_pace_pg + away_pace_pg) / 2  — the average possessions/48 of both teams.
      Range: ~85–115 in modern NBA.
  ``pace_adj_total``
      A pace-adjusted projected total computed as:
          pace_adj_total = (home_off_rtg + away_off_rtg) × combined_pace / 100
      This replicates the standard pace × efficiency formula but uses atlas-refined
      pace values (smoothed over the entire season as-of, not just L10) when the
      store atlas is populated, falling back to season_games L10 pace.
  ``pace_tier_interaction``
      Interaction dummy: 1.0 if BOTH teams are FAST or VERY_FAST, −1.0 if BOTH are
      SLOW or MODERATE, 0.0 otherwise (asymmetric matchup).  This allows the model
      to learn a nonlinear up/down adjustment on top of the linear pace projection.

Target
------
``total`` — the game O/U line (combined score of both teams).

Scope
-----
``pregame`` — both teams' pace profiles are knowable before tip-off.  The atlas
is built from data <= as_of, so there is no lookahead.

Data sources
------------
PRIMARY — ``pace_identity`` atlas section (team entity)
    Provides tempo.pace_pg, tempo.pace_identity_label, efficiency.off_rtg.
    Read via store.read_atlas (reinforcement loop path when the store is populated).
    If the store is absent or returns None, falls back to team_advanced_stats.parquet.

FALLBACK — ``data/team_advanced_stats.parquet``
    Cols: team_tricode, game_date, pace, off_rtg.
    Filtered to game_date <= as_of (leak-safe).
    Used when the atlas is not yet populated (bootstrap path).

DEFER notice
------------
* CLV gate requires >=30 Pinnacle game-total closing lines; DEFER until
  ``data/lines/`` accumulates enough dated mainline CSVs.
* pace_tier_interaction is a categorical encoding; its predictive value needs
  walk-forward validation with actual game totals as labels.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict

# ---------------------------------------------------------------------------
# Repo root (script-relative — works on Windows local + RunPod Linux)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_ADV_STATS_PATH = _ROOT / "data" / "team_advanced_stats.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MIN_PACE: float = 80.0   # plausibility filter: possessions/48
_MIN_RTG: float = 85.0    # plausibility filter: offensive rating

# Pace identity labels deemed FAST or above (for the interaction dummy)
_FAST_LABELS = frozenset({"FAST", "VERY_FAST"})
_SLOW_LABELS = frozenset({"SLOW", "MODERATE"})

# Module-level parquet cache (populated once per process)
_adv_df: Optional[pd.DataFrame] = None


def _load_adv() -> pd.DataFrame:
    """Lazy-load team_advanced_stats.parquet once per process."""
    global _adv_df
    if _adv_df is None:
        if _ADV_STATS_PATH.exists():
            try:
                _adv_df = pd.read_parquet(_ADV_STATS_PATH)
                _adv_df["game_date"] = pd.to_datetime(
                    _adv_df["game_date"], errors="coerce"
                )
            except Exception:
                _adv_df = pd.DataFrame()
        else:
            _adv_df = pd.DataFrame()
    return _adv_df


def _rd(v: object) -> Optional[float]:
    """Return cleaned float or None for NaN/inf/non-numeric."""
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _team_pace_from_parquet(
    tricode: str, as_of: _dt.datetime
) -> Dict[str, Optional[float]]:
    """Aggregate pace + off_rtg from team_advanced_stats <= as_of.

    LEAK-SAFE: filters game_date <= as_of before aggregating.
    Returns a dict with keys: pace_pg, off_rtg.
    """
    df = _load_adv()
    if df.empty or "team_tricode" not in df.columns:
        return {}
    cutoff = pd.Timestamp(as_of)
    rows = df[(df["team_tricode"] == tricode) & (df["game_date"] <= cutoff)]
    if rows.empty:
        return {}
    pace_col = "pace" if "pace" in rows.columns else None
    rtg_col = "off_rtg" if "off_rtg" in rows.columns else None
    result: Dict[str, Optional[float]] = {}
    if pace_col:
        v = _rd(rows[pace_col].mean())
        if v is not None and v >= _MIN_PACE:
            result["pace_pg"] = v
    if rtg_col:
        v = _rd(rows[rtg_col].mean())
        if v is not None and v >= _MIN_RTG:
            result["off_rtg"] = v
    return result


def _pace_label(pace_pg: float) -> str:
    """Map pace (possessions/48) to the same categorical bins as the atlas."""
    if pace_pg < 98.0:
        return "SLOW"
    if pace_pg < 100.5:
        return "MODERATE"
    if pace_pg < 103.0:
        return "FAST"
    return "VERY_FAST"


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class PaceMatchupTotal(Signal):
    """Combined-pace adjustment to the game total (target=total, scope=pregame).

    Reads both teams' ``pace_identity`` atlas sections (or falls back to
    team_advanced_stats.parquet) and projects a combined-pace-adjusted game total.

    Emits a dict with three sub-features:
      combined_pace        — average possessions/48 of both teams.
      pace_adj_total       — pace × efficiency total projection.
      pace_tier_interaction — +1 (both fast), −1 (both slow), 0 (asymmetric).
    """

    name: str = "pace_matchup_total"
    target: str = "total"
    scope: str = "pregame"
    reads_atlas: List[str] = ["pace_identity"]
    emits: List[str] = ["combined_pace", "pace_adj_total", "pace_tier_interaction"]

    # ------------------------------------------------------------------
    def _read_team_pace(
        self, tricode: str, as_of: _dt.datetime
    ) -> Dict[str, object]:
        """Return pace data for one team, preferring the atlas store.

        Falls back to team_advanced_stats.parquet when the store is absent
        or returns nothing for the team.

        Returns a dict with keys: pace_pg (float), off_rtg (float),
        pace_identity_label (str).  Any field may be None.
        """
        result: Dict[str, object] = {
            "pace_pg": None,
            "off_rtg": None,
            "pace_identity_label": None,
        }

        # --- Try the atlas store first (ARM-B → ARM-A reinforcement) ---
        if self.store is not None:
            atlas = self.read_atlas(tricode, "pace_identity", as_of)
            if atlas:
                tempo = atlas.get("tempo", {}) or {}
                eff = atlas.get("efficiency", {}) or {}
                pace_pg = _rd(tempo.get("pace_pg"))
                off_rtg = _rd(eff.get("off_rtg"))
                label = tempo.get("pace_identity_label")
                if pace_pg is not None and pace_pg >= _MIN_PACE:
                    result["pace_pg"] = pace_pg
                    result["off_rtg"] = off_rtg
                    if label:
                        result["pace_identity_label"] = str(label)
                    elif pace_pg is not None:
                        result["pace_identity_label"] = _pace_label(pace_pg)
                    return result

        # --- Fallback: parquet aggregate ---
        parquet_data = _team_pace_from_parquet(tricode, as_of)
        pace_pg = parquet_data.get("pace_pg")
        off_rtg = parquet_data.get("off_rtg")
        if pace_pg is not None:
            result["pace_pg"] = pace_pg
            result["off_rtg"] = off_rtg
            result["pace_identity_label"] = _pace_label(float(pace_pg))
        return result

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute combined-pace total adjustment for one pregame decision.

        LEAK-SAFE: all data reads go through _read_team_pace which filters
        to <= ctx.decision_time.

        Returns None if either team's pace data is unavailable.
        """
        if not ctx.team or not ctx.opp:
            return None

        as_of = ctx.decision_time
        home_data = self._read_team_pace(ctx.team, as_of)
        away_data = self._read_team_pace(ctx.opp, as_of)

        home_pace = _rd(home_data.get("pace_pg"))
        away_pace = _rd(away_data.get("pace_pg"))
        home_rtg = _rd(home_data.get("off_rtg"))
        away_rtg = _rd(away_data.get("off_rtg"))

        # Need at minimum both pace values to compute combined_pace
        if home_pace is None or away_pace is None:
            return None

        combined_pace = round((home_pace + away_pace) / 2.0, 4)

        # Pace-adjusted projected total; falls back gracefully if rtg missing
        if home_rtg is not None and away_rtg is not None:
            rtg_sum = home_rtg + away_rtg
            pace_adj_total = round(rtg_sum * combined_pace / 100.0, 4)
        else:
            pace_adj_total = float("nan")

        # Tier interaction dummy
        home_label = home_data.get("pace_identity_label")
        away_label = away_data.get("pace_identity_label")
        if home_label in _FAST_LABELS and away_label in _FAST_LABELS:
            tier_interaction = 1.0
        elif home_label in _SLOW_LABELS and away_label in _SLOW_LABELS:
            tier_interaction = -1.0
        else:
            tier_interaction = 0.0

        return {
            "combined_pace": combined_pace,
            "pace_adj_total": pace_adj_total,
            "pace_tier_interaction": tier_interaction,
        }

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Matchups where both teams have a FAST/VERY_FAST pace identity "
                "produce more possessions and higher combined scores than league-average "
                "matchups; the combined-pace-adjusted total (pace × off-rtg / 100) "
                "reduces O/U MAE relative to a flat league-average projection."
            ),
            rationale=(
                "Pace is the primary multiplier on possessions per game; a fast-vs-fast "
                "matchup generates ~4-6 extra possessions vs a slow-vs-slow game, "
                "worth ~8-12 pts to the total.  Off-rtg captures scoring efficiency on "
                "each possession.  Combining both via (off_rtg_home + off_rtg_away) × "
                "combined_pace / 100 gives a physics-grounded total projection; the "
                "tier_interaction dummy lets the model fit a nonlinear regime shift "
                "beyond the linear pace term.  The atlas smooths out L10 noise in "
                "season_games and incorporates per-game pace variance as a confidence "
                "weight."
            ),
            source="seed",
            atlas_fields=["pace_identity"],
            expected_verdict=Verdict.DEFER,
            priority="P2",
        )
