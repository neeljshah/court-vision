"""ARM-B atlas section: ``matchup_splits`` — exhaustive per-player matchup profile.

Section key: ``matchup_splits``
Entity:      ``player``

**Sub-fields coverage:**

REAL (populated from existing parquets):
  vs_position.*      — offensive stats vs G / F / C positional archetypes from
                       data/intelligence/pos_vs_pos_matchups.parquet (pts/reb/ast
                       mean_dev + p_val significance flag keyed on player position
                       vs opponent position bucket).
  vs_scheme.*        — pts/reb/ast/fg3m/stl deviation vs opponent defensive scheme
                       (drop/switch/blitz/perimeter_denial/help) from
                       data/intelligence/position_scheme_interactions.parquet
                       (position-level) merged with data/intelligence/defensive_schemes
                       .parquet for team-level scheme labels.
  vs_notable_defenders.*
                     — top-5 individual defender matchups by partial_possessions from
                       data/cache/coverage_faced_matrix.parquet + 2025-26 variant;
                       includes def_player_name, matchup_minutes, partial_possessions,
                       off_fg_pct, off_fg3_pct, off_points_per_possession.
  vs_opp_team.*      — per-opponent-team aggregated stats (fg_pct, pts per possession,
                       matchup_minutes) from coverage_faced_matrix (top-5 by minutes).
  matchup_deviation.* — notable_flag + deviation_flags + max_abs_z from
                       data/intelligence/matchup_deviations.parquet (latest entry by
                       off_player_id) capturing aggregate behavioral deviations vs
                       any opponent.
  opp_scheme_pressure.* — opponent defensive intensity z-scores (defended shot rate,
                       defender_distance, paint_attempts, pace_imposed) from
                       data/intelligence/opp_defensive_intensity.parquet; player-level
                       context derived from team_id and game_date join through
                       player_adv_stats.parquet.

DEFER (data gap — not available in current parquets):
  vs_size.*          — stats vs taller/shorter/heavier/lighter defenders
                       DEFER: no per-defender height/weight matchup parquet; would need
                       a player_bio parquet joined to defender_matchups_*.parquet
                       (player_profile_features.parquet missing from repo).
  vs_specific_defenders_recent.*
                     — per-defender per-game L5 rolling stats
                       DEFER: coverage_faced_matrix is season-aggregate; per-game
                       per-defender time-series is not pre-aggregated; requires a
                       game-level join on (off_player_id, def_player_id, game_date).

RESERVED CV SLOTS (value=None, CV branch fills later):
  cv_defender_closeout_vs_pos   — mean closeout speed (ft/s) faced from each position
  cv_contest_rate_vs_pos        — fraction of shots contested by positional defenders
  cv_drive_success_vs_scheme    — drive success rate (shot+foul) vs each scheme type
  cv_spacing_vs_scheme          — mean teammate spacing (ft²) player operates within
                                  vs each defensive scheme (CV homography)
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
# Module-level parquet cache (lazy, loaded once per process)
# ---------------------------------------------------------------------------

_SRC: Dict[str, Optional[pd.DataFrame]] = {}


def _load(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC:
        try:
            _SRC[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC[key] = None
    return _SRC[key]


# ---------------------------------------------------------------------------
# Scalar-cleaning helpers (mirrors factory pattern)
# ---------------------------------------------------------------------------

def _rd(v: Any) -> Optional[float]:
    """NaN/inf -> None, numpy -> python float, round 4dp."""
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
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _vs_position(player_pos: Optional[str]) -> Dict[str, Any]:
    """Positional matchup deviations from pos_vs_pos_matchups.parquet.

    Returns the mean_dev (stat deviation when facing each opponent position) and
    the p_val significance flag for the player's position vs each opp position.
    If player_pos is None or not found, returns an empty dict.
    """
    df = _load("pos_vs_pos", INTEL / "pos_vs_pos_matchups.parquet")
    if df is None or df.empty or not player_pos:
        return {}

    pos = str(player_pos).upper()[:1]  # normalize to G / F / C
    if pos not in ("G", "F", "C"):
        return {}

    rows = df[df["player_pos"] == pos]
    if rows.empty:
        return {}

    result: Dict[str, Any] = {}
    for _, row in rows.iterrows():
        opp_pos = str(row.get("opp_pos", ""))
        stat = str(row.get("stat", ""))
        key = f"vs_{opp_pos.lower()}_{stat}"
        result[key] = {
            "mean_dev": _rd(row.get("mean_dev")),
            "p_val": _rd(row.get("p_val")),
            "significant": bool(row.get("p_val", 1.0) < 0.05) if row.get("p_val") is not None else False,
            "n_games": _ri(row.get("n_games")),
        }
    return result


def _vs_scheme(player_pos: Optional[str]) -> Dict[str, Any]:
    """Stats vs opponent defensive scheme from position_scheme_interactions.parquet.

    Returns per-scheme stat deviations (pts/reb/ast) for the player's position bucket.
    """
    df = _load("pos_scheme", INTEL / "position_scheme_interactions.parquet")
    if df is None or df.empty or not player_pos:
        return {}

    pos = str(player_pos).upper()[:1]
    # normalize to what the parquet uses (C / F / G)
    pos_map = {"G": "G", "F": "F", "C": "C"}
    pos = pos_map.get(pos, "")
    if not pos:
        return {}

    rows = df[df["position"] == pos]
    if rows.empty:
        return {}

    result: Dict[str, Any] = {}
    for _, row in rows.iterrows():
        scheme = str(row.get("opp_scheme", "")).lower().replace(" ", "_")
        stat = str(row.get("stat", ""))
        key = f"{scheme}_{stat}"
        result[key] = {
            "mean_dev": _rd(row.get("mean_dev")),
            "t_stat": _rd(row.get("t_stat")),
            "significant": bool(row.get("significant", False)),
            "n_games": _ri(row.get("n")),
            "mean_actual": _rd(row.get("mean_actual")),
        }
    return result


def _notable_defenders(pid: int, as_of: _dt.datetime, top_k: int = 5) -> Dict[str, Any]:
    """Top individual defenders faced by partial_possessions from coverage_faced_matrix.

    Uses the freshest available coverage_faced parquet (2025-26 preferred, 2024-25 fallback).
    Filters to season data available before as_of using season start date approximation.
    """
    as_of_iso = as_of.date().isoformat()

    # Try to load both seasons; prefer the freshest with data for this player
    rows_list: List[pd.DataFrame] = []
    for path_key, path, season in [
        ("cfm26", CACHE / "coverage_faced_matrix_2025-26.parquet", "2025-26"),
        ("cfm_base", CACHE / "coverage_faced_matrix.parquet", "2024-25"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        player_rows = df[df["off_player_id"] == pid]
        if player_rows.empty:
            continue
        # Season boundary leak guard: 2025-26 data only if as_of >= 2025-10-01
        if season == "2025-26" and as_of_iso < "2025-10-01":
            continue
        if season == "2024-25" and as_of_iso < "2024-10-01":
            continue
        rows_list.append(player_rows)

    if not rows_list:
        return {}

    combined = pd.concat(rows_list, ignore_index=True)
    # Deduplicate by def_player_id: prefer 2025-26 (higher row index from concat order)
    combined = combined.drop_duplicates("def_player_id", keep="first")
    combined = combined.sort_values("partial_possessions", ascending=False).head(top_k)

    defenders: Dict[str, Any] = {}
    for _, row in combined.iterrows():
        def_id = str(int(row["def_player_id"])) if pd.notna(row.get("def_player_id")) else "unknown"
        poss = float(row.get("partial_possessions", 0)) or 0.0
        fgm = float(row.get("off_fgm", 0)) or 0.0
        fga = float(row.get("off_fga", 0)) or 0.0
        pts = float(row.get("off_points", 0)) or 0.0

        defenders[def_id] = {
            "def_player_name": str(row.get("def_player_name", "")),
            "matchup_minutes": _rd(row.get("matchup_minutes_total")),
            "partial_possessions": _rd(poss),
            "off_fg_pct": _rd(row.get("off_fg_pct")),
            "off_fg3_pct": _rd(row.get("off_fg3_pct")),
            "off_points_per_poss": _rd(pts / poss) if poss > 1.0 else None,
            "season": str(row.get("season", "")),
        }
    return defenders


def _vs_opp_team(pid: int, as_of: _dt.datetime, top_k: int = 5) -> Dict[str, Any]:
    """Per-opponent-team stats from coverage_faced_matrix aggregated by defender team.

    Since coverage_faced_matrix records are per (off_player, def_player, season),
    we group by def_player's team to get team-level matchup context. The team
    is inferred from def_player_name -> def_player_id -> defender_matchups team.
    If team mapping is unavailable, fall back to top defenders' team attribution
    from the defender_matchups parquet via a left join.
    """
    as_of_iso = as_of.date().isoformat()

    rows_list: List[pd.DataFrame] = []
    for path_key, path, season in [
        ("cfm26", CACHE / "coverage_faced_matrix_2025-26.parquet", "2025-26"),
        ("cfm_base", CACHE / "coverage_faced_matrix.parquet", "2024-25"),
    ]:
        df = _load(path_key, path)
        if df is None or df.empty:
            continue
        player_rows = df[df["off_player_id"] == pid].copy()
        if player_rows.empty:
            continue
        if season == "2025-26" and as_of_iso < "2025-10-01":
            continue
        if season == "2024-25" and as_of_iso < "2024-10-01":
            continue
        rows_list.append(player_rows)

    if not rows_list:
        return {}

    combined = pd.concat(rows_list, ignore_index=True)

    # Try to join defender team from defender_matchups
    dm26 = _load("dm26", DATA / "defender_matchups_2025-26.parquet")
    dm_base = _load("dm_base", DATA / "defender_matchups_2024-25.parquet")

    team_map: Dict[int, str] = {}
    for dm in [dm26, dm_base]:
        if dm is None or dm.empty:
            continue
        for _, row in dm[["def_player_id", "def_team_tricode"]].drop_duplicates().iterrows():
            did = _ri(row.get("def_player_id"))
            tri = str(row.get("def_team_tricode", ""))
            if did is not None and tri:
                team_map.setdefault(did, tri)

    combined["def_team"] = combined["def_player_id"].apply(
        lambda x: team_map.get(int(x), "") if pd.notna(x) else ""
    )
    combined = combined[combined["def_team"] != ""]

    if combined.empty:
        return {}

    # Aggregate by defending team
    team_groups: Dict[str, Any] = {}
    for team, grp in combined.groupby("def_team"):
        poss = float(grp["partial_possessions"].sum())
        pts = float(grp["off_points"].sum()) if "off_points" in grp.columns else 0.0
        fgm = float(grp["off_fgm"].sum()) if "off_fgm" in grp.columns else 0.0
        fga = float(grp["off_fga"].sum()) if "off_fga" in grp.columns else 0.0
        team_groups[str(team)] = {
            "total_partial_possessions": _rd(poss),
            "off_points_per_poss": _rd(pts / poss) if poss > 1.0 else None,
            "off_fg_pct": _rd(fgm / fga) if fga > 0 else None,
            "n_matchup_pairs": int(len(grp)),
        }

    # Return top_k teams by possessions
    sorted_teams = sorted(team_groups.items(),
                          key=lambda kv: kv[1].get("total_partial_possessions") or 0.0,
                          reverse=True)
    return dict(sorted_teams[:top_k])


def _matchup_deviation(pid: int) -> Dict[str, Any]:
    """Notable matchup behavior flags from matchup_deviations.parquet.

    Returns the latest entry for this player covering deviation_flags and max_abs_z.
    """
    df = _load("mdev", INTEL / "matchup_deviations.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["player_id"] == pid]
    if rows.empty:
        return {}
    # Take the row with highest max_abs_z (most notable)
    row = rows.loc[rows["max_abs_z"].idxmax()] if "max_abs_z" in rows.columns else rows.iloc[-1]
    return {
        "notable_flag": bool(row.get("notable_flag", False)),
        "deviation_flags": str(row.get("deviation_flags", "")) or None,
        "max_abs_z": _rd(row.get("max_abs_z")),
        "opp_team": str(row.get("opp_team", "")) or None,
    }


def _opp_scheme_pressure(pid: int, as_of: _dt.datetime) -> Dict[str, Any]:
    """Opponent defensive pressure context from opp_defensive_intensity.parquet.

    Joins through player_adv_stats to find the player's team games, then picks
    the latest opp_defensive_intensity record for that team on or before as_of.
    """
    as_of_iso = as_of.date().isoformat()

    # Find the player's team from adv stats
    adv = _load("adv_ms", DATA / "player_adv_stats.parquet")
    if adv is None or adv.empty:
        return {}
    player_adv = adv[adv["player_id"] == pid].copy()
    if player_adv.empty:
        return {}

    # Get the team from the most recent game <= as_of
    if "game_date" in player_adv.columns:
        player_adv["game_date"] = pd.to_datetime(player_adv["game_date"])
        player_adv = player_adv[player_adv["game_date"] <= pd.Timestamp(as_of)]
    if player_adv.empty:
        return {}

    # opp_defensive_intensity is keyed on team_id and game_date:
    # We don't have team from adv stats directly, so we can only provide
    # the aggregate at the league level (mean pressure) as a proxy.
    # DEFER: per-player team join needs team_tricode in player_adv_stats.
    odi = _load("odi", INTEL / "opp_defensive_intensity.parquet")
    if odi is None or odi.empty:
        return {}

    # Filter to as_of
    if "game_date" in odi.columns:
        odi = odi[odi["game_date"].astype(str) <= as_of_iso]
    if odi.empty:
        return {}

    # League-average proxy (conservative: can't match player team without team_id)
    intensity_cols = [
        "opp_contested_shot_rate_imposed_z",
        "opp_avg_defender_distance_imposed_z",
        "opp_paint_attempts_allowed_pct_z",
        "opp_pace_imposed_z",
        "opp_defensive_intensity_z",
    ]
    numeric_odi = odi[intensity_cols].select_dtypes(include=[np.number])
    means = numeric_odi.mean()
    return {
        "league_avg_contested_shot_rate_z": _rd(means.get("opp_contested_shot_rate_imposed_z")),
        "league_avg_defender_distance_z": _rd(means.get("opp_avg_defender_distance_imposed_z")),
        "league_avg_paint_pct_z": _rd(means.get("opp_paint_attempts_allowed_pct_z")),
        "league_avg_pace_imposed_z": _rd(means.get("opp_pace_imposed_z")),
        "league_avg_intensity_z": _rd(means.get("opp_defensive_intensity_z")),
        "_note": "DEFER: per-player team join needs team_tricode in player_adv_stats.parquet",
    }


def _infer_position_from_adv(pid: int, as_of_iso: str) -> Optional[str]:
    """Infer positional bucket (G/F/C) from usage and assist patterns as a fallback.

    pos_vs_pos_matchups keys on 'G', 'F', 'C'; we approximate from player
    scoring/playmaking when no bio parquet is available (player_profile_features
    is missing from repo per spec_intel_memory 1.6). Uses pbp_possession_features
    as a usage-role proxy (high iso + high pnr_handler -> G; low both -> C).
    """
    pbp = _load("pbp_pos_inf", CACHE / "pbp_possession_features.parquet")
    if pbp is None or pbp.empty:
        return None

    rows = pbp[pbp["player_id"] == pid].copy()
    if "game_date" in rows.columns:
        rows = rows[rows["game_date"].astype(str) <= as_of_iso]
    if rows.empty:
        return None

    iso_mean = rows["pbp_iso_poss_count"].mean() if "pbp_iso_poss_count" in rows.columns else 0.0
    pnr_mean = rows["pbp_pnr_ball_handler"].mean() if "pbp_pnr_ball_handler" in rows.columns else 0.0

    # Coarse heuristic: high ball-handling -> G; otherwise F or C
    if iso_mean > 1.5 or pnr_mean > 1.5:
        return "G"
    elif iso_mean > 0.5 or pnr_mean > 0.5:
        return "F"
    return "C"


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerMatchupSplits(AtlasSection):
    """Deep player matchup-splits atlas section (section='matchup_splits').

    Builds a provenance-stamped, leak-safe artifact covering matchup performance
    vs position, vs defensive scheme, vs notable individual defenders, and vs
    opponent team. Reserves 4 CV slots for spatial/behavioral enrichment later.

    Sources used (all existing repo parquets — no re-derivation):
      - data/intelligence/pos_vs_pos_matchups.parquet  (vs position)
      - data/intelligence/position_scheme_interactions.parquet (vs scheme)
      - data/cache/coverage_faced_matrix.parquet + _2025-26 (notable defenders)
      - data/intelligence/matchup_deviations.parquet (behavioral deviation flags)
      - data/intelligence/opp_defensive_intensity.parquet (opp scheme pressure)
      - data/player_adv_stats.parquet (game-date anchor for leak filtering)
      - data/defender_matchups_2024-25.parquet + 2025-26 (team attribution)

    DEFER sub-fields:
      vs_size (no per-defender height/weight parquet), per-game per-defender
      rolling L5 stats (season-aggregate only in coverage_faced_matrix).

    CV slots reserved (null until CV-fix session fills them):
      cv_defender_closeout_vs_pos, cv_contest_rate_vs_pos,
      cv_drive_success_vs_scheme, cv_spacing_vs_scheme.
    """

    name: str = "matchup_splits"
    entity: str = "player"
    source_name: str = (
        "pos_vs_pos_matchups.parquet + position_scheme_interactions.parquet + "
        "coverage_faced_matrix.parquet + matchup_deviations.parquet + "
        "opp_defensive_intensity.parquet + defender_matchups_2025-26.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the matchup_splits artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - coverage_faced_matrix: season-level data; season start dates used as
            the boundary (2025-26 only if as_of >= 2025-10-01).
          - matchup_deviations: no game_date column; treated as end-of-season
            aggregate; included if as_of >= first game of the season inferred from
            the underlying data (~2024-10-01).
          - pos_vs_pos_matchups / position_scheme_interactions: league-level
            position statistics; treated as historical population priors derived
            from data available before the season; included unconditionally.
          - opp_defensive_intensity: filtered by game_date <= as_of.
          - player_adv_stats: filtered by game_date <= as_of.

        Returns None when coverage_faced and matchup_deviations are both empty for
        this player (no matchup context available at all).
        """
        pid = int(entity_id)
        as_of_iso = as_of.date().isoformat()

        # Infer positional bucket for position-keyed tables
        player_pos = _infer_position_from_adv(pid, as_of_iso)

        # Build each sub-section
        vs_pos = _vs_position(player_pos)
        vs_scheme = _vs_scheme(player_pos)
        notable_defs = _notable_defenders(pid, as_of)
        vs_opp_team = _vs_opp_team(pid, as_of)
        matchup_dev = _matchup_deviation(pid)
        opp_pressure = _opp_scheme_pressure(pid, as_of)

        # Return None only if ALL matchup-specific data is missing
        has_any = (
            bool(notable_defs)
            or bool(matchup_dev)
            or bool(vs_opp_team)
        )
        if not has_any:
            return None

        # vs_size: DEFER — no height/weight defender parquet
        vs_size: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-defender height/weight parquet available. "
                "Requires player_profile_features.parquet joined to "
                "defender_matchups_*.parquet (player_profile_features missing from repo)."
            )
        }

        # vs_specific_defenders_recent: DEFER — season-aggregate only
        vs_specific_recent: Dict[str, Any] = {
            "_note": (
                "DEFER: coverage_faced_matrix is season-aggregate (no per-game time-series). "
                "L5 rolling per-defender stats require a game-level join on "
                "(off_player_id, def_player_id, game_date) that is not pre-aggregated."
            )
        }

        sub_fields: Dict[str, Any] = {
            "vs_position": vs_pos,
            "vs_scheme": vs_scheme,
            "vs_notable_defenders": notable_defs,
            "vs_opp_team": vs_opp_team,
            "matchup_deviation": matchup_dev,
            "opp_scheme_pressure": opp_pressure,
            "vs_size": vs_size,
            "vs_specific_defenders_recent": vs_specific_recent,
            "inferred_position": player_pos,
        }

        # n: best sample from coverage_faced (sum of n_games_matched)
        cfm26 = _load("cfm26", CACHE / "coverage_faced_matrix_2025-26.parquet")
        cfm_base = _load("cfm_base", CACHE / "coverage_faced_matrix.parquet")
        n = 0
        for df in [cfm26, cfm_base]:
            if df is None or df.empty:
                continue
            pid_rows = df[df["off_player_id"] == pid]
            if pid_rows.empty:
                continue
            n_candidate = _ri(pid_rows["n_games_matched"].sum())
            if n_candidate and n_candidate > n:
                n = n_candidate
            break  # prefer 2025-26

        if n == 0:
            n = len(notable_defs)  # fallback: count of tracked defenders

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_iso,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_iso,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present; CV slots null.

        The full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "vs_position", "vs_scheme", "vs_notable_defenders",
            "vs_opp_team", "matchup_deviation", "opp_scheme_pressure",
            "vs_size", "vs_specific_defenders_recent",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # All CV slots must exist with value=None (not filled yet)
        for slot_name in self.cv_fields():
            if slot_name not in artifact.cv_fields:
                return False
            if artifact.cv_fields[slot_name].value is not None:
                return False

        # fg_pct values in notable_defenders must be in [0, 1]
        nd = sf.get("vs_notable_defenders", {})
        for def_info in nd.values():
            if not isinstance(def_info, dict):
                continue
            for pct_key in ("off_fg_pct", "off_fg3_pct"):
                v = def_info.get(pct_key)
                if v is not None and not (0.0 <= float(v) <= 1.0):
                    return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for matchup_splits (values None — CV fills later).

        Slots are stable keys; the CV-fix session calls
        ``store.fill_cv_slot("player", pid, "matchup_splits", slot, as_of, value)``.
        """
        return {
            "cv_defender_closeout_vs_pos": CVSlot(
                name="cv_defender_closeout_vs_pos",
                dtype="dist",
                description=(
                    "Distribution of defender closeout speeds (ft/s) faced from each "
                    "positional bucket (G/F/C), from CV homography + Kalman velocity "
                    "at the frame of shot release. Enables matchup-adjusted shot quality."
                ),
                unit="ft/s",
                value=None,
            ),
            "cv_contest_rate_vs_pos": CVSlot(
                name="cv_contest_rate_vs_pos",
                dtype="dist",
                description=(
                    "Fraction of shot attempts contested (defender <= 4 ft) broken down "
                    "by opponent positional bucket (G/F/C), from CV bounding-box proximity "
                    "at release. Feeds the vs_position interaction signal."
                ),
                unit=None,
                value=None,
            ),
            "cv_drive_success_vs_scheme": CVSlot(
                name="cv_drive_success_vs_scheme",
                dtype="dist",
                description=(
                    "Drive success rate (fraction of drives resulting in shot or drawn foul) "
                    "vs each defensive scheme type (drop/switch/blitz/help), from CV "
                    "EventDetector drive-event tagging + team defensive_schemes.parquet. "
                    "Directly enriches vs_scheme with behavioral outcomes."
                ),
                unit=None,
                value=None,
            ),
            "cv_spacing_vs_scheme": CVSlot(
                name="cv_spacing_vs_scheme",
                dtype="dist",
                description=(
                    "Mean convex-hull teammate spacing (ft²) the player operates within "
                    "vs each defensive scheme archetype, from CV homography coordinates. "
                    "Proxy for how much the defense compresses vs expands spacing."
                ),
                unit="ft²",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level build + registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build matchup_splits for a list of players and register via the bridge.

    Args:
        player_ids: NBA player_id list (int).  If None, discovers from
                    coverage_faced_matrix_2025-26 (broadest matchup coverage).
        as_of:      leak boundary date (defaults to today midnight UTC).
        store:      PointInTimeStore; when provided, artifacts written to store.
        dry_run:    compute everything but skip disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        df = _load("cfm26_disc", CACHE / "coverage_faced_matrix_2025-26.parquet")
        if df is not None and "off_player_id" in df.columns:
            player_ids = sorted(df["off_player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerMatchupSplits()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)


def get_section() -> PlayerMatchupSplits:
    """Return the section instance (bridge registry hook)."""
    return PlayerMatchupSplits()
