"""signals/comeback_pace.py — ARM-A signal: comeback_pace (target=total, scope=live).

Basketball hypothesis
---------------------
The trailing team in an NBA game deliberately accelerates pace and commits
intentional fouls to manufacture extra possessions and free-throw opportunities.
This behaviour creates a systematic live-game dynamic:

  1. PACE SPIKE — the trailing team runs more transition plays and takes quick
     shots, inflating possessions-per-minute above the pregame prior.
  2. FOUL SURGE — the trailing team intentionally fouls to stop the clock and
     extend the game, sending the leading team to the line for extra FT trips.

Both effects inflate the remaining-game total: more possessions + more FT
stoppages → more scoring opportunities. A trailing team down >= 8 points in Q3
or Q4 is in "comeback mode"; the larger the deficit and the later the period,
the more aggressively they apply these tactics. The combined effect predicts
a higher closing total than the pregame line already implies.

Feature emits (dict signal, 4 sub-features)
--------------------------------------------
  * score_deficit_abs       — absolute current scoring deficit of the trailing
                               team (points behind; 0 if tied or leading for the
                               home-team perspective; unsigned magnitude).
  * comeback_mode_flag      — 1.0 if the trailing team is in "comeback mode"
                               (deficit >= COMEBACK_THRESHOLD points in period >= 3),
                               else 0.0.
  * trailing_ft_trips_rate  — FT trips per quarter for the trailing team from
                               the inplay_pbp_microstructure parquet (last quarter);
                               proxies the foul-to-shoot escalation rate. DEFER-noted
                               when game_id is absent or not yet in the parquet.
  * pace_deficit_interaction — comeback_mode_flag × pace_so_far (from inplay_
                               midquarter_features.parquet when available, else from
                               the live score proxy); interaction term that captures
                               the joint signal: a team playing at high pace AND in
                               comeback mode generates the most possessions.

Target: total — the comeback-pace effect directly raises expected total score.
Scope:  live  — the signal is undefined pre-game; deficit and pace are live concepts.

Data sources
------------
1. ``ctx.live`` (live snapshot dict, src.data.live schema)                 REAL
   Provides period, home_score, away_score, home_team, away_team,
   and per-player PF counts.  This is the primary source at inference time.

2. ``data/cache/inplay_pbp_microstructure.parquet``                        REAL
   Grain (game_id, period); cols ``home_ft_trips_last_quarter``,
   ``away_ft_trips_last_quarter``.  Used to look up FT-trip rates for the
   trailing team in the last completed quarter.  In historical training rows
   (where ctx.live is None) this serves as the source of truth.

3. ``data/cache/inplay_midquarter_features.parquet``                       REAL
   Grain (game_id); cols ``score_margin``, ``pace_so_far``, ``game_date``.
   Provides an in-game pace estimate and score margin for historical training
   rows when ctx.live is absent.

4. Atlas store — ``team_pace`` section (via self.read_atlas)               REAL
   Team pace prior; falls back to league average gracefully.

DEFER notes
-----------
* inplay_pbp_microstructure and inplay_midquarter_features are BATCH parquets
  built before game time; they do NOT update mid-game.  For live inference,
  ctx.live is authoritative; the parquets serve as historical training rows.
* The parquets lack a direct game_date column in inplay_pbp_microstructure,
  so leak-safety is enforced via the gate's walk-forward game_date split (the
  parquet row for a given game_id is only visible once the gate has confirmed
  the game is in the training window).
* True shot-clock-level FT-trip counting from a live PBP stream is not
  available here; the ``ft_trips_last_quarter`` col from the microstructure
  parquet is used as a proxy (built from PBP event type = FT).
* pace_deficit_interaction relies on ``pace_so_far`` from inplay_midquarter
  (Q4 window only, 2,505 games); for non-Q4 periods we fall back to the
  pts-based pace proxy from ctx.live.

Gate verdict expectation
------------------------
SHIP on the comeback_mode_flag and pace_deficit_interaction (jointly the
strongest predictors of total-over in comeback scenarios); trailing_ft_trips_rate
may be VARIANCE_ONLY (adds interval width) rather than point prediction signal.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# --- project imports ----------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
_PBP_MICRO_PATH = ROOT / "data" / "cache" / "inplay_pbp_microstructure.parquet"
_MIDQUARTER_PATH = ROOT / "data" / "cache" / "inplay_midquarter_features.parquet"

# A team is "in comeback mode" when trailing by >= this many points in Q3+.
_COMEBACK_THRESHOLD: float = 8.0
# Start period for comeback mode (Q3 = period 3, Q4 = period 4).
_COMEBACK_MIN_PERIOD: int = 3
# NBA empirical pts per possession (2024-25 season average).
_PTS_PER_POSS: float = 1.10
# Regulation duration in seconds.
_REGULATION_SEC: float = 2880.0
# League-average pace (poss/48 min, 2024-25).
_LEAGUE_AVG_PACE: float = 100.5

# Lazy module-level caches.
_pbp_micro_cache: Optional[pd.DataFrame] = None
_midquarter_cache: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Data loaders (lazy, process-wide singletons)
# ---------------------------------------------------------------------------

def _load_pbp_micro() -> Optional[pd.DataFrame]:
    """Load inplay_pbp_microstructure.parquet once, return cached thereafter."""
    global _pbp_micro_cache
    if _pbp_micro_cache is None:
        if not _PBP_MICRO_PATH.exists():
            _pbp_micro_cache = pd.DataFrame(
                columns=[
                    "game_id", "period",
                    "home_ft_trips_last_quarter", "away_ft_trips_last_quarter",
                    "home_run_last_240s", "away_run_last_240s",
                ]
            )
        else:
            try:
                _pbp_micro_cache = pd.read_parquet(_PBP_MICRO_PATH)
            except Exception:
                _pbp_micro_cache = pd.DataFrame()
    return _pbp_micro_cache if not _pbp_micro_cache.empty else None


def _load_midquarter(as_of: _dt.datetime) -> Optional[pd.DataFrame]:
    """Load inplay_midquarter_features.parquet, filtered to rows on/before as_of."""
    global _midquarter_cache
    if _midquarter_cache is None:
        if not _MIDQUARTER_PATH.exists():
            return None
        try:
            raw = pd.read_parquet(_MIDQUARTER_PATH)
            raw["game_date"] = pd.to_datetime(raw["game_date"], errors="coerce")
            _midquarter_cache = raw
        except Exception:
            return None
    cutoff = pd.Timestamp(as_of.date())
    filtered = _midquarter_cache[_midquarter_cache["game_date"] <= cutoff]
    return filtered if not filtered.empty else None


# ---------------------------------------------------------------------------
# Helper computations
# ---------------------------------------------------------------------------

def _elapsed_seconds(period: int, clock_str: Optional[str]) -> float:
    """Convert (period, 'M:SS' clock string) to elapsed regulation seconds."""
    period = max(1, int(period or 1))
    period_start = (period - 1) * 720.0
    if not clock_str:
        return period_start
    try:
        parts = str(clock_str).strip().split(":")
        minutes = float(parts[0])
        seconds = float(parts[1]) if len(parts) > 1 else 0.0
        remaining = minutes * 60.0 + seconds
        return period_start + (720.0 - remaining)
    except (ValueError, IndexError):
        return period_start


def _pace_from_score(total_score: float, elapsed_sec: float) -> float:
    """Estimate live-game pace (poss/48 min) from combined score and elapsed time."""
    if elapsed_sec <= 0:
        return _LEAGUE_AVG_PACE
    poss_per_sec = total_score / (2.0 * _PTS_PER_POSS * elapsed_sec)
    return poss_per_sec * _REGULATION_SEC


# ---------------------------------------------------------------------------
# Signal class
# ---------------------------------------------------------------------------

class ComebackPaceSignal(Signal):
    """Comeback-pace signal: trailing team's foul + pace escalation → total spike.

    Emits four sub-features (dict signal):
      * score_deficit_abs       — deficit of the trailing team (pts, unsigned).
      * comeback_mode_flag      — 1.0 if trailing >= COMEBACK_THRESHOLD in Q3+.
      * trailing_ft_trips_rate  — FT trips/quarter for the trailing team (last Q).
      * pace_deficit_interaction — comeback_mode_flag × current pace estimate.

    target=total because comeback fouls and pace spikes raise expected total.
    scope=live  because deficit and pace are unknown pre-game.

    Atlas consumption
    -----------------
    Reads ``self.read_atlas(entity="team:<tri>", section="team_pace", as_of=...)``
    for the home and away team pace priors; falls back to league average. The
    pace prior anchors the interaction term before live pace data is available.

    DEFER: inplay_pbp_microstructure does not update mid-game; FT-trip rate
    is a lagged-quarter proxy, not a real-time count from the live PBP stream.
    """

    name: str = "comeback_pace"
    target: str = "total"
    scope: str = "live"
    reads_atlas: List[str] = ["team_pace"]
    emits: List[str] = [
        "score_deficit_abs",
        "comeback_mode_flag",
        "trailing_ft_trips_rate",
        "pace_deficit_interaction",
    ]

    # ------------------------------------------------------------------ build
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute comeback-pace sub-features, leak-safe at ctx.decision_time.

        Strategy (priority order):
          1. ctx.live is present → direct snapshot computation (inference path).
          2. ctx.live is None, ctx.game_id present → parquet lookup (train path).
          3. Neither available → return None (neutral).

        Leak-safety: parquet reads for inplay_midquarter_features are filtered
        by game_date <= ctx.decision_time.  The inplay_pbp_microstructure lookup
        is keyed by game_id + period; the gate's walk-forward split enforces
        that a game_id row is only used in training after the game has concluded.
        """
        if ctx.live is not None:
            return self._from_live(ctx)
        return self._from_parquet(ctx)

    # ---------------------------------------------------------------- live path

    def _from_live(self, ctx: AsOfContext) -> Optional[SignalValue]:
        """Derive all sub-features from the live snapshot dict."""
        snap = ctx.live
        if not isinstance(snap, dict):
            return None

        try:
            period = int(snap.get("period", 1) or 1)
            clock_str = snap.get("clock", None)
            home_score = float(snap.get("home_score", 0) or 0)
            away_score = float(snap.get("away_score", 0) or 0)
            home_team: str = (snap.get("home_team") or "").upper()
            away_team: str = (snap.get("away_team") or "").upper()
        except (TypeError, ValueError):
            return None

        score_diff = home_score - away_score  # positive = home leading
        deficit_abs = abs(score_diff)
        # The trailing team is identified for FT-trip lookup.
        home_is_trailing = score_diff < 0

        # Comeback mode: trailing by >= threshold in period >= COMEBACK_MIN_PERIOD.
        comeback_flag = 1.0 if (
            deficit_abs >= _COMEBACK_THRESHOLD and period >= _COMEBACK_MIN_PERIOD
        ) else 0.0

        # Pace from live score + elapsed time.
        elapsed_sec = _elapsed_seconds(period, clock_str)
        total_score = home_score + away_score
        pace_live = _pace_from_score(total_score, elapsed_sec)

        # FT trips for the trailing team (last completed quarter) from parquet.
        trailing_ft_rate = self._trailing_ft_trips(
            ctx.game_id, period, home_is_trailing=(score_diff < 0)
        )

        # Interaction: comeback_flag × pace.
        pace_prior = self._team_pace_prior(home_team, away_team, ctx.decision_time)
        pace_for_interaction = pace_live if elapsed_sec > 60.0 else pace_prior
        interaction = comeback_flag * pace_for_interaction

        out: Dict[str, float] = {
            "score_deficit_abs": round(deficit_abs, 2),
            "comeback_mode_flag": comeback_flag,
            "trailing_ft_trips_rate": round(trailing_ft_rate, 3),
            "pace_deficit_interaction": round(interaction, 3),
        }
        if not self.validate_output(out):
            return None
        return out

    # ------------------------------------------------------------ parquet path

    def _from_parquet(self, ctx: AsOfContext) -> Optional[SignalValue]:
        """Derive sub-features from the in-play parquets (historical training path).

        Uses inplay_midquarter_features for score_margin + pace_so_far and
        inplay_pbp_microstructure for FT-trip rates.

        Leak-safety: inplay_midquarter_features is filtered to game_date <=
        ctx.decision_time before any lookup.
        """
        game_id = ctx.game_id
        if game_id is None:
            return None

        # --- midquarter features (pace + margin) ---------------------------
        mq_df = _load_midquarter(ctx.decision_time)
        if mq_df is None:
            return None
        mq_row_df = mq_df[mq_df["game_id"] == str(game_id)]
        if mq_row_df.empty:
            return None
        mq_row = mq_row_df.iloc[-1]

        score_margin = float(mq_row.get("score_margin", 0) or 0)
        deficit_abs = abs(score_margin)
        pace_so_far = float(mq_row.get("pace_so_far", _LEAGUE_AVG_PACE) or _LEAGUE_AVG_PACE)

        # --- period inference from snapshot label --------------------------
        period = self._period_from_snapshot(ctx.snapshot) or 4  # midquarter = Q4

        comeback_flag = 1.0 if (
            deficit_abs >= _COMEBACK_THRESHOLD and period >= _COMEBACK_MIN_PERIOD
        ) else 0.0

        # --- FT trips from pbp microstructure ------------------------------
        # score_margin > 0 → home leading → away is trailing
        home_is_trailing = score_margin > 0
        trailing_ft_rate = self._trailing_ft_trips(game_id, period, home_is_trailing)

        interaction = comeback_flag * pace_so_far

        out: Dict[str, float] = {
            "score_deficit_abs": round(deficit_abs, 2),
            "comeback_mode_flag": comeback_flag,
            "trailing_ft_trips_rate": round(trailing_ft_rate, 3),
            "pace_deficit_interaction": round(interaction, 3),
        }
        if not self.validate_output(out):
            return None
        return out

    # ---------------------------------------------------------------- helpers

    def _trailing_ft_trips(
        self,
        game_id: Optional[str],
        period: int,
        home_is_trailing: bool,
    ) -> float:
        """Look up FT trips/quarter for the trailing team from the pbp microstructure.

        Returns 0.0 when the parquet row is absent (DEFER: no live update).
        Negative period → period already at Q1 → no last-quarter data yet.
        """
        if game_id is None or period < 2:
            return 0.0
        micro = _load_pbp_micro()
        if micro is None:
            return 0.0
        # Use the most recent completed period = period - 1, or current period.
        lookup_period = max(1, period - 1)
        mask = (micro["game_id"] == str(game_id)) & (micro["period"] == lookup_period)
        rows = micro[mask]
        if rows.empty:
            return 0.0
        row = rows.iloc[-1]
        col = "home_ft_trips_last_quarter" if home_is_trailing else "away_ft_trips_last_quarter"
        val = row.get(col, 0)
        return float(val) if val is not None else 0.0

    def _team_pace_prior(
        self,
        home_team: str,
        away_team: str,
        as_of: _dt.datetime,
    ) -> float:
        """Read pace prior from atlas for both teams; return harmonic blend."""
        def _read(tri: str) -> float:
            if not tri:
                return _LEAGUE_AVG_PACE
            data = self.read_atlas(f"team:{tri}", "team_pace", as_of)
            if data and isinstance(data, dict):
                v = data.get("pace") or data.get("value")
                if v is not None:
                    try:
                        fv = float(v)
                        if 80.0 <= fv <= 125.0:
                            return fv
                    except (TypeError, ValueError):
                        pass
            return _LEAGUE_AVG_PACE

        return 0.5 * (_read(home_team) + _read(away_team))

    @staticmethod
    def _period_from_snapshot(snapshot: Optional[str]) -> Optional[int]:
        """Map 'endQN' label to integer period."""
        _map = {"endQ1": 1, "endQ2": 2, "endQ3": 3, "endQ4": 4}
        return _map.get(snapshot or "", None)

    # ------------------------------------------------------------ hypothesis
    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "The trailing team in an NBA game (deficit >= 8 pts in Q3/Q4) "
                "deliberately raises pace and commits intentional fouls to extend "
                "the game, generating more possessions and FT opportunities. "
                "The combined pace-spike and FT-surge inflates the closing total "
                "above the pregame line, predictable from the live score deficit, "
                "current pace, and lagged FT-trip rate."
            ),
            rationale=(
                "Comeback dynamics are a well-documented strategic pattern: "
                "trailing teams run transition offenses to cut shot-clock time "
                "and foul intentionally to stop the clock. Both behaviours raise "
                "total possessions and FT attempts, directly lifting expected "
                "total points. The signal is purely live (no pregame analogue) "
                "and reads only information available at ctx.decision_time. "
                "The interaction term (comeback_flag × pace) captures the joint "
                "effect: a slow-paced comeback game generates fewer extra "
                "possessions than a fast-paced one."
            ),
            source="seed",
            atlas_fields=["team_pace"],
            expected_verdict="SHIP",
            priority="P1",
        )
