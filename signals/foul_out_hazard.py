"""signals/foul_out_hazard.py — Foul-out hazard signal (ARM-A, scope=live).

Basketball hypothesis
---------------------
As a player accumulates personal fouls during a game, the coaching staff reduces
their minutes exposure to avoid a disqualification (6th foul in regulation, or
the league-standard foul-out threshold).  The hazard compounds with game clock:
a player on 4 fouls in Q3 is far more likely to be benched than one on 4 fouls
in Q4 garbage time.  This signal converts {current_pf_count, period, clock_elapsed}
into a [0, 1] foul-out hazard score that the minutes model can consume directly.

Signal contract
---------------
  name    = "foul_out_hazard"
  target  = "minutes"
  scope   = "live"
  emits   = ["hazard", "fouls_remaining", "pf_rate_l5"]

The three sub-features are:

  hazard          float in [0, 1].  Smoothed logistic of (current_pf – adj_threshold)
                  weighted by fraction-of-game remaining.  0 = no risk; 1 = foul-out
                  imminent.  Returns 0.5 when player has already fouled out.

  fouls_remaining float in [0, 6].  PF_LIMIT − current_pf_count (clamped to 0).
                  Direct feature for the minutes model (smaller = riskier).

  pf_rate_l5     float ≥ 0.  Historical fouls-per-36-minutes from the last 5 games
                  (from foul_features.parquet via foul_propensity atlas).  Priors for
                  which players chronically attract foul trouble.

Data sources (leak-safe)
------------------------
  LIVE  : ctx.live snapshot dict (src/data/live.py schema) — current pf count per player.
  STORE : "foul_propensity" atlas section read with as_of=ctx.decision_time.
          Backed by data/cache/foul_features.parquet (grain: player_id, game_id, game_date).
  CLOCK : ctx.live["period"] + ctx.live["clock"] — game progress.

DEFER items (missing data)
--------------------------
  DEFER-1: Player-specific foul thresholds for overtime periods are not modelled
           (6 fouls = foul-out in regulation; OT threshold is also 6 but Q tracking
           differs).  Currently uses a fixed PF_LIMIT=6 for all periods.

  DEFER-2: ctx.live player rows do not carry per-quarter foul splits (pf_q1..pf_q4
           are only present in player_quarter_stats.parquet, not in the live snapshot
           base schema — see spec_data.md §6).  The live pf value is cumulative and
           is used directly.

  DEFER-3: Team-level foul state (home_max_player_pfs from inplay_foul_state.parquet)
           is available per game_id×period but is team-aggregate, not player-specific.
           When the individual player's live pf count is missing, we fall back to
           team max_player_pf as a weak proxy — this should be replaced with a proper
           player-level live box join when available.
"""
from __future__ import annotations

import datetime as _dt
import math
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.loop.signal import (
    SCOPES, TARGETS, AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PF_LIMIT: int = 6          # personal fouls until foul-out (NBA regulation)
_FOUL_OUT_PF: int = PF_LIMIT  # alias for clarity

# Minutes elapsed per completed period (each quarter = 12 min; OT = 5 min)
_PERIOD_MINUTES = {1: 12, 2: 12, 3: 12, 4: 12}
_TOTAL_REG_MINUTES: float = 48.0

# Logistic steepness — controls how sharply hazard rises near threshold
_LOGISTIC_K: float = 2.5

ROOT = Path(__file__).resolve().parents[1]
_FOUL_FEAT_PATH = ROOT / "data" / "cache" / "foul_features.parquet"
_FOUL_STATE_PATH = ROOT / "data" / "cache" / "inplay_foul_state.parquet"


# ---------------------------------------------------------------------------
# Module-level lazy cache (avoids re-reading parquet on every call)
# ---------------------------------------------------------------------------

_foul_feat_cache: Optional[pd.DataFrame] = None
_foul_state_cache: Optional[pd.DataFrame] = None


def _load_foul_features() -> pd.DataFrame:
    """Lazy-load foul_features.parquet (player-level L5/L10 pf rates)."""
    global _foul_feat_cache
    if _foul_feat_cache is None:
        try:
            _foul_feat_cache = pd.read_parquet(_FOUL_FEAT_PATH)
            _foul_feat_cache["game_date"] = pd.to_datetime(
                _foul_feat_cache["game_date"]
            ).dt.date
        except Exception as exc:
            warnings.warn(f"foul_out_hazard: cannot load foul_features.parquet: {exc}")
            _foul_feat_cache = pd.DataFrame()
    return _foul_feat_cache


def _load_foul_state() -> pd.DataFrame:
    """Lazy-load inplay_foul_state.parquet (team-level cumulative PFs per period)."""
    global _foul_state_cache
    if _foul_state_cache is None:
        try:
            _foul_state_cache = pd.read_parquet(_FOUL_STATE_PATH)
        except Exception as exc:
            warnings.warn(f"foul_out_hazard: cannot load inplay_foul_state.parquet: {exc}")
            _foul_state_cache = pd.DataFrame()
    return _foul_state_cache


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _elapsed_minutes(period: int, clock_str: str) -> float:
    """Return total elapsed game minutes from period + MM:SS clock string.

    The NBA game clock counts DOWN within a period. period=1 start = 12:00,
    so elapsed_in_period = 12 − remaining.

    Args:
        period:    current period (1..4 regulation, 5+ OT).
        clock_str: string like "8:42" or "M:SS".

    Returns:
        Total elapsed game minutes (0..48+ for OT).
    """
    try:
        parts = clock_str.strip().split(":")
        mins_remaining_in_period = float(parts[0]) + float(parts[1]) / 60.0
    except Exception:
        mins_remaining_in_period = 0.0

    period_length = _PERIOD_MINUTES.get(period, 12)
    mins_elapsed_in_period = period_length - mins_remaining_in_period

    # Sum of completed periods
    completed = sum(_PERIOD_MINUTES.get(p, 12) for p in range(1, period))
    return float(completed + mins_elapsed_in_period)


def _foul_hazard_score(current_pf: int, elapsed: float,
                        total: float = _TOTAL_REG_MINUTES) -> float:
    """Compute hazard in [0, 1] for current foul count + game progress.

    Uses a logistic function centred at the foul threshold adjusted by the
    fraction of game remaining.  More time remaining amplifies the risk.

    Logic:
        fouls_remaining = PF_LIMIT − current_pf
        fraction_remaining = (total − elapsed) / total
        raw = (current_pf − adj_threshold) * K
        hazard = sigmoid(raw) * fraction_weight

    where adj_threshold relaxes slightly at end-of-game (the coach is less
    worried about foul-out with 30 seconds left).

    Args:
        current_pf: player's current personal foul count (cumulative).
        elapsed:    elapsed game minutes.
        total:      expected total game minutes.

    Returns:
        Hazard score in [0, 1].
    """
    if current_pf >= _FOUL_OUT_PF:
        return 0.5   # already fouled out; signal is neutral past this point

    fraction_elapsed = min(elapsed / max(total, 1.0), 1.0)
    fraction_remaining = 1.0 - fraction_elapsed

    # Threshold softens (player can hold more fouls) when little time is left
    adj_threshold = PF_LIMIT - 1.5 + fraction_elapsed  # moves from 4.5 → 5.5

    # Logistic hazard
    raw = _LOGISTIC_K * (current_pf - adj_threshold)
    logistic = 1.0 / (1.0 + math.exp(-raw))

    # Weight by fraction remaining: danger only matters when time is left
    return float(logistic * fraction_remaining)


# ---------------------------------------------------------------------------
# Signal implementation
# ---------------------------------------------------------------------------

class FoulOutHazard(Signal):
    """Foul-out hazard signal for live minutes projections.

    Reads:
      - ctx.live snapshot (current player PF count, period, clock).
      - "foul_propensity" atlas section from the store for pf_per_36_l5 prior.
      - inplay_foul_state.parquet for team-level fallback (DEFER-3).

    Emits three sub-features: hazard, fouls_remaining, pf_rate_l5.
    Returns None when live snapshot is absent (pregame context).
    """

    name: str = "foul_out_hazard"
    target: str = "minutes"
    scope: str = "live"
    reads_atlas: List[str] = ["foul_propensity"]
    emits: List[str] = ["hazard", "fouls_remaining", "pf_rate_l5"]

    # ---- build ---------------------------------------------------------------

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the foul-out hazard sub-features for one live decision.

        Leak-safe: all reads filtered to ctx.decision_time.  Live snapshot
        carries only information visible at halftime / quarter-end, not future
        fouls.

        Args:
            ctx: the decision context.  Must have scope="live" and a populated
                 ctx.live dict with player rows to return non-None.

        Returns:
            Dict with keys hazard, fouls_remaining, pf_rate_l5; or None if
            the context is not live / player not found in the snapshot.
        """
        if ctx.live is None or ctx.player_id is None:
            return None

        # ---- 1. Pull current foul count from the live snapshot ---------------
        current_pf: Optional[float] = None
        players: List[Dict[str, Any]] = ctx.live.get("players", [])
        for row in players:
            if row.get("player_id") == ctx.player_id:
                current_pf = float(row.get("pf", 0) or 0)
                break

        # DEFER-3 fallback: team-level max pf as proxy when player not in snap
        if current_pf is None:
            current_pf = self._team_max_pf_fallback(ctx)

        if current_pf is None:
            return None   # no foul info available

        # ---- 2. Game progress (period + clock) --------------------------------
        period: int = int(ctx.live.get("period", 1))
        clock_str: str = str(ctx.live.get("clock", "12:00"))
        elapsed = _elapsed_minutes(period, clock_str)

        # ---- 3. Hazard score --------------------------------------------------
        hazard = _foul_hazard_score(int(current_pf), elapsed)
        fouls_remaining = max(0.0, float(PF_LIMIT - current_pf))

        # ---- 4. Historical foul-rate prior from atlas -------------------------
        pf_rate_l5 = self._pf_rate_from_atlas(ctx)

        return {
            "hazard": hazard,
            "fouls_remaining": fouls_remaining,
            "pf_rate_l5": pf_rate_l5,
        }

    # ---- hypothesis ----------------------------------------------------------

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's current personal-foul count combined with game clock "
                "determines their foul-out probability, which coaches convert directly "
                "into reduced minutes — a player on 4 fouls early in Q3 is benched "
                "longer than one on 4 fouls in Q4, making this a predictive feature "
                "for remaining-minutes projections in live contexts."
            ),
            rationale=(
                "Minutes-model residuals spike for players who finish with fewer "
                "minutes than projected due to foul trouble (not injury).  The raw "
                "foul count is in the live snapshot; the historical pf_rate_l5 from "
                "foul_features.parquet gives a prior for which players chronically "
                "attract foul trouble.  The product of count × clock-remaining "
                "captures the real coaching decision.  Expected: VARIANCE_ONLY or "
                "SHIP — foul trouble is a sparse but large-magnitude minutes mover."
            ),
            source="seed",
            atlas_fields=["foul_propensity"],
            expected_verdict=Verdict.VARIANCE_ONLY,
            priority="P1",
        )

    # ---- private helpers -----------------------------------------------------

    def _pf_rate_from_atlas(self, ctx: AsOfContext) -> float:
        """Read pf_per_36_l5 from the foul_propensity atlas section (leak-safe).

        Falls back to the raw foul_features.parquet when the store is cold.
        Returns 0.0 as a neutral prior when no data is available.
        """
        # 1. Try store atlas (warmest / fastest path)
        atlas = self.read_atlas(
            f"player:{ctx.player_id}", "foul_propensity", ctx.decision_time
        )
        if atlas is not None:
            val = atlas.get("pf_per_36_l5")
            if val is not None:
                return float(val)

        # 2. Fall back to parquet (cold store)
        if ctx.player_id is None or ctx.game_date is None:
            return 0.0
        df = _load_foul_features()
        if df.empty:
            return 0.0
        try:
            cutoff = _dt.date.fromisoformat(ctx.game_date)
            mask = (
                (df["player_id"] == ctx.player_id)
                & (df["game_date"] < cutoff)        # leak-safe: strictly before
            )
            rows = df[mask].sort_values("game_date").tail(1)
            if rows.empty:
                return 0.0
            val = rows["pf_per_36_l5"].iloc[0]
            return float(val) if pd.notna(val) else 0.0
        except Exception:
            return 0.0

    def _team_max_pf_fallback(self, ctx: AsOfContext) -> Optional[float]:
        """DEFER-3: team-level max_player_pfs as a weak proxy (inplay_foul_state).

        Used only when the individual player row is absent from ctx.live.players.
        This is a conservative overestimate (max across team, not the player's own).
        """
        game_id = ctx.live.get("game_id") if ctx.live else None
        period = ctx.live.get("period", 1) if ctx.live else 1
        if not game_id:
            return None
        df = _load_foul_state()
        if df.empty:
            return None
        try:
            mask = (df["game_id"] == str(game_id)) & (df["period"] == int(period))
            row = df[mask]
            if row.empty:
                return None
            # Determine home vs away from ctx.live for the right column
            home_team = ctx.live.get("home_team", "") if ctx.live else ""
            team = ctx.team or ""
            if team == home_team:
                return float(row["home_max_player_pfs"].iloc[0] or 0)
            else:
                return float(row["away_max_player_pfs"].iloc[0] or 0)
        except Exception:
            return None
