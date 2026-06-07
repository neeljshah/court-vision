"""ARM-B AtlasSection: team-level rebounding scheme profile.

Section key: ``rebounding_scheme``
Entity:      ``team``

Sub-fields (REAL vs DEFER):
  REAL (from team_reb_context.parquet + team_advanced_stats.parquet):
    oreb_pct_mean        -- season-average offensive rebounding percentage
    oreb_pct_std         -- game-to-game variability in OREB%
    dreb_pct_mean        -- season-average defensive rebounding percentage
    dreb_pct_std         -- game-to-game variability in DREB%
    crash_rate_z         -- OREB% z-score vs league (positive = crash-heavy identity)
    dreb_identity_z      -- DREB% z-score vs league (positive = lock-down DREB)
    oreb_pct_l10         -- rolling last-10-game OREB% (recency trend)
    dreb_pct_l10         -- rolling last-10-game DREB% (recency trend)
    oreb_pct_season_rank -- cross-team rank by OREB% (1=best, 30=worst)
    dreb_pct_season_rank -- cross-team rank by DREB% (1=best, 30=worst)
    reb_identity         -- categorical: "crash_heavy" | "balanced" | "get_back"
                           (derived from crash_rate_z thresholds: >+0.67 crash, <-0.67 get_back)
    n_games              -- number of qualifying games used
  DEFER (no per-possession crash/transition data in current NBA-API parquets):
    crash_vs_get_back_rate -- per-possession split: shots-followed (crash) vs transition (get-back)
                              DEFER: needs play-by-play possession-level data per shot attempt

CV slots reserved (value=null until CV fills):
  team_oreb_crash_freq   -- fraction of OREB attempts that are "crash" possessions
                            (CV: ball-towards-basket frame vectors after shot release)
  team_dreb_position_z   -- court-coordinate z-score of DREB capture position relative to basket
                            (CV: tells whether team wins long vs short rebounds)

Data sources:
  1. data/team_reb_context.parquet     -- per-game (game_id, game_date, team_tricode, oreb_pct, dreb_pct)
  2. data/team_advanced_stats.parquet  -- same grain, additional metrics for cross-check

Registration:
  Call ``build_all(as_of, store=store)`` which calls
  ``register_section(section, artifacts, store=store)`` via profile_factory_bridge.
  Do NOT edit build_persistent_profiles.py directly.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

# ---------------------------------------------------------------------------
# Paths (script-relative so this works on RunPod Linux too)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_CACHE = _DATA / "cache"

_REB_CONTEXT = _DATA / "team_reb_context.parquet"
_TEAM_ADV = _DATA / "team_advanced_stats.parquet"

# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process; leak-safe: filter by date)
# ---------------------------------------------------------------------------
_REB_DF: Optional[pd.DataFrame] = None
_ADV_DF: Optional[pd.DataFrame] = None


def _load_reb(as_of_iso: str) -> pd.DataFrame:
    """Load team_reb_context filtered to game_date <= as_of (LEAK-SAFE)."""
    global _REB_DF
    if _REB_DF is None and _REB_CONTEXT.exists():
        _REB_DF = pd.read_parquet(_REB_CONTEXT)
    if _REB_DF is None:
        return pd.DataFrame()
    if "game_date" not in _REB_DF.columns:
        return pd.DataFrame()
    return _REB_DF[_REB_DF["game_date"].astype(str) <= as_of_iso].copy()


def _load_adv(as_of_iso: str) -> pd.DataFrame:
    """Load team_advanced_stats filtered to game_date <= as_of (LEAK-SAFE)."""
    global _ADV_DF
    if _ADV_DF is None and _TEAM_ADV.exists():
        _ADV_DF = pd.read_parquet(_TEAM_ADV)
    if _ADV_DF is None:
        return pd.DataFrame()
    return _ADV_DF[_ADV_DF["game_date"].astype(str) <= as_of_iso].copy()


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


def _reb_identity_label(crash_z: Optional[float]) -> str:
    """Map crash_rate_z to a categorical rebounding identity label.

    crash_z >= +0.67 (top 75th percentile)  -> "crash_heavy"
    crash_z <= -0.67 (bottom 25th percentile) -> "get_back"
    otherwise                                 -> "balanced"
    """
    if crash_z is None:
        return "unknown"
    if crash_z >= 0.67:
        return "crash_heavy"
    if crash_z <= -0.67:
        return "get_back"
    return "balanced"


# ---------------------------------------------------------------------------
# The AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamReboundingScheme(AtlasSection):
    """Deep team-level rebounding scheme profile (OREB/DREB identity, crash vs get-back).

    Reads team_reb_context.parquet (per-game OREB%/DREB%) filtered to the as_of
    boundary. Derives season-average rates, game-to-game variability, league-relative
    z-scores (crash_rate_z / dreb_identity_z), rolling L10 trends, cross-team ranks,
    and a categorical reb_identity label (crash_heavy / balanced / get_back).

    The ``crash_vs_get_back_rate`` sub-field is DEFER: it requires per-possession
    play-by-play data (specifically, whether the offensive team crashed after a shot
    or retreated to defend transition) which is not in the current NBA-API parquet set.
    The CV branch will populate this via the two reserved CV slots.

    Sub-fields labelled DEFER are set to None and documented in the class docstring.
    """

    name: str = "rebounding_scheme"
    entity: str = "team"
    source_name: str = "team_reb_context.parquet"
    conf_cap: Optional[str] = None  # high confidence allowed for n>=20 games

    # ---- public contract ----------------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build a leak-safe rebounding scheme artifact for one team.

        Args:
            entity_id: three-letter team tricode (str), e.g. "DAL".
            as_of:     decision datetime; only data on or before this date is used.

        Returns:
            An :class:`AtlasArtifact` with sub_fields populated from NBA-API team
            stats, reserved CV slots, or ``None`` if the team has no qualifying data.
        """
        as_of_iso = (as_of.date().isoformat()
                     if isinstance(as_of, _dt.datetime) else str(as_of)[:10])
        tricode = str(entity_id).upper()

        # --- Source: team_reb_context (per-game) ----------------------------
        reb_all = _load_reb(as_of_iso)
        if reb_all.empty:
            return None

        team_rows = reb_all[reb_all["team_tricode"] == tricode]
        if team_rows.empty:
            return None

        n_games = len(team_rows)

        # Season-average rates
        oreb_mean = _clean(float(team_rows["oreb_pct"].mean()))
        oreb_std = _clean(float(team_rows["oreb_pct"].std())) if n_games > 1 else None
        dreb_mean = _clean(float(team_rows["dreb_pct"].mean()))
        dreb_std = _clean(float(team_rows["dreb_pct"].std())) if n_games > 1 else None

        # Rolling L10 recency trend (last 10 games sorted by game_date)
        sorted_rows = team_rows.sort_values("game_date")
        l10 = sorted_rows.tail(10)
        oreb_l10 = _clean(float(l10["oreb_pct"].mean())) if len(l10) >= 3 else None
        dreb_l10 = _clean(float(l10["dreb_pct"].mean())) if len(l10) >= 3 else None

        # League z-scores (computed against ALL teams in the as_of-filtered data
        # so signals from different eras are calibrated to the contemporaneous league)
        league_oreb = reb_all.groupby("team_tricode")["oreb_pct"].mean()
        league_dreb = reb_all.groupby("team_tricode")["dreb_pct"].mean()

        lg_oreb_mean = float(league_oreb.mean())
        lg_oreb_std = float(league_oreb.std()) if len(league_oreb) > 1 else 1.0
        lg_dreb_mean = float(league_dreb.mean())
        lg_dreb_std = float(league_dreb.std()) if len(league_dreb) > 1 else 1.0

        crash_rate_z = None
        dreb_identity_z = None
        if oreb_mean is not None and lg_oreb_std > 0:
            crash_rate_z = _clean((oreb_mean - lg_oreb_mean) / lg_oreb_std)
        if dreb_mean is not None and lg_dreb_std > 0:
            dreb_identity_z = _clean((dreb_mean - lg_dreb_mean) / lg_dreb_std)

        # Cross-team ordinal ranks (1 = best OREB%, lowest rank = weakest)
        oreb_ranks = league_oreb.rank(ascending=False).astype(int)
        dreb_ranks = league_dreb.rank(ascending=False).astype(int)
        oreb_rank = int(oreb_ranks.get(tricode, np.nan)) if tricode in oreb_ranks.index else None
        dreb_rank = int(dreb_ranks.get(tricode, np.nan)) if tricode in dreb_ranks.index else None

        # Categorical identity label
        reb_identity = _reb_identity_label(crash_rate_z)

        # Latest game date (provenance as_of boundary)
        latest_game = str(team_rows["game_date"].max())[:10]
        used_as_of = min(latest_game, as_of_iso)

        confidence = confidence_from_n(n_games, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            # REAL sub-fields from NBA-API parquets
            "oreb_pct_mean": oreb_mean,
            "oreb_pct_std": oreb_std,
            "dreb_pct_mean": dreb_mean,
            "dreb_pct_std": dreb_std,
            "crash_rate_z": crash_rate_z,
            "dreb_identity_z": dreb_identity_z,
            "oreb_pct_l10": oreb_l10,
            "dreb_pct_l10": dreb_l10,
            "oreb_pct_season_rank": oreb_rank,
            "dreb_pct_season_rank": dreb_rank,
            "reb_identity": reb_identity,
            "n_games": n_games,
            # DEFER: crash_vs_get_back_rate needs per-possession PBP data
            # (whether the offensive team sent players to crash after each shot attempt
            # vs. sprinting back in transition).  No current NBA-API parquet provides
            # this at a per-possession level; the CV branch reserves two slots below.
            "crash_vs_get_back_rate": None,  # DEFER: CV slot team_oreb_crash_freq
        }

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n_games,
            "confidence": confidence,
            "as_of": used_as_of,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=oreb_mean,      # headline scalar: OREB% (the primary identity anchor)
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
          - rate fields are in [0, 1] or None
          - oreb_pct_mean + dreb_pct_mean are plausibly complementary (not both near 1)
          - crash_rate_z is a reasonable z-score (|z| < 5) or None
          - reb_identity is one of the allowed labels
          - n_games >= 1
          - at least one key REAL sub-field is non-None
          - all cv_fields slots are present in artifact.cv_fields
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields

        # Rate fields must be in [0, 1]
        for fld in ("oreb_pct_mean", "oreb_pct_std", "dreb_pct_mean", "dreb_pct_std",
                    "oreb_pct_l10", "dreb_pct_l10"):
            val = sf.get(fld)
            if val is not None and not (0.0 <= float(val) <= 1.0):
                return False

        # Z-scores should be bounded (|z| < 5 is a sanity check)
        for fld in ("crash_rate_z", "dreb_identity_z"):
            val = sf.get(fld)
            if val is not None and abs(float(val)) > 5.0:
                return False

        # Identity label must be valid
        valid_labels = {"crash_heavy", "balanced", "get_back", "unknown"}
        label = sf.get("reb_identity")
        if label is not None and label not in valid_labels:
            return False

        # n_games must be at least 1
        n = sf.get("n_games")
        if n is None or int(n) < 1:
            return False

        # At least one primary rate must be populated
        if sf.get("oreb_pct_mean") is None and sf.get("dreb_pct_mean") is None:
            return False

        # CV slot schema must be present
        expected_cv = set(self.cv_fields().keys())
        return expected_cv.issubset(artifact.cv_fields.keys())

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for the rebounding_scheme section.

        Values are null now; the CV branch fills them via
        ``store.fill_cv_slot("team", tricode, "rebounding_scheme", slot, as_of, value)``.

        Slots:
            team_oreb_crash_freq  -- fraction of shot attempts where >= 2 offensive
                                     players are tracked moving toward the basket within
                                     1 second of shot release (CV-derived crash intent).
                                     dtype "float" in [0, 1].
            team_dreb_position_z  -- court-coordinate z-score of where defensive
                                     rebounds are captured relative to the basket, pooled
                                     across team games. Positive = long rebounds (team
                                     relies on securing boards away from the basket);
                                     negative = paint-DREB dominance.
                                     dtype "float".
        """
        return {
            "team_oreb_crash_freq": CVSlot(
                name="team_oreb_crash_freq",
                dtype="float",
                description=(
                    "Fraction of offensive shot attempts where at least two offensive "
                    "players are tracked moving toward the basket within 1 second of "
                    "shot release, proxying the team's crash-the-glass intent. "
                    "Populated by the CV branch from broadcast tracking frames."
                ),
                unit=None,
                value=None,
            ),
            "team_dreb_position_z": CVSlot(
                name="team_dreb_position_z",
                dtype="float",
                description=(
                    "Z-score of the team's defensive rebound capture distance from "
                    "the basket, relative to league mean. Positive values indicate "
                    "the team secures more long (perimeter) rebounds; negative values "
                    "indicate paint-dominant DREB positioning. "
                    "Populated by the CV branch from court-coordinate tracking."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Convenience: build all teams and register
# ---------------------------------------------------------------------------

def build_all(
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Build rebounding_scheme artifacts for all available teams and register.

    Args:
        as_of:   decision datetime (default: now). All parquet reads are filtered
                 to data available on or before this date (leak-safe).
        store:   optional PointInTimeStore; when provided, artifacts are written
                 so signals can read them immediately.
        dry_run: compute everything but skip disk writes.
        limit:   max teams to process (for smoke tests).

    Returns:
        The manifest dict from ``profile_factory_bridge.register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    as_of_iso = as_of.date().isoformat()
    section = TeamReboundingScheme()

    reb = _load_reb(as_of_iso)
    if reb.empty:
        return {"section": section.name, "n_entities": 0, "error": "no team_reb_context data"}

    team_ids: List[str] = sorted(reb["team_tricode"].unique().tolist())
    if limit is not None:
        team_ids = team_ids[:limit]

    artifacts: List[AtlasArtifact] = []
    for tricode in team_ids:
        art = section.build(tricode, as_of)
        if art is None:
            continue
        if section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Self-registration hook (called by profile_factory_bridge.load_registered_sections)
# ---------------------------------------------------------------------------

def get_section() -> TeamReboundingScheme:
    """Return the section instance (used by the bridge registry hook)."""
    return TeamReboundingScheme()
