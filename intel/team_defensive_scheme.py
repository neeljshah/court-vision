"""ARM-B atlas section: ``defensive_scheme`` — exhaustive per-team defensive profile.

Implements :class:`AtlasSection` for the ``"defensive_scheme"`` section of a team's
persistent profile.  Every sub-field below comes from existing parquets/JSON listed in
spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from existing parquets/JSON):
  coverage_scheme.*    — drop_score, dominant_tag, all_tags, thematic scheme label
                         (DROP COVERAGE / SWITCH HEAVY / PAINT-FIRST / PERIMETER DENIAL
                         / PACE CONTROL / ISO FORCE / HELP DEFENSE / ACTIVE CLOSEOUTS)
                         from data/intelligence/defensive_schemes.parquet
                         + data/intelligence/scheme_indicators.json (axis scores, tags,
                           imposed_deviations, interpretation, confidence).
  rim_protection.*     — opp_paint_pct_allowed_z, opp_3pt_pct_allowed_z,
                         opp_mid_pct_allowed_z, opp_paint_dwell_pct_allowed_z,
                         opp_shot_mix_deviation_z (latest game_date <= as_of, high-n
                         window) from data/intelligence/opp_paint_allowance.parquet.
  perimeter_pressure.* — opp_contested_shot_rate_imposed_z,
                         opp_avg_defender_distance_imposed_z,
                         opp_catch_shoot_allowed_pct_z, opp_closeout_speed_imposed_z,
                         opp_pace_imposed_z, opp_defensive_intensity_z
                         from data/intelligence/opp_defensive_intensity.parquet
                         (latest game_date <= as_of).
  scheme_axes.*        — raw scheme-indicator axis scores (drop_score,
                         paint_protection_score, perimeter_denial_score,
                         pace_control_score, iso_force_score, closeout_score,
                         quality_z, quality_correction, n_opposing_player_games,
                         n_unique_opponents) from defensive_schemes.parquet and
                         scheme_indicators.json.
  imposed_deviations.* — CV-derived opponent-imposed z-score deviations across
                         ~23 tracked metrics (potential_assists, avg_spacing,
                         contested_shot_rate, avg_defender_distance, etc.) from
                         scheme_indicators.json["teams"][tricode]["imposed_deviations"].
  top_impact_players.* — list of top-5 players most deviated by this team's scheme,
                         from scheme_indicators.json["teams"][tricode]["top_players"].
  ratings_context.*    — team def_rtg + pace (season average) for contextualising
                         scheme intensity, from data/team_advanced_stats.parquet
                         filtered to game_date <= as_of.

DEFER (data gap — not available in current parquets):
  zone_usage.*         — fraction of possessions played in zone vs man-to-man
                         DEFER: no possession-level defense-type annotation in repo;
                         would require PBP zone-call tagging or Synergy defense API.
  blitz_coverage.*     — pick-and-roll blitz/hedge rate per possession
                         DEFER: no PBP PKR defensive assignment parquet; requires
                         Synergy PKR defense or manual PBP parsing.
  switch_rate.*        — fraction of screens resulting in a defensive switch
                         DEFER: no per-possession screen-tracking annotation available
                         (CV switch_rate_measured reserved as a CV slot below).

RESERVED CV SLOTS (value=None, CV branch fills later):
  avg_contest          — mean contest level imposed on opposing shooters (fraction
                         of opponent shots defended within 4 ft), from CV EventDetector
                         + homography.
  switch_rate_measured — fraction of defensive possessions in which a switch occurred,
                         measured from CV player-pair proximity at screen frame.
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
INTEL = DATA / "intelligence"
CACHE = DATA / "cache"

# ---------------------------------------------------------------------------
# Module-level lazy data cache (one load per process per path)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Any] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _load_json(key: str, path: Path) -> Optional[Any]:
    """Load a JSON file once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            if path.exists():
                with path.open(encoding="utf-8") as fh:
                    _SRC_CACHE[key] = json.load(fh)
            else:
                _SRC_CACHE[key] = None
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
    """Clean integer scalar: NaN/inf -> None, numpy -> python int."""
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
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _scheme_from_parquet(tricode: str) -> Dict[str, Any]:
    """Return scheme row from defensive_schemes.parquet for the given team tricode.

    Source: data/intelligence/defensive_schemes.parquet.
    Columns used: drop_score, paint_protection_score, perimeter_denial_score,
    pace_control_score, iso_force_score, closeout_score, perimeter_denial_raw,
    quality_z, quality_correction, n_opposing_player_games, n_unique_opponents,
    confidence, dominant_tag, all_tags.
    """
    df = _load_parquet("def_schemes", INTEL / "defensive_schemes.parquet")
    if df is None or df.empty:
        return {}
    row_df = df[df["team"] == tricode]
    if row_df.empty:
        return {}
    row = row_df.iloc[0]
    return {
        "drop_score": _rd(row.get("drop_score")),
        "paint_protection_score": _rd(row.get("paint_protection_score")),
        "perimeter_denial_score": _rd(row.get("perimeter_denial_score")),
        "pace_control_score": _rd(row.get("pace_control_score")),
        "iso_force_score": _rd(row.get("iso_force_score")),
        "closeout_score": _rd(row.get("closeout_score")),
        "perimeter_denial_raw": _rd(row.get("perimeter_denial_raw")),
        "quality_z": _rd(row.get("quality_z")),
        "quality_correction": _rd(row.get("quality_correction")),
        "n_opposing_player_games": _ri(row.get("n_opposing_player_games")),
        "n_unique_opponents": _ri(row.get("n_unique_opponents")),
        "confidence_src": str(row.get("confidence", "low")),
        "dominant_tag": str(row.get("dominant_tag", "")) if row.get("dominant_tag") else None,
        "all_tags": str(row.get("all_tags", "")) if row.get("all_tags") else None,
    }


def _scheme_indicators(tricode: str) -> Dict[str, Any]:
    """Return per-team scheme indicators from scheme_indicators.json.

    Source: data/intelligence/scheme_indicators.json["teams"][tricode].
    Returns imposed_deviations dict, top_players list, tags, interpretation.
    """
    doc = _load_json("scheme_indicators", INTEL / "scheme_indicators.json")
    if not doc or not isinstance(doc, dict):
        return {}
    teams = doc.get("teams", {})
    if tricode not in teams:
        return {}
    t = teams[tricode]
    return {
        "tags": list(t.get("tags", [])),
        "dominant_tag": t.get("dominant_tag"),
        "axes": {k: _rd(v) for k, v in (t.get("axes") or {}).items()},
        "imposed_deviations": {
            k: _rd(v) for k, v in (t.get("imposed_deviations") or {}).items()
        },
        "top_players": list(t.get("top_players", [])),
        "interpretation": t.get("interpretation"),
        "n_player_games": _ri(t.get("n_player_games")),
        "n_unique_opponents": _ri(t.get("n_unique_opponents")),
        "confidence_src": t.get("confidence", "low"),
    }


def _rim_protection(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Rim protection profile from opp_paint_allowance.parquet, filtered to <= as_of.

    Selects the highest-n_games_window snapshot with game_date <= as_of.
    Source: data/intelligence/opp_paint_allowance.parquet.
    """
    df = _load_parquet("opp_paint", INTEL / "opp_paint_allowance.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_id"] == tricode].copy()
    if rows.empty:
        return {}
    # Filter to game_date <= as_of (LEAK GUARD)
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}
    # Pick the snapshot with the largest n_games_window (most data, freshest roll)
    if "n_games_window" in rows.columns:
        rows = rows.sort_values("n_games_window", ascending=False)
    row = rows.iloc[0]
    return {
        "opp_paint_pct_allowed_z": _rd(row.get("opp_paint_pct_allowed_z")),
        "opp_3pt_pct_allowed_z": _rd(row.get("opp_3pt_pct_allowed_z")),
        "opp_mid_pct_allowed_z": _rd(row.get("opp_mid_pct_allowed_z")),
        "opp_paint_dwell_pct_allowed_z": _rd(row.get("opp_paint_dwell_pct_allowed_z")),
        "opp_shot_mix_deviation_z": _rd(row.get("opp_shot_mix_deviation_z")),
        "n_games_window": _ri(row.get("n_games_window")),
        "data_density": str(row.get("data_density", "")) if row.get("data_density") else None,
        "_as_of_src": str(row.get("game_date", ""))[:10] if "game_date" in row.index else None,
    }


def _perimeter_pressure(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Perimeter pressure profile from opp_defensive_intensity.parquet, filtered to <= as_of.

    Selects the highest-n_games_window snapshot with game_date <= as_of.
    Source: data/intelligence/opp_defensive_intensity.parquet.
    """
    df = _load_parquet("opp_def_int", INTEL / "opp_defensive_intensity.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_id"] == tricode].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}
    if "n_games_window" in rows.columns:
        rows = rows.sort_values("n_games_window", ascending=False)
    row = rows.iloc[0]
    return {
        "opp_contested_shot_rate_imposed_z": _rd(row.get("opp_contested_shot_rate_imposed_z")),
        "opp_avg_defender_distance_imposed_z": _rd(row.get("opp_avg_defender_distance_imposed_z")),
        "opp_paint_attempts_allowed_pct_z": _rd(row.get("opp_paint_attempts_allowed_pct_z")),
        "opp_pace_imposed_z": _rd(row.get("opp_pace_imposed_z")),
        "opp_catch_shoot_allowed_pct_z": _rd(row.get("opp_catch_shoot_allowed_pct_z")),
        "opp_closeout_speed_imposed_z": _rd(row.get("opp_closeout_speed_imposed_z")),
        "opp_defensive_intensity_z": _rd(row.get("opp_defensive_intensity_z")),
        "n_games_window": _ri(row.get("n_games_window")),
        "data_density": str(row.get("data_density", "")) if row.get("data_density") else None,
        "_as_of_src": str(row.get("game_date", ""))[:10] if "game_date" in row.index else None,
    }


def _ratings_context(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-aggregate defensive ratings from team_advanced_stats.parquet, <= as_of.

    Source: data/team_advanced_stats.parquet.
    Provides def_rtg and pace as context for interpreting scheme intensity.
    """
    df = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_tricode"] == tricode].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}
    n = len(rows)
    means = rows[[c for c in ["def_rtg", "pace", "oreb_pct", "dreb_pct"] if c in rows.columns]].mean()
    return {
        "def_rtg": _rd(means.get("def_rtg")),
        "pace": _rd(means.get("pace")),
        "oreb_pct": _rd(means.get("oreb_pct")),
        "dreb_pct": _rd(means.get("dreb_pct")),
        "n_games": n,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamDefensiveScheme(AtlasSection):
    """Deep team defensive scheme atlas section (team entity, section='defensive_scheme').

    Builds a provenance-stamped, leak-safe artifact covering:
      - coverage_scheme: dominant scheme tag + axis scores (drop/switch/blitz/zone themes)
      - scheme_axes:     raw indicator axis scores (drop/paint/perimeter/pace/iso/closeout)
      - imposed_deviations: CV-derived z-deviations the team imposes on opponents
      - rim_protection:  shot-zone mix (paint/3pt/mid) opponent allowances vs league avg
      - perimeter_pressure: contested-shot-rate, defender-distance, pace, closeout speed
      - ratings_context: def_rtg + pace for intensity context
      - top_impact_players: players most affected by this team's scheme
      - zone_usage, blitz_coverage, switch_rate: DEFER (no PBP/Synergy defense type data)

    Reserves 2 CV slots:
      avg_contest       — CV-measured opponent shot contest rate
      switch_rate_measured — CV-measured defensive switch rate at screens

    Sources:
      - data/intelligence/defensive_schemes.parquet (scheme scores + tags, 30 teams)
      - data/intelligence/scheme_indicators.json (detailed imposed deviations, per team)
      - data/intelligence/opp_paint_allowance.parquet (rim protection, game_date keyed)
      - data/intelligence/opp_defensive_intensity.parquet (perimeter pressure, game_date keyed)
      - data/team_advanced_stats.parquet (def_rtg/pace, game_date keyed)

    DEFER sections (no source data currently available):
      - zone_usage:       possession-level zone vs man annotation not in repo
      - blitz_coverage:   PBP PKR defensive assignment not available
      - switch_rate:      per-possession screen-tracking annotation not available
                          (reserved as CV slot switch_rate_measured)
    """

    name: str = "defensive_scheme"
    entity: str = "team"
    source_name: str = (
        "defensive_schemes.parquet + scheme_indicators.json + "
        "opp_paint_allowance.parquet + opp_defensive_intensity.parquet + "
        "team_advanced_stats.parquet"
    )
    conf_cap: Optional[str] = None  # CV slots capped separately via fill_cv_slot

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the defensive_scheme artifact for team ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - opp_paint_allowance and opp_defensive_intensity are filtered to
            game_date <= as_of before aggregation.
          - team_advanced_stats is filtered to game_date <= as_of.
          - defensive_schemes.parquet and scheme_indicators.json are season-level
            summaries with no game_date column; accepted as pre-published season
            aggregates (same treatment as playtypes/tracking in player_shot_profile).

        Args:
            entity_id: team tricode string (e.g. "BOS", "LAL").
            as_of:     datetime representing the decision boundary (leak cutoff).

        Returns:
            AtlasArtifact with populated sub_fields and reserved cv_fields,
            or None if no source has data for this team.
        """
        tricode = str(entity_id).upper().strip()
        as_of_str = as_of.date().isoformat()

        # Gather all sub-components
        scheme_pq = _scheme_from_parquet(tricode)
        scheme_ind = _scheme_indicators(tricode)
        rim = _rim_protection(tricode, as_of)
        perimeter = _perimeter_pressure(tricode, as_of)
        ratings = _ratings_context(tricode, as_of)

        # Bail if nothing populated (team absent from all sources)
        all_empty = (
            not scheme_pq and not scheme_ind and not rim
            and not perimeter and not ratings
        )
        if all_empty:
            return None

        # --- coverage_scheme: dominant theme, all tags, thematic description ---
        dominant_tag = (
            scheme_ind.get("dominant_tag")
            or scheme_pq.get("dominant_tag")
        )
        all_tags_str = scheme_pq.get("all_tags") or ""
        all_tags_list = [t.strip() for t in all_tags_str.split("|") if t.strip()]
        tags_from_ind = scheme_ind.get("tags") or []
        merged_tags = list(dict.fromkeys(tags_from_ind + all_tags_list))  # dedup, preserve order

        coverage_scheme: Dict[str, Any] = {
            "dominant_tag": dominant_tag,
            "all_tags": merged_tags,
            "n_scheme_tags": len(merged_tags),
            "interpretation": scheme_ind.get("interpretation"),
            # Drop vs switch is encoded as drop_score sign:
            # positive = drop coverage tendency, negative = switch/hedge tendency
            "drop_vs_switch": (
                "drop" if (scheme_pq.get("drop_score") or 0.0) > 0.10
                else "switch" if (scheme_pq.get("drop_score") or 0.0) < -0.10
                else "mixed"
            ),
            # Zone usage and blitz rate DEFERRED
            "zone_usage": {
                "_note": (
                    "DEFER: no possession-level defense-type annotation in repo. "
                    "Requires PBP zone-call tagging or Synergy defense API."
                )
            },
            "blitz_coverage": {
                "_note": (
                    "DEFER: no PBP PKR defensive-assignment parquet. "
                    "Requires Synergy PKR defense or manual PBP parsing."
                )
            },
        }

        # --- scheme_axes: raw indicator scores from both sources ---
        axes_from_ind = scheme_ind.get("axes") or {}
        scheme_axes: Dict[str, Any] = {
            "drop_score": scheme_pq.get("drop_score") or axes_from_ind.get("drop_score"),
            "paint_protection_score": (
                scheme_pq.get("paint_protection_score")
                or axes_from_ind.get("paint_protection_score")
            ),
            "perimeter_denial_score": (
                scheme_pq.get("perimeter_denial_score")
                or axes_from_ind.get("perimeter_denial_score")
            ),
            "pace_control_score": (
                scheme_pq.get("pace_control_score")
                or axes_from_ind.get("pace_control_score")
            ),
            "iso_force_score": (
                scheme_pq.get("iso_force_score")
                or axes_from_ind.get("iso_force_score")
            ),
            "closeout_score": (
                scheme_pq.get("closeout_score")
                or axes_from_ind.get("closeout_score")
            ),
            "perimeter_denial_raw": (
                scheme_pq.get("perimeter_denial_raw")
                or axes_from_ind.get("perimeter_denial_raw")
            ),
            "quality_z": (
                scheme_pq.get("quality_z")
                or axes_from_ind.get("quality_z")
            ),
            "quality_correction": (
                scheme_pq.get("quality_correction")
                or axes_from_ind.get("quality_correction")
            ),
            "n_opposing_player_games": (
                scheme_pq.get("n_opposing_player_games")
                or scheme_ind.get("n_player_games")
            ),
            "n_unique_opponents": (
                scheme_pq.get("n_unique_opponents")
                or scheme_ind.get("n_unique_opponents")
            ),
        }

        # --- imposed_deviations: z-score deviations imposed on opponents ---
        imposed_deviations: Dict[str, Any] = dict(
            scheme_ind.get("imposed_deviations") or {}
        )

        # --- top_impact_players: players most deviated by this team's scheme ---
        top_impact_players: List[Any] = list(
            scheme_ind.get("top_players") or []
        )

        # --- DEFER sub-sections ---
        switch_rate_subfield: Dict[str, Any] = {
            "_note": (
                "DEFER: per-possession screen-tracking annotation not available. "
                "Measured switch_rate reserved as a CV slot (switch_rate_measured)."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "coverage_scheme": coverage_scheme,
            "scheme_axes": scheme_axes,
            "imposed_deviations": imposed_deviations,
            "rim_protection": rim,
            "perimeter_pressure": perimeter,
            "ratings_context": ratings,
            "top_impact_players": top_impact_players,
            "switch_rate": switch_rate_subfield,
        }

        # --- Determine n: best game-count available ---
        n_candidates: List[int] = []
        if scheme_pq.get("n_opposing_player_games"):
            n_candidates.append(int(scheme_pq["n_opposing_player_games"]))
        if scheme_ind.get("n_player_games"):
            n_candidates.append(int(scheme_ind["n_player_games"]))
        if ratings.get("n_games"):
            n_candidates.append(int(ratings["n_games"]))
        if perimeter.get("n_games_window"):
            n_candidates.append(int(perimeter["n_games_window"]))
        n = max(n_candidates) if n_candidates else 1

        # Determine confidence from the scheme parquet (already computed) or from n
        src_conf = (
            scheme_pq.get("confidence_src")
            or scheme_ind.get("confidence_src")
            or "low"
        )
        # Map the source confidence string and re-validate against n
        conf_from_n_val = confidence_from_n(n, cap=self.conf_cap)
        # Take the higher of source-provided confidence and n-derived confidence
        _CONF_ORDER = {"low": 0, "med": 1, "high": 2}
        confidence = (
            src_conf
            if _CONF_ORDER.get(str(src_conf), 0) >= _CONF_ORDER.get(conf_from_n_val, 0)
            else conf_from_n_val
        )

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=dominant_tag,  # headline: dominant scheme tag
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, axis scores plausible.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {
            "coverage_scheme", "scheme_axes", "imposed_deviations",
            "rim_protection", "perimeter_pressure", "ratings_context",
            "top_impact_players", "switch_rate",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Axis scores should be in a sane range (z-scores and scheme-axes, not pct)
        axes = sf.get("scheme_axes", {})
        for key in [
            "drop_score", "paint_protection_score", "perimeter_denial_score",
            "pace_control_score", "iso_force_score", "closeout_score",
        ]:
            v = axes.get(key)
            if v is not None and not (-5.0 <= v <= 5.0):
                return False

        # coverage_scheme must have dominant_tag and all_tags
        cs = sf.get("coverage_scheme", {})
        if "dominant_tag" not in cs or "all_tags" not in cs:
            return False

        # CV fields: all values must be None (CV branch hasn't run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for defensive_scheme (values None — CV branch fills later).

        The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "defensive_scheme", slot, as_of, value)``
        to populate these WITHOUT a profile rebuild.

        Slots are the two named in the task spec:
          avg_contest       — average contest level imposed on opponents (fraction)
          switch_rate_measured — defensive switch rate at screens (fraction)
        """
        return {
            "avg_contest": CVSlot(
                name="avg_contest",
                dtype="float",
                description=(
                    "Mean fraction of opposing shot attempts defended within 4 ft "
                    "(contested), measured by CV EventDetector + homography proximity "
                    "at release frame across all tracked home-and-away games."
                ),
                unit=None,
                value=None,
            ),
            "switch_rate_measured": CVSlot(
                name="switch_rate_measured",
                dtype="float",
                description=(
                    "Fraction of defensive possessions in which a switch occurred, "
                    "measured from CV player-pair proximity at screen-set frames; "
                    "operationalised as the fraction of frames where a defensive pair "
                    "exchanges guarded-player assignments within 0.5s of screen contact."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    team_tricodes: Optional[List[str]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build defensive_scheme for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of 3-letter team tricodes.  If None, discovers from
                       defensive_schemes.parquet (all 30 teams).
        as_of:        leak boundary date (defaults to today midnight UTC).
        store:        PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:      skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        df = _load_parquet("def_schemes", INTEL / "defensive_schemes.parquet")
        if df is not None and not df.empty and "team" in df.columns:
            team_tricodes = sorted(df["team"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamDefensiveScheme()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
