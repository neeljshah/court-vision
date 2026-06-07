"""ARM-B AtlasSection: player-level rebounding profile.

Section key: ``rebounding_profile``
Entity:      ``player``

Sub-fields (REAL vs DEFER):
  REAL (from player_adv_stats.parquet + hustle_features*.parquet):
    oreb_rate_mean, oreb_rate_std, dreb_rate_mean, dreb_rate_std,
    total_reb_rate_mean, box_outs_per_game, n_hustle_seasons,
    oreb_pct_career, dreb_pct_career, oreb_dreb_ratio,
    reb_consistency_cv (from per_player_confidence.parquet when available).
  DEFER (no per-player per-game box-out/crash/contested-reb data available):
    crash_vs_get_back_tendency, contested_reb_pct, uncontested_reb_pct.

CV slots reserved (value=null until CV fills):
  boxout_position  -- court x/y distribution when establishing box-out position
  rebound_distance -- distance travelled to secure rebound (ft)
  vertical         -- proxy jump height / vertical involvement metric

Data sources:
  1. data/player_adv_stats.parquet          -- per-game oreb/dreb/total reb_pct
  2. data/cache/hustle_features.parquet     -- box_outs per game (multi-season)
  3. data/cache/hustle_features_2025-26.parquet -- current-season hustle
  4. data/intelligence/per_player_confidence.parquet -- reb_cv (optional)

Registration:
  ``register_section(section, artifacts, store=store)`` via profile_factory_bridge.
  Do NOT edit build_persistent_profiles.py directly.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

# ---------------------------------------------------------------------------
# Paths (always script-relative so this works on RunPod Linux too)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_CACHE = _DATA / "cache"
_INTEL = _DATA / "intelligence"

_ADV_STATS = _DATA / "player_adv_stats.parquet"
_HUSTLE_BASE = _CACHE / "hustle_features.parquet"
_HUSTLE_2526 = _CACHE / "hustle_features_2025-26.parquet"
_CONF_PARQ = _INTEL / "per_player_confidence.parquet"


# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process; leak-safe: filter by date)
# ---------------------------------------------------------------------------
_ADV_DF: Optional[pd.DataFrame] = None
_HUSTLE_DF: Optional[pd.DataFrame] = None
_CONF_DF: Optional[pd.DataFrame] = None


def _load_adv(as_of_iso: str) -> pd.DataFrame:
    """Load player_adv_stats filtered to game_date <= as_of."""
    global _ADV_DF
    if _ADV_DF is None and _ADV_STATS.exists():
        _ADV_DF = pd.read_parquet(_ADV_STATS)
    if _ADV_DF is None:
        return pd.DataFrame()
    return _ADV_DF[_ADV_DF["game_date"].astype(str) <= as_of_iso].copy()


def _load_hustle(as_of_iso: str) -> pd.DataFrame:
    """Concatenate hustle_features + 2025-26 and filter to season cutoff.

    Hustle parquets are season-level (no game_date), so we map season end-dates
    to approximate the leak boundary:  2024-25 ends ~2025-04-13; 2025-26 data
    is included if as_of >= 2025-10-01 (season open).
    """
    global _HUSTLE_DF
    if _HUSTLE_DF is None:
        parts = []
        if _HUSTLE_BASE.exists():
            parts.append(pd.read_parquet(_HUSTLE_BASE))
        if _HUSTLE_2526.exists():
            parts.append(pd.read_parquet(_HUSTLE_2526))
        if parts:
            _HUSTLE_DF = pd.concat(parts, ignore_index=True)
    if _HUSTLE_DF is None:
        return pd.DataFrame()

    # Approximate season end-date boundary (YYYY-MM-DD format)
    _SEASON_CUTOFFS = {
        "2018-19": "2019-06-13", "2019-20": "2020-10-11", "2020-21": "2021-07-20",
        "2021-22": "2022-06-16", "2022-23": "2023-06-12", "2023-24": "2024-06-17",
        "2024-25": "2025-06-30", "2025-26": "2026-06-30",
    }
    allowed = {s for s, end in _SEASON_CUTOFFS.items() if end <= as_of_iso or as_of_iso >= end[:7] + "-01"}
    # More conservative: only include season if its start is before as_of
    allowed = {s for s, end in _SEASON_CUTOFFS.items() if _season_start(s) <= as_of_iso}
    return _HUSTLE_DF[_HUSTLE_DF["season"].isin(allowed)].copy()


def _season_start(season: str) -> str:
    """Return YYYY-MM-DD for ~October 1 of the first calendar year of the season."""
    year = int(season.split("-")[0])
    return f"{year}-10-01"


def _load_conf_df() -> Optional[pd.DataFrame]:
    """Load per_player_confidence (no as_of column; use as supplementary)."""
    global _CONF_DF
    if _CONF_DF is None and _CONF_PARQ.exists():
        _CONF_DF = pd.read_parquet(_CONF_PARQ)
    return _CONF_DF


def _clean(v: Any) -> Any:
    """NaN/inf -> None, numpy scalar -> python, round floats to 4dp."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ---------------------------------------------------------------------------
# The AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerReboundingProfile(AtlasSection):
    """Deep per-player rebounding profile (OREB/DREB rates, box-outs, CV slots).

    Reads player_adv_stats.parquet (per-game oreb/dreb percentage) and
    hustle_features*.parquet (box_outs per game) filtered to as_of boundaries.
    CV slots for boxout_position, rebound_distance, and vertical are reserved
    with null values for the CV branch to fill later.

    Sub-fields labelled DEFER (crash_vs_get_back_tendency, contested_reb_pct,
    uncontested_reb_pct) require per-play tracking data that does not exist
    in the current NBA-API parquet set; they will be populated by the CV branch.
    """

    name: str = "rebounding_profile"
    entity: str = "player"
    source_name: str = "player_adv_stats.parquet + hustle_features.parquet"
    conf_cap: Optional[str] = None  # no cap; high confidence allowed from large n

    # ---- public contract ----------------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build a leak-safe rebounding profile artifact for one player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data on or before this date is used.

        Returns:
            An :class:`AtlasArtifact` with sub_fields populated from NBA-API stats
            and reserved CV slots, or ``None`` if the player has no qualifying data.
        """
        as_of_iso = as_of.date().isoformat() if isinstance(as_of, _dt.datetime) else str(as_of)[:10]
        pid = int(entity_id)

        # --- Source 1: per-game advanced stats (oreb/dreb rate) ----------
        adv = _load_adv(as_of_iso)
        player_adv = adv[adv["player_id"] == pid] if not adv.empty else pd.DataFrame()

        # --- Source 2: hustle (box_outs per game, season-level) ----------
        hustle = _load_hustle(as_of_iso)
        player_hustle = hustle[hustle["player_id"] == pid] if not hustle.empty else pd.DataFrame()

        # Skip entirely if no data in either source
        if player_adv.empty and player_hustle.empty:
            return None

        # --- Build sub_fields -------------------------------------------
        n_games = 0
        oreb_rate_mean = oreb_rate_std = None
        dreb_rate_mean = dreb_rate_std = None
        total_reb_rate_mean = None
        oreb_pct_career = dreb_pct_career = None
        oreb_dreb_ratio = None
        latest_adv_as_of = None

        if not player_adv.empty:
            n_games = len(player_adv)
            oreb_col = player_adv["offensivereboundpercentage"].dropna()
            dreb_col = player_adv["defensivereboundpercentage"].dropna()
            total_col = player_adv["reboundpercentage"].dropna()

            if len(oreb_col) > 0:
                oreb_rate_mean = _clean(float(oreb_col.mean()))
                oreb_rate_std = _clean(float(oreb_col.std())) if len(oreb_col) > 1 else None
                oreb_pct_career = oreb_rate_mean  # same — season-level average

            if len(dreb_col) > 0:
                dreb_rate_mean = _clean(float(dreb_col.mean()))
                dreb_rate_std = _clean(float(dreb_col.std())) if len(dreb_col) > 1 else None
                dreb_pct_career = dreb_rate_mean

            if len(total_col) > 0:
                total_reb_rate_mean = _clean(float(total_col.mean()))

            if oreb_rate_mean is not None and dreb_rate_mean is not None and dreb_rate_mean > 0:
                oreb_dreb_ratio = _clean(oreb_rate_mean / dreb_rate_mean)

            latest_adv_as_of = str(player_adv["game_date"].max())[:10]

        # --- Hustle: box_outs per game + seasons covered -----------------
        box_outs_per_game = None
        n_hustle_seasons = 0
        latest_hustle_as_of = None

        if not player_hustle.empty:
            # Use the latest season's value (most current estimate)
            latest_row = player_hustle.sort_values("season").iloc[-1]
            box_outs_per_game = _clean(float(latest_row["hustle_box_outs"]))
            n_hustle_seasons = int(player_hustle["season"].nunique())
            latest_hustle_as_of = _season_end_approx(str(latest_row["season"]))

        # --- Supplementary: reb consistency coefficient of variation ----
        reb_consistency_cv = None
        conf_df = _load_conf_df()
        if conf_df is not None and "player_id" in conf_df.columns:
            conf_row = conf_df[conf_df["player_id"] == pid]
            if not conf_row.empty and "reb_cv" in conf_df.columns:
                reb_consistency_cv = _clean(float(conf_row["reb_cv"].iloc[0]))

        # --- Provenance --------------------------------------------------
        # n = number of qualifying per-game records (most reliable sample size)
        n = max(n_games, n_hustle_seasons * 30)  # conservative floor from hustle
        n = n_games if n_games > 0 else n_hustle_seasons * 30

        # as_of = latest date we consumed, capped at the decision boundary.
        # Hustle parquets are season-level; _season_end_approx may return a future
        # date relative to as_of_iso. We MUST NOT claim knowledge beyond as_of_iso
        # (leak-safety: the artifact as_of is the newest source date we can vouch for).
        as_of_dates = [d for d in [latest_adv_as_of, latest_hustle_as_of] if d]
        raw_as_of = max(as_of_dates) if as_of_dates else as_of_iso
        used_as_of = min(raw_as_of, as_of_iso)  # hard-cap at decision boundary

        confidence = confidence_from_n(n, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            # REAL sub-fields from NBA-API parquets
            "oreb_rate_mean": oreb_rate_mean,
            "oreb_rate_std": oreb_rate_std,
            "dreb_rate_mean": dreb_rate_mean,
            "dreb_rate_std": dreb_rate_std,
            "total_reb_rate_mean": total_reb_rate_mean,
            "oreb_pct_career": oreb_pct_career,
            "dreb_pct_career": dreb_pct_career,
            "oreb_dreb_ratio": oreb_dreb_ratio,
            "box_outs_per_game": box_outs_per_game,
            "n_hustle_seasons": n_hustle_seasons,
            "reb_consistency_cv": reb_consistency_cv,
            # DEFER sub-fields: no per-play NBA-API source available; CV fills later
            # crash_vs_get_back_tendency: DEFER -- needs PBP + spatial tracking
            # contested_reb_pct:          DEFER -- needs per-rebound contest data
            # uncontested_reb_pct:        DEFER -- inverse of above
            "crash_vs_get_back_tendency": None,  # DEFER: CV slot boxout_position
            "contested_reb_pct": None,           # DEFER: no API source
            "uncontested_reb_pct": None,         # DEFER: no API source
        }

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": used_as_of,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=total_reb_rate_mean,   # headline scalar: total reb rate
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=used_as_of,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity checks on the built artifact.

        Returns True iff:
          - section/entity match this class
          - all rate fields are in [0, 1] or None
          - oreb_rate_mean + dreb_rate_mean <= 1.0 (cannot both be near 100%)
          - box_outs_per_game >= 0 if present
          - at least one REAL sub-field is non-None (not an empty shell)
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields

        # Rate fields must be in [0, 1]
        rate_fields = [
            "oreb_rate_mean", "dreb_rate_mean", "total_reb_rate_mean",
            "oreb_pct_career", "dreb_pct_career",
        ]
        for fld in rate_fields:
            val = sf.get(fld)
            if val is not None and not (0.0 <= float(val) <= 1.0):
                return False

        # Box-outs must be non-negative
        bo = sf.get("box_outs_per_game")
        if bo is not None and float(bo) < 0:
            return False

        # oreb+dreb cannot exceed 1.0 (both expressed as fraction of available)
        oreb = sf.get("oreb_rate_mean")
        dreb = sf.get("dreb_rate_mean")
        if oreb is not None and dreb is not None and float(oreb) + float(dreb) > 1.05:
            return False

        # At least one real numeric field must be populated
        real_fields = ["oreb_rate_mean", "dreb_rate_mean", "box_outs_per_game"]
        if all(sf.get(f) is None for f in real_fields):
            return False

        # CV slot schema must be present
        return all(s in artifact.cv_fields for s in self.cv_fields())

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for the rebounding_profile section.

        Values are null now; the CV branch fills them via
        ``store.fill_cv_slot("player", pid, "rebounding_profile", slot, as_of, value)``.

        Slots:
            boxout_position:   court (x,y) distribution when establishing box-out;
                               dtype "dist" (will carry a centroid/spread encoding).
            rebound_distance:  average distance (ft) the player travels to secure
                               the rebound; dtype "float", unit "ft".
            vertical:          proxy vertical involvement: jump frequency / height
                               index derived from pose estimation; dtype "float".
        """
        return {
            "boxout_position": CVSlot(
                name="boxout_position",
                dtype="dist",
                description=(
                    "Court coordinate distribution (x,y centroid + spread) where "
                    "the player establishes a box-out position before a rebound attempt."
                ),
                unit=None,
                value=None,
            ),
            "rebound_distance": CVSlot(
                name="rebound_distance",
                dtype="float",
                description=(
                    "Mean distance (ft) the player travels from their position at "
                    "shot release to the point of rebound capture."
                ),
                unit="ft",
                value=None,
            ),
            "vertical": CVSlot(
                name="vertical",
                dtype="float",
                description=(
                    "Proxy vertical involvement index: frequency and estimated height "
                    "of jump actions near rebound events, derived from pose estimation."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _season_end_approx(season: str) -> str:
    """Approximate season end date (June 30 of the second calendar year)."""
    try:
        second_year = int(season.split("-")[0]) + 1
        return f"{second_year}-06-30"
    except (IndexError, ValueError):
        return "2025-06-30"


# ---------------------------------------------------------------------------
# Convenience: build all players and register
# ---------------------------------------------------------------------------

def build_all(
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Build rebounding_profile artifacts for all available players and register.

    Args:
        as_of:   decision datetime (default: now). All parquet reads are filtered
                 to data available on or before this date (leak-safe).
        store:   optional PointInTimeStore; when provided, artifacts are written
                 so signals can read them immediately.
        dry_run: compute everything but skip disk writes.
        limit:   max players to process (for smoke tests).

    Returns:
        The manifest dict from ``profile_factory_bridge.register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    as_of_iso = as_of.date().isoformat()
    section = PlayerReboundingProfile()

    # Collect all player IDs from the advanced stats parquet (broadest coverage)
    adv = _load_adv(as_of_iso)
    if adv.empty:
        return {"section": section.name, "n_entities": 0, "error": "no adv stats data"}

    player_ids = sorted(adv["player_id"].unique().tolist())
    if limit is not None:
        player_ids = player_ids[:limit]

    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        art = section.build(pid, as_of)
        if art is None:
            continue
        if section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Self-registration hook (called by profile_factory_bridge.load_registered_sections)
# ---------------------------------------------------------------------------

def get_section() -> PlayerReboundingProfile:
    """Return the section instance (used by the bridge registry hook)."""
    return PlayerReboundingProfile()
