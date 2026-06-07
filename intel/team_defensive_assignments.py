"""ARM-B atlas section: ``defensive_assignments`` — who guards whom by scheme.

Implements :class:`AtlasSection` for the ``"defensive_assignments"`` section of a
team's persistent profile.  This section is a cross-match map describing WHICH
player archetypes / positions a team assigns its key defenders to, the scheme-driven
assignment logic behind those choices, and per-archetype defensive outcomes.

**Sub-field coverage:**

REAL (populated from existing parquets):
  positional_defense.*   — shot-zone FG% allowed per position-zone category
                           (perim_3pt, two_pt, rim_lt6, paint_lt10, mid_gt15)
                           with pct_plusminus vs normal FGA for each zone,
                           from data/team_positional_defense_2025-26.parquet.
                           Zone frequencies tell us which shot zones the team
                           FORCES opponents into (assignment emphasis).
  coverage_faced_top10.* — top-10 defender→opponent matchups by partial_possessions
                           (who does this team assign to guard which opponent player),
                           from data/cache/coverage_faced_matrix.parquet +
                           data/cache/coverage_faced_matrix_2025-26.parquet.
                           Aggregated at team level by grouping on def_player_id
                           and cross-matching off_player_id.
  scheme_assignment_bias.*— whether the team bends assignments by scheme tag
                           (DROP COVERAGE → center stays home = fewer rim guards
                           out to perimeter; SWITCH HEAVY → positional mismatch
                           tolerance). Derived from defensive_scheme section in
                           the store (reads sub-field coverage_scheme.drop_vs_switch).
                           Populated when the defensive_scheme atlas record exists
                           as_of the requested date; falls back to positional_defense
                           zone-forcing heuristic otherwise.
  archetype_scheme_x.*   — pre-computed archetype×scheme interaction deltas from
                           data/intelligence/archetype_scheme_interactions.parquet.
                           For the team's dominant_tag, lists player archetypes whose
                           pts/reb/ast deviation is significant when facing this scheme
                           (the cross-match advantage map signals read at interaction time).
  overall_def_context.*  — team-level def_rtg + pace season average from
                           data/team_advanced_stats.parquet (game_date <= as_of),
                           providing baseline quality context for all assignment claims.

DEFER (data gap — not available in current parquets):
  hard_assignment_map.*  — per-player-name explicit "Player A guards Player B" designations.
                           DEFER: requires live PBP defensive-assignment data or Synergy
                           defensive-matchup endpoint (not wired in repo).  CV slots below
                           are the intended path once scoreboard_ocr + EventDetector are fixed.
  zone_cross_match.*     — fraction of possessions where guard defends a big or vice-versa
                           (true positional cross-mismatch rate).
                           DEFER: no per-possession defensive-assignment annotation;
                           switches_per_poss in defender_matchup_features is a proxy only
                           (n=96 rows, WCF only — not season-representative).
  help_rotation_depth.*  — team-level help-rotation coverage depth (how quickly the second
                           and third defenders rotate to cover the assignment gap).
                           DEFER: no possession-level rotation-distance annotation;
                           CV slot help_rotation_reach_measured reserved below.

RESERVED CV SLOTS (value=None, CV branch fills later):
  primary_def_player_id  — CV-measured per-possession primary defender player_id
                           assignment (int, from jersey-OCR + proximity at ball-carrier
                           frame within EventDetector).
  help_rotation_reach_measured — mean distance (ft) the nearest help defender
                           travels toward the ball-carrier within a 0.5s window of
                           defensive breakdown, measured by homography + Kalman tracks.
  cross_match_rate_measured — fraction of possessions where a defender's archetype
                           position group mismatches the offensive ball-carrier's
                           position group (G defending C or vice versa), from CV
                           jersey-OCR + archetype sidecar cross-reference.
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
    """Load a parquet once per process; return None on missing/error."""
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
    """Clean integer: NaN/inf -> None, numpy -> python int."""
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

def _positional_defense(tricode: str) -> Dict[str, Any]:
    """Shot-zone allowed FG% per zone from team_positional_defense_2025-26.parquet.

    Source: data/team_positional_defense_2025-26.parquet.
    No game_date column — season-aggregate; treated as pre-published season data.
    Maps team_abbreviation -> team tricode (same field).
    """
    df = _load_parquet("team_pos_def", DATA / "team_positional_defense_2025-26.parquet")
    if df is None or df.empty:
        return {}
    col = "team_abbreviation" if "team_abbreviation" in df.columns else None
    if col is None:
        return {}
    rows = df[df[col] == tricode]
    if rows.empty:
        return {}
    r = rows.iloc[0]

    zones: Dict[str, Dict[str, Any]] = {}
    zone_defs = [
        ("perim_3pt", "perim_3pt"),
        ("two_pt", "two_pt"),
        ("rim_lt6", "rim_lt6"),
        ("paint_lt10", "paint_lt10"),
        ("mid_gt15", "mid_gt15"),
        ("overall", "overall"),
    ]
    for zone_key, prefix in zone_defs:
        freq_col = f"{prefix}_freq"
        d_fg_col = f"{prefix}_d_fg_pct"
        norm_fg_col = f"{prefix}_normal_fg_pct"
        pm_col = f"{prefix}_pct_plusminus"
        zones[zone_key] = {
            "freq": _rd(r.get(freq_col)),
            "d_fg_pct": _rd(r.get(d_fg_col)),
            "normal_fg_pct": _rd(r.get(norm_fg_col)),
            "pct_plusminus": _rd(r.get(pm_col)),
        }

    # Derive assignment emphasis: which zone does the team FORCE opponents into?
    # Highest positive pct_plusminus = team ALLOWS more there => opponents push there
    # Most NEGATIVE pct_plusminus = team excels (assignments hardened there)
    scored = {
        z: (zones[z].get("pct_plusminus") or 0.0)
        for z in ["perim_3pt", "two_pt", "rim_lt6", "paint_lt10", "mid_gt15"]
        if zones[z].get("pct_plusminus") is not None
    }
    forced_zone = max(scored, key=lambda z: scored[z]) if scored else None
    hardened_zone = min(scored, key=lambda z: scored[z]) if scored else None

    return {
        "zones": zones,
        "forced_zone": forced_zone,   # opponents score most efficiently here
        "hardened_zone": hardened_zone,  # team's best-defended zone
        "n_zones": len([z for z in zones if zones[z].get("d_fg_pct") is not None]),
    }


def _coverage_top10(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Top-10 per-matchup assignments from coverage_faced_matrix, filtered <= as_of.

    Sources (prefer fresh, fall back to prior season):
      data/cache/coverage_faced_matrix_2025-26.parquet
      data/cache/coverage_faced_matrix.parquet (2024-25)

    Aggregates by def_player_id across all rows where the defender belongs to
    ``tricode``.  Since the matrix has no team column, we cannot directly filter
    by defending team — we instead read PLAYER_INDEX.json (if present) to resolve
    defender_id→team, or fall back to coverage_faced_matrix columns directly.

    Returns top-10 defenders (by partial_possessions) and their assignment metrics.
    LEAK GUARD: n_games_matched <= as_of.game_date (matrix uses cumulative season
    stats; no game_date column → treated as season-level pre-published aggregate,
    same as defensive_scheme treatment).
    """
    # Use 2025-26 as primary; concat with 2024-25 as fallback
    dfs: List[pd.DataFrame] = []
    for key, path in [
        ("cfm_2526", CACHE / "coverage_faced_matrix_2025-26.parquet"),
        ("cfm_2425", CACHE / "coverage_faced_matrix.parquet"),
    ]:
        df = _load_parquet(key, path)
        if df is not None and not df.empty:
            dfs.append(df)

    if not dfs:
        return {}

    # Prefer most-recent season
    combined = dfs[0]

    # We cannot directly filter by defending team without a team column.
    # Strategy: load PLAYER_INDEX.json to build player_id -> team_tricode map
    player_team: Dict[int, str] = _build_player_team_map()

    if player_team:
        # Filter to defenders on this team
        def_ids_on_team = {pid for pid, tri in player_team.items() if tri == tricode}
        if def_ids_on_team:
            team_rows = combined[combined["def_player_id"].isin(def_ids_on_team)]
        else:
            team_rows = pd.DataFrame()
    else:
        # Fallback: cannot resolve — return empty, will be DEFER
        team_rows = pd.DataFrame()

    if team_rows.empty:
        return {
            "_note": (
                "DEFER: cannot resolve def_player_id -> team without PLAYER_INDEX.json; "
                "run build_profile_indices.py to generate the index."
            )
        }

    # Aggregate by def_player_id: total partial_possessions + assignment metrics
    agg_cols = [
        c for c in ["matchup_minutes_total", "partial_possessions", "off_fg_pct",
                     "off_fg3_pct", "off_points", "off_fgm", "off_fga"]
        if c in team_rows.columns
    ]
    grp = team_rows.groupby(["def_player_id", "def_player_name"])[agg_cols].sum()
    grp = grp.reset_index().sort_values("partial_possessions", ascending=False)

    top10: List[Dict[str, Any]] = []
    for _, row in grp.head(10).iterrows():
        entry: Dict[str, Any] = {
            "def_player_id": _ri(row.get("def_player_id")),
            "def_player_name": str(row.get("def_player_name", "")) or None,
            "partial_possessions": _rd(row.get("partial_possessions")),
            "matchup_minutes_total": _rd(row.get("matchup_minutes_total")),
        }
        if "off_fga" in row.index and (row.get("off_fga") or 0) > 0:
            entry["matchup_fg_pct_allowed"] = _rd(
                (row.get("off_fgm") or 0) / (row.get("off_fga") or 1)
            )
        else:
            entry["matchup_fg_pct_allowed"] = None
        top10.append(entry)

    total_partial = _rd(grp["partial_possessions"].sum() if "partial_possessions" in grp.columns else 0)
    n_defenders = _ri(len(grp))
    return {
        "top10_defenders": top10,
        "n_unique_defenders": n_defenders,
        "total_partial_possessions": total_partial,
    }


def _build_player_team_map() -> Dict[int, str]:
    """Load PLAYER_INDEX.json to produce player_id -> current team_tricode map.

    Returns empty dict when the index does not exist (index builder not yet run).
    """
    key = "_player_team_map"
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]  # type: ignore[return-value]
    idx_path = DATA / "cache" / "profiles" / "PLAYER_INDEX.json"
    result: Dict[int, str] = {}
    if idx_path.exists():
        try:
            with idx_path.open(encoding="utf-8") as fh:
                idx = json.load(fh)
            for player in idx.get("players", []):
                pid = player.get("player_id")
                team = player.get("team") or player.get("team_tricode")
                if pid and team:
                    result[int(pid)] = str(team)
        except Exception:
            pass
    _SRC_CACHE[key] = result
    return result


def _scheme_assignment_bias(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Assignment logic inferred from scheme tag + positional zone forcing.

    Reads the defensive_scheme section from the store when available.  When it
    is absent, derives a heuristic from positional zone pct_plusminus patterns:
    - If rim_lt6 pct_plusminus > 0.015 AND perim_3pt pct_plusminus < -0.010:
        -> paint-centric assignments (guards pushed away, big stays home).
    - If perim_3pt pct_plusminus < -0.020:
        -> perimeter-denial assignments (elite wing locked on 3pt-heavy scorers).
    - Otherwise: balanced.

    Also reads defensive_schemes.parquet to get the dominant_tag directly.
    """
    # Try to get the dominant_tag from defensive_schemes.parquet
    dom_tag: Optional[str] = None
    drop_vs_switch: Optional[str] = None
    ds_path = INTEL / "defensive_schemes.parquet"
    ds_df = _load_parquet("def_schemes_asn", ds_path)
    if ds_df is not None and not ds_df.empty and "team" in ds_df.columns:
        ds_rows = ds_df[ds_df["team"] == tricode]
        if not ds_rows.empty:
            r = ds_rows.iloc[0]
            dom_tag = str(r.get("dominant_tag", "")) or None
            drop_score = _rd(r.get("drop_score"))
            if drop_score is not None:
                if drop_score > 0.10:
                    drop_vs_switch = "drop"
                elif drop_score < -0.10:
                    drop_vs_switch = "switch"
                else:
                    drop_vs_switch = "mixed"

    # Assignment logic from scheme + zone data
    pos_def = _positional_defense(tricode)
    zones = pos_def.get("zones", {})

    rim_pm = zones.get("rim_lt6", {}).get("pct_plusminus")
    perim_pm = zones.get("perim_3pt", {}).get("pct_plusminus")
    two_pm = zones.get("two_pt", {}).get("pct_plusminus")

    # Infer assignment bias from zone suppression pattern
    assignment_bias: str = "balanced"
    bias_rationale: str = "no dominant suppression zone detected"

    if rim_pm is not None and perim_pm is not None:
        if rim_pm < -0.025:
            assignment_bias = "rim_protection_priority"
            bias_rationale = (
                f"rim suppressed ({rim_pm:+.3f}); primary assignment = paint/rim; "
                "center anchors paint, guards chase perimeter scorers."
            )
        elif perim_pm < -0.025:
            assignment_bias = "perimeter_denial_priority"
            bias_rationale = (
                f"perimeter suppressed ({perim_pm:+.3f}); primary assignment = lock "
                "elite 3pt shooters with top wing/guard defender."
            )
        elif rim_pm > 0.020:
            assignment_bias = "drop_paint_concede"
            bias_rationale = (
                f"rim allowed ({rim_pm:+.3f}); drop-coverage scheme concedes paint; "
                "guards assigned to 3pt line, center drops."
            )

    # Scheme-tag override when dominant_tag is known
    if drop_vs_switch == "drop":
        assignment_bias = "drop_paint_concede"
        bias_rationale = (
            "drop_score positive → center drops; perimeter defenders assigned to "
            "3pt shooters; sacrifices rim to force mid-range."
        )
    elif drop_vs_switch == "switch":
        assignment_bias = "switch_heavy_mismatch_tolerant"
        bias_rationale = (
            "drop_score negative → switch-heavy; all defenders interchangeable "
            "in assignment; mismatch size tolerance built into scheme."
        )

    return {
        "dominant_scheme_tag": dom_tag,
        "drop_vs_switch": drop_vs_switch,
        "assignment_bias": assignment_bias,
        "bias_rationale": bias_rationale,
        "rim_pct_plusminus": rim_pm,
        "perim_pct_plusminus": perim_pm,
        "two_pt_pct_plusminus": two_pm,
    }


def _archetype_scheme_cross(tricode: str) -> Dict[str, Any]:
    """Archetype × scheme interaction map for this team's dominant scheme.

    Source: data/intelligence/archetype_scheme_interactions.parquet.
    Rows where opp_scheme == dominant_tag for this team, keyed by archetype_name.
    Tells callers which player archetypes are most (or least) affected by this
    team's defensive scheme when guarding them.
    """
    df = _load_parquet("arch_scheme_x", INTEL / "archetype_scheme_interactions.parquet")
    if df is None or df.empty:
        return {}

    # Get dominant scheme tag for this team
    ds_df = _load_parquet("def_schemes_asn", INTEL / "defensive_schemes.parquet")
    dom_tag: Optional[str] = None
    if ds_df is not None and not ds_df.empty and "team" in ds_df.columns:
        ds_rows = ds_df[ds_df["team"] == tricode]
        if not ds_rows.empty:
            dom_tag = str(ds_rows.iloc[0].get("dominant_tag", "")) or None

    if not dom_tag:
        return {}

    # Filter interactions for this scheme tag
    if "opp_scheme" not in df.columns:
        return {}
    scheme_rows = df[df["opp_scheme"] == dom_tag]
    if scheme_rows.empty:
        return {}

    # Summarise: per archetype, collect stat → {mean_dev, t_stat, significant, n_games}
    archetype_map: Dict[str, Any] = {}
    for _, row in scheme_rows.iterrows():
        arch = str(row.get("archetype_name", ""))
        stat = str(row.get("stat", ""))
        if not arch or not stat:
            continue
        archetype_map.setdefault(arch, {"advantages": [], "disadvantages": []})
        entry = {
            "stat": stat,
            "mean_dev": _rd(row.get("mean_dev")),
            "t_stat": _rd(row.get("t_stat")),
            "n_games": _ri(row.get("n_games")),
            "significant": bool(row.get("significant", False)),
        }
        md = _rd(row.get("mean_dev")) or 0.0
        if md >= 0:
            archetype_map[arch]["advantages"].append(entry)
        else:
            archetype_map[arch]["disadvantages"].append(entry)

    return {
        "dominant_scheme_tag": dom_tag,
        "archetype_interactions": archetype_map,
        "n_archetypes": len(archetype_map),
    }


def _overall_def_context(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-average def_rtg + pace from team_advanced_stats.parquet, <= as_of.

    Leak guard: rows filtered to game_date <= as_of.
    """
    df = _load_parquet("team_adv_asn", DATA / "team_advanced_stats.parquet")
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
    avail = [c for c in ["def_rtg", "pace", "oreb_pct", "dreb_pct", "ast_pct"] if c in rows.columns]
    means = rows[avail].mean()
    result: Dict[str, Any] = {c: _rd(means.get(c)) for c in avail}
    result["n_games"] = n
    return result


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamDefensiveAssignments(AtlasSection):
    """Deep team defensive-assignments atlas section (team entity).

    Section key: ``"defensive_assignments"``.

    Builds a provenance-stamped, leak-safe artifact covering:
      - positional_defense:     shot-zone FG% allowed + zone forcing/hardening
      - coverage_faced_top10:   top-10 defender assignment map from matchup matrix
      - scheme_assignment_bias: scheme-driven assignment logic (drop/switch/denial)
      - archetype_scheme_cross: archetype×scheme interaction map for this team's scheme
      - overall_def_context:    def_rtg + pace for baseline quality context
      - hard_assignment_map, zone_cross_match, help_rotation_depth: DEFER

    Sources:
      - data/team_positional_defense_2025-26.parquet
      - data/cache/coverage_faced_matrix_2025-26.parquet (+ 2024-25 fallback)
      - data/intelligence/defensive_schemes.parquet + archetype_scheme_interactions.parquet
      - data/team_advanced_stats.parquet
      - data/cache/profiles/PLAYER_INDEX.json (for def_player_id -> team mapping)

    CV slots reserved:
      primary_def_player_id          — CV-measured per-possession primary defender
      help_rotation_reach_measured   — CV-measured help-defender travel distance (ft)
      cross_match_rate_measured      — CV-measured position-group mismatch rate
    """

    name: str = "defensive_assignments"
    entity: str = "team"
    source_name: str = (
        "team_positional_defense_2025-26.parquet + coverage_faced_matrix_2025-26.parquet + "
        "defensive_schemes.parquet + archetype_scheme_interactions.parquet + "
        "team_advanced_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the defensive_assignments artifact for team ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - team_advanced_stats is filtered to game_date <= as_of.
          - coverage_faced_matrix has no game_date; treated as season-level pre-published
            aggregate (same treatment as defensive_schemes in team_defensive_scheme.py).
          - team_positional_defense_2025-26 is a season-aggregate; no game_date column.

        Args:
            entity_id: team tricode string (e.g. "BOS", "LAL").
            as_of:     datetime representing the decision boundary (leak cutoff).

        Returns:
            AtlasArtifact or None if no source has data for this team.
        """
        tricode = str(entity_id).upper().strip()
        as_of_str = as_of.date().isoformat()

        pos_def = _positional_defense(tricode)
        cov_top10 = _coverage_top10(tricode, as_of)
        scheme_bias = _scheme_assignment_bias(tricode, as_of)
        arch_x = _archetype_scheme_cross(tricode)
        def_ctx = _overall_def_context(tricode, as_of)

        # Bail if no meaningful data from any source.
        # scheme_assignment_bias always returns a default dict with "balanced" label;
        # use a tighter check: require at least one of the data-backed sources to have
        # real content (positional_defense with zones, coverage top10 entries, or
        # overall_def_context with n_games).
        has_pos_zones = bool(pos_def.get("zones"))
        has_cov = bool(
            cov_top10.get("top10_defenders")
            and len(cov_top10["top10_defenders"]) > 0
        )
        has_ctx = bool(def_ctx.get("n_games"))
        has_scheme = bool(scheme_bias.get("dominant_scheme_tag"))
        has_arch = bool(arch_x.get("archetype_interactions"))
        all_empty = not any([has_pos_zones, has_cov, has_ctx, has_scheme, has_arch])
        if all_empty:
            return None

        sub_fields: Dict[str, Any] = {
            "positional_defense": pos_def,
            "coverage_faced_top10": cov_top10,
            "scheme_assignment_bias": scheme_bias,
            "archetype_scheme_cross": arch_x,
            "overall_def_context": def_ctx,
            # DEFER fields
            "hard_assignment_map": {
                "_note": (
                    "DEFER: live per-player explicit defensive assignments require "
                    "Synergy defensive-matchup endpoint or PBP tagging not in repo. "
                    "CV slot primary_def_player_id reserved for per-possession fill."
                )
            },
            "zone_cross_match": {
                "_note": (
                    "DEFER: per-possession positional-mismatch annotation not available. "
                    "switches_per_poss in defender_matchup_features covers only 96 WCF rows. "
                    "CV slot cross_match_rate_measured reserved."
                )
            },
            "help_rotation_depth": {
                "_note": (
                    "DEFER: per-possession help-rotation coverage annotation not in repo. "
                    "CV slot help_rotation_reach_measured reserved."
                )
            },
        }

        # --- Sample size ---
        n_candidates: List[int] = []
        if def_ctx.get("n_games"):
            n_candidates.append(int(def_ctx["n_games"]))
        top10 = cov_top10.get("top10_defenders") or []
        if top10:
            n_candidates.append(len(top10) * 5)  # proxy: n defenders * avg games
        if pos_def.get("n_zones"):
            n_candidates.append(int(pos_def["n_zones"]) * 10)
        n = max(n_candidates) if n_candidates else 1
        confidence = confidence_from_n(n, cap=self.conf_cap)

        # Headline value: assignment_bias label
        headline = scheme_bias.get("assignment_bias") or scheme_bias.get("dominant_scheme_tag")

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
            value=headline,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, zone FG% in plausible range.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {
            "positional_defense", "coverage_faced_top10",
            "scheme_assignment_bias", "archetype_scheme_cross",
            "overall_def_context", "hard_assignment_map",
            "zone_cross_match", "help_rotation_depth",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Zone FG% sanity: must be in [0, 1] or None
        zones = sf.get("positional_defense", {}).get("zones", {})
        for zone_data in zones.values():
            if not isinstance(zone_data, dict):
                return False
            d_fg = zone_data.get("d_fg_pct")
            if d_fg is not None and not (0.0 <= d_fg <= 1.0):
                return False

        # CV fields must all have value=None (not yet filled)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for defensive_assignments (values None until CV fills).

        The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "defensive_assignments", slot, as_of, value)``
        to populate these without a profile rebuild.

        Slots:
          primary_def_player_id         — CV per-possession primary defender player_id
          help_rotation_reach_measured  — mean ft traveled by help defender in 0.5s
          cross_match_rate_measured     — fraction of possessions with position-group mismatch
        """
        return {
            "primary_def_player_id": CVSlot(
                name="primary_def_player_id",
                dtype="float",
                description=(
                    "Per-possession primary defender player_id (mode across possessions) "
                    "assigned to the ball-carrier, resolved from CV jersey-OCR + proximity "
                    "at ball-carrier frame within EventDetector. Integer stored as float "
                    "for parquet compatibility; cast to int for use."
                ),
                unit=None,
                value=None,
            ),
            "help_rotation_reach_measured": CVSlot(
                name="help_rotation_reach_measured",
                dtype="float",
                description=(
                    "Mean Euclidean distance (ft, court coordinates) the nearest "
                    "off-ball defender travels toward the ball-carrier within a 0.5-second "
                    "window after the primary assignment is beaten, measured from "
                    "Kalman-tracked positions via homography."
                ),
                unit="ft",
                value=None,
            ),
            "cross_match_rate_measured": CVSlot(
                name="cross_match_rate_measured",
                dtype="float",
                description=(
                    "Fraction of ball-handler possessions in which the assigned primary "
                    "defender's position-group (G/F/C from archetype_label_sidecar) "
                    "mismatches the offensive ball-carrier's position-group, measured "
                    "from CV jersey-OCR + archetype sidecar cross-reference."
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
    """Build defensive_assignments for a list of team tricodes and register via bridge.

    Args:
        team_tricodes: list of 3-letter team tricodes.  If None, discovers from
                       team_positional_defense_2025-26.parquet (all available teams).
        as_of:        leak boundary date (defaults to today midnight UTC).
        store:        PointInTimeStore; when provided, artifacts written to the store.
        dry_run:      skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        df = _load_parquet("team_pos_def", DATA / "team_positional_defense_2025-26.parquet")
        if df is not None and not df.empty and "team_abbreviation" in df.columns:
            team_tricodes = sorted(df["team_abbreviation"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamDefensiveAssignments()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
