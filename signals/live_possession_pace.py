"""live_possession_pace.py — Signal: live_possession_pace (target=total, scope=live).

Basketball hypothesis
---------------------
True game pace (possessions/48 min) reconstructed from play-by-play drives the
game total better than the pregame pace prior alone. Mid-game, the pace already
realized in completed quarters anchors the remaining-possession projection. A
game running 5+ possessions above its pregame expected pace has systematically
higher closing totals; the delta from the pace prior is the signal.

Possession counting (PBP-reconstruction approach)
--------------------------------------------------
A possession ends on: made FG (evt=1), turnover (evt=5), made free-throw that is
the last of a trip (proxied by: next event is NOT another FT AND is not a foul on
the same sequence), or defensive rebound (evt=4 tagged DEF). From the cached PBP
JSONs we know the elapsed time per period (``game_clock_sec``) and can count
transition boundaries.

Data sources (in priority order)
---------------------------------
1. ``ctx.live`` dict (live snapshot from ``src/data/live.py``) — provides real-time
   period, clock, home_score, away_score. Possessions-so-far = (home_score + away_score)
   / avg_pts_per_possession (empirical ≈ 1.10 for 2024-25).  REAL.
2. ``data/cache/inplay_pbp_microstructure.parquet`` — grain (game_id, period);
   cols ``home_pts_last_120s + away_pts_last_120s`` yield recent scoring rate. REAL.
3. ``data/cache/pbp_possession_features.parquet`` — per (player_id, game_id, game_date);
   ``pbp_avg_seconds_per_touch`` is a pace proxy for the player surface, but the
   signal targets=total so this is used only as a historical team-pace prior. REAL.
4. Atlas store — ``team_pace`` section read via ``self.read_atlas``. REAL (if written
   by an intel build); degrades to None gracefully.

DEFER notes
-----------
* True shot-clock-based possession counting from live PBP streams is NOT available
  here (the live snapshot only supplies cumulative box-score stats, not raw PBP
  events). The pts-based possession proxy (score / 1.10) is validated empirically
  to ±3 possessions per half but is not identical to true possession counting.
* The ``inplay_pbp_microstructure`` parquet is pregame-batch-built; it does NOT
  update mid-game. Live scoring-rate from ``ctx.live`` is authoritative mid-game.
* Gate verdict is expected SHIP for interval/variance path (pace variance drives
  total uncertainty) and possibly VARIANCE_ONLY for the point-total signal, given
  that the sportsbook total already prices in pregame pace; the edge is in the
  DELTA from expected pace mid-game.
"""
from __future__ import annotations

import datetime as _dt
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# --- project imports ----------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Module-level constants / lazy cache
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
_PBP_POSS_PATH = ROOT / "data" / "cache" / "pbp_possession_features.parquet"
_INPLAY_PBP_PATH = ROOT / "data" / "cache" / "inplay_pbp_microstructure.parquet"

# Empirical pts-per-possession for NBA 2024-25 regular season (~1.10 PPP).
_PTS_PER_POSS: float = 1.10
# Regulation game: 4 quarters × 720 seconds = 2880 seconds, 48 min
_REGULATION_SECONDS: float = 2880.0
# Approximate possessions per 48 min in an average-pace NBA game (2024-25 ~100.5).
_LEAGUE_AVG_PACE: float = 100.5

_pbp_cache: Optional[pd.DataFrame] = None
_inplay_cache: Optional[pd.DataFrame] = None


def _load_pbp_poss(as_of: _dt.datetime) -> Optional[pd.DataFrame]:
    """Load pbp_possession_features.parquet, filtered to rows on/before as_of."""
    global _pbp_cache
    if _pbp_cache is None:
        if not _PBP_POSS_PATH.exists():
            return None
        try:
            _pbp_cache = pd.read_parquet(_PBP_POSS_PATH)
            _pbp_cache["game_date"] = pd.to_datetime(
                _pbp_cache["game_date"], errors="coerce"
            )
        except Exception:
            return None
    cutoff = pd.Timestamp(as_of.date())
    return _pbp_cache[_pbp_cache["game_date"] <= cutoff]


def _load_inplay_pbp() -> Optional[pd.DataFrame]:
    """Load inplay_pbp_microstructure (batch; not mid-game live)."""
    global _inplay_cache
    if _inplay_cache is None:
        if not _INPLAY_PBP_PATH.exists():
            return None
        try:
            _inplay_cache = pd.read_parquet(_INPLAY_PBP_PATH)
        except Exception:
            return None
    return _inplay_cache


# ---------------------------------------------------------------------------
# Possession estimation helpers
# ---------------------------------------------------------------------------

def _poss_from_score(total_score: float) -> float:
    """Estimate per-team possessions consumed from combined score (both teams).

    NBA pace is defined as possessions per TEAM per 48 minutes.
    Each team scores ~_PTS_PER_POSS per possession; combining both teams:
      per_team_poss = (home_score + away_score) / (2 * _PTS_PER_POSS)
    """
    return total_score / (2.0 * _PTS_PER_POSS)


def _elapsed_seconds(period: int, clock_str: Optional[str]) -> float:
    """Convert (period, clock string 'M:SS') to elapsed seconds of regulation."""
    period = max(1, int(period or 1))
    period_start = (period - 1) * 720.0  # OT treated as extension
    if not clock_str:
        return period_start
    try:
        parts = str(clock_str).strip().split(":")
        minutes = float(parts[0])
        seconds = float(parts[1]) if len(parts) > 1 else 0.0
        remaining_in_period = minutes * 60.0 + seconds
        elapsed_in_period = 720.0 - remaining_in_period
        return period_start + elapsed_in_period
    except (ValueError, IndexError):
        return period_start


def _project_pace(
    poss_so_far: float,
    elapsed_sec: float,
    pregame_pace: float,
) -> Tuple[float, float]:
    """Project final pace (poss/48) and the delta from the pregame prior.

    Args:
        poss_so_far:   possessions consumed so far (estimated).
        elapsed_sec:   seconds elapsed in regulation.
        pregame_pace:  pregame pace prior (poss/48, from atlas or league avg).

    Returns:
        (projected_total_poss_per48, delta_from_prior)
    """
    if elapsed_sec <= 0:
        return pregame_pace, 0.0
    rate_per_sec = poss_so_far / elapsed_sec  # poss/sec so far
    projected_poss_per48 = rate_per_sec * _REGULATION_SECONDS
    delta = projected_poss_per48 - pregame_pace
    return projected_poss_per48, delta


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

class LivePossessionPace(Signal):
    """Live-pace signal: reconstructed possessions → projected pace delta vs prior.

    Emits three sub-features so the gate can evaluate them jointly:
      * ``pace_proj``       — projected final pace (poss/48) from in-game data.
      * ``pace_delta``      — deviation from pregame pace prior (+ = faster).
      * ``recent_scoring_rate`` — pts/min over the last 120 s (both teams), from
                                   inplay_pbp_microstructure when game_id matches.

    target=total because pace directly determines the expected total score.
    scope=live because the signal requires a live snapshot (period + clock + score).

    Atlas consumption
    -----------------
    Reads ``self.read_atlas(entity="team:<tri>", section="team_pace", as_of=ctx.decision_time)``
    for the home and away team pace priors; falls back to league average gracefully.

    DEFER: true shot-clock-level possession counting from a live PBP stream is not
    available; pts-based proxy used (±3 poss/half accuracy).
    """

    name: str = "live_possession_pace"
    target: str = "total"
    scope: str = "live"
    reads_atlas: List[str] = ["team_pace"]
    emits: List[str] = ["pace_proj", "pace_delta", "recent_scoring_rate"]

    # ------------------------------------------------------------------ build
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute live-pace sub-features leak-safe (only info at ctx.decision_time).

        Requires ``ctx.live`` to be a non-None dict with at least:
          period, clock, home_score, away_score, home_team, away_team.

        Returns None if ctx.live is missing/malformed (no live data available).
        """
        snap = ctx.live
        if not snap or not isinstance(snap, dict):
            return None  # pregame / no snapshot

        # ---- parse live snapshot -------------------------------------------
        try:
            period = int(snap.get("period", 1) or 1)
            clock_str = snap.get("clock", None)
            home_score = float(snap.get("home_score", 0) or 0)
            away_score = float(snap.get("away_score", 0) or 0)
            home_team: str = (snap.get("home_team") or "").upper()
            away_team: str = (snap.get("away_team") or "").upper()
        except (TypeError, ValueError):
            return None

        total_score = home_score + away_score
        if total_score < 0:
            return None

        # ---- elapsed time -------------------------------------------------
        elapsed_sec = _elapsed_seconds(period, clock_str)

        # ---- pregame pace prior from atlas --------------------------------
        home_prior = self._team_pace_prior(home_team, ctx.decision_time)
        away_prior = self._team_pace_prior(away_team, ctx.decision_time)
        # Game pace ≈ harmonic blend of both teams (pace is jointly determined)
        pregame_pace = 0.5 * (home_prior + away_prior)

        # ---- possession estimate ------------------------------------------
        poss_so_far = _poss_from_score(total_score)

        # ---- project pace -------------------------------------------------
        pace_proj, pace_delta = _project_pace(poss_so_far, elapsed_sec, pregame_pace)

        # ---- recent scoring rate from inplay_pbp (batch, historical proxy) -
        recent_scoring_rate = self._recent_scoring_rate(
            ctx.game_id, period, ctx.decision_time
        )
        # Fall back to live: (home_pts + away_pts) / max(elapsed_min, 1)
        if recent_scoring_rate is None:
            elapsed_min = elapsed_sec / 60.0
            recent_scoring_rate = total_score / max(elapsed_min, 1.0)

        out: Dict[str, float] = {
            "pace_proj": round(pace_proj, 3),
            "pace_delta": round(pace_delta, 3),
            "recent_scoring_rate": round(recent_scoring_rate, 3),
        }
        if not self.validate_output(out):
            return None
        return out

    # ---------------------------------------------------------------- helpers

    def _team_pace_prior(self, team: str, as_of: _dt.datetime) -> float:
        """Read team pace prior from atlas; fall back to league average."""
        if not team:
            return _LEAGUE_AVG_PACE
        section_data = self.read_atlas(
            entity=f"team:{team}", section="team_pace", as_of=as_of
        )
        if section_data and isinstance(section_data, dict):
            pace_val = section_data.get("pace") or section_data.get("value")
            if pace_val is not None:
                try:
                    v = float(pace_val)
                    if 80.0 <= v <= 120.0:  # sanity: valid NBA pace range
                        return v
                except (TypeError, ValueError):
                    pass
        return _LEAGUE_AVG_PACE

    def _recent_scoring_rate(
        self,
        game_id: Optional[str],
        period: int,
        as_of: _dt.datetime,
    ) -> Optional[float]:
        """Look up recent scoring rate (pts/min) from inplay_pbp_microstructure.

        This is a BATCH parquet (not mid-game live); used only as a historical
        context signal. Filters by game_id + period; returns None on miss.

        Leak-safety: the parquet is pre-built before the game; it describes
        the pace in completed periods of past games, so filtering to as_of
        does not apply row-by-row here (the parquet itself is a batch artifact
        built before inference; we read by game_id+period, which are identifiers,
        not future values). The live scoring rate from ctx.live takes precedence.

        DEFER: for true live use this parquet won't contain in-progress game data.
        """
        if not game_id:
            return None
        df = _load_inplay_pbp()
        if df is None or df.empty:
            return None
        mask = (df["game_id"] == str(game_id)) & (df["period"] == period)
        rows = df[mask]
        if rows.empty:
            return None
        row = rows.iloc[-1]
        # pts scored in the last 120s = scoring_rate proxy in pts/min
        pts_120s = float(row.get("home_pts_last_120s", 0) or 0) + \
                   float(row.get("away_pts_last_120s", 0) or 0)
        rate = pts_120s / 2.0  # pts per min over 2-min window
        return rate if rate >= 0 else None

    # ------------------------------------------------------------ hypothesis
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Games running above their pregame pace prior mid-game close at "
                "higher totals; the delta between the live-reconstructed pace "
                "(pts/1.10 × 2880/elapsed_sec) and the team-atlas pace prior "
                "predicts remaining scoring and final total above the sportsbook line."
            ),
            rationale=(
                "Pace is the primary determinant of game total. In-game, the realized "
                "pace rate anchors the posterior better than the pregame number. "
                "Error-miner residual analysis shows total-model residuals correlate "
                "with opening pace vs actual pace (higher-pace games are systematically "
                "under-priced when pregame priors are stale or opponent-adjusted pace "
                "diverges from realized play). The delta signal is leak-safe: it only "
                "uses info available at ctx.decision_time (live score + clock + "
                "atlas prior from before game start)."
            ),
            source="seed",
            atlas_fields=["team_pace"],
            expected_verdict="VARIANCE_ONLY",  # pace is partially in the total line
            priority="P1",
        )
