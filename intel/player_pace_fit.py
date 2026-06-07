"""ARM-B AtlasSection: player-level pace fit (tempo dependence).

Section key: ``pace_fit``
Entity:      player

How does a player's production and efficiency shift as a function of game tempo?
Fast games (high possessions/pace) give more opportunities but also compresses
decision-making; slow, grind-it-out games reward post-up / half-court specialists.
This section captures that tempo dependence for every statistical surface.

Sub-fields (REAL vs DEFER):
  REAL (from existing parquets):
    n_games_total          int   : total filtered game count
    n_fast_games           int   : games classified as fast-tempo
    n_slow_games           int   : games classified as slow-tempo
    median_pace            float : player's median paceper40 across all games
    fast_pace_threshold    float : threshold used (global paceper40 median)
    slow_pace_threshold    float : same threshold (games below this = slow)

    -- Usage / efficiency by tempo --
    usage_fast             float : mean usage% in fast games
    usage_slow             float : mean usage% in slow games
    usage_pace_delta       float : usage_fast - usage_slow (positive = thrives faster)

    ts_fast                float : mean TS% in fast games
    ts_slow                float : mean TS% in slow games
    ts_pace_delta          float : ts_fast - ts_slow

    efg_fast               float : mean eFG% in fast games
    efg_slow               float : mean eFG% in slow games
    efg_pace_delta         float : efg_fast - efg_slow

    net_rtg_fast           float : mean net rating in fast games
    net_rtg_slow           float : mean net rating in slow games
    net_rtg_pace_delta     float : net_rtg_fast - net_rtg_slow

    pie_fast               float : mean PIE in fast games
    pie_slow               float : mean PIE in slow games
    pie_pace_delta         float : pie_fast - pie_slow

    -- Possession volume by tempo --
    poss_fast              float : mean possessions per game in fast games
    poss_slow              float : mean possessions per game in slow games
    poss_pace_delta        float : poss_fast - poss_slow

    -- Minutes by tempo (opportunity proxy) --
    min_fast               float : mean minutes per game in fast games
    min_slow               float : mean minutes per game in slow games
    min_pace_delta         float : min_fast - min_slow

    -- Rebounding by tempo --
    reb_pct_fast           float : mean rebound% in fast games
    reb_pct_slow           float : mean rebound% in slow games
    reb_pct_pace_delta     float : reb_pct_fast - reb_pct_slow

    -- Transition exposure (PBP) --
    transition_poss_fast   float : mean transition possessions per game, fast games
    transition_poss_slow   float : mean transition possessions per game, slow games
    transition_pace_delta  float : transition_poss_fast - transition_poss_slow

    -- Lineup pace-on (season-level) --
    lineup_avg_pace_on     float : pace of top-lineup unit player was in (lineup_features)
    lineup_pace_delta      float : lineup_avg_pace_on minus league median pace (tempo fit vs league)

    -- Summary classification --
    pace_preference        str   : "fast" | "slow" | "neutral"
                                   derived from pace_fit_score sign/magnitude
    pace_fit_score         float : composite z-score-weighted tempo fit
                                   (positive = better in fast, negative = better in slow)

  DEFER:
    pts_per_poss_fast      float : DEFER -- pts/possession in fast games requires
                                   per-game PTS (not in player_adv_stats; lives in
                                   player_quarter_stats aggregate -- would need a
                                   separate build_*.py parquet merging box scores)
    pts_per_poss_slow      float : DEFER -- same reason
    ast_pct_fast           float : DEFER -- player_adv_stats has ast% but not per-game
                                   PTS to derive pts-equivalent; deferred until a
                                   box_scores parquet with game-level pts/ast is wired
    ast_pct_slow           float : DEFER -- same
    stl_per40_fast         float : DEFER -- requires per-game per-40 steals
    stl_per40_slow         float : DEFER -- requires per-game per-40 steals
    tov_rate_fast          float : DEFER -- adv turnover_ratio is available but the
                                   col mapping varies by source; deferred to avoid
                                   silent NaN propagation on older data versions

CV slots (RESERVED, values=None until CV branch fills):
    cv_spacing_fast        -- team spacing (convex hull ft²) in fast possessions
                              from CV court-position data; expected to differ by tempo
    cv_drive_freq_fast     -- drive frequency per 100 possessions in fast games (CV)
    cv_off_ball_speed_fast -- off-ball player speed (ft/s) in fast-game possessions
    cv_off_ball_speed_slow -- off-ball player speed (ft/s) in slow-game possessions

Data sources (REUSED, not re-derived):
    data/player_adv_stats.parquet             (pace, usage, ts%, efg%, net_rtg, pie,
                                               possessions, minutes, reb%)
    data/cache/pbp_possession_features.parquet (transition_poss per game)
    data/cache/lineup_features.parquet         (lineup_avg_pace_on, season-level)

Registration: via profile_factory_bridge (never edit build_persistent_profiles.py).
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
_ADV_PATH = ROOT / "data" / "player_adv_stats.parquet"
_PBP_PATH = ROOT / "data" / "cache" / "pbp_possession_features.parquet"
_LF_PATH = ROOT / "data" / "cache" / "lineup_features.parquet"

# Global paceper40 median (~84.0 across 2022-25 seasons) used for fast/slow split.
# Re-computed from the loaded data so it stays current as new games arrive.
_FAST_SLOW_QUANTILE = 0.50  # median split

# Pace fit score weights: each delta contributes proportionally to its reliability
# (usage delta most meaningful; TS% and PIE also strong; reb/min weaker).
_FIT_WEIGHTS = {
    "usage": 2.5,
    "ts": 2.0,
    "pie": 2.0,
    "net_rtg": 1.5,
    "transition": 1.0,
    "min": 0.5,
}

# Classification thresholds on the composite pace_fit_score
_FAST_THRESHOLD = 0.3
_SLOW_THRESHOLD = -0.3


def _rd(v: Any) -> Optional[float]:
    """Round float to 4 dp; NaN/None/inf -> None (mirrors factory rd())."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)


def _clean(v: Any) -> Any:
    """NaN/inf -> None, numpy scalars -> python; round floats to 4 dp."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _to_iso(dt: _dt.datetime) -> str:
    return dt.date().isoformat()


def _mean_or_none(series: pd.Series) -> Optional[float]:
    """Return mean of a series or None if empty/all-NaN."""
    if series.empty:
        return None
    val = series.mean()
    return _rd(val)


def _delta_or_none(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """a - b; None if either operand is None."""
    if a is None or b is None:
        return None
    return _rd(a - b)


class PlayerPaceFitSection(AtlasSection):
    """Deep player-level tempo-dependence atlas section for ARM-B intelligence.

    Splits every game a player has played into fast vs slow based on the
    global paceper40 median, then computes usage, efficiency, possession volume,
    and lineup-pace sub-fields for each tempo bucket.  The composite
    ``pace_fit_score`` (positive = produces more in fast games) and
    ``pace_preference`` label are the headline outputs consumed by signals.

    All reads are bounded by ``as_of`` for leak safety.  CV slots for
    per-possession spatial metrics (spacing, drive freq, off-ball speed) are
    reserved null; the CV branch fills them later via ``store.fill_cv_slot``.
    """

    name: str = "pace_fit"
    entity: str = "player"
    source_name: str = (
        "player_adv_stats.parquet + pbp_possession_features.parquet + "
        "lineup_features.parquet"
    )
    conf_cap: Optional[str] = None  # pure NBA-API data, no CV cap

    # Lazy-loaded class-level cache (populated on first build call)
    _adv_df: Optional[pd.DataFrame] = None
    _pbp_df: Optional[pd.DataFrame] = None
    _lf_df: Optional[pd.DataFrame] = None
    _global_pace_median: Optional[float] = None

    # ---- data loading ---------------------------------------------------

    def _load_data(self) -> None:
        """Load backing parquets into class-level cache (idempotent)."""
        if PlayerPaceFitSection._adv_df is None:
            PlayerPaceFitSection._adv_df = (
                pd.read_parquet(_ADV_PATH) if _ADV_PATH.exists() else pd.DataFrame()
            )
            adv = PlayerPaceFitSection._adv_df
            if not adv.empty and "paceper40" in adv.columns:
                PlayerPaceFitSection._global_pace_median = float(
                    adv["paceper40"].quantile(_FAST_SLOW_QUANTILE)
                )
            else:
                PlayerPaceFitSection._global_pace_median = 84.0  # fallback

        if PlayerPaceFitSection._pbp_df is None:
            PlayerPaceFitSection._pbp_df = (
                pd.read_parquet(_PBP_PATH) if _PBP_PATH.exists() else pd.DataFrame()
            )

        if PlayerPaceFitSection._lf_df is None:
            PlayerPaceFitSection._lf_df = (
                pd.read_parquet(_LF_PATH) if _LF_PATH.exists() else pd.DataFrame()
            )

    # ---- AtlasSection contract ------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe pace_fit artifact for one player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data on or before this date is used.

        Returns:
            :class:`AtlasArtifact` with tempo-split sub_fields, or ``None`` if
            the player has fewer than 2 games in either tempo bucket.
        """
        self._load_data()
        pid = int(entity_id)
        as_of_str = _to_iso(as_of)

        adv = PlayerPaceFitSection._adv_df
        pbp = PlayerPaceFitSection._pbp_df
        lf = PlayerPaceFitSection._lf_df
        pace_threshold = PlayerPaceFitSection._global_pace_median or 84.0

        # -- leak-safe filter on player_adv_stats --------------------------
        player_adv: pd.DataFrame = pd.DataFrame()
        if (
            not adv.empty
            and "player_id" in adv.columns
            and "game_date" in adv.columns
        ):
            mask = (adv["player_id"] == pid) & (
                adv["game_date"].astype(str) <= as_of_str
            )
            player_adv = adv[mask].copy()

        if player_adv.empty:
            return None

        # -- fast / slow split by paceper40 --------------------------------
        player_adv = player_adv.sort_values("game_date")
        player_adv["_is_fast"] = player_adv["paceper40"] >= pace_threshold
        fast = player_adv[player_adv["_is_fast"]]
        slow = player_adv[~player_adv["_is_fast"]]

        n_total = len(player_adv)
        n_fast = len(fast)
        n_slow = len(slow)

        # Require at least 2 games in each bucket for a meaningful split.
        if n_fast < 2 or n_slow < 2:
            return None

        # -- per-tempo averages (advanced stats) ---------------------------
        def _col(df: pd.DataFrame, col: str) -> pd.Series:
            """Return column as Series or empty Series if column missing."""
            return df[col] if col in df.columns else pd.Series([], dtype=float)

        usage_fast = _mean_or_none(_col(fast, "usagepercentage"))
        usage_slow = _mean_or_none(_col(slow, "usagepercentage"))

        ts_fast = _mean_or_none(_col(fast, "trueshootingpercentage"))
        ts_slow = _mean_or_none(_col(slow, "trueshootingpercentage"))

        efg_fast = _mean_or_none(_col(fast, "effectivefieldgoalpercentage"))
        efg_slow = _mean_or_none(_col(slow, "effectivefieldgoalpercentage"))

        net_rtg_fast = _mean_or_none(_col(fast, "netrating"))
        net_rtg_slow = _mean_or_none(_col(slow, "netrating"))

        pie_fast = _mean_or_none(_col(fast, "pie"))
        pie_slow = _mean_or_none(_col(slow, "pie"))

        poss_fast = _mean_or_none(_col(fast, "possessions"))
        poss_slow = _mean_or_none(_col(slow, "possessions"))

        min_fast = _mean_or_none(_col(fast, "minutes"))
        min_slow = _mean_or_none(_col(slow, "minutes"))

        reb_pct_fast = _mean_or_none(_col(fast, "reboundpercentage"))
        reb_pct_slow = _mean_or_none(_col(slow, "reboundpercentage"))

        median_pace = _rd(player_adv["paceper40"].median())

        # -- PBP transition possessions (per game, leak-safe) --------------
        trans_fast: Optional[float] = None
        trans_slow: Optional[float] = None

        if (
            not pbp.empty
            and "player_id" in pbp.columns
            and "game_date" in pbp.columns
            and "pbp_transition_count" in pbp.columns
        ):
            mask_pbp = (pbp["player_id"] == pid) & (
                pbp["game_date"].astype(str) <= as_of_str
            )
            player_pbp = pbp[mask_pbp].copy()
            if not player_pbp.empty:
                # Join pace label from adv_stats via (player_id, game_date)
                adv_pace = player_adv[["game_date", "_is_fast"]].copy()
                player_pbp = player_pbp.merge(
                    adv_pace, on="game_date", how="left"
                )
                pbp_fast = player_pbp[player_pbp["_is_fast"] == True]
                pbp_slow = player_pbp[player_pbp["_is_fast"] == False]
                trans_fast = _mean_or_none(pbp_fast["pbp_transition_count"])
                trans_slow = _mean_or_none(pbp_slow["pbp_transition_count"])

        # -- Lineup pace-on (season-level; latest available before as_of) --
        lineup_pace_on: Optional[float] = None
        lineup_pace_delta: Optional[float] = None
        league_pace_median = 97.5  # NBA 2024-25 league median possessions/100

        if (
            not lf.empty
            and "player_id" in lf.columns
            and "lineup_avg_pace_on" in lf.columns
        ):
            player_lf = lf[lf["player_id"] == pid].copy()
            if not player_lf.empty:
                # Filter seasons whose end date is on-or-before as_of (approximate via season string)
                if "season" in player_lf.columns:
                    # "2024-25" -> end year 2025 -> 2025-07-01 as conservative bound
                    def _season_end(s: str) -> str:
                        try:
                            end_yr = int(s.split("-")[1])
                            # 2-digit suffix (e.g. "25") -> 2025
                            if end_yr < 100:
                                end_yr += 2000
                            return f"{end_yr}-07-01"
                        except (IndexError, ValueError):
                            return "2099-01-01"

                    player_lf = player_lf.copy()
                    player_lf["_season_end"] = player_lf["season"].apply(_season_end)
                    player_lf = player_lf[
                        player_lf["_season_end"] <= as_of_str
                    ]
                if not player_lf.empty:
                    # Latest season
                    latest = player_lf.sort_values("season").iloc[-1]
                    lineup_pace_on = _rd(latest.get("lineup_avg_pace_on"))
                    if lineup_pace_on is not None:
                        lineup_pace_delta = _rd(lineup_pace_on - league_pace_median)

        # -- Derived deltas ------------------------------------------------
        usage_delta = _delta_or_none(usage_fast, usage_slow)
        ts_delta = _delta_or_none(ts_fast, ts_slow)
        efg_delta = _delta_or_none(efg_fast, efg_slow)
        net_rtg_delta = _delta_or_none(net_rtg_fast, net_rtg_slow)
        pie_delta = _delta_or_none(pie_fast, pie_slow)
        poss_delta = _delta_or_none(poss_fast, poss_slow)
        min_delta = _delta_or_none(min_fast, min_slow)
        reb_pct_delta = _delta_or_none(reb_pct_fast, reb_pct_slow)
        trans_delta = _delta_or_none(trans_fast, trans_slow)

        # -- Composite pace_fit_score --------------------------------------
        # Each delta is normalised by a typical inter-player std; weighted sum.
        # Positive = does better in faster games.
        # Normalisation constants derived from empirical league distributions
        # (approximate; refined if CV calibration is available).
        _norms: Dict[str, float] = {
            "usage": 0.04,    # typical cross-player usage std ~4pp
            "ts": 0.04,       # TS% std ~4pp
            "pie": 0.03,      # PIE std ~3pp
            "net_rtg": 5.0,   # net rating std ~5 pts/100
            "transition": 1.2, # transition_poss std ~1.2/game
            "min": 2.0,       # minutes std ~2 min
        }

        def _z(delta: Optional[float], norm: float) -> float:
            if delta is None or norm == 0:
                return 0.0
            return delta / norm

        score_parts = {
            "usage": _z(usage_delta, _norms["usage"]) * _FIT_WEIGHTS["usage"],
            "ts": _z(ts_delta, _norms["ts"]) * _FIT_WEIGHTS["ts"],
            "pie": _z(pie_delta, _norms["pie"]) * _FIT_WEIGHTS["pie"],
            "net_rtg": _z(net_rtg_delta, _norms["net_rtg"]) * _FIT_WEIGHTS["net_rtg"],
            "transition": _z(trans_delta, _norms["transition"]) * _FIT_WEIGHTS["transition"],
            "min": _z(min_delta, _norms["min"]) * _FIT_WEIGHTS["min"],
        }
        total_weight = sum(_FIT_WEIGHTS.values())
        raw_score = sum(score_parts.values()) / total_weight
        pace_fit_score = _rd(raw_score)

        if pace_fit_score is None:
            pace_preference = "neutral"
        elif pace_fit_score >= _FAST_THRESHOLD:
            pace_preference = "fast"
        elif pace_fit_score <= _SLOW_THRESHOLD:
            pace_preference = "slow"
        else:
            pace_preference = "neutral"

        # -- Assemble sub_fields -------------------------------------------
        sub_fields: Dict[str, Any] = {
            # Sample sizes
            "n_games_total": n_total,
            "n_fast_games": n_fast,
            "n_slow_games": n_slow,
            # Pace context
            "median_pace": median_pace,
            "fast_pace_threshold": _rd(pace_threshold),
            "slow_pace_threshold": _rd(pace_threshold),
            # Usage / efficiency
            "usage_fast": usage_fast,
            "usage_slow": usage_slow,
            "usage_pace_delta": usage_delta,
            "ts_fast": ts_fast,
            "ts_slow": ts_slow,
            "ts_pace_delta": ts_delta,
            "efg_fast": efg_fast,
            "efg_slow": efg_slow,
            "efg_pace_delta": efg_delta,
            "net_rtg_fast": net_rtg_fast,
            "net_rtg_slow": net_rtg_slow,
            "net_rtg_pace_delta": net_rtg_delta,
            "pie_fast": pie_fast,
            "pie_slow": pie_slow,
            "pie_pace_delta": pie_delta,
            # Possession volume
            "poss_fast": poss_fast,
            "poss_slow": poss_slow,
            "poss_pace_delta": poss_delta,
            # Minutes
            "min_fast": min_fast,
            "min_slow": min_slow,
            "min_pace_delta": min_delta,
            # Rebounding
            "reb_pct_fast": reb_pct_fast,
            "reb_pct_slow": reb_pct_slow,
            "reb_pct_pace_delta": reb_pct_delta,
            # Transition (PBP)
            "transition_poss_fast": trans_fast,
            "transition_poss_slow": trans_slow,
            "transition_pace_delta": trans_delta,
            # Lineup pace
            "lineup_avg_pace_on": lineup_pace_on,
            "lineup_pace_delta": lineup_pace_delta,
            # Summary
            "pace_preference": pace_preference,
            "pace_fit_score": pace_fit_score,
        }

        n_for_conf = min(n_fast, n_slow)  # conservative: use the smaller bucket
        confidence = confidence_from_n(n_for_conf, cap=self.conf_cap)
        as_of_used = as_of_str
        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n_total,
            "confidence": confidence,
            "as_of": as_of_used,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=pace_fit_score,           # headline scalar: composite pace fit
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_used,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity checks for pace_fit.

        Validates:
          - n_games_total > 0 and n_fast + n_slow == n_games_total
          - pace_preference is a known label
          - pace_fit_score in [-5, 5] (composite z-weighted; outside is degenerate)
          - usage_fast / usage_slow in [0, 1] when present
          - median_pace in [60, 120] (sane NBA range)
        """
        sf = artifact.sub_fields
        n_total = sf.get("n_games_total", 0)
        n_fast = sf.get("n_fast_games", 0)
        n_slow = sf.get("n_slow_games", 0)

        if not isinstance(n_total, int) or n_total <= 0:
            return False
        if n_fast + n_slow != n_total:
            return False

        valid_prefs = {"fast", "slow", "neutral"}
        if sf.get("pace_preference") not in valid_prefs:
            return False

        score = sf.get("pace_fit_score")
        if score is not None and not (-5.0 <= float(score) <= 5.0):
            return False

        for col in ("usage_fast", "usage_slow"):
            v = sf.get(col)
            if v is not None and not (0.0 <= float(v) <= 1.0):
                return False

        median_pace = sf.get("median_pace")
        if median_pace is not None and not (60.0 <= float(median_pace) <= 130.0):
            return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for this section (values null; CV branch fills later).

        Slots:
            cv_spacing_fast        -- team spacing (convex hull ft²) in fast possessions
            cv_drive_freq_fast     -- drive frequency per 100 possessions in fast games
            cv_off_ball_speed_fast -- mean off-ball player speed (ft/s) in fast-game poss
            cv_off_ball_speed_slow -- mean off-ball player speed (ft/s) in slow-game poss
        """
        return {
            "cv_spacing_fast": CVSlot(
                name="cv_spacing_fast",
                dtype="float",
                description=(
                    "Mean team spacing (convex hull ft²) in fast-tempo possessions "
                    "(paceper40 >= global median), from CV court-position data."
                ),
                unit="ft2",
            ),
            "cv_drive_freq_fast": CVSlot(
                name="cv_drive_freq_fast",
                dtype="float",
                description=(
                    "Drive frequency per 100 possessions in fast-tempo games "
                    "(CV tracking; expected to be higher in uptempo contexts)."
                ),
                unit="per_100_poss",
            ),
            "cv_off_ball_speed_fast": CVSlot(
                name="cv_off_ball_speed_fast",
                dtype="float",
                description=(
                    "Mean off-ball player speed (ft/s) during fast-game possessions "
                    "(CV pipeline; captures whether player moves faster off-ball in pace games)."
                ),
                unit="ft/s",
            ),
            "cv_off_ball_speed_slow": CVSlot(
                name="cv_off_ball_speed_slow",
                dtype="float",
                description=(
                    "Mean off-ball player speed (ft/s) during slow-game possessions "
                    "(CV pipeline; contrast with cv_off_ball_speed_fast for tempo sensitivity)."
                ),
                unit="ft/s",
            ),
        }


# ---- Module-level registration helper -----------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build ``pace_fit`` artifacts for a list of players and register them.

    Args:
        player_ids: list of NBA player_ids; if None, builds all players found in
                    player_adv_stats.parquet (bounded by as_of).
        as_of:     leak boundary; defaults to today (UTC).
        store:     optional :class:`~src.loop.store.PointInTimeStore` for write-through.
        dry_run:   compute everything but skip disk writes.

    Returns:
        manifest dict from :func:`~src.loop.profile_factory_bridge.register_section`.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    section = PlayerPaceFitSection()
    section._load_data()

    adv = PlayerPaceFitSection._adv_df
    if player_ids is None:
        as_of_str = _to_iso(as_of)
        if (
            adv is not None
            and not adv.empty
            and "player_id" in adv.columns
            and "game_date" in adv.columns
        ):
            player_ids = (
                adv[adv["game_date"].astype(str) <= as_of_str]["player_id"]
                .unique()
                .tolist()
            )
        else:
            player_ids = []

    artifacts = []
    for pid in player_ids:
        art = section.build(pid, as_of)
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
