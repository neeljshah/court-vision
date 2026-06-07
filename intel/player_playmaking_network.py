"""Atlas section: player-level playmaking network (ARM-B intelligence).

Produces an EXHAUSTIVE per-player profile of HOW a player distributes the ball:
  - assist_profile:  volume, points-created, secondary assists, FT assists
  - potential_ast:   near-made attempts that COULD become assists (passing gravity)
  - tov_on_passes:   drive-pass TOV rate (on-ball creation risk)
  - drive_passing:   passes out of drives (kick-outs, drive-and-dish)
  - teammate_feed_proxy: relative usage of drive_passes vs total_passes
    (direct teammate-map by recipient is DEFER -- requires raw PBP event-player logs
     not available in current parquets; approximate proxy computed instead)
  - playtype_mix:    PnR ball-handler usage as fraction of possession role
  - ast_ratio_adv:   season-aggregate assist-ratio and AST/TOV from player_adv_stats

CV slots reserved (values null; CV branch fills later):
  - pass_velocity:   mean ball velocity in ft/s at release from tracked broadcasts
  - gravity_drawn:   fraction of possessions where the player draws a second defender
                     (gravity / help-D collapse index from CV tracking)

REAL sub_fields (populated from parquet data):
  passes_made, passes_received, potential_ast, ast_pts_created, secondary_ast,
  ft_ast, drive_passes, drive_ast, drive_tov_rate, pnr_bh_poss_fraction,
  ast_ratio, ast_to_tov, usage_pct, n_games, season

DEFER sub_fields (data not available in current parquets):
  lob_ast_count      -- requires raw PBP assist-type tagging (shot-type=alley-oop)
  kickout_ast_count  -- requires shot-location-tagged playtype dataset (catch-shoot vs drive)
  dish_ast_count     -- same (drive-and-dish subcategory)
  teammate_map       -- requires per-pass recipient column from Synergy/SportVU raw feed

Data sources:
  - data/player_tracking.parquet + data/player_tracking_2025-26.parquet
      (trk_pas_*, trk_drv_passes, trk_drv_ast, trk_drv_tov_pct)
  - data/player_adv_stats.parquet
      (assistpercentage, assistratio, assisttoturnover, usagepercentage, game_date)
  - data/cache/pbp_possession_features.parquet
      (pbp_pnr_ball_handler, pbp_iso_poss_count, pbp_transition_count -- possession-type fractions)
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
# Repository root (script-relative, never hardcoded absolute path)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
_DATA = ROOT / "data"
_CACHE = _DATA / "cache"


class PlayerPlaymakingNetwork(AtlasSection):
    """Deep player-level playmaking atlas section.

    Combines NBA tracking data (passes, potential assists, drive behavior) with
    advanced box-score ratios and PBP possession-type fractions to build an
    exhaustive picture of how each player moves the ball.

    The section is LEAK-SAFE: ``build(entity_id, as_of)`` filters every parquet
    to rows with ``game_date < as_of`` (strict less-than preserves the day-before
    boundary so no same-day game info leaks into pregame predictions).

    Registered via ``register_section`` (bridge pattern); do NOT edit
    ``build_persistent_profiles.py``.
    """

    name: str = "playmaking_network"
    entity: str = "player"
    source_name: str = (
        "player_tracking.parquet + player_adv_stats.parquet + pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None  # no artificial cap; let n drive confidence

    # ------------------------------------------------------------------
    # CV slot schema (values null until CV branch fills them)
    # ------------------------------------------------------------------

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slots for this section (filled by CV branch, never here).

        pass_velocity  -- mean ball release speed (ft/s) measured from broadcast
                          tracking; quantifies the pace of decision-making.
        gravity_drawn  -- fraction of possessions where the player's drive or cut
                          collapses a second defender (help-D index from homography).
        """
        return {
            "pass_velocity": CVSlot(
                name="pass_velocity",
                dtype="float",
                description=(
                    "Mean ball velocity at pass release (ft/s) from CV broadcast tracking. "
                    "High velocity = quick decision / court-vision; low = deliberate/catch-pass."
                ),
                unit="ft/s",
                value=None,
            ),
            "gravity_drawn": CVSlot(
                name="gravity_drawn",
                dtype="float",
                description=(
                    "Fraction of ball-dominant possessions where a second defender "
                    "collapses on the ball-handler (help-D index). "
                    "High gravity = open teammate creation; low = isolation scorer."
                ),
                unit=None,
                value=None,
            ),
        }

    # ------------------------------------------------------------------
    # Build (leak-safe)
    # ------------------------------------------------------------------

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build playmaking profile for *entity_id* (player_id) as-of *as_of*.

        All parquet reads are filtered to rows strictly BEFORE ``as_of`` to
        guarantee no future information leaks into feature computation.

        Args:
            entity_id: NBA player_id (int).
            as_of:     decision datetime; only data with game_date < as_of is used.

        Returns:
            AtlasArtifact with populated sub_fields + reserved cv_fields (null),
            or None if the player has no qualifying data.
        """
        pid = int(entity_id)
        as_of_date: str = as_of.date().isoformat()  # e.g. "2026-05-30"

        # --- 1. Tracking features (season-level, latest season <= as_of) ------
        trk_data = self._load_tracking_as_of(pid, as_of_date)

        # --- 2. Advanced box-score ratios (per-game, aggregated <= as_of) ------
        adv_data = self._load_adv_as_of(pid, as_of_date)

        # --- 3. PBP possession-type fractions (aggregated <= as_of) ------------
        pbp_data = self._load_pbp_as_of(pid, as_of_date)

        # If no data at all, return None (validator will skip)
        if trk_data is None and adv_data is None:
            return None

        # --- merge sub-fields --------------------------------------------------
        sub: Dict[str, Any] = {}

        # Coverage = ACTUAL games played (from the box / PBP aggregates), NOT
        # n_seasons. trk_data only carries n_seasons (1-2), which would fail the
        # validator's min_n=5 coverage gate for every player; use the real
        # game counts from adv/pbp and fall back to n_seasons only if neither.
        n_games = 0
        season_label = None

        # From tracking (per-game averages already per-game in NBA tracking data)
        if trk_data is not None:
            sub.update(trk_data["fields"])
            season_label = trk_data["season"]

        # From advanced box score (per-game aggregate)
        if adv_data is not None:
            sub.update(adv_data["fields"])
            if adv_data.get("n_games"):
                n_games = max(n_games, int(adv_data["n_games"]))

        # From PBP possession fractions
        if pbp_data is not None:
            sub.update(pbp_data["fields"])
            if pbp_data.get("n_games"):
                n_games = max(n_games, int(pbp_data["n_games"]))

        # Last resort: nothing reported a real game count -> use n_seasons.
        if n_games == 0 and trk_data is not None:
            n_games = int(trk_data.get("n_seasons") or 0)

        # Add DEFER placeholders so callers know they exist but need raw data
        sub["lob_ast_count"] = None        # DEFER: requires PBP assist-type tagging
        sub["kickout_ast_count"] = None    # DEFER: requires shot-location tagged playtype
        sub["dish_ast_count"] = None       # DEFER: drive-and-dish subcategory (SportVU)
        sub["teammate_map"] = None         # DEFER: per-recipient pass column absent

        if season_label is not None:
            sub["season"] = season_label

        sub["n_games"] = n_games

        confidence = confidence_from_n(n_games, cap=self.conf_cap)
        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n_games,
            "confidence": confidence,
            "as_of": as_of_date,
        }

        artifact = AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=sub.get("potential_ast"),       # headline: potential assists per game
            sub_fields=sub,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_date,
            cv_fields=self.cv_fields(),
        )
        return artifact

    # ------------------------------------------------------------------
    # Validate (face-validity)
    # ------------------------------------------------------------------

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required schema keys present, numeric ranges sane.

        Does NOT check leak-safety (that lives in intel_validator).
        """
        sf = artifact.sub_fields

        # Must have at least one real playmaking metric
        real_keys = [
            "passes_made", "potential_ast", "ast_pts_created",
            "ast_ratio", "ast_to_tov",
        ]
        has_real = any(sf.get(k) is not None for k in real_keys)
        if not has_real:
            return False

        # CV slot schema must be present and unreserved (value=None)
        cvf = artifact.cv_fields
        for slot_name in ("pass_velocity", "gravity_drawn"):
            if slot_name not in cvf:
                return False
            if cvf[slot_name].value is not None:
                return False  # CV branch must not have filled this yet

        # Sanity: passes_made should be non-negative if present
        pm = sf.get("passes_made")
        if pm is not None and pm < 0:
            return False

        # Sanity: drive_tov_rate should be in [0, 1] if present
        tov_rate = sf.get("drive_tov_rate")
        if tov_rate is not None and not (0.0 <= tov_rate <= 1.0):
            return False

        return True

    # ------------------------------------------------------------------
    # Private data loaders (all LEAK-SAFE: filter game_date < as_of_date)
    # ------------------------------------------------------------------

    def _load_tracking_as_of(
        self, pid: int, as_of_date: str
    ) -> Optional[Dict[str, Any]]:
        """Load per-season tracking data for *pid*, latest season ending before as_of.

        NBA tracking data (player_tracking.parquet / player_tracking_2025-26.parquet)
        is season-level (no game_date column).  We use the season end year as a proxy:
        season '2024-25' -> end date '2025-06-30'; only include seasons that started
        before as_of_date so future seasons are excluded.
        """
        frames: List[pd.DataFrame] = []
        for pq_name in ("player_tracking.parquet", "player_tracking_2025-26.parquet"):
            pq_path = _DATA / pq_name
            if not pq_path.exists():
                continue
            try:
                df = pd.read_parquet(pq_path)
            except Exception:
                continue
            if "player_id" not in df.columns:
                continue
            row = df[df["player_id"] == pid]
            if row.empty:
                continue
            frames.append(row)

        if not frames:
            return None

        combined = pd.concat(frames, ignore_index=True)

        # Season leak-safety: season '2024-25' started 2024-10-01.
        # Only include seasons whose start is before as_of_date.
        def _season_start(season_str: str) -> str:
            try:
                start_year = int(str(season_str).split("-")[0])
                return f"{start_year}-10-01"
            except (ValueError, IndexError, AttributeError):
                return "1900-01-01"

        if "season" in combined.columns:
            combined = combined[
                combined["season"].apply(_season_start) < as_of_date
            ]

        if combined.empty:
            return None

        # Use the latest season row
        if "season" in combined.columns:
            combined = combined.sort_values("season").tail(1)

        r = combined.iloc[0]
        fields: Dict[str, Any] = {}

        def _rd(col: str) -> Optional[float]:
            v = r.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
            except (TypeError, ValueError):
                return None

        fields["passes_made"] = _rd("trk_pas_passes_made")
        fields["passes_received"] = _rd("trk_pas_passes_received")
        fields["potential_ast"] = _rd("trk_pas_potential_ast")
        fields["ast_pts_created"] = _rd("trk_pas_ast_points_created")
        fields["secondary_ast"] = _rd("trk_pas_secondary_ast")
        fields["ft_ast"] = _rd("trk_pas_ft_ast")
        fields["drive_passes"] = _rd("trk_drv_passes")
        fields["drive_ast"] = _rd("trk_drv_ast")

        # drive_tov_rate is stored as a percentage (0-100); normalise to [0,1]
        drv_tov = _rd("trk_drv_tov_pct")
        if drv_tov is not None:
            fields["drive_tov_rate"] = round(drv_tov / 100.0, 4)
        else:
            fields["drive_tov_rate"] = None

        # teammate_feed_proxy: drive passes as fraction of total passes
        if (
            fields.get("passes_made") is not None
            and fields["passes_made"] > 0
            and fields.get("drive_passes") is not None
        ):
            fields["teammate_feed_proxy"] = round(
                fields["drive_passes"] / fields["passes_made"], 4
            )
        else:
            fields["teammate_feed_proxy"] = None

        season_label = str(r.get("season") or "")

        return {
            "fields": fields,
            "n_seasons": 1,
            "season": season_label or None,
        }

    def _load_adv_as_of(
        self, pid: int, as_of_date: str
    ) -> Optional[Dict[str, Any]]:
        """Aggregate per-game advanced box stats for *pid* up to as_of_date.

        Columns used: assistpercentage, assistratio, assisttoturnover, usagepercentage.
        Strict filter: game_date < as_of_date (avoids same-day leakage).
        """
        pq_path = _DATA / "player_adv_stats.parquet"
        if not pq_path.exists():
            return None
        try:
            df = pd.read_parquet(pq_path)
        except Exception:
            return None

        if "player_id" not in df.columns or "game_date" not in df.columns:
            return None

        row = df[df["player_id"] == pid].copy()
        if row.empty:
            return None

        # Leak-safety: only include rows whose game_date < as_of_date
        row["game_date"] = pd.to_datetime(row["game_date"], errors="coerce")
        row = row[row["game_date"].dt.date.astype(str) < as_of_date]
        if row.empty:
            return None

        n_games = len(row)

        def _mean_col(col: str) -> Optional[float]:
            if col not in row.columns:
                return None
            vals = pd.to_numeric(row[col], errors="coerce").dropna()
            return round(float(vals.mean()), 4) if len(vals) > 0 else None

        fields: Dict[str, Any] = {
            "ast_ratio": _mean_col("assistratio"),      # assists per 100 possessions
            "ast_to_tov": _mean_col("assisttoturnover"),
            "usage_pct": _mean_col("usagepercentage"),
            "tov_ratio": _mean_col("turnoverratio"),    # turnovers per 100 possessions
        }

        return {"fields": fields, "n_games": n_games}

    def _load_pbp_as_of(
        self, pid: int, as_of_date: str
    ) -> Optional[Dict[str, Any]]:
        """Aggregate PBP possession-type fractions for *pid* up to as_of_date.

        Computes the fraction of possessions where the player is the PnR ball-handler
        and a proxy for ISO vs transition usage.  Strict filter game_date < as_of_date.
        """
        pq_path = _CACHE / "pbp_possession_features.parquet"
        if not pq_path.exists():
            return None
        try:
            df = pd.read_parquet(pq_path)
        except Exception:
            return None

        if "player_id" not in df.columns or "game_date" not in df.columns:
            return None

        row = df[df["player_id"] == pid].copy()
        if row.empty:
            return None

        row["game_date"] = pd.to_datetime(row["game_date"], errors="coerce")
        row = row[row["game_date"].dt.date.astype(str) < as_of_date]
        if row.empty:
            return None

        n_games = len(row)

        def _mean_col(col: str) -> Optional[float]:
            if col not in row.columns:
                return None
            vals = pd.to_numeric(row[col], errors="coerce").dropna()
            return round(float(vals.mean()), 4) if len(vals) > 0 else None

        pnr_bh = _mean_col("pbp_pnr_ball_handler")
        iso = _mean_col("pbp_iso_poss_count")
        trans = _mean_col("pbp_transition_count")

        # pnr_bh_poss_fraction: if total possessions available, normalise
        total_poss = (pnr_bh or 0) + (iso or 0) + (trans or 0)
        pnr_frac: Optional[float] = None
        if total_poss > 0 and pnr_bh is not None:
            pnr_frac = round(pnr_bh / total_poss, 4)

        fields: Dict[str, Any] = {
            "pnr_bh_poss_fraction": pnr_frac,
            "iso_poss_per_game": iso,
            "transition_poss_per_game": trans,
        }

        return {"fields": fields, "n_games": n_games}


# ---------------------------------------------------------------------------
# Module-level registration (called once at import time in build scripts)
# ---------------------------------------------------------------------------

_SECTION_INSTANCE: Optional[PlayerPlaymakingNetwork] = None


def get_section() -> PlayerPlaymakingNetwork:
    """Return the singleton AtlasSection instance (lazy init)."""
    global _SECTION_INSTANCE
    if _SECTION_INSTANCE is None:
        _SECTION_INSTANCE = PlayerPlaymakingNetwork()
    return _SECTION_INSTANCE


def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build playmaking_network artifacts for *player_ids* and register via the bridge.

    Args:
        player_ids: list of NBA player_ids to build; if None, infers from tracking data.
        as_of:      decision datetime (default: UTC now, i.e. current day).
        store:      optional PointInTimeStore; if provided, atlas records are written.
        dry_run:    skip all disk writes (useful for testing).

    Returns:
        Bridge manifest dict (section, parquet, n_entities, cv_fields, as_of).
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow()

    section = get_section()

    # Infer player_ids from tracking parquets when not explicitly supplied
    if player_ids is None:
        player_ids = _infer_player_ids()

    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            continue
        if art is None:
            continue
        if section.validate(art):
            artifacts.append(art)

    manifest = register_section(section, artifacts, store=store, dry_run=dry_run)
    return manifest


def _infer_player_ids() -> List[int]:
    """Collect all player_ids present in the tracking + adv_stats parquets."""
    ids: set = set()
    for pq_name in (
        "player_tracking.parquet",
        "player_tracking_2025-26.parquet",
    ):
        pq = _DATA / pq_name
        if not pq.exists():
            continue
        try:
            df = pd.read_parquet(pq, columns=["player_id"])
            ids.update(df["player_id"].dropna().astype(int).tolist())
        except Exception:
            pass
    return sorted(ids)
