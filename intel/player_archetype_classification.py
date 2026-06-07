"""ARM-B atlas section: ``archetype_classification`` — player scheme role + playstyle cluster.

Implements :class:`AtlasSection` for the ``"archetype_classification"`` section of a
player's persistent profile.  This section provides the player→archetype→league shrinkage
prior: the archetype label + CV-based playstyle cluster the simulator and VARIANCE_ONLY
signals shrink toward (DESIGN.md §6 point 2).

**Sub-field coverage:**

REAL (populated from existing parquets — NO re-derivation):
  archetype.*         — primary_archetype_id / primary_archetype_name / archetype_source
                        (fingerprints_kbest → archetype_label_sidecar fallback) from
                        data/intelligence/player_fingerprints_kbest.parquet and
                        data/intelligence/archetype_label_sidecar.parquet.
  cluster_features.*  — CV-derived playstyle fingerprint features used to assign the
                        cluster: paint_dwell_pct, shot_zone_paint/mid/3pt_pct,
                        avg_shot_distance, touches_per_game, shots_per_possession,
                        possession_duration_avg, second_chance_rate, preshot_velocity_peak,
                        defender_approach_speed, play_type_* pcts, catch_shoot_pct,
                        avg_dribble_count, contested_shot_rate, avg_defender_distance
                        — from data/intelligence/player_fingerprints_kbest.parquet.
  drift.*             — consistency_score, drift_tag (STABLE/TRANSITIONING/DRIFTING),
                        recent_archetype_name, top_alternate_archetype_name,
                        archetype_distribution — from data/intelligence/archetype_drift.parquet.
  scheme_role.*       — position (Guard/Forward/Center/etc.), season_exp, bio_as_of
                        — from data/cache/player_profile_features.parquet.
  usage_efficiency.*  — season-aggregate usage_pct, ts_pct, efg_pct, off_rating, def_rating,
                        net_rating filtered to games <= as_of
                        — from data/player_adv_stats.parquet.
  synergy.*           — syn_pnr_bh_ppp, syn_spotup_ppp, syn_iso_ppp, syn_postup_ppp,
                        syn_transition_ppp — from data/cache/synergy_ppp_features.parquet.
  dist_from_centroid  — float distance of the player from their archetype cluster centre
                        (quality-of-fit signal); from player_fingerprints_kbest.

DEFER (data gap — not available in current parquets):
  on_off_by_archetype.* — how a player's on/off impact differs across archetype match-ups
                           DEFER: on_off_features.parquet has season-level data but no
                           per-opponent-archetype split.
  scheme_interaction.*  — per-archetype × per-opponent-scheme expected stat deviation
                           DEFER: archetype_scheme_interactions.parquet has this at archetype
                           grain (not per-player, per-game); no player_id column.

RESERVED CV SLOTS (value=None, CV branch fills later):
  cv_archetype_dist     — per-game KMeans distance-from-centroid averaged over CV games
                          (more granular than the batch fingerprint dist_from_centroid)
  cv_spacing_profile    — mean team convex-hull spacing when THIS player is on court (ft²)
  cv_paint_touch_rate   — fraction of possessions where player touches ball in the paint
  cv_ball_handler_rate  — fraction of possessions where player is the primary ball-handler
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
DATA = ROOT / "data"
CACHE = DATA / "cache"
INTEL = DATA / "intelligence"


# ---------------------------------------------------------------------------
# Data-loading helpers (lazy, module-level cache)
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


def _rs(v: Any) -> Optional[str]:
    """Clean string scalar; return None for nan/None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v)
    return s if s and s.lower() not in ("nan", "none", "") else None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _archetype_from_kbest(pid: int) -> Dict[str, Any]:
    """Primary archetype + cluster features from player_fingerprints_kbest.parquet.

    The kbest parquet is indexed by player_id (as the DataFrame index).
    Falls back to archetype_label_sidecar if player_id absent in kbest.
    """
    df = _load("fp_kbest", INTEL / "player_fingerprints_kbest.parquet")
    result: Dict[str, Any] = {}

    if df is not None and not df.empty:
        # player_id may be the index (int) — check index first
        if df.index.name == "player_id" or (
            df.index.dtype in (np.int64, np.int32)
            and pid in df.index
        ):
            if pid in df.index:
                row = df.loc[pid]
                result["_source"] = "player_fingerprints_kbest"
                result["archetype_id"] = _ri(row.get("archetype_id"))
                result["archetype_name"] = _rs(row.get("archetype_name"))
                result["dist_from_centroid"] = _rd(row.get("dist_from_centroid"))
                result["n_cv_games"] = _ri(row.get("n_cv_games"))
                result["k_value"] = _ri(row.get("k_value"))
                # Cluster features
                _CLUSTER_COLS = [
                    "paint_dwell_pct", "shot_zone_paint_pct", "shot_zone_mid_range_pct",
                    "shot_zone_3pt_pct", "avg_shot_distance", "touches_per_game",
                    "shots_per_possession", "possession_duration_avg", "second_chance_rate",
                    "potential_assists", "preshot_velocity_peak", "defender_approach_speed",
                    "play_type_transition_pct", "play_type_isolation_pct", "play_type_post_pct",
                    "catch_shoot_pct", "avg_dribble_count", "contested_shot_rate",
                    "avg_defender_distance",
                ]
                for col in _CLUSTER_COLS:
                    v = row.get(col)
                    if v is not None:
                        result[f"cf_{col}"] = _rd(v)
                return result
        # Try player_id as a regular column
        if "player_id" in df.columns:
            rows = df[df["player_id"] == pid]
            if not rows.empty:
                row = rows.iloc[0]
                result["_source"] = "player_fingerprints_kbest"
                result["archetype_id"] = _ri(row.get("archetype_id"))
                result["archetype_name"] = _rs(row.get("archetype_name"))
                result["dist_from_centroid"] = _rd(row.get("dist_from_centroid"))
                result["n_cv_games"] = _ri(row.get("n_cv_games"))
                result["k_value"] = _ri(row.get("k_value"))
                _CLUSTER_COLS = [
                    "paint_dwell_pct", "shot_zone_paint_pct", "shot_zone_mid_range_pct",
                    "shot_zone_3pt_pct", "avg_shot_distance", "touches_per_game",
                    "shots_per_possession", "possession_duration_avg", "second_chance_rate",
                    "potential_assists", "preshot_velocity_peak", "defender_approach_speed",
                    "play_type_transition_pct", "play_type_isolation_pct", "play_type_post_pct",
                    "catch_shoot_pct", "avg_dribble_count", "contested_shot_rate",
                    "avg_defender_distance",
                ]
                for col in _CLUSTER_COLS:
                    v = row.get(col)
                    if v is not None:
                        result[f"cf_{col}"] = _rd(v)
                return result

    # Fallback: archetype_label_sidecar (less detail — no cluster features)
    sidecar = _load("arch_sidecar", INTEL / "archetype_label_sidecar.parquet")
    if sidecar is not None and not sidecar.empty and "player_id" in sidecar.columns:
        rows = sidecar[sidecar["player_id"] == pid]
        if not rows.empty:
            row = rows.iloc[0]
            result["_source"] = "archetype_label_sidecar"
            result["archetype_id"] = _ri(row.get("archetype_id"))
            result["archetype_name"] = _rs(row.get("archetype_name"))

    return result


def _drift_for_player(pid: int) -> Dict[str, Any]:
    """Archetype stability / drift info from archetype_drift.parquet."""
    df = _load("arch_drift", INTEL / "archetype_drift.parquet")
    if df is None or df.empty or "player_id" not in df.columns:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    out: Dict[str, Any] = {
        "consistency_score": _rd(row.get("consistency_score")),
        "drift_tag": _rs(row.get("drift_tag")),  # STABLE / TRANSITIONING / DRIFTING
        "n_games": _ri(row.get("n_games")),
        "recent_archetype_name": _rs(row.get("recent_archetype_name")),
        "top_alternate_archetype_name": _rs(row.get("top_alternate_archetype_name")),
    }
    # archetype_distribution is a list/dict — safe-serialize
    dist_raw = row.get("archetype_distribution")
    if dist_raw is not None:
        try:
            if pd.isna(dist_raw):
                dist_raw = None
        except (TypeError, ValueError):
            pass
        if dist_raw is not None:
            if isinstance(dist_raw, str):
                import json as _json
                try:
                    out["archetype_distribution"] = _json.loads(dist_raw)
                except Exception:
                    out["archetype_distribution"] = dist_raw
            else:
                out["archetype_distribution"] = dist_raw
    return out


def _bio_scheme_role(pid: int) -> Dict[str, Any]:
    """Position + experience from player_profile_features.parquet (no date filter needed)."""
    df = _load("bio", CACHE / "player_profile_features.parquet")
    if df is None or df.empty or "player_id" not in df.columns:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    row = rows.iloc[0]
    return {
        "position": _rs(row.get("position")),
        "season_exp": _ri(row.get("season_exp")),
        "bio_as_of": _rs(row.get("profile_as_of")),
    }


def _usage_efficiency(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-aggregate usage/efficiency from player_adv_stats, filtered <= as_of."""
    df = _load("adv", DATA / "player_adv_stats.parquet")
    if df is None or df.empty or "player_id" not in df.columns:
        return {}
    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    _COLS = [
        "usagepercentage", "trueshootingpercentage",
        "effectivefieldgoalpercentage", "offensiverating",
        "defensiverating", "netrating",
    ]
    means = rows[[c for c in _COLS if c in rows.columns]].mean()
    return {
        "usage_pct": _rd(means.get("usagepercentage")),
        "ts_pct": _rd(means.get("trueshootingpercentage")),
        "efg_pct": _rd(means.get("effectivefieldgoalpercentage")),
        "off_rating": _rd(means.get("offensiverating")),
        "def_rating": _rd(means.get("defensiverating")),
        "net_rating": _rd(means.get("netrating")),
        "n_games": n,
    }


def _synergy_for_player(pid: int) -> Dict[str, Any]:
    """Play-type PPP from synergy_ppp_features; latest season (no game_date filter needed)."""
    df = _load("syn", CACHE / "synergy_ppp_features.parquet")
    if df is None or df.empty or "player_id" not in df.columns:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    if "season" in rows.columns:
        rows = rows.sort_values("season", ascending=False)
    row = rows.iloc[0]
    return {
        "syn_pnr_bh_ppp": _rd(row.get("syn_pnr_bh_ppp")),
        "syn_spotup_ppp": _rd(row.get("syn_spotup_ppp")),
        "syn_iso_ppp": _rd(row.get("syn_iso_ppp")),
        "syn_postup_ppp": _rd(row.get("syn_postup_ppp")),
        "syn_transition_ppp": _rd(row.get("syn_transition_ppp")),
        "season": _rs(row.get("season")),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerArchetypeClassification(AtlasSection):
    """Scheme role + playstyle cluster section for player shrinkage priors.

    This is the keystone of the reinforcement loop (DESIGN.md §6 point 2):
    ``archetype_classification`` provides the player→archetype→league prior
    that the simulator and VARIANCE_ONLY signals shrink toward.  The section
    also enables intel-scan (DESIGN.md §6 point 3) — residual buckets whose
    players share an archetype → a Hypothesis — and archetype × opponent-scheme
    interaction features (§6 point 1).

    Sources used:
      - data/intelligence/player_fingerprints_kbest.parquet  (primary archetype + cluster features)
      - data/intelligence/archetype_label_sidecar.parquet    (fallback label)
      - data/intelligence/archetype_drift.parquet            (stability / drift metrics)
      - data/cache/player_profile_features.parquet           (position / bio)
      - data/player_adv_stats.parquet                        (usage/efficiency, as_of filtered)
      - data/cache/synergy_ppp_features.parquet              (play-type PPP)

    DEFER sections:
      - on_off_by_archetype — on_off_features.parquet is season-level, not split by opp archetype
      - scheme_interaction  — archetype_scheme_interactions.parquet is archetype-grain (no player_id)

    RESERVED CV SLOTS (None until CV branch fills):
      - cv_archetype_dist    — per-game KMeans dist-from-centroid over CV games
      - cv_spacing_profile   — mean team spacing when player is on court (ft²)
      - cv_paint_touch_rate  — fraction of possessions ball touches the paint by this player
      - cv_ball_handler_rate — fraction of possessions this player is primary handler
    """

    name: str = "archetype_classification"
    entity: str = "player"
    source_name: str = (
        "player_fingerprints_kbest.parquet + archetype_label_sidecar.parquet + "
        "archetype_drift.parquet + player_profile_features.parquet + "
        "player_adv_stats.parquet + synergy_ppp_features.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the archetype_classification artifact for player ``entity_id``.

        Leak guarantee:
          - player_adv_stats filtered to game_date <= as_of (per-game source).
          - All other sources are season-level / static entity tables without
            game_date; they are pre-published summaries that existed before the
            as_of boundary and are safe to read in their entirety.
          - CV n_cv_games in player_fingerprints reflects a historical game count
            frozen at the time the fingerprint was built — no future leakage.

        Returns None when the player is absent from all archetype and label sources.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # Primary: archetype label + cluster features
        arch = _archetype_from_kbest(pid)

        # If no archetype data at all, skip this player (cannot provide the prior)
        if not arch or arch.get("archetype_name") is None:
            return None

        drift = _drift_for_player(pid)
        bio = _bio_scheme_role(pid)
        usage = _usage_efficiency(pid, as_of)
        synergy = _synergy_for_player(pid)

        # --- Archetype sub-dict ---
        archetype_sub: Dict[str, Any] = {
            "primary_archetype_id": arch.get("archetype_id"),
            "primary_archetype_name": arch.get("archetype_name"),
            "archetype_source": arch.get("_source", "unknown"),
            "dist_from_centroid": arch.get("dist_from_centroid"),
            "n_cv_games": arch.get("n_cv_games"),
            "k_value": arch.get("k_value"),
        }

        # --- Cluster-feature sub-dict (CV-derived behavioral fingerprint) ---
        cluster_features: Dict[str, Any] = {
            k[3:]: v  # strip the cf_ prefix added by _archetype_from_kbest
            for k, v in arch.items()
            if k.startswith("cf_")
        }

        # --- Drift sub-dict ---
        drift_sub: Dict[str, Any] = {
            "consistency_score": drift.get("consistency_score"),
            "drift_tag": drift.get("drift_tag"),
            "drift_n_games": drift.get("n_games"),
            "recent_archetype_name": drift.get("recent_archetype_name"),
            "top_alternate_archetype_name": drift.get("top_alternate_archetype_name"),
            "archetype_distribution": drift.get("archetype_distribution"),
        } if drift else {"_note": "player absent from archetype_drift.parquet"}

        # --- Scheme role sub-dict (from bio) ---
        scheme_role_sub: Dict[str, Any] = dict(bio) if bio else {
            "_note": "DEFER: player absent from player_profile_features.parquet"
        }

        # --- Usage / efficiency sub-dict (as_of filtered) ---
        usage_efficiency_sub: Dict[str, Any] = dict(usage) if usage else {
            "_note": "DEFER: player absent from player_adv_stats.parquet at this as_of"
        }

        # --- Synergy sub-dict ---
        synergy_sub: Dict[str, Any] = dict(synergy) if synergy else {
            "_note": "DEFER: player absent from synergy_ppp_features.parquet"
        }

        # --- DEFER stubs ---
        on_off_by_archetype: Dict[str, Any] = {
            "_note": (
                "DEFER: on_off_features.parquet is season-level only; no per-opponent-"
                "archetype split exists. Wire when archetype-split on/off data is built."
            )
        }
        scheme_interaction: Dict[str, Any] = {
            "_note": (
                "DEFER: archetype_scheme_interactions.parquet has archetype-grain rows "
                "(no player_id column); player-level scheme-interaction requires a join "
                "on archetype_id that would add noise. Read via the archetype sub_field."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "archetype": archetype_sub,
            "cluster_features": cluster_features,
            "drift": drift_sub,
            "scheme_role": scheme_role_sub,
            "usage_efficiency": usage_efficiency_sub,
            "synergy": synergy_sub,
            "on_off_by_archetype": on_off_by_archetype,
            "scheme_interaction": scheme_interaction,
        }

        # Headline value: the archetype name (useful for downstream str comparisons)
        headline_value = arch.get("archetype_name")

        # --- n = max across game-count sources ---
        n_candidates: List[int] = []
        if usage.get("n_games"):
            n_candidates.append(usage["n_games"])
        if drift.get("n_games"):
            n_candidates.append(drift["n_games"])
        if arch.get("n_cv_games"):
            n_candidates.append(arch["n_cv_games"])
        n = max(n_candidates) if n_candidates else 1

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
            value=headline_value,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present and values in sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "archetype", "cluster_features", "drift", "scheme_role",
            "usage_efficiency", "synergy", "on_off_by_archetype", "scheme_interaction",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # archetype must have at least a name
        arch = sf.get("archetype", {})
        if not arch.get("primary_archetype_name"):
            return False

        # usage_efficiency sanity: usage_pct in [0,1], ratings in plausible range
        ue = sf.get("usage_efficiency", {})
        for pct_key in ("usage_pct", "ts_pct", "efg_pct"):
            v = ue.get(pct_key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False
        for rtg_key in ("off_rating", "def_rating", "net_rating"):
            v = ue.get(rtg_key)
            if v is not None and not (-50.0 <= v <= 200.0):
                return False

        # dist_from_centroid should be non-negative if present
        dist = arch.get("dist_from_centroid")
        if dist is not None and dist < 0:
            return False

        # CV fields must all have value=None (CV branch hasn't run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for archetype_classification (values None now).

        The CV branch fills these via
        ``store.fill_cv_slot("player", pid, "archetype_classification", slot, as_of, value)``
        without a profile-factory rebuild (DESIGN.md §4 CV-slot lifecycle).
        """
        return {
            "cv_archetype_dist": CVSlot(
                name="cv_archetype_dist",
                dtype="float",
                description=(
                    "Per-game KMeans distance from archetype cluster centroid averaged "
                    "over all CV-tracked games for this player.  More granular than the "
                    "batch fingerprint dist_from_centroid; reflects in-season cluster drift."
                ),
                unit=None,
                value=None,
            ),
            "cv_spacing_profile": CVSlot(
                name="cv_spacing_profile",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft²) of all five teammates when this player "
                    "is on court, averaged across CV-tracked possessions.  Measures the "
                    "floor-spacing context the player operates in."
                ),
                unit="ft²",
                value=None,
            ),
            "cv_paint_touch_rate": CVSlot(
                name="cv_paint_touch_rate",
                dtype="float",
                description=(
                    "Fraction of half-court offensive possessions where this player "
                    "physically touches the ball inside the paint (CV position + "
                    "ball-handler-detection).  Distinguishes true interior players "
                    "from perimeter players who may post up occasionally."
                ),
                unit=None,
                value=None,
            ),
            "cv_ball_handler_rate": CVSlot(
                name="cv_ball_handler_rate",
                dtype="float",
                description=(
                    "Fraction of possessions where this player is identified as the "
                    "primary ball-handler (longest continuous possession segment), "
                    "from CV handler_isolation and velocity-toward-basket signal."
                ),
                unit=None,
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
    """Build archetype_classification for a list of player_ids and register.

    Discovers player_ids from the union of fingerprints_kbest + archetype_label_sidecar
    when not supplied.

    Args:
        player_ids: NBA player_id ints.  None = auto-discover from archetype parquets.
        as_of:      leak boundary (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written leak-safe.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        pids: set = set()
        # Discover from kbest (index or player_id column)
        df_kb = _load("fp_kbest", INTEL / "player_fingerprints_kbest.parquet")
        if df_kb is not None and not df_kb.empty:
            if "player_id" in df_kb.columns:
                pids.update(df_kb["player_id"].dropna().astype(int).tolist())
            elif df_kb.index.dtype in (np.int64, np.int32, int):
                pids.update(df_kb.index.dropna().astype(int).tolist())
        # Discover from sidecar
        df_sc = _load("arch_sidecar", INTEL / "archetype_label_sidecar.parquet")
        if df_sc is not None and not df_sc.empty and "player_id" in df_sc.columns:
            pids.update(df_sc["player_id"].dropna().astype(int).tolist())
        player_ids = sorted(pids)

    section = PlayerArchetypeClassification()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
