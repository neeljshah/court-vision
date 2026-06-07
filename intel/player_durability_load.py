"""ARM-B AtlasSection: player-level durability and load management profile.

Section key: ``durability_load``
Entity:      ``player``

Covers every detail of how a player's body holds up and how their team manages
their workload: injury history patterns, games-missed tendencies, load-management
behaviour (coach-decision DNPs on high-rest nights), and minutes caps on return
from injury.

Sub-field availability (REAL vs DEFER):

  REAL (populated from existing parquets):
    games_missed_injury_total  -- career games missed due to injury (dnp_rows.parquet)
    games_missed_injury_l3seas -- games missed in last 3 seasons (dnp_rows)
    injury_dnp_rate            -- fraction of team games missed for injury (dnp_rows)
    load_mgmt_dnp_count        -- coach-decision DNPs (non-injury rest games, dnp_rows)
    load_mgmt_dnp_rate         -- fraction of team games that were load-mgmt DNPs
    rolling_dnp_rate_l20       -- rolling last-20-game DNP rate (dnp_features_player.parquet)
    current_status             -- latest known injury status from injury_features.parquet
    current_availability       -- latest availability_factor (0=OUT, 0.5=QUESTIONABLE, 1=ACTIVE)
    age_years                  -- age at the as_of date from player_profile_features.parquet
    seasons_in_league          -- career length proxy (years_in_league_as_of from bio parquet)
    minutes_per_game_mean      -- mean minutes per game played from player_adv_stats.parquet
    minutes_per_game_std       -- standard deviation of minutes (game-to-game load variability)
    high_minutes_game_rate     -- fraction of games with >= 34 minutes (heavy-load proxy)
    minutes_cap_return_mean    -- mean minutes in first 3 games after any injury DNP spell
                                  (approximates team's return-from-injury minutes cap)
    n_injury_return_spells     -- count of distinct injury-DNP spells (proxy: injury recurrence)

  DEFER (data not available in current parquet set):
    injury_body_part_breakdown -- no structured body-part classification in dnp_comments
    soft_tissue_vs_structural  -- would require NLP parsing of dnp_comment free text
    rpe_load_score             -- no real RPE/training-load data available (needs wearables)

CV slots reserved (value=null until CV fills):
    fatigue_velocity_trend  -- per-game velocity-mean decline over the last N frames
                               (CV tracking: fatigue indicator from movement speed decay)
    sprint_rate             -- fraction of possessions with sprint-speed bursts
                               (CV tracking: explosive-effort load proxy)

Data sources:
  1. data/dnp_rows.parquet                    -- per-game DNP log with reason codes
  2. data/cache/dnp_features_player.parquet   -- rolling l20 DNP rate per player-game
  3. data/cache/injury_features.parquet       -- latest injury status snapshot
  4. data/cache/player_profile_features.parquet -- bio (age, seasons_in_league)
  5. data/player_adv_stats.parquet            -- per-game minutes played

Registration:
  ``register_section(section, artifacts, store=store)`` via profile_factory_bridge.
  Do NOT edit scripts/build_persistent_profiles.py directly.
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
# Paths (always script-relative so this works on RunPod Linux too)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_CACHE = _DATA / "cache"

_DNP_ROWS = _DATA / "dnp_rows.parquet"
_DNP_FEAT_PLAYER = _CACHE / "dnp_features_player.parquet"
_INJURY_FEAT = _CACHE / "injury_features.parquet"
_BIO_FEAT = _CACHE / "player_profile_features.parquet"
_ADV_STATS = _DATA / "player_adv_stats.parquet"

# Minutes threshold that counts as a "high-load" game
_HIGH_MINUTES_THRESHOLD = 34.0

# Number of games after injury return to estimate minutes cap
_RETURN_WINDOW = 3


# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process; leak-safe: filter by date)
# ---------------------------------------------------------------------------
_DNP_DF: Optional[pd.DataFrame] = None
_DNP_FEAT_DF: Optional[pd.DataFrame] = None
_INJURY_DF: Optional[pd.DataFrame] = None
_BIO_DF: Optional[pd.DataFrame] = None
_ADV_DF: Optional[pd.DataFrame] = None


def _load_dnp(as_of_iso: str) -> pd.DataFrame:
    """Load dnp_rows filtered to game_date <= as_of (leak-safe)."""
    global _DNP_DF
    if _DNP_DF is None and _DNP_ROWS.exists():
        _DNP_DF = pd.read_parquet(_DNP_ROWS)
        _DNP_DF["game_date"] = _DNP_DF["game_date"].astype(str).str[:10]
    if _DNP_DF is None:
        return pd.DataFrame()
    return _DNP_DF[_DNP_DF["game_date"] <= as_of_iso].copy()


def _load_dnp_feat(as_of_iso: str) -> pd.DataFrame:
    """Load dnp_features_player filtered to game_date <= as_of."""
    global _DNP_FEAT_DF
    if _DNP_FEAT_DF is None and _DNP_FEAT_PLAYER.exists():
        _DNP_FEAT_DF = pd.read_parquet(_DNP_FEAT_PLAYER)
        _DNP_FEAT_DF["game_date"] = _DNP_FEAT_DF["game_date"].astype(str).str[:10]
    if _DNP_FEAT_DF is None:
        return pd.DataFrame()
    return _DNP_FEAT_DF[_DNP_FEAT_DF["game_date"] <= as_of_iso].copy()


def _load_injury(as_of_iso: str) -> pd.DataFrame:
    """Load injury_features; status snapshots are point-in-time by listed_date."""
    global _INJURY_DF
    if _INJURY_DF is None and _INJURY_FEAT.exists():
        _INJURY_DF = pd.read_parquet(_INJURY_FEAT)
        if "listed_date" in _INJURY_DF.columns:
            _INJURY_DF["listed_date_str"] = (
                _INJURY_DF["listed_date"].astype(str).str[:10]
            )
    if _INJURY_DF is None:
        return pd.DataFrame()
    if "listed_date_str" in _INJURY_DF.columns:
        return _INJURY_DF[_INJURY_DF["listed_date_str"] <= as_of_iso].copy()
    return _INJURY_DF.copy()


def _load_bio() -> pd.DataFrame:
    """Load player_profile_features (profile_as_of is the build date, not per-game)."""
    global _BIO_DF
    if _BIO_DF is None and _BIO_FEAT.exists():
        _BIO_DF = pd.read_parquet(_BIO_FEAT)
    return _BIO_DF if _BIO_DF is not None else pd.DataFrame()


def _load_adv(as_of_iso: str) -> pd.DataFrame:
    """Load player_adv_stats filtered to game_date <= as_of."""
    global _ADV_DF
    if _ADV_DF is None and _ADV_STATS.exists():
        _ADV_DF = pd.read_parquet(_ADV_STATS)
        _ADV_DF["game_date"] = _ADV_DF["game_date"].astype(str).str[:10]
    if _ADV_DF is None:
        return pd.DataFrame()
    return _ADV_DF[_ADV_DF["game_date"] <= as_of_iso].copy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(v: Any) -> Any:
    """NaN/inf -> None; numpy scalar -> python; float rounded to 4dp."""
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


def _season_start(season: str) -> str:
    """Return YYYY-MM-DD for approximately October 1 of the first year of the season."""
    try:
        year = int(season.split("-")[0])
        return f"{year}-10-01"
    except (IndexError, ValueError):
        return "2020-10-01"


def _count_injury_spells(
    sorted_dates: List[str], gap_days: int = 7
) -> int:
    """Count distinct injury spells from a sorted list of date strings.

    A new spell starts when the gap between consecutive game_dates exceeds
    ``gap_days`` days (proxy: player was healthy in between).
    """
    if not sorted_dates:
        return 0
    spells = 1
    for i in range(1, len(sorted_dates)):
        try:
            d0 = _dt.date.fromisoformat(sorted_dates[i - 1])
            d1 = _dt.date.fromisoformat(sorted_dates[i])
            if (d1 - d0).days > gap_days:
                spells += 1
        except (ValueError, TypeError):
            continue
    return spells


# ---------------------------------------------------------------------------
# The AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerDurabilityLoad(AtlasSection):
    """Deep per-player durability and load-management profile.

    Reads dnp_rows.parquet (injury vs coach-decision DNPs), dnp_features_player
    (rolling DNP rate), injury_features (current status snapshot), player_profile_
    features (age/seniority), and player_adv_stats (per-game minutes) — all
    filtered to the as_of date boundary for leak-safety.

    Sub-fields labelled DEFER (injury_body_part_breakdown,
    soft_tissue_vs_structural, rpe_load_score) require either NLP on dnp_comment
    free text or wearable/training-load data not present in the current parquet set.

    CV slots reserved (value=None):
        fatigue_velocity_trend -- per-game velocity decline detected by CV tracking
        sprint_rate            -- fraction of possessions with sprint bursts (CV)
    """

    name: str = "durability_load"
    entity: str = "player"
    source_name: str = (
        "dnp_rows.parquet + dnp_features_player.parquet + "
        "injury_features.parquet + player_profile_features.parquet + "
        "player_adv_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ---- public contract ------------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build a leak-safe durability_load artifact for one player.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data on or before this date is used.

        Returns:
            An :class:`AtlasArtifact` with all sub_fields populated where data
            exists and reserved CV slots at null, or ``None`` if no qualifying
            data exists for this player.
        """
        as_of_iso = (
            as_of.date().isoformat()
            if isinstance(as_of, _dt.datetime)
            else str(as_of)[:10]
        )
        pid = int(entity_id)

        # ---- Source 1: dnp_rows (per-game DNP log) -----------------------
        dnp_all = _load_dnp(as_of_iso)
        p_dnp = dnp_all[dnp_all["player_id"] == pid].copy() if not dnp_all.empty else pd.DataFrame()

        # ---- Source 2: dnp_features_player (rolling DNP rate) -----------
        dnp_feat_all = _load_dnp_feat(as_of_iso)
        p_dnp_feat = (
            dnp_feat_all[dnp_feat_all["player_id"] == pid].copy()
            if not dnp_feat_all.empty
            else pd.DataFrame()
        )

        # ---- Source 3: injury_features (current status snapshot) --------
        inj_all = _load_injury(as_of_iso)
        p_inj = (
            inj_all[inj_all["player_id"] == pid].copy()
            if (not inj_all.empty and "player_id" in inj_all.columns)
            else pd.DataFrame()
        )

        # ---- Source 4: bio (age / seniority) ----------------------------
        bio_all = _load_bio()
        p_bio = (
            bio_all[bio_all["player_id"] == pid].copy()
            if (not bio_all.empty and "player_id" in bio_all.columns)
            else pd.DataFrame()
        )

        # ---- Source 5: player_adv_stats (per-game minutes) --------------
        adv_all = _load_adv(as_of_iso)
        p_adv = (
            adv_all[adv_all["player_id"] == pid].copy()
            if not adv_all.empty
            else pd.DataFrame()
        )

        # Require at least one source to contain this player
        if p_dnp.empty and p_adv.empty and p_bio.empty:
            return None

        # ---- Compute sub-fields from DNP data ---------------------------
        games_missed_injury_total: Optional[int] = None
        games_missed_injury_l3seas: Optional[int] = None
        injury_dnp_rate: Optional[float] = None
        load_mgmt_dnp_count: Optional[int] = None
        load_mgmt_dnp_rate: Optional[float] = None
        n_injury_return_spells: Optional[int] = None
        minutes_cap_return_mean: Optional[float] = None
        latest_dnp_as_of: Optional[str] = None

        if not p_dnp.empty:
            inj_mask = p_dnp["dnp_reason"] == "injury"
            load_mask = p_dnp["dnp_reason"] == "coach_decision"

            inj_rows = p_dnp[inj_mask]
            load_rows = p_dnp[load_mask]

            games_missed_injury_total = int(len(inj_rows))
            load_mgmt_dnp_count = int(len(load_rows))

            # Total team games (all seasons for this player) as denominator
            total_games = len(p_dnp)

            if total_games > 0:
                injury_dnp_rate = _clean(len(inj_rows) / total_games)
                load_mgmt_dnp_rate = _clean(len(load_rows) / total_games)

            # Games missed in last 3 seasons
            if "season" in p_dnp.columns:
                seasons_sorted = sorted(p_dnp["season"].unique())
                last_3 = set(seasons_sorted[-3:])
                games_missed_injury_l3seas = int(
                    len(inj_rows[inj_rows["season"].isin(last_3)])
                )
            else:
                games_missed_injury_l3seas = games_missed_injury_total

            # Count distinct injury spells
            inj_dates = sorted(inj_rows["game_date"].astype(str).tolist())
            n_injury_return_spells = _count_injury_spells(inj_dates)

            latest_dnp_as_of = max(p_dnp["game_date"].astype(str).tolist(), default=None)

        # ---- Minutes cap on return from injury (from adv_stats) ---------
        if not p_adv.empty and not p_dnp.empty and "game_date" in p_adv.columns:
            inj_rows = p_dnp[p_dnp["dnp_reason"] == "injury"]
            if not inj_rows.empty:
                inj_dates_set = set(inj_rows["game_date"].astype(str).tolist())
                adv_sorted = p_adv.sort_values("game_date")
                adv_dates = adv_sorted["game_date"].astype(str).tolist()
                adv_minutes = adv_sorted["minutes"].tolist()

                return_mins: List[float] = []
                for i, gd in enumerate(adv_dates):
                    # Look back: was the previous game (any) in the injury set?
                    if i == 0:
                        continue
                    prev_date = adv_dates[i - 1]
                    if prev_date in inj_dates_set:
                        # Player returns: grab this game + up to 2 more
                        for j in range(i, min(i + _RETURN_WINDOW, len(adv_dates))):
                            m = adv_minutes[j]
                            if m is not None and not (
                                isinstance(m, float) and np.isnan(m)
                            ):
                                return_mins.append(float(m))

                if return_mins:
                    minutes_cap_return_mean = _clean(float(np.mean(return_mins)))

        # ---- Rolling DNP rate from dnp_features_player ------------------
        rolling_dnp_rate_l20: Optional[float] = None
        if not p_dnp_feat.empty and "player_dnp_rate_l20" in p_dnp_feat.columns:
            latest_feat = p_dnp_feat.sort_values("game_date").iloc[-1]
            rolling_dnp_rate_l20 = _clean(latest_feat["player_dnp_rate_l20"])

        # ---- Current injury status (most recent snapshot <= as_of) ------
        current_status: Optional[str] = None
        current_availability: Optional[float] = None

        if not p_inj.empty:
            if "listed_date_str" in p_inj.columns:
                latest_inj = p_inj.sort_values("listed_date_str").iloc[-1]
            else:
                latest_inj = p_inj.iloc[-1]
            current_status = str(latest_inj.get("status", "Unknown"))
            av = latest_inj.get("availability_factor")
            current_availability = _clean(av)

        # ---- Bio: age and seniority -------------------------------------
        age_years: Optional[float] = None
        seasons_in_league: Optional[int] = None

        if not p_bio.empty:
            bio_row = p_bio.iloc[0]
            if "age_precise_days_as_of" in p_bio.columns:
                days = bio_row.get("age_precise_days_as_of")
                if days is not None:
                    age_years = _clean(float(days) / 365.25)
            if "years_in_league_as_of" in p_bio.columns:
                sil = bio_row.get("years_in_league_as_of")
                if sil is not None:
                    seasons_in_league = int(sil)

        # ---- Per-game minutes from adv_stats ----------------------------
        minutes_per_game_mean: Optional[float] = None
        minutes_per_game_std: Optional[float] = None
        high_minutes_game_rate: Optional[float] = None
        latest_adv_as_of: Optional[str] = None

        if not p_adv.empty and "minutes" in p_adv.columns:
            mins = p_adv["minutes"].dropna()
            if len(mins) > 0:
                minutes_per_game_mean = _clean(float(mins.mean()))
                minutes_per_game_std = (
                    _clean(float(mins.std())) if len(mins) > 1 else None
                )
                high_minutes_game_rate = _clean(
                    float((mins >= _HIGH_MINUTES_THRESHOLD).sum()) / len(mins)
                )
            latest_adv_as_of = str(p_adv["game_date"].max())[:10]

        # ---- Provenance -------------------------------------------------
        # n = total DNP events or games with minutes data (best sample size)
        n_dnp = len(p_dnp) if not p_dnp.empty else 0
        n_adv = len(p_adv) if not p_adv.empty else 0
        n = max(n_dnp, n_adv)

        # as_of = latest date consumed from any source, hard-capped at as_of_iso
        as_of_dates = [
            d for d in [latest_dnp_as_of, latest_adv_as_of]
            if d
        ]
        raw_as_of = max(as_of_dates) if as_of_dates else as_of_iso
        used_as_of = min(raw_as_of, as_of_iso)

        confidence = confidence_from_n(n, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            # --- REAL sub-fields from NBA-API parquets ---
            "games_missed_injury_total": games_missed_injury_total,
            "games_missed_injury_l3seas": games_missed_injury_l3seas,
            "injury_dnp_rate": injury_dnp_rate,
            "load_mgmt_dnp_count": load_mgmt_dnp_count,
            "load_mgmt_dnp_rate": load_mgmt_dnp_rate,
            "rolling_dnp_rate_l20": rolling_dnp_rate_l20,
            "current_status": current_status,
            "current_availability": current_availability,
            "age_years": age_years,
            "seasons_in_league": seasons_in_league,
            "minutes_per_game_mean": minutes_per_game_mean,
            "minutes_per_game_std": minutes_per_game_std,
            "high_minutes_game_rate": high_minutes_game_rate,
            "minutes_cap_return_mean": minutes_cap_return_mean,
            "n_injury_return_spells": n_injury_return_spells,
            # --- DEFER sub-fields: not derivable from current parquets ---
            # injury_body_part_breakdown: DEFER -- needs NLP on dnp_comment text
            # soft_tissue_vs_structural:  DEFER -- needs NLP on dnp_comment text
            # rpe_load_score:             DEFER -- needs wearable/training-load data
            "injury_body_part_breakdown": None,   # DEFER: requires NLP/structured injury log
            "soft_tissue_vs_structural": None,    # DEFER: requires NLP classification
            "rpe_load_score": None,               # DEFER: requires wearable data
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
            value=injury_dnp_rate,  # headline: fraction of games missed to injury
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=used_as_of,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity checks on the built artifact.

        Returns True iff:
          - section/entity keys match this class
          - rate fields are in [0, 1] where non-None
          - all minute fields are non-negative where non-None
          - age is plausible (18-50 years) where non-None
          - at least one REAL numeric sub-field is non-None
          - all reserved CV slots are present in artifact.cv_fields
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields

        # Rate fields must be in [0, 1]
        rate_fields = [
            "injury_dnp_rate", "load_mgmt_dnp_rate",
            "rolling_dnp_rate_l20", "high_minutes_game_rate",
            "current_availability",
        ]
        for fld in rate_fields:
            val = sf.get(fld)
            if val is not None and not (0.0 <= float(val) <= 1.0):
                return False

        # Minutes must be non-negative (and sensible: < 60)
        for fld in ("minutes_per_game_mean", "minutes_per_game_std",
                    "minutes_cap_return_mean"):
            val = sf.get(fld)
            if val is not None:
                if float(val) < 0 or float(val) > 60:
                    return False

        # Age must be plausible
        age = sf.get("age_years")
        if age is not None and not (14.0 <= float(age) <= 60.0):
            return False

        # Count fields must be non-negative integers
        for fld in ("games_missed_injury_total", "games_missed_injury_l3seas",
                    "load_mgmt_dnp_count", "n_injury_return_spells"):
            val = sf.get(fld)
            if val is not None and float(val) < 0:
                return False

        # At least one real numeric field must be populated
        real_numeric = [
            "games_missed_injury_total", "injury_dnp_rate",
            "minutes_per_game_mean", "age_years",
        ]
        if all(sf.get(f) is None for f in real_numeric):
            return False

        # All reserved CV slots must be present
        return all(s in artifact.cv_fields for s in self.cv_fields())

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Return the two reserved CV slots for this section (values null now).

        The CV branch fills these via:
          ``store.fill_cv_slot("player", pid, "durability_load", slot, as_of, value)``

        Slots:
            fatigue_velocity_trend:
                Per-game decline in mean movement velocity over the last N frames,
                captured by CV tracking. A negative trend signals in-game fatigue
                accumulation and is a proxy for cumulative load stress.
                dtype="float", unit="ft/s per game"

            sprint_rate:
                Fraction of tracked possessions during which the player reaches
                sprint-threshold speed (>= ~15 ft/s). High sprint rates on
                recovering/load-managed players correlate with re-injury risk.
                dtype="float", unit=None (fraction 0-1)
        """
        return {
            "fatigue_velocity_trend": CVSlot(
                name="fatigue_velocity_trend",
                dtype="float",
                description=(
                    "Per-game decline in mean movement velocity (ft/s) over "
                    "the last N tracked frames. Negative = increasing fatigue "
                    "accumulation; signals cumulative workload stress from CV tracking."
                ),
                unit="ft/s per game",
                value=None,
            ),
            "sprint_rate": CVSlot(
                name="sprint_rate",
                dtype="float",
                description=(
                    "Fraction of tracked possessions where the player reaches "
                    "sprint-threshold speed (>= 15 ft/s). High values on recently "
                    "injured players indicate elevated re-injury risk from CV tracking."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Convenience: build all players and register via the bridge
# ---------------------------------------------------------------------------

def build_all(
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Build durability_load artifacts for all available players and register.

    Args:
        as_of:   decision datetime (default: now). All reads filtered to <= as_of.
        store:   optional PointInTimeStore; when provided, artifacts are written
                 so signals can read them immediately (leak-safe reinforcement).
        dry_run: compute everything but skip all disk writes.
        limit:   cap on number of players processed (for smoke tests).

    Returns:
        The manifest dict from ``profile_factory_bridge.register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    as_of_iso = as_of.date().isoformat()
    section = PlayerDurabilityLoad()

    # Collect player IDs from DNP rows (broadest coverage for this section)
    dnp = _load_dnp(as_of_iso)
    adv = _load_adv(as_of_iso)

    pids_dnp = set(dnp["player_id"].dropna().astype(int).tolist()) if not dnp.empty else set()
    pids_adv = set(adv["player_id"].dropna().astype(int).tolist()) if not adv.empty else set()
    player_ids = sorted(pids_dnp | pids_adv)

    if limit is not None:
        player_ids = player_ids[:limit]

    if not player_ids:
        return {"section": section.name, "n_entities": 0, "error": "no source data"}

    artifacts = []
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

def get_section() -> PlayerDurabilityLoad:
    """Return the section instance (used by the bridge registry hook)."""
    return PlayerDurabilityLoad()
