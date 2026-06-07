"""ARM-B atlas section: ``isolation_profile`` — per-player isolation usage + efficiency.

Implements :class:`AtlasSection` for the ``"isolation_profile"`` section of a
player's persistent profile.  All sub-fields come from existing parquets listed in
spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  frequency.*    — isolation play frequency (freq_pct) and points per possession (ppp)
                   from playtypes_2025-26.parquet (fallback: playtypes.parquet).
                   Also iso_poss_per_game from pbp_possession_features.parquet.
  efficiency.*   — ppp (already in frequency), plus pts_ft_share / and_one_rate
                   from atlas_player_scoring_creation.parquet as FT-draw rate proxies.
  ft_draw.*      — fta_per_36_q50 median prediction from ft_rate_predictions.parquet
                   (per-game model output, filtered to games <= as_of).
  late_clock.*   — pbp_late_clock_shots per game + ratio of late-clock shots to iso
                   possessions from pbp_possession_features.parquet.
  vs_set_defense.*— halfcourt_pts_share from atlas_player_scoring_creation.parquet as a
                    proxy for fraction of scoring opportunity in set (non-transition)
                    defense. Complements iso freq_pct (isolation occurs almost
                    exclusively in halfcourt/set defense).

DEFER (data gap — not available in current parquets):
  defender_quality.*  — opponent defensive rating when assigned to guard this player;
                        no per-matchup defensive-rating-by-play-type parquet exists.
  late_shot_ppp.*     — ppp on possessions ending with <7 s on shot clock;
                        shot_clock_buckets uses player_name pkey (not player_id).
  fg_pct_iso.*        — raw FG% on isolation attempts;
                        playtypes parquet has only freq_pct + ppp, not FGA/FGM.

RESERVED CV SLOTS (value=None, CV branch fills later):
  defender_distance_iso — mean nearest-defender distance at shot release on
                          CV-tagged isolation possessions (ft).
  blow_by_rate          — fraction of iso possessions where ball-handler
                          beats the defender off the dribble before shooting,
                          from CV EventDetector drive classification.
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


# ---------------------------------------------------------------------------
# Per-source helpers
# ---------------------------------------------------------------------------

def _playtypes_iso(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Return Isolation play-type stats from playtypes parquet (latest season <= as_of).

    Returns freq_pct (proportion in [0,1]) and ppp for isolation possessions.
    Season-keyed only (no game_date); uses the freshest source that has data.
    """
    for path_key, path in [
        ("pt26", DATA / "playtypes_2025-26.parquet"),
        ("pt_base", DATA / "playtypes.parquet"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        rows = df[(df["player_id"] == pid) & (df["play_type"] == "Isolation")]
        if rows.empty:
            continue
        if "season" in rows.columns:
            rows = rows.sort_values("season", ascending=False)
        row = rows.iloc[0]
        freq = _rd(row.get("freq_pct"))
        # freq_pct in playtypes is already a proportion in [0,1] (e.g. 0.067)
        # Null out-of-range values per CRITICAL LESSON 3
        if freq is not None and not (0.0 <= freq <= 1.0):
            freq = None
        return {
            "iso_freq_pct": freq,
            "iso_ppp": _rd(row.get("ppp")),
            "_source_season": str(row.get("season", "")),
        }
    return {}


def _pbp_iso(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Per-game ISO and late-clock counts from pbp_possession_features, <= as_of.

    Returns n (actual game count), iso_poss_per_game, late_clock_shots_pg,
    late_clock_iso_ratio (late_clock / iso_poss on games with iso > 0).
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter via game_date (CRITICAL LESSON 5)
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)  # actual game rows (CRITICAL LESSON 1)

    iso_pg = _rd(rows["pbp_iso_poss_count"].mean()) if "pbp_iso_poss_count" in rows.columns else None
    late_pg = _rd(rows["pbp_late_clock_shots"].mean()) if "pbp_late_clock_shots" in rows.columns else None

    # Late-clock iso rate: on games where iso > 0, what fraction are late-clock?
    late_clock_iso_ratio: Optional[float] = None
    if "pbp_iso_poss_count" in rows.columns and "pbp_late_clock_shots" in rows.columns:
        iso_games = rows[rows["pbp_iso_poss_count"] > 0].copy()
        if not iso_games.empty:
            ratio = (iso_games["pbp_late_clock_shots"] / iso_games["pbp_iso_poss_count"]).mean()
            v = _rd(ratio)
            # This is a ratio that can exceed 1 (late_clock can include non-iso shots),
            # so we do NOT enforce [0,1] — it is a rate not a proportion
            late_clock_iso_ratio = v

    return {
        "n": n,
        "iso_poss_per_game": iso_pg,
        "late_clock_shots_pg": late_pg,
        "late_clock_iso_ratio": late_clock_iso_ratio,
    }


def _scoring_creation_iso(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Read atlas_player_scoring_creation for FT-draw proxies and set-defense share.

    Uses and_one_rate (FT drawn on made shots) and pts_ft_share (FT points fraction)
    as proxies for iso FT-draw rate. halfcourt_pts_share proxies vs-set-defense scoring.
    These fields are from a pre-built atlas parquet (no leak concern — already built
    with its own as_of boundary; we read the row as-is).
    """
    path = CACHE / "atlas_player_scoring_creation.parquet"
    df = _load("scoring_creation", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}

    row = rows.iloc[0]
    and_one = _rd(row.get("and_one_rate"))
    pts_ft_share = _rd(row.get("pts_ft_share"))
    halfcourt_share = _rd(row.get("halfcourt_pts_share"))
    transition_share = _rd(row.get("transition_pts_share"))

    # Enforce proportion bounds [0,1] per CRITICAL LESSON 3
    def _clamp01(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        return v if 0.0 <= v <= 1.0 else None

    return {
        "and_one_rate": _clamp01(and_one),
        "pts_ft_share": _clamp01(pts_ft_share),
        "halfcourt_pts_share": _clamp01(halfcourt_share),
        "transition_pts_share": _clamp01(transition_share),
    }


def _ft_draw_rate(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Per-game FT rate prediction (fta_per_36_q50) from ft_rate_predictions, <= as_of.

    Provides a model-based FT draw rate estimate. This is a per-game rate
    (FTA per 36 minutes) not a proportion, so it is not subject to [0,1] clamping.
    """
    path = INTEL / "ft_rate_predictions.parquet"
    df = _load("ft_rate_pred", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter via game_date (CRITICAL LESSON 5)
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n_rows = len(rows)
    fta_q50 = _rd(rows["fta_per_36_q50"].mean()) if "fta_per_36_q50" in rows.columns else None
    fta_q10 = _rd(rows["fta_per_36_q10"].mean()) if "fta_per_36_q10" in rows.columns else None
    fta_q90 = _rd(rows["fta_per_36_q90"].mean()) if "fta_per_36_q90" in rows.columns else None
    archetype = str(rows["archetype_name"].iloc[-1]) if "archetype_name" in rows.columns else None

    return {
        "fta_per_36_q50": fta_q50,
        "fta_per_36_q10": fta_q10,
        "fta_per_36_q90": fta_q90,
        "archetype_name": archetype,
        "n": n_rows,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerIsolationProfile(AtlasSection):
    """Deep player isolation-play atlas section (player entity, section='isolation_profile').

    Builds a provenance-stamped, leak-safe artifact covering isolation frequency,
    points per possession, FT-draw rate, vs-set-defense proxy, and late-clock iso
    rate. Reserves 2 CV slots for CV-branch enrichment (values None until filled).

    Sources used:
      - data/playtypes_2025-26.parquet + data/playtypes.parquet (iso freq_pct, ppp)
      - data/cache/pbp_possession_features.parquet (iso_poss_pg, late_clock_shots)
      - data/cache/atlas_player_scoring_creation.parquet (and_one_rate, pts_ft_share,
        halfcourt/transition_pts_share for vs-set-defense proxy)
      - data/intelligence/ft_rate_predictions.parquet (fta_per_36 model estimate)

    DEFER sections (no source parquet exists yet):
      - defender_quality — no per-matchup defensive-rating-by-play-type parquet
      - late_shot_ppp    — shot_clock_buckets uses player_name pkey not player_id
      - fg_pct_iso       — playtypes parquet has only freq_pct + ppp, not FGA/FGM
    """

    name: str = "isolation_profile"
    entity: str = "player"
    source_name: str = (
        "playtypes_2025-26.parquet + pbp_possession_features.parquet + "
        "atlas_player_scoring_creation.parquet + ft_rate_predictions.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the isolation_profile artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: pbp_possession_features and ft_rate_predictions are filtered
        to game_date <= as_of. Playtypes is season-keyed (pre-published season summary).
        atlas_player_scoring_creation was built with its own as_of boundary.

        Returns None when all sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        pt = _playtypes_iso(pid, as_of)
        pbp = _pbp_iso(pid, as_of)
        sc = _scoring_creation_iso(pid, as_of)
        ftr = _ft_draw_rate(pid, as_of)

        # Bail if nothing was populated
        if not pt and not pbp and not sc and not ftr:
            return None

        # --- frequency sub-dict ---
        frequency: Dict[str, Any] = {
            "iso_freq_pct": pt.get("iso_freq_pct"),
            "iso_ppp": pt.get("iso_ppp"),
            "iso_poss_per_game": pbp.get("iso_poss_per_game"),
            "_source_season": pt.get("_source_season"),
        }

        # --- efficiency sub-dict ---
        efficiency: Dict[str, Any] = {
            "iso_ppp": pt.get("iso_ppp"),
            "and_one_rate": sc.get("and_one_rate"),
            "pts_ft_share": sc.get("pts_ft_share"),
        }

        # --- ft_draw sub-dict ---
        ft_draw: Dict[str, Any] = {
            "fta_per_36_q50": ftr.get("fta_per_36_q50"),
            "fta_per_36_q10": ftr.get("fta_per_36_q10"),
            "fta_per_36_q90": ftr.get("fta_per_36_q90"),
            "archetype_name": ftr.get("archetype_name"),
        }

        # --- vs_set_defense sub-dict ---
        # halfcourt_pts_share = fraction of pts scored in halfcourt (set defense)
        # High value = player predominantly operates vs set defense (iso-friendly)
        vs_set_defense: Dict[str, Any] = {
            "halfcourt_pts_share": sc.get("halfcourt_pts_share"),
            "transition_pts_share": sc.get("transition_pts_share"),
            "_note": (
                "halfcourt_pts_share is scoring share vs set defense "
                "(non-transition). DEFER: per-play-type defensive rating by "
                "opponent not available."
            ),
        }

        # --- late_clock sub-dict ---
        late_clock: Dict[str, Any] = {
            "late_clock_shots_pg": pbp.get("late_clock_shots_pg"),
            "late_clock_iso_ratio": pbp.get("late_clock_iso_ratio"),
            "_note": (
                "late_clock_iso_ratio = late-clock shots / iso possessions "
                "(on games with iso > 0). DEFER: ppp on <7 s possessions "
                "(shot_clock_buckets pkey is player_name not player_id)."
            ),
        }

        # --- DEFER sections ---
        defender_quality: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-matchup defensive-rating-by-play-type parquet. "
                "Would require joining defender_matchups with play-type endpoints."
            ),
        }

        fg_pct_iso: Dict[str, Any] = {
            "_note": (
                "DEFER: playtypes parquet contains only freq_pct + ppp, "
                "not raw FGA/FGM; fg% on isolation attempts unavailable."
            ),
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "frequency": frequency,
            "efficiency": efficiency,
            "ft_draw": ft_draw,
            "vs_set_defense": vs_set_defense,
            "late_clock": late_clock,
            "defender_quality": defender_quality,
            "fg_pct_iso": fg_pct_iso,
        }

        # --- Determine n from actual game-row counts (CRITICAL LESSON 1) ---
        n_candidates: List[int] = []
        if pbp.get("n"):
            n_candidates.append(int(pbp["n"]))
        if ftr.get("n"):
            n_candidates.append(int(ftr["n"]))
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
            value=pt.get("iso_freq_pct"),  # headline: isolation usage rate
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present, proportions in [0,1].

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "frequency", "efficiency", "ft_draw",
            "vs_set_defense", "late_clock",
            "defender_quality", "fg_pct_iso",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sanity-check proportion fields stay in [0,1]
        freq = sf.get("frequency", {})
        v = freq.get("iso_freq_pct")
        if v is not None and not (0.0 <= v <= 1.0):
            return False

        for share_key in ["halfcourt_pts_share", "transition_pts_share"]:
            v = sf.get("vs_set_defense", {}).get(share_key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        eff = sf.get("efficiency", {})
        for rate_key in ["and_one_rate", "pts_ft_share"]:
            v = eff.get(rate_key)
            if v is not None and not (0.0 <= v <= 1.0):
                return False

        # CV fields must be reserved (null)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for isolation_profile (values None until CV fills).

        Slots: defender_distance_iso (mean defender proximity at iso shot release)
               blow_by_rate (fraction of iso possessions where ball-handler beats
               the primary defender off the dribble before shooting).
        """
        return {
            "defender_distance_iso": CVSlot(
                name="defender_distance_iso",
                dtype="float",
                description=(
                    "Mean nearest-defender distance (ft) at shot release on "
                    "CV-tagged isolation possessions, from homography coordinates "
                    "and EventDetector play-type classification."
                ),
                unit="ft",
                value=None,
            ),
            "blow_by_rate": CVSlot(
                name="blow_by_rate",
                dtype="float",
                description=(
                    "Fraction of isolation possessions (per CV EventDetector) "
                    "where the ball-handler beats the primary defender off the "
                    "dribble before shooting or drawing contact."
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
    """Build isolation_profile for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int). If None, discovers from playtypes.
        as_of:      leak boundary date (defaults to today).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        for path_key, path in [
            ("pt26_disc", DATA / "playtypes_2025-26.parquet"),
            ("pt_disc", DATA / "playtypes.parquet"),
        ]:
            df = _load(path_key, path)
            if df is not None and not df.empty and "player_id" in df.columns:
                player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
                break
        if player_ids is None:
            player_ids = []

    section = PlayerIsolationProfile()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
