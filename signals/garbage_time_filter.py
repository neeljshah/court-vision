"""Signal: garbage_time_filter — blowout noise suppressor (target=pts, scope=both).

Basketball hypothesis
---------------------
Blowout garbage-time minutes are noise: when a game is decided early the losing
team's starters sit, benchwarmers pad or suppress stats unpredictably, and the
winning team's stars rest.  Training on these rows corrupts the model's signal.
This signal emits the fraction of a game that was in *garbage time* (margin >= 15
with <= 5 min left in Q4) as a continuous feature.  At inference (pregame/live) it
emits a blowout probability derived from the pre-game spread / ELO differential.

Feature emitted
---------------
``garbage_time_filter`` → float in [0, 1].
  * Training rows: ground-truth ``gt_frac`` from
    ``data/intelligence/garbage_time_segments.parquet`` joined on ``game_id``.
  * Pregame inference: blowout probability estimated from
    ``data/pregame_spreads.parquet`` (``abs(home_spread)``) and
    ``data/nba/season_games_<season>.json`` (``sim_score_diff_std``).
  * Live inference: live Q4 score margin from ``ctx.live`` snapshot scaled to [0,1].

Data sources used
-----------------
PRIMARY (training):
  ``data/intelligence/garbage_time_segments.parquet``
  grain: (game_id, period, clock) — is_garbage_time bool
  → aggregated to per-game ``gt_frac = mean(is_garbage_time)`` [0, 1].

SECONDARY (pre-game proxy):
  ``data/pregame_spreads.parquet``
  grain: (game_date, home_team, away_team) — home_spread float
  → logistic transform of abs(home_spread) → blowout probability.

  ``data/nba/season_games_<season>.json`` (rows keyed by game_id)
  → sim_score_diff_std used to narrow the spread-to-probability conversion.

TERTIARY (live):
  ctx.live snapshot keys: ``score_margin`` or derive from home_score/away_score.

Atlas reads
-----------
``game_context`` section (if written by ARM-B): may carry ``expected_margin``
or ``blowout_prob`` for the matchup.  Used as a soft prior when available.

DEFER items
-----------
* ``sim_score_diff_std`` from season_games is MISSING for ~40 % of game_ids
  (early-season rows have defaults of 10.2).  The signal degrades gracefully
  to spread-only when std is unavailable.
* Pregame spread coverage is ~2024-25 season only (data/pregame_spreads.parquet
  has 1316 rows vs ~3000 expected for 3+ seasons).  For out-of-coverage rows the
  signal returns ``None`` (neutral) so the training matrix loses no rows — they
  are NaN-filled by the model's median imputer.
* Gate verdict expectation: SHIP for PTS (strongest garbage-time suppression);
  VARIANCE_ONLY for REB/AST (blowout affects volume but minutes are the driver).
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# --------------------------------------------------------------------------- #
# Repo root — script-relative, never hardcoded (memory: RunPod compatibility)  #
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# Paths                                                                         #
# --------------------------------------------------------------------------- #
_GT_SEGMENTS_PATH = _ROOT / "data" / "intelligence" / "garbage_time_segments.parquet"
_SPREADS_PATH = _ROOT / "data" / "pregame_spreads.parquet"
_SEASON_GAMES_DIR = _ROOT / "data" / "nba"

# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #
# Logistic function: P(blowout) = sigmoid(k * (|spread| - threshold))
_SPREAD_THRESHOLD = 8.0   # spreads above this start signalling blowout risk
_SPREAD_K = 0.25          # steepness

# Live: score margin that constitutes garbage time (pts)
_LIVE_GT_MARGIN = 15.0
# Remaining minutes threshold for live Q4 garbage time
_LIVE_MIN_REMAINING = 5.0

# Module-level caches (populated on first access; invalidated by _as_of gate)
_gt_cache: Optional[pd.DataFrame] = None          # game_id -> gt_frac
_spreads_cache: Optional[pd.DataFrame] = None      # date+teams -> home_spread
_season_games_cache: Dict[str, Dict[str, Any]] = {}  # season -> {game_id: row}


# --------------------------------------------------------------------------- #
# Data loaders (lazy, process-scoped)                                           #
# --------------------------------------------------------------------------- #

def _load_gt_per_game() -> pd.DataFrame:
    """Return a DataFrame (game_id, gt_frac, build_date) from the segments file."""
    global _gt_cache
    if _gt_cache is not None:
        return _gt_cache
    if not _GT_SEGMENTS_PATH.exists():
        _gt_cache = pd.DataFrame(columns=["game_id", "gt_frac", "build_date"])
        return _gt_cache
    raw = pd.read_parquet(_GT_SEGMENTS_PATH, columns=["game_id", "is_garbage_time", "build_date"])
    agg = (
        raw.groupby("game_id")
        .agg(
            gt_frac=("is_garbage_time", "mean"),
            build_date=("build_date", "first"),
        )
        .reset_index()
    )
    _gt_cache = agg
    return _gt_cache


def _load_spreads() -> pd.DataFrame:
    """Return pregame spreads DataFrame."""
    global _spreads_cache
    if _spreads_cache is not None:
        return _spreads_cache
    if not _SPREADS_PATH.exists():
        _spreads_cache = pd.DataFrame(
            columns=["game_date", "home_team", "away_team", "home_spread"]
        )
        return _spreads_cache
    _spreads_cache = pd.read_parquet(
        _SPREADS_PATH,
        columns=["game_date", "home_team", "away_team", "home_spread"],
    )
    return _spreads_cache


def _load_season_games(season: str) -> Dict[str, Any]:
    """Return {game_id: row_dict} for the given season (lazy, cached)."""
    if season in _season_games_cache:
        return _season_games_cache[season]
    path = _SEASON_GAMES_DIR / f"season_games_{season}.json"
    if not path.exists():
        _season_games_cache[season] = {}
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("rows", []) if isinstance(data, dict) else data
    mapping = {str(r.get("game_id", "")): r for r in rows if r.get("game_id")}
    _season_games_cache[season] = mapping
    return mapping


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _spread_to_blowout_prob(abs_spread: float, sim_std: Optional[float] = None) -> float:
    """Convert absolute pregame spread to blowout probability [0, 1].

    Uses a logistic centred at ``_SPREAD_THRESHOLD`` (8 pts).  When
    ``sim_std`` is available it adjusts steepness: a tighter std means
    the game is more predictable, amplifying the spread signal.
    """
    k = _SPREAD_K
    if sim_std is not None and sim_std > 0:
        # Narrower distribution → game more decided → steeper logistic
        k = k * (10.2 / sim_std)  # 10.2 = empirical mean std from season_games
    return _sigmoid(k * (abs_spread - _SPREAD_THRESHOLD))


def _live_gt_fraction(live: Dict[str, Any]) -> Optional[float]:
    """Estimate garbage-time fraction from a live snapshot dict.

    Returns a float [0, 1] or None if the snapshot is insufficient.
    Schema: period (int), clock ("M:SS"), home_score, away_score.
    """
    try:
        period = int(live.get("period", 0))
        if period != 4:
            return 0.0  # Only Q4 is garbage time
        # Parse clock
        clock_str = str(live.get("clock", "12:00"))
        parts = clock_str.split(":")
        minutes_remaining = float(parts[0]) + float(parts[1]) / 60.0
        if minutes_remaining > _LIVE_MIN_REMAINING:
            return 0.0  # Too early in Q4

        home_score = float(live.get("home_score", 0))
        away_score = float(live.get("away_score", 0))
        margin = abs(home_score - away_score)
        if margin < _LIVE_GT_MARGIN:
            return 0.0
        # Scale: margin 15 → ~0.5, margin 25 → ~0.9, saturates at 1.0
        # Sigmoid centred at 15 with steepness 0.15
        return min(1.0, _sigmoid(0.15 * (margin - _LIVE_GT_MARGIN)))
    except (TypeError, ValueError, IndexError):
        return None


# --------------------------------------------------------------------------- #
# Signal class                                                                  #
# --------------------------------------------------------------------------- #

class GarbageTimeFilter(Signal):
    """Blowout / garbage-time noise suppressor signal (target=pts, scope=both).

    Emits the fraction of the game that was in garbage time (ground-truth during
    training; blowout probability at inference time).  The model learns that rows
    with high values are high-noise and should contribute less to the gradient.

    Reads atlas sections:
      ``game_context`` — optional matchup-level ``blowout_prob`` written by ARM-B.
    """

    name: str = "garbage_time_filter"
    target: str = "pts"
    scope: str = "both"
    reads_atlas: List[str] = ["game_context"]
    emits: List[str] = []  # scalar signal; no sub-features

    # --------------------------------------------------------------------- #
    # Core build                                                              #
    # --------------------------------------------------------------------- #

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return a float [0, 1] representing blowout / garbage-time fraction.

        Leak-safety contract:
        * Training rows: reads ``data/intelligence/garbage_time_segments.parquet``
          filtered by ``build_date <= ctx.decision_time`` (only past labels).
        * Pregame rows: reads ``data/pregame_spreads.parquet`` (fetched before
          game tip-off) and season_games (built from completed-game data before
          the season starts — safe as pre-game prior).
        * Live rows: reads ``ctx.live`` snapshot (real-time; only used when
          ``ctx.scope == 'live'``).

        Returns ``None`` (neutral) when no data is available for this game.
        """
        decision_iso = ctx.as_of_iso()  # YYYY-MM-DD

        # ----------------------------------------------------------------- #
        # 1. Try to read the atlas for a matchup-level blowout prior          #
        # ----------------------------------------------------------------- #
        atlas_prior: Optional[float] = None
        if self.store is not None and ctx.game_id is not None:
            game_ctx = self.read_atlas(
                f"game:{ctx.game_id}", "game_context", ctx.decision_time
            )
            if isinstance(game_ctx, dict):
                bp = game_ctx.get("blowout_prob")
                if bp is not None:
                    try:
                        atlas_prior = float(bp)
                    except (TypeError, ValueError):
                        pass

        # ----------------------------------------------------------------- #
        # 2. Live scope: use the live snapshot margin                          #
        # ----------------------------------------------------------------- #
        if ctx.scope == "live" and ctx.live is not None:
            frac = _live_gt_fraction(ctx.live)
            if frac is not None:
                return float(frac)
            # Fallback to pregame path if live parse fails

        # ----------------------------------------------------------------- #
        # 3. Training / pregame: check the ground-truth segments table        #
        #    (only use rows whose build_date <= decision_time — LEAK-SAFE)   #
        # ----------------------------------------------------------------- #
        if ctx.game_id is not None:
            gt_df = _load_gt_per_game()
            row = gt_df[gt_df["game_id"] == str(ctx.game_id)]
            if not row.empty:
                build_date = row["build_date"].iloc[0]
                # Leak guard: only use if the segments were built before decision
                try:
                    if str(build_date) <= decision_iso:
                        return float(row["gt_frac"].iloc[0])
                except (TypeError, ValueError):
                    pass

        # ----------------------------------------------------------------- #
        # 4. Pregame: derive blowout probability from spread / ELO            #
        # ----------------------------------------------------------------- #
        if ctx.game_date is not None and ctx.team is not None:
            spreads = _load_spreads()
            if not spreads.empty:
                # Match by game_date + team membership (home or away)
                mask = (
                    (spreads["game_date"] == ctx.game_date)
                    & (
                        (spreads["home_team"] == ctx.team)
                        | (spreads["away_team"] == ctx.team)
                    )
                )
                matched = spreads[mask]
                if not matched.empty:
                    home_spread = float(matched["home_spread"].iloc[0])
                    abs_spread = abs(home_spread)

                    # Optionally read sim_score_diff_std from season_games
                    sim_std: Optional[float] = None
                    if ctx.season and ctx.game_id:
                        sg_map = _load_season_games(ctx.season)
                        sg_row = sg_map.get(str(ctx.game_id), {})
                        raw_std = sg_row.get("sim_score_diff_std")
                        if raw_std is not None:
                            try:
                                sim_std = float(raw_std)
                            except (TypeError, ValueError):
                                pass

                    prob = _spread_to_blowout_prob(abs_spread, sim_std)
                    # Blend with atlas prior if available
                    if atlas_prior is not None:
                        prob = 0.5 * prob + 0.5 * atlas_prior
                    return prob

        # 5. Atlas prior as last resort (ARM-B provided a blowout estimate)
        if atlas_prior is not None:
            return atlas_prior

        # 6. No data available → neutral (NaN-fill handled by model)
        return None

    # --------------------------------------------------------------------- #
    # Hypothesis                                                              #
    # --------------------------------------------------------------------- #

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Games with high garbage-time fractions produce noisy, "
                "unrepresentative stat lines; down-weighting or excluding these "
                "rows reduces training noise and improves out-of-sample MAE for "
                "PTS (and, secondarily, REB/AST)."
            ),
            rationale=(
                "Existing haircut (apply_garbage_time_haircut) shows spread >=6 "
                "already ships (0.98–0.92 factors for PTS/REB/AST).  A continuous "
                "gt_frac feature gives the model richer blowout context and allows "
                "it to learn the non-linear relationship between blowout severity "
                "and stat distortion, beyond what the coarse 3-bin haircut captures."
            ),
            source="seed",
            atlas_fields=["game_context"],
            expected_verdict="SHIP",
            priority="P1",
        )
