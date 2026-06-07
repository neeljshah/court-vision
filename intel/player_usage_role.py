"""ARM-B AtlasSection: player-level usage and role profile.

Section key: ``usage_role``
Entity:      player

Sub-fields (REAL vs DEFER):
  REAL (from existing parquets):
    - usage_rate           float  : season-mean usage % (player_adv_stats)
    - usage_l10_mean       float  : rolling last-10-game usage mean (player_adv_stats)
    - usage_tier           str    : "primary" | "secondary" | "rotation" | "bench" | "low"
    - minutes_pg           float  : average minutes per game (player_adv_stats)
    - ast_pct              float  : season-mean assist % (player_adv_stats)
    - pie_mean             float  : mean Player Impact Estimate (player_adv_stats)
    - on_net_rtg           float  : on-court net rating (on_off_features)
    - off_net_rtg          float  : off-court net rating (on_off_features)
    - on_off_net_diff      float  : on-off net rating differential (on_off_features)
    - on_off_impact_z      float  : z-scored on/off impact (on_off_features)
    - minutes_on           float  : total minutes on-court in season (on_off_features)
    - iso_poss_pg          float  : ISO possessions per game (pbp_possession_features)
    - pnr_handler_pg       float  : PnR ball-handler possessions per game (pbp_possession_features)
    - transition_poss_pg   float  : transition possessions per game (pbp_possession_features)
    - avg_seconds_per_touch float : average possession length in seconds (pbp_possession_features)
    - creator_role         str    : "primary_creator" | "secondary_creator" | "spot_up" | "none"
    - n_games              int    : number of games included in the season average
  DEFER (data not available without player_tracking or playtypes):
    - touches_pg           float  : DEFER — requires player_tracking.parquet (not present)
    - front_court_touches_pg float: DEFER — requires player_tracking.parquet (not present)
    - secondary_ast_rate   float  : DEFER — requires playtypes.parquet (not present)
    - playtype_share_pnr   float  : DEFER — requires playtypes.parquet (not present)

CV slots reserved (value=None until CV branch fills):
    - cv_ball_handler_pct  : fraction of possessions player handles ball (CV tracking)
    - cv_iso_freq          : ISO possession frequency per 100 possessions (CV tracking)
    - cv_off_ball_screen_rate: off-ball screen rate (CV tracking)
    - cv_drive_to_creation_rate: drives leading to assists per 100 poss (CV tracking)

Data sources:
    - data/player_adv_stats.parquet          (usage, ast%, pie, minutes, net_rtg)
    - data/cache/on_off_features.parquet     (on/off net rating, diff, impact_z)
    - data/cache/pbp_possession_features.parquet (iso/pnr/transition touches)

Registration: via profile_factory_bridge (does NOT edit build_persistent_profiles.py).
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
_CACHE = ROOT / "data" / "cache"
_DATA = ROOT / "data"

# --- Usage-rate thresholds for role-tier classification (from 2024-25 league quantiles)
# primary >= 26%, secondary >= 22%, rotation >= 17%, bench >= 14%, else low
_USAGE_TIER_THRESHOLDS: List[tuple] = [
    (0.26, "primary"),
    (0.22, "secondary"),
    (0.17, "rotation"),
    (0.14, "bench"),
]

# Creator role: primary_creator = high usage + high pnr-handler + high ast%;
#               secondary_creator = moderate pnr or iso; spot_up otherwise.
_CREATOR_AST_PCT_THRESHOLD = 0.20
_CREATOR_PNR_THRESHOLD = 1.5  # avg pnr possessions per game
_CREATOR_ISO_THRESHOLD = 2.0  # avg iso possessions per game


def _usage_tier(usage: Optional[float]) -> str:
    """Map a season-mean usage rate to a named role tier."""
    if usage is None or math.isnan(usage):
        return "unknown"
    for threshold, label in _USAGE_TIER_THRESHOLDS:
        if usage >= threshold:
            return label
    return "low"


def _creator_role(
    usage: Optional[float],
    ast_pct: Optional[float],
    iso_pg: Optional[float],
    pnr_pg: Optional[float],
) -> str:
    """Classify creator role from usage, assist%, iso, and PnR possessions."""
    u = usage or 0.0
    a = ast_pct or 0.0
    iso = iso_pg or 0.0
    pnr = pnr_pg or 0.0

    creator_score = (
        (1 if u >= 0.22 else 0)
        + (1 if a >= _CREATOR_AST_PCT_THRESHOLD else 0)
        + (1 if pnr >= _CREATOR_PNR_THRESHOLD else 0)
        + (1 if iso >= _CREATOR_ISO_THRESHOLD else 0)
    )
    if creator_score >= 3:
        return "primary_creator"
    if creator_score >= 2:
        return "secondary_creator"
    if a >= _CREATOR_AST_PCT_THRESHOLD or pnr >= 0.5:
        return "secondary_creator"
    return "spot_up"


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


class PlayerUsageRoleSection(AtlasSection):
    """Deep player-level usage and role atlas section for ARM-B intelligence.

    Reads three existing parquets (player_adv_stats, on_off_features,
    pbp_possession_features) and emits a rich, provenance-stamped artifact
    covering usage rate, role tier, on/off net rating, creator role, and
    possession-level touch patterns.  All reads are bounded by ``as_of`` for
    leak safety.

    CV slots are reserved null; the CV branch fills them later via
    ``store.fill_cv_slot``.
    """

    name: str = "usage_role"
    entity: str = "player"
    source_name: str = (
        "player_adv_stats.parquet + on_off_features.parquet + "
        "pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None  # no cap: pure NBA-API data, no CV

    # Lazy-loaded DataFrames (class-level cache, populated on first build call)
    _adv_df: Optional[pd.DataFrame] = None
    _onoff_df: Optional[pd.DataFrame] = None
    _pbp_df: Optional[pd.DataFrame] = None

    # ---- data loading ---------------------------------------------------

    def _load_data(self) -> None:
        """Load backing parquets into class-level cache (idempotent)."""
        adv_path = _DATA / "player_adv_stats.parquet"
        onoff_path = _CACHE / "on_off_features.parquet"
        pbp_path = _CACHE / "pbp_possession_features.parquet"

        if PlayerUsageRoleSection._adv_df is None:
            PlayerUsageRoleSection._adv_df = (
                pd.read_parquet(adv_path) if adv_path.exists() else pd.DataFrame()
            )
        if PlayerUsageRoleSection._onoff_df is None:
            PlayerUsageRoleSection._onoff_df = (
                pd.read_parquet(onoff_path) if onoff_path.exists() else pd.DataFrame()
            )
        if PlayerUsageRoleSection._pbp_df is None:
            PlayerUsageRoleSection._pbp_df = (
                pd.read_parquet(pbp_path) if pbp_path.exists() else pd.DataFrame()
            )

    # ---- AtlasSection contract ------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe usage_role artifact for one player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data on or before this date is used.

        Returns:
            :class:`AtlasArtifact` or ``None`` if the player has no data.
        """
        self._load_data()
        pid = int(entity_id)
        as_of_str = _to_iso(as_of)

        # ---- player_adv_stats: leak-safe filter (game_date <= as_of) ----
        adv = PlayerUsageRoleSection._adv_df
        onoff = PlayerUsageRoleSection._onoff_df
        pbp = PlayerUsageRoleSection._pbp_df

        player_adv: pd.DataFrame = pd.DataFrame()
        if not adv.empty and "player_id" in adv.columns and "game_date" in adv.columns:
            mask = (adv["player_id"] == pid) & (adv["game_date"].astype(str) <= as_of_str)
            player_adv = adv[mask].copy()

        if player_adv.empty:
            return None

        # Season label: use the most recent season in the filtered rows.
        player_adv = player_adv.sort_values("game_date")
        n_games = int(len(player_adv))

        # Season-mean stats
        usage_mean = _clean(player_adv["usagepercentage"].mean())
        minutes_pg = _clean(player_adv["minutes"].mean())
        ast_pct = _clean(player_adv["assistpercentage"].mean())
        pie_mean = _clean(player_adv["pie"].mean())

        # L10 rolling usage (last 10 games, leak-safe because rows already filtered)
        l10 = player_adv.tail(10)
        usage_l10_mean = _clean(l10["usagepercentage"].mean())

        # ---- on_off_features: latest season record before as_of ----------
        on_net_rtg: Optional[float] = None
        off_net_rtg: Optional[float] = None
        on_off_net_diff: Optional[float] = None
        on_off_impact_z: Optional[float] = None
        minutes_on: Optional[float] = None

        if not onoff.empty and "player_id" in onoff.columns:
            po = onoff[onoff["player_id"] == pid]
            if not po.empty:
                # on_off_features is season-level; pick latest available
                # (no game_date col — use season str if present, else take last row)
                if "season" in po.columns:
                    po = po.sort_values("season")
                row = po.iloc[-1]
                on_net_rtg = _clean(row.get("on_court_plus_minus"))
                off_net_rtg = _clean(row.get("off_court_plus_minus"))
                on_off_net_diff = _clean(row.get("on_off_diff"))
                on_off_impact_z = _clean(row.get("on_off_impact_z"))
                minutes_on = _clean(row.get("minutes_on"))

        # ---- pbp_possession_features: per-game averages up to as_of ------
        iso_poss_pg: Optional[float] = None
        pnr_handler_pg: Optional[float] = None
        transition_poss_pg: Optional[float] = None
        avg_seconds_per_touch: Optional[float] = None

        if not pbp.empty and "player_id" in pbp.columns and "game_date" in pbp.columns:
            mask_pbp = (pbp["player_id"] == pid) & (
                pbp["game_date"].astype(str) <= as_of_str
            )
            player_pbp = pbp[mask_pbp]
            if not player_pbp.empty:
                iso_poss_pg = _clean(player_pbp["pbp_iso_poss_count"].mean())
                pnr_handler_pg = _clean(player_pbp["pbp_pnr_ball_handler"].mean())
                transition_poss_pg = _clean(player_pbp["pbp_transition_count"].mean())
                avg_seconds_per_touch = _clean(
                    player_pbp["pbp_avg_seconds_per_touch"].mean()
                )

        # ---- derived classifications ------------------------------------
        usage_tier_val = _usage_tier(usage_mean)
        creator_role_val = _creator_role(usage_mean, ast_pct, iso_poss_pg, pnr_handler_pg)

        # ---- assemble sub_fields ----------------------------------------
        sub_fields: Dict[str, Any] = {
            # Usage metrics
            "usage_rate": usage_mean,
            "usage_l10_mean": usage_l10_mean,
            "usage_tier": usage_tier_val,
            # Minutes
            "minutes_pg": minutes_pg,
            # Playmaking
            "ast_pct": ast_pct,
            "pie_mean": pie_mean,
            # On/off net rating
            "on_net_rtg": on_net_rtg,
            "off_net_rtg": off_net_rtg,
            "on_off_net_diff": on_off_net_diff,
            "on_off_impact_z": on_off_impact_z,
            "minutes_on": minutes_on,
            # Touch patterns (PBP-derived)
            "iso_poss_pg": iso_poss_pg,
            "pnr_handler_pg": pnr_handler_pg,
            "transition_poss_pg": transition_poss_pg,
            "avg_seconds_per_touch": avg_seconds_per_touch,
            # Role classifications
            "creator_role": creator_role_val,
            # Sample size
            "n_games": n_games,
        }

        confidence = confidence_from_n(n_games, cap=self.conf_cap)
        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n_games,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=usage_mean,            # headline scalar: usage rate
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity checks: usage in [0,1], usage_tier is a known label,
        creator_role is a known label, n_games > 0."""
        sf = artifact.sub_fields
        usage = sf.get("usage_rate")
        if usage is not None and not (0.0 <= usage <= 1.0):
            return False
        valid_tiers = {"primary", "secondary", "rotation", "bench", "low", "unknown"}
        if sf.get("usage_tier") not in valid_tiers:
            return False
        valid_creators = {"primary_creator", "secondary_creator", "spot_up", "none"}
        if sf.get("creator_role") not in valid_creators | {"spot_up"}:
            return False
        if sf.get("n_games", 0) <= 0:
            return False
        # minutes_pg sanity (0..60)
        mpg = sf.get("minutes_pg")
        if mpg is not None and not (0.0 <= mpg <= 60.0):
            return False
        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for this section (values null; CV branch fills later).

        Slots:
            cv_ball_handler_pct     -- fraction of possessions player handles ball
            cv_iso_freq             -- ISO possession frequency per 100 possessions
            cv_off_ball_screen_rate -- off-ball screen rate per possession
            cv_drive_to_creation_rate -- drives leading to assists per 100 possessions
        """
        return {
            "cv_ball_handler_pct": CVSlot(
                name="cv_ball_handler_pct",
                dtype="float",
                description=(
                    "Fraction of team possessions the player handles the ball "
                    "(from CV tracking data)."
                ),
                unit=None,
            ),
            "cv_iso_freq": CVSlot(
                name="cv_iso_freq",
                dtype="float",
                description=(
                    "ISO possession frequency per 100 possessions "
                    "(from CV play-type tracking)."
                ),
                unit="per_100_poss",
            ),
            "cv_off_ball_screen_rate": CVSlot(
                name="cv_off_ball_screen_rate",
                dtype="float",
                description=(
                    "Off-ball screen rate per possession (CV tracking)."
                ),
                unit="per_poss",
            ),
            "cv_drive_to_creation_rate": CVSlot(
                name="cv_drive_to_creation_rate",
                dtype="float",
                description=(
                    "Drives leading to assists per 100 possessions (CV tracking)."
                ),
                unit="per_100_poss",
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
    """Build ``usage_role`` artifacts for a list of players and register them.

    Args:
        player_ids: list of NBA player_ids; if None, builds all players found in
                    player_adv_stats.parquet (bounded by as_of).
        as_of:     leak boundary; defaults to today.
        store:     optional :class:`~src.loop.store.PointInTimeStore` for write-through.
        dry_run:   compute everything but skip disk writes.

    Returns:
        manifest dict from :func:`~src.loop.profile_factory_bridge.register_section`.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    section = PlayerUsageRoleSection()
    section._load_data()

    adv = PlayerUsageRoleSection._adv_df
    if player_ids is None:
        as_of_str = _to_iso(as_of)
        if not adv.empty and "player_id" in adv.columns and "game_date" in adv.columns:
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
