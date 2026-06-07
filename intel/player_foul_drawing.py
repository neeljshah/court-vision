"""ARM-B atlas section: ``foul_drawing`` -- per-player foul-drawing / FT-generation profile.

Implements :class:`AtlasSection` for the ``"foul_drawing"`` section of a player's
persistent profile.  The section captures HOW a player generates free throws -- the
drawing angle -- distinct from ``ft_profile`` (which covers FT% and shooting ability)
and from ``foul_tendency`` (which covers fouls COMMITTED).

**Sub-field coverage:**

REAL (populated from parquets):
  ft_generation.*   -- fta_per_36 (FT attempts per 36 min), fta_pg (per game),
                       pct_pts_from_ft (share of scoring via FT line).
                       Source: data/cache/atlas_player_ft_profile.parquet (reuses the
                       already-built ft_profile section's ``attempts`` sub-dict to avoid
                       re-deriving from raw boxscores; n from that artifact).
  drive_draw.*      -- drive-based foul-draw rate: drives_pg and drive FTA proxy
                       (drive_pts_pg minus drive_fg_pct*2 is a noisy proxy, so we use
                       trk_drv_count as drive volume + playtypes Postup/Isolation/
                       PRBallHandler freq as contact-seeking share).
                       Source: data/player_tracking_2025-26.parquet +
                       data/player_tracking.parquet + data/playtypes_2025-26.parquet +
                       data/playtypes.parquet.
  and_one.*         -- and_one rate (and-1 calls per game) from
                       data/cache/pbp_possession_features.parquet (pbp_and1_count,
                       leak-safe via game_date filter).
  shooting_foul_share.* -- pct_pts_from_ft (from player_breakdown_features, season-level)
                       as a proxy for shooting-foul share of total scoring; direct
                       shooting-foul-drawn count not available without PBP PLAYER2.
  contact_seek.*    -- contact-seeking play-type share: combined freq_pct of Postup +
                       Isolation + PRBallHandler from playtypes (drives + post + ISO =
                       highest-contact creation types). Values are already in [0,1]
                       (playtypes freq_pct is a proportion in the source).
  hustle.*          -- charges_drawn_pg from data/cache/hustle_features_2025-26.parquet +
                       data/cache/hustle_features.parquet (season-aggregate; leak-safe by
                       picking the latest season whose data existed <= as_of).

DEFER (data gap -- not available from current parquets):
  drive_fta_rate    -- FTA generated specifically on drives (requires PBP PLAYER2_ID
                       to attribute shooting-foul on drive; PLAYER2 lost in V3->V2
                       normalisation; DEFER: spec_features §2 GOTCHA).
  post_foul_rate    -- FTA generated specifically on post-ups (same V3->V2 PLAYER2
                       attribution gap as drive_fta_rate).
  trip_foul_rate    -- FTA generated on trips to the line (multi-foul sequences)
                       DEFER: no PBP sequence-level parquet available.

RESERVED CV SLOTS (value=None, CV branch fills later):
  contact_seek_rate -- rate at which the player initiates body contact in the lane,
                       estimated from CV defender-proximity at drive/post termination
                       and acceleration toward the basket in the final 0.5 s before
                       contact (homography + Kalman velocity).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy-load cache
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, numpy -> python float, round 4 dp."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _ri(v: Any) -> Optional[int]:
    """Clean integer scalar."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _clamp_rate(v: Optional[float]) -> Optional[float]:
    """Clamp a proportion/rate to [0, 1]; return None if out of range or None."""
    if v is None:
        return None
    if v < 0.0 or v > 1.0:
        return None
    return round(v, 4)


# ---------------------------------------------------------------------------
# Source aggregation helpers
# ---------------------------------------------------------------------------

def _ft_generation_from_atlas(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Pull FT-generation sub-fields from the existing atlas_player_ft_profile parquet.

    Reuses the already-built ``ft_profile`` section's ``attempts`` sub-dict to avoid
    re-deriving raw boxscores. LEAK-SAFE: ft_profile.as_of is checked against as_of;
    if it post-dates the build boundary the row is rejected.
    """
    path = CACHE / "atlas_player_ft_profile.parquet"
    df = _load("ft_atlas", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}

    row = rows.iloc[0]

    # Leak-safety: reject if the ft_profile was built after our as_of
    row_as_of = str(row.get("as_of") or "")[:10]
    if row_as_of and row_as_of > as_of.date().isoformat():
        return {}

    # Decode the JSON-stored 'attempts' sub-dict
    attempts_raw = row.get("attempts")
    if isinstance(attempts_raw, str):
        try:
            attempts = json.loads(attempts_raw)
        except Exception:
            attempts = {}
    elif isinstance(attempts_raw, dict):
        attempts = attempts_raw
    else:
        attempts = {}

    n_games = _ri(attempts.get("n_games")) or _ri(row.get("n"))
    fta_pg = _rd(attempts.get("fta_pg"))
    fta_per_36 = _rd(attempts.get("fta_per_36"))
    pct_pts_from_ft = _rd(attempts.get("pct_pts_from_ft"))

    # Validate pct_pts_from_ft is in [0, 1]
    pct_pts_from_ft = _clamp_rate(pct_pts_from_ft)

    return {
        "fta_pg": fta_pg,
        "fta_per_36": fta_per_36,
        "pct_pts_from_ft": pct_pts_from_ft,
        "n_games": n_games,
    }


def _drive_draw_from_tracking(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Drive-volume context from player_tracking (latest season <= as_of).

    Provides drives_pg (raw drive volume) and drive_pts_pg as context for
    contact-seeking tendency. The actual foul-draw-on-drive rate is DEFER
    (requires PBP PLAYER2_ID, which is lost in V3->V2 normalisation).

    LEAK-SAFE: season-keyed sources (tracking) are accepted as-is -- they are
    pre-published end-of-season summaries, the same policy used by shot_profile.
    """
    for path_key, path in [
        ("trk26", DATA / "player_tracking_2025-26.parquet"),
        ("trk_base", DATA / "player_tracking.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        drives_pg = _rd(row.get("trk_drv_count"))
        drive_pts_pg = _rd(row.get("trk_drv_pts"))
        drive_fg_pct = _rd(row.get("trk_drv_fg_pct"))
        # drive_fg_pct must be in [0,1]
        drive_fg_pct = _clamp_rate(drive_fg_pct)
        return {
            "drives_pg": drives_pg,
            "drive_pts_pg": drive_pts_pg,
            "drive_fg_pct": drive_fg_pct,
            "drive_fta_rate": None,  # DEFER -- PBP PLAYER2 lost
            "_drive_fta_note": (
                "DEFER: drive-specific FTA rate requires PBP PLAYER2_ID attribution "
                "(fouled-player). V3->V2 normalisation in pbp_scraper.py sets "
                "PLAYER2_ID='0'; unavailable until PBP feed is restored."
            ),
        }
    return {}


def _contact_seek_from_playtypes(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Contact-seeking play-type share from playtypes (latest season <= as_of).

    Combines Postup + Isolation + PRBallHandler freq_pct as the high-contact
    creation share. Values come from the source already in [0, 1] (they are
    fractions of total possessions used for that play type), so no rescaling
    needed; we clamp to guard against any upstream data issues.

    LEAK-SAFE: accepts the latest season from playtypes (same policy as shot_profile).
    """
    pt: Dict[str, float] = {}

    for path_key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        for _, r in rows.iterrows():
            play_type = str(r.get("play_type", ""))
            freq = _rd(r.get("freq_pct"))
            # freq_pct is already a proportion in [0,1] from the source
            freq = _clamp_rate(freq)
            if play_type and play_type not in pt and freq is not None:
                pt[play_type] = freq
        break  # use freshest source only

    if not pt:
        return {}

    postup_freq = pt.get("Postup")
    iso_freq = pt.get("Isolation")
    pnr_bh_freq = pt.get("PRBallHandler")

    # Contact-seeking combined share: sum of high-contact creation types
    contact_parts = [v for v in [postup_freq, iso_freq, pnr_bh_freq] if v is not None]
    contact_seeking_share = round(sum(contact_parts), 4) if contact_parts else None
    # Cap at 1.0 (cannot exceed 100% of possessions)
    if contact_seeking_share is not None and contact_seeking_share > 1.0:
        contact_seeking_share = 1.0

    return {
        "postup_freq_pct": postup_freq,
        "isolation_freq_pct": iso_freq,
        "pnr_bh_freq_pct": pnr_bh_freq,
        "contact_seeking_share": contact_seeking_share,
    }


def _and_one_from_pbp(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """And-1 rate from pbp_possession_features (per-game, leak-safe via game_date).

    pbp_and1_count is the number of and-1 plays per game. We aggregate across
    all games <= as_of and return the mean.
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]

    if rows.empty:
        return {}

    n_games = len(rows)
    and1_pg = _rd(rows["pbp_and1_count"].mean()) if "pbp_and1_count" in rows.columns else None

    return {
        "and1_pg": and1_pg,
        "n_games": n_games,
    }


def _shooting_foul_share_from_breakdown(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Shooting-foul share proxy from player_breakdown_features (season-level).

    ``scoring_pct_pts_ft`` is the fraction of all points that came from free throws,
    which is a reliable season-level proxy for shooting-foul drawing frequency.
    Already in [0, 1] from the source; we clamp to guard against data issues.

    LEAK-SAFE: accepted as season-level aggregate (same policy as other season sources).
    """
    for path_key, path in [
        ("breakdown26", DATA / "cache" / "player_breakdown_features.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        pct = _rd(row.get("scoring_pct_pts_ft"))
        pct = _clamp_rate(pct)
        return {
            "pct_scoring_via_ft": pct,
            "direct_shooting_foul_count": None,  # DEFER -- PBP PLAYER2_ID attribution lost
            "_foul_count_note": (
                "DEFER: direct shooting-foul-drawn count requires PBP PLAYER2_ID; "
                "V3->V2 normalisation sets PLAYER2='0'. Proxy only: pct_scoring_via_ft."
            ),
        }
    return {}


def _hustle_draw_from_hustle(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Charges drawn from hustle_features_2025-26 + hustle_features.

    charges_drawn_pg is the per-game average of drawn charges (defensive foul drawn).
    Season-level source; accepted as end-of-season aggregate (same policy as tracking).
    """
    for path_key, path in [
        ("hus26", CACHE / "hustle_features_2025-26.parquet"),
        ("hus_base", CACHE / "hustle_features.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        gp = _rd(row.get("hustle_games_played"))
        charges = _rd(row.get("hustle_charges_drawn"))
        season = str(row.get("season", ""))
        return {
            "charges_drawn_pg": charges,
            "hustle_games_played": _ri(gp) if gp is not None else None,
            "_source_season": season,
        }
    return {}


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerFoulDrawing(AtlasSection):
    """Foul-drawing / FT-generation atlas section (player entity, section='foul_drawing').

    Captures HOW a player generates free throws: FTA volume per 36, drive volume,
    contact-seeking play-type share, and-1 rate, and FT share of scoring.
    Complements ``ft_profile`` (FT%, stability, hack-candidate) and
    ``foul_tendency`` (committed fouls / foul-out risk).

    Reserves 1 CV slot for contact-seeking rate from broadcast CV tracking.

    Sources:
      - data/cache/atlas_player_ft_profile.parquet (FT-generation rates)
      - data/player_tracking_2025-26.parquet + data/player_tracking.parquet (drive vol)
      - data/playtypes_2025-26.parquet + data/playtypes.parquet (contact-seeking share)
      - data/cache/pbp_possession_features.parquet (and-1 per game, leak-safe)
      - data/cache/player_breakdown_features.parquet (pct_scoring_via_ft)
      - data/cache/hustle_features_2025-26.parquet + hustle_features.parquet (charges)

    DEFER sections:
      - drive_fta_rate: PBP PLAYER2_ID attribution lost (V3->V2 normalisation)
      - post_foul_rate: same PBP attribution gap
      - trip_foul_rate: no PBP sequence parquet available
    """

    name: str = "foul_drawing"
    entity: str = "player"
    source_name: str = (
        "atlas_player_ft_profile.parquet + player_tracking_2025-26.parquet + "
        "playtypes_2025-26.parquet + pbp_possession_features.parquet + "
        "player_breakdown_features.parquet + hustle_features_2025-26.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the foul_drawing artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - pbp_possession_features filtered to game_date <= as_of (per-game source).
          - atlas_player_ft_profile.as_of is checked against as_of; rejected if newer.
          - Season-keyed sources (tracking, playtypes, hustle, breakdown) are treated as
            pre-published end-of-season aggregates -- same policy as shot_profile.

        Returns None when all sources are absent for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        ft_gen = _ft_generation_from_atlas(pid, as_of)
        drive = _drive_draw_from_tracking(pid, as_of)
        contact_seek = _contact_seek_from_playtypes(pid, as_of)
        and_one = _and_one_from_pbp(pid, as_of)
        sf_share = _shooting_foul_share_from_breakdown(pid, as_of)
        hustle = _hustle_draw_from_hustle(pid, as_of)

        # Bail if nothing populated at all
        all_empty = (
            not ft_gen and not drive and not contact_seek
            and not and_one and not sf_share and not hustle
        )
        if all_empty:
            return None

        # --- Determine n: use the largest game count across per-game sources ---
        n_candidates: List[int] = []
        if ft_gen.get("n_games"):
            n_candidates.append(ft_gen["n_games"])
        if and_one.get("n_games"):
            n_candidates.append(and_one["n_games"])
        if hustle.get("hustle_games_played"):
            n_candidates.append(hustle["hustle_games_played"])
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            "ft_generation": ft_gen,
            "drive_draw": drive,
            "contact_seeking": contact_seek,
            "and_one": and_one,
            "shooting_foul_share": sf_share,
            "hustle_draw": hustle,
        }

        provenance = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=_rd(ft_gen.get("fta_per_36")),  # headline: FTA/36 as summary scalar
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present; proportions in [0, 1].

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "ft_generation", "drive_draw", "contact_seeking",
            "and_one", "shooting_foul_share", "hustle_draw",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sanity-check proportions in [0, 1]
        cs = sf.get("contact_seeking", {})
        for key in ["postup_freq_pct", "isolation_freq_pct", "pnr_bh_freq_pct",
                    "contact_seeking_share"]:
            v = cs.get(key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        ft = sf.get("ft_generation", {})
        pct = ft.get("pct_pts_from_ft")
        if pct is not None and not (0.0 <= pct <= 1.0):
            return False

        drive = sf.get("drive_draw", {})
        dfg = drive.get("drive_fg_pct")
        if dfg is not None and not (0.0 <= dfg <= 1.0):
            return False

        sf_share = sf.get("shooting_foul_share", {})
        spct = sf_share.get("pct_scoring_via_ft")
        if spct is not None and not (0.0 <= spct <= 1.0):
            return False

        # CV fields: declared slots must be present and null-valued
        for slot_name in self.cv_fields():
            if slot_name not in artifact.cv_fields:
                return False
            if artifact.cv_fields[slot_name].value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for foul_drawing (values None -- CV fills later).

        The CV branch populates ``contact_seek_rate`` from broadcast tracking data
        by calling ``store.fill_cv_slot("player", pid, "foul_drawing", ...)`` without
        a profile rebuild.
        """
        return {
            "contact_seek_rate": CVSlot(
                name="contact_seek_rate",
                dtype="float",
                description=(
                    "Rate (fraction of drive/post terminations) at which the player "
                    "initiates body contact in the lane, estimated from CV "
                    "defender-proximity at drive/post termination and acceleration "
                    "toward the basket in the final 0.5 s before contact. "
                    "Derived from homography court coordinates + Kalman velocity "
                    "estimates from OSNet tracking + EventDetector drive events."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build foul_drawing for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from ft_profile
                    atlas (players who already have FT data built).
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        # Discover from the atlas_player_ft_profile parquet (broadest player coverage)
        ft_path = CACHE / "atlas_player_ft_profile.parquet"
        if ft_path.exists():
            try:
                ft_df = pd.read_parquet(ft_path)
                player_ids = sorted(
                    ft_df["player_id"].dropna().astype(int).unique().tolist()
                )
            except Exception:
                player_ids = []
        if not player_ids:
            # Fallback: discover from pbp_possession_features
            pbp_path = CACHE / "pbp_possession_features.parquet"
            if pbp_path.exists():
                try:
                    pbp_df = pd.read_parquet(pbp_path)
                    player_ids = sorted(
                        pbp_df["player_id"].dropna().astype(int).unique().tolist()
                    )
                except Exception:
                    player_ids = []

    if player_ids is None:
        player_ids = []

    section = PlayerFoulDrawing()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
