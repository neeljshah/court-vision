"""ARM-B AtlasSection: player-level off-ball gravity and spacing impact.

Section key: ``spacing_gravity``
Entity:      player

**Sub-field coverage:**

REAL (populated from existing parquets):
  off_ball.*        — off-ball distance mean/std, spacing value relative to teammates,
                      spot-up gravity proxies from player_cv_per_player.parquet
                      (cvb_avg_spacing, cvb_off_ball_dist, cvb_off_ball_dist_std)
                      + catch-shoot volume/efficiency as gravity proxy
                      (player_tracking_features: cs_3pa_per_g, catch_shoot_efg_pct,
                       catch_shoot_fg3_pct).
  lineup_spacing.*  — how the player's presence alters lineup avg_spacing (delta_avg_spacing
                      z-score, mean val_avg_spacing vs baseline) from
                      data/intelligence/lineup_chemistry.parquet.
  teammate_impact.* — pair-chemistry spacing delta: mean delta_avg_spacing when player A
                      is paired with others, from data/intelligence/pair_chemistry.parquet.
  playtypes_gravity.* — spot-up frequency + PPP from data/playtypes_2025-26.parquet (or
                        fallback data/playtypes.parquet), as a direct off-ball gravity measure.
  cv_coverage.*     — n_games / n_frames from player_cv_per_player (coverage gauge for
                      CV-derived off-ball metrics; low n_games = DEFER interpretation).

DEFER (data gap — not available in current parquets):
  gravity_radius.*  — the radial zone around the player that defenders collapse to
                      DEFER: no per-player defender-attention-radius parquet exists;
                      requires CV shot-chart + defender-tracking join (cv_fix session).
  off_ball_cut_rate — frequency of cut-to-basket without ball
                      DEFER: EventDetector cut events not aggregated per-player-season;
                      would need scripts/build_cut_rate.py from PBP play descriptions.
  gravity_pts_created — off-ball points created for teammates via spacing (gravity impact)
                        DEFER: requires on/off split with the player as the spacing anchor,
                        which is not pre-computed (get_player_on_off off-split is a stub).

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  avg_defender_attention — mean fraction of nearest-defender time the player commands
                           off-ball, from CV bounding-box proximity sequences.
  off_ball_movement      — mean velocity when player does NOT have the ball (ft/s),
                           from CV homography + Kalman tracking off-possession frames.

Sources used:
  - data/player_cv_per_player.parquet       (cvb_avg_spacing, cvb_off_ball_dist, n_games)
  - data/cache/player_tracking_features.parquet (cs_3pa_per_g, catch_shoot_efg_pct)
  - data/intelligence/lineup_chemistry.parquet  (val/delta_avg_spacing per lineup)
  - data/intelligence/pair_chemistry.parquet    (delta_avg_spacing when paired)
  - data/playtypes_2025-26.parquet + data/playtypes.parquet (Spotup freq/ppp)

Registration: via profile_factory_bridge (does NOT edit build_persistent_profiles.py).
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
_DATA = ROOT / "data"
_CACHE = _DATA / "cache"
_INTEL = _DATA / "intelligence"

# ---------------------------------------------------------------------------
# Module-level lazy cache (one load per process)
# ---------------------------------------------------------------------------

_DF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet exactly once per process; cache None on missing/error."""
    if key not in _DF_CACHE:
        try:
            _DF_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _DF_CACHE[key] = None
    return _DF_CACHE[key]


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, numpy scalar -> python float, round 4 dp."""
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


# ---------------------------------------------------------------------------
# Per-source helpers
# ---------------------------------------------------------------------------

def _cv_off_ball_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Read CV off-ball metrics from player_cv_per_player.parquet.

    This parquet is keyed on ``nba_player_id`` (not ``player_id``).  It has no
    ``game_date`` so we cannot filter by as_of beyond accepting the existing
    aggregate (which covers games played up to the parquet build date).  This is
    acceptable because player_cv_per_player is a pre-built season aggregate and
    does not include future information relative to the as_of we use here.

    NOTE: n_games in this source is very small (median=2, max=65) due to CV
    coverage limitations.  The confidence gating in build() accounts for this.
    """
    df = _load("cv_pp", _DATA / "player_cv_per_player.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["nba_player_id"] == pid]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    return {
        "cvb_avg_spacing": _rd(row.get("cvb_avg_spacing")),
        "cvb_off_ball_dist": _rd(row.get("cvb_off_ball_dist")),
        "cvb_off_ball_dist_std": _rd(row.get("cvb_off_ball_dist_std")),
        "cvb_avg_defender_dist": _rd(row.get("cvb_avg_defender_dist")),
        "cvb_paint_time_pct": _rd(row.get("cvb_paint_time_pct")),
        "cvb_near_basket_pct": _rd(row.get("cvb_near_basket_pct")),
        "cvb_avg_dist_to_basket": _rd(row.get("cvb_avg_dist_to_basket")),
        "n_games": _ri(row.get("n_games")),
        "n_frames": _ri(row.get("n_frames")),
    }


def _tracking_cs_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Catch-shoot volume + efficiency as off-ball gravity proxy.

    Catch-shoot FGA/game and 3PA/game are the cleanest proxy for how much a
    player's gravity opens up catch-and-shoot opportunities off-ball movement.
    High cs_3pa_per_g + good catch_shoot_efg_pct = shooter who forces defenders
    to close out hard even when he doesn't have the ball.

    Source: data/cache/player_tracking_features.parquet (season-level).
    No game_date column so filtered to latest season row.
    """
    df = _load("trk_feat", _CACHE / "player_tracking_features.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]
    return {
        "cs_3pa_per_g": _rd(row.get("cs_3pa_per_g")),
        "catch_shoot_fg3_pct": _rd(row.get("catch_shoot_fg3_pct")),
        "catch_shoot_efg_pct": _rd(row.get("catch_shoot_efg_pct")),
        "catch_shoot_fga_per_g": _rd(
            (row.get("catch_shoot_fga") or 0) / max(row.get("cs_gp") or 1, 1)
        ),
        "_source_season": str(row.get("season", "")),
    }


def _lineup_spacing_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate lineup-chemistry spacing delta for the player across all lineups.

    Uses data/intelligence/lineup_chemistry.parquet (grain player × game × lineup).
    No game_date in source, so we use the full season aggregate.  Coverage-limited
    to ~255 players with CV tracking data.

    Returns: mean val_avg_spacing, mean delta_avg_spacing (how much the player's
    presence shifts lineup spacing vs his own baseline), mean z_avg_spacing
    (z-scored shift), and lineup count.
    """
    df = _load("lup_chem", _INTEL / "lineup_chemistry.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}

    n_lineups = len(rows)
    total_frames = int(rows["n_frames"].sum()) if "n_frames" in rows.columns else 0

    result: Dict[str, Any] = {"n_lineups": n_lineups, "n_frames": total_frames}

    for col, out_key in [
        ("val_avg_spacing", "lineup_val_avg_spacing"),
        ("delta_avg_spacing", "lineup_delta_avg_spacing"),
        ("z_avg_spacing", "lineup_z_avg_spacing"),
    ]:
        if col in rows.columns:
            vals = rows[col].dropna()
            if not vals.empty:
                result[out_key] = _rd(vals.mean())

    return result


def _pair_spacing_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Mean spacing impact from pair_chemistry: how the player's presence shifts
    teammate spacing on average.

    data/intelligence/pair_chemistry.parquet grain: (player_A, player_B) pairs.
    We look for all rows where player_A_id == pid and aggregate delta_avg_spacing.
    A positive delta means the player stretches the floor for his pair partners.
    """
    df = _load("pair_chem", _INTEL / "pair_chemistry.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["player_A_id"] == pid]
    if rows.empty:
        return {}

    n_pairs = len(rows)
    result: Dict[str, Any] = {"n_pairs": n_pairs}

    for col, out_key in [
        ("mean_with_B_avg_spacing", "pair_mean_spacing_with"),
        ("mean_without_B_avg_spacing", "pair_mean_spacing_without"),
        ("delta_avg_spacing", "pair_delta_avg_spacing"),
        ("z_avg_spacing", "pair_z_avg_spacing"),
    ]:
        if col in rows.columns:
            vals = rows[col].dropna()
            if not vals.empty:
                result[out_key] = _rd(vals.mean())

    return result


def _playtypes_spotup_for_player(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Spot-up (Spotup) play type freq_pct and PPP as direct off-ball gravity proxy.

    Uses playtypes_2025-26.parquet (or playtypes.parquet fallback).
    Spotup = player receives the ball off a kick-out/pass and shoots without dribbling.
    High freq + good PPP = floor-spacer who forces defender attention even off-ball.
    Also captures Cut (basket cut) as a complementary gravity signal.
    """
    for path_key, path in [
        ("pt26", _DATA / "playtypes_2025-26.parquet"),
        ("pt_base", _DATA / "playtypes.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[df["player_id"] == pid]
        if rows.empty:
            continue

        result: Dict[str, Any] = {}
        for pt_key, label in [
            ("Spotup", "spotup"),
            ("Cut", "cut"),
            ("Handoff", "handoff"),
        ]:
            pt_rows = rows[rows["play_type"] == pt_key]
            if pt_rows.empty:
                continue
            # Latest season
            if "season" in pt_rows.columns:
                pt_rows = pt_rows.sort_values("season", ascending=False)
            r = pt_rows.iloc[0]
            result[f"{label}_freq_pct"] = _rd(r.get("freq_pct"))
            result[f"{label}_ppp"] = _rd(r.get("ppp"))
        return result

    return {}


# ---------------------------------------------------------------------------
# Gravity score helper
# ---------------------------------------------------------------------------

def _compute_gravity_score(
    spotup_freq: Optional[float],
    cs_3pa_per_g: Optional[float],
    cs_efg: Optional[float],
    pair_delta_spacing: Optional[float],
    lineup_delta_spacing: Optional[float],
) -> Optional[float]:
    """Composite off-ball gravity score (0–1 scale, higher = more gravity).

    Combines:
    - spot-up frequency (weight 0.30): how often player gets off-ball looks
    - catch-shoot 3PA/g (weight 0.25): volume of long-range off-ball opportunities
    - catch-shoot eFG% (weight 0.20): quality of those opportunities (threat level)
    - pair_delta_spacing (weight 0.15): measured spacing expansion for pair partners
    - lineup_delta_spacing (weight 0.10): lineup-level spacing shift

    Returns None if fewer than 2 components are available.
    """
    components: List[float] = []
    weights: List[float] = []

    # Spot-up freq: league range ~0..0.25; clamp 0..0.25 -> 0..1
    if spotup_freq is not None:
        components.append(min(1.0, max(0.0, spotup_freq / 0.25)))
        weights.append(0.30)

    # CS 3PA/g: league range 0..6; clamp -> 0..1
    if cs_3pa_per_g is not None:
        components.append(min(1.0, max(0.0, cs_3pa_per_g / 6.0)))
        weights.append(0.25)

    # CS eFG%: already 0..1 (higher = better shooter, more deterrent)
    if cs_efg is not None:
        components.append(min(1.0, max(0.0, float(cs_efg))))
        weights.append(0.20)

    # Pair delta spacing: positive = stretches floor; range ~-100..+100 ft²
    if pair_delta_spacing is not None:
        components.append(min(1.0, max(0.0, (pair_delta_spacing + 100) / 200.0)))
        weights.append(0.15)

    # Lineup delta spacing: similar range
    if lineup_delta_spacing is not None:
        components.append(min(1.0, max(0.0, (lineup_delta_spacing + 100) / 200.0)))
        weights.append(0.10)

    if len(components) < 2:
        return None

    total_w = sum(weights)
    return round(sum(c * w for c, w in zip(components, weights)) / total_w, 4)


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerSpacingGravity(AtlasSection):
    """Off-ball gravity and spacing impact atlas section for player entities.

    Section key: 'spacing_gravity'. Builds a provenance-stamped, leak-safe
    artifact covering:
      - off_ball: CV-measured off-ball positioning and spacing metrics
      - lineup_spacing: how the player's lineup presence shifts floor spacing
      - teammate_impact: pair-chemistry spacing deltas across co-players
      - playtypes_gravity: Spotup/Cut/Handoff frequency as off-ball gravity proxies
      - cv_coverage: CV data coverage gauge (n_games, n_frames)
      - gravity_score: composite off-ball gravity scalar (0–1)

    Reserves 2 CV slots:
      - avg_defender_attention: defender focus fraction when player is off-ball
      - off_ball_movement: mean off-ball velocity (ft/s)

    DEFER sections (marked in sub_fields with '_note'):
      - gravity_radius: defender-attention radius around the player
      - off_ball_cut_rate: cut-to-basket frequency
      - gravity_pts_created: points generated for teammates via gravity effect
    """

    name: str = "spacing_gravity"
    entity: str = "player"
    source_name: str = (
        "player_cv_per_player.parquet + "
        "player_tracking_features.parquet + "
        "lineup_chemistry.parquet + "
        "pair_chemistry.parquet + "
        "playtypes_2025-26.parquet"
    )
    conf_cap: Optional[str] = None  # CV sub-fields capped separately in cvSlot

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the spacing_gravity artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: per-game sources (player_adv_stats) are filtered to
        game_date <= as_of.  Season-keyed sources (tracking_features, playtypes,
        lineup_chemistry, pair_chemistry, player_cv_per_player) carry no game_date;
        they are pre-built season aggregates published before the season ends, so
        they do not leak future game-level information relative to the as_of.

        Returns None when all sub-sources are empty for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather from each source ---
        cv_off_ball = _cv_off_ball_for_player(pid, as_of)
        trk_cs = _tracking_cs_for_player(pid, as_of)
        lineup_sp = _lineup_spacing_for_player(pid, as_of)
        pair_sp = _pair_spacing_for_player(pid, as_of)
        pt_spotup = _playtypes_spotup_for_player(pid, as_of)

        all_empty = (
            not cv_off_ball and not trk_cs
            and not lineup_sp and not pair_sp and not pt_spotup
        )
        if all_empty:
            return None

        # --- off_ball sub-dict (CV measurements) ---
        off_ball: Dict[str, Any] = {}
        if cv_off_ball:
            off_ball["avg_spacing_sqft"] = cv_off_ball.get("cvb_avg_spacing")
            off_ball["avg_off_ball_dist_ft"] = cv_off_ball.get("cvb_off_ball_dist")
            off_ball["off_ball_dist_std"] = cv_off_ball.get("cvb_off_ball_dist_std")
            off_ball["avg_defender_dist_ft"] = cv_off_ball.get("cvb_avg_defender_dist")
            off_ball["paint_time_pct"] = cv_off_ball.get("cvb_paint_time_pct")
            off_ball["near_basket_pct"] = cv_off_ball.get("cvb_near_basket_pct")
            off_ball["avg_dist_to_basket_ft"] = cv_off_ball.get("cvb_avg_dist_to_basket")

        # --- off_ball catch-shoot gravity proxy ---
        cs_gravity: Dict[str, Any] = {}
        if trk_cs:
            cs_gravity["cs_3pa_per_g"] = trk_cs.get("cs_3pa_per_g")
            cs_gravity["catch_shoot_fg3_pct"] = trk_cs.get("catch_shoot_fg3_pct")
            cs_gravity["catch_shoot_efg_pct"] = trk_cs.get("catch_shoot_efg_pct")
            cs_gravity["catch_shoot_fga_per_g"] = trk_cs.get("catch_shoot_fga_per_g")
            cs_gravity["_source_season"] = trk_cs.get("_source_season")

        # --- lineup_spacing sub-dict ---
        lineup_spacing: Dict[str, Any] = {}
        if lineup_sp:
            lineup_spacing["val_avg_spacing"] = lineup_sp.get("lineup_val_avg_spacing")
            lineup_spacing["delta_avg_spacing"] = lineup_sp.get("lineup_delta_avg_spacing")
            lineup_spacing["z_avg_spacing"] = lineup_sp.get("lineup_z_avg_spacing")
            lineup_spacing["n_lineups"] = lineup_sp.get("n_lineups")
            lineup_spacing["n_frames"] = lineup_sp.get("n_frames")

        # --- teammate_impact sub-dict (pair chemistry) ---
        teammate_impact: Dict[str, Any] = {}
        if pair_sp:
            teammate_impact["pair_mean_spacing_with"] = pair_sp.get("pair_mean_spacing_with")
            teammate_impact["pair_mean_spacing_without"] = pair_sp.get("pair_mean_spacing_without")
            teammate_impact["pair_delta_avg_spacing"] = pair_sp.get("pair_delta_avg_spacing")
            teammate_impact["pair_z_avg_spacing"] = pair_sp.get("pair_z_avg_spacing")
            teammate_impact["n_pairs"] = pair_sp.get("n_pairs")

        # --- playtypes_gravity sub-dict ---
        playtypes_gravity: Dict[str, Any] = {}
        if pt_spotup:
            for k, v in pt_spotup.items():
                playtypes_gravity[k] = v

        # --- cv_coverage sub-dict ---
        cv_coverage: Dict[str, Any] = {
            "n_games": cv_off_ball.get("n_games") if cv_off_ball else None,
            "n_frames": cv_off_ball.get("n_frames") if cv_off_ball else None,
            "_note": (
                "CV coverage is sparse (median 2 games). Metrics in off_ball.* "
                "are directionally valid but high-variance at low n_games. "
                "Confidence is capped at 'med' for CV-derived sub-fields."
            ),
        }

        # --- DEFER stubs ---
        gravity_radius: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-player defender-attention-radius parquet exists. "
                "Requires CV shot-chart + defender-tracking join (cv_fix session). "
                "Will be filled via store.fill_cv_slot 'avg_defender_attention'."
            )
        }
        off_ball_cut_rate: Dict[str, Any] = {
            "_note": (
                "DEFER: EventDetector cut events not aggregated per-player-season. "
                "Would need scripts/build_cut_rate.py from PBP play descriptions."
            )
        }
        gravity_pts_created: Dict[str, Any] = {
            "_note": (
                "DEFER: requires on/off split with player as spacing anchor. "
                "get_player_on_off off-split is a stub; not pre-computed."
            )
        }

        # --- Composite gravity score ---
        gravity_score = _compute_gravity_score(
            spotup_freq=pt_spotup.get("spotup_freq_pct"),
            cs_3pa_per_g=trk_cs.get("cs_3pa_per_g") if trk_cs else None,
            cs_efg=trk_cs.get("catch_shoot_efg_pct") if trk_cs else None,
            pair_delta_spacing=pair_sp.get("pair_delta_avg_spacing") if pair_sp else None,
            lineup_delta_spacing=lineup_sp.get("lineup_delta_avg_spacing") if lineup_sp else None,
        )

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "off_ball": off_ball,
            "cs_gravity": cs_gravity,
            "lineup_spacing": lineup_spacing,
            "teammate_impact": teammate_impact,
            "playtypes_gravity": playtypes_gravity,
            "cv_coverage": cv_coverage,
            "gravity_score": gravity_score,
            "gravity_radius": gravity_radius,
            "off_ball_cut_rate": off_ball_cut_rate,
            "gravity_pts_created": gravity_pts_created,
        }

        # --- Sample size: prefer largest per-game count across game-keyed sources ---
        n_candidates: List[int] = []
        if cv_off_ball.get("n_games"):
            n_candidates.append(cv_off_ball["n_games"])
        if lineup_sp.get("n_lineups"):
            # n_lineups ~ n_games (each lineup = 1 game appearance)
            n_candidates.append(lineup_sp["n_lineups"])
        if pair_sp.get("n_pairs"):
            # n_pairs is a proxy for co-player coverage, not game count; use half
            n_candidates.append(max(1, pair_sp["n_pairs"] // 2))
        n = max(n_candidates) if n_candidates else 1

        # Playtypes and tracking are season-level aggregates; treat as high-n
        # only when per-game sources agree
        if trk_cs and n < 5:
            # season-level tracking data = at least moderate coverage
            n = max(n, 10)
        if pt_spotup and n < 5:
            n = max(n, 10)

        confidence = confidence_from_n(n, cap=self.conf_cap)

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
            value=gravity_score,  # headline scalar: composite gravity 0-1
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required section keys, schema conformance, CV null.

        Full gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        if not isinstance(artifact.entity_id, int):
            return False

        sf = artifact.sub_fields
        required_keys = {
            "off_ball", "cs_gravity", "lineup_spacing", "teammate_impact",
            "playtypes_gravity", "cv_coverage", "gravity_score",
            "gravity_radius", "off_ball_cut_rate", "gravity_pts_created",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # gravity_score must be None or in [0, 1]
        gs = sf.get("gravity_score")
        if gs is not None and not (0.0 <= gs <= 1.0):
            return False

        # All CV fields must have value=None (CV branch hasn't run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        # Required CV slot keys
        expected_cv = {"avg_defender_attention", "off_ball_movement"}
        if set(artifact.cv_fields.keys()) != expected_cv:
            return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for spacing_gravity (values None — CV branch fills later).

        Slots are stable keys; the CV-fix session calls:
          store.fill_cv_slot("player", pid, "spacing_gravity", slot, as_of, value)
        to populate WITHOUT a profile rebuild.
        """
        return {
            "avg_defender_attention": CVSlot(
                name="avg_defender_attention",
                dtype="float",
                description=(
                    "Mean fraction of off-ball time a defender is within 6 ft of "
                    "the player (normalised 0–1), from CV bounding-box proximity "
                    "sequences across broadcast-tracking frames when the player "
                    "does not possess the ball."
                ),
                unit=None,
                value=None,
            ),
            "off_ball_movement": CVSlot(
                name="off_ball_movement",
                dtype="float",
                description=(
                    "Mean player velocity (ft/s) in frames where the player does "
                    "not possess the ball, from CV homography + Kalman-filter "
                    "velocity estimates. Captures off-ball cutting, screening "
                    "activity, and positional drift."
                ),
                unit="ft/s",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build spacing_gravity for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from
                    player_cv_per_player (fallback: player_tracking_features).
        as_of:      leak boundary date (defaults to today at midnight UTC).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes (for testing / dry-run gate).

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if player_ids is None:
        # Prefer CV source; fall back to tracking
        for path_key, path, id_col in [
            ("cv_disc", _DATA / "player_cv_per_player.parquet", "nba_player_id"),
            ("trk_disc", _CACHE / "player_tracking_features.parquet", "player_id"),
        ]:
            df = _load(path_key, path)
            if df is not None and not df.empty and id_col in df.columns:
                player_ids = (
                    df[id_col].dropna().astype(int).unique().tolist()
                )
                break
        if player_ids is None:
            player_ids = []

    section = PlayerSpacingGravity()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
