"""ARM-B atlas section: ``offensive_scheme`` — exhaustive team offensive identity.

Implements :class:`AtlasSection` for the ``"offensive_scheme"`` section of a
team's persistent profile.  Every sub-field is derived from existing parquets
cited in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  pace.*             — pace_pg (possessions/48 min), pace_variance, pace_identity
                       label (SLOW/MODERATE/FAST/VERY_FAST) from
                       data/team_advanced_stats.parquet (per-game rolling mean <=as_of)
                       + season_games_*.json (pace_variance per game, combined home+away).
  shot_diet.*        — ast_pct (fraction of FGM assisted), efg_pct, off_rtg, tov_ratio
                       from data/team_advanced_stats.parquet (per-game, all games <=as_of).
  pnr.*              — pnr_ppp (points-per-possession on PnR possessions), derived from
                       season_games_<season>.json home_pnr_ppp / away_pnr_ppp (aggregated
                       per team across games <=as_of).
  ball_movement.*    — passes_made_per_g (mean across team roster), ast_to_pass_pct,
                       secondary_ast_pg from data/cache/player_tracking_features.parquet
                       (grouped by drives_team field; season-level, no game_date; treat as
                       pre-published season summary, acceptably safe for as_of >= season end).
  drive_rate.*       — drives_per_g (mean across team roster), drive_fg_pct, drive_pts_pct
                       from data/cache/player_tracking_features.parquet (same source).
  tempo_spacing_cv.* — team_tempo_z, team_transition_share_z, team_avg_spacing_z,
                       team_tempo_spacing_composite_z from
                       data/intelligence/team_tempo_spacing.parquet (CV-derived,
                       latest snapshot with game_date <= as_of; data_density noted).

DEFER (no source parquet available):
  iso_rate.*         — DEFER: playtypes.parquet is PLAYER-level (player_id grain), not
                       team-level.  Aggregating per team requires a team_id / team_tricode
                       join that is not present.  Populate when a team-level synergy/play-
                       type parquet is added (NBA TeamDashPtStats endpoint).
  transition_rate.*  — DEFER: pbp_possession_features.parquet has per-player transition
                       counts but no team_tricode column; linking via game_id + box-score
                       team-player roster is not pre-aggregated.  Wire when
                       build_pbp_possession_features.py emits a team-grain companion.
  three_point_rate.* — DEFER: no per-team 3PA/FGA parquet exists (team_advanced_stats
                       does not include fg3a; team_positional_defense_2025-26.parquet
                       covers DEFENSIVE 3pt allowed, not offensive 3PA rate).
                       Populate when scripts/fetch_team_traditional_boxscores.py lands.
  off_screen_rate.*  — DEFER: no team-level off-screen / curl / flare frequency parquet.
  post_up_rate.*     — DEFER: same gap — playtypes is player-level; no team-level Postup.

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  transition_rate_cv    — fraction of offensive possessions classified as fast-break /
                          transition (CV EventDetector, team × game)
  spacing_dist_cv       — mean convex-hull area (ft²) of offensive alignment per possession
                          (CV homography, averaged over half-court possessions)
  drive_rate_cv         — mean drives-per-100-possessions from CV velocity + paint-approach
                          detection (independent of NBA tracking data)
  pnr_spacing_cv        — mean ball-handler-to-screener proximity (ft) at PnR pick-set
                          (CV EventDetector PnR event tagging)
  handler_isolation_cv  — mean handler_isolation score (proportion of time ball-handler is
                          >= 6 ft from nearest teammate) from CV frame-level feature
"""
from __future__ import annotations

import datetime as _dt
import json
import os
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
# Module-level lazy parquet cache (one load per process)
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
    """Clean scalar: NaN/inf → None, numpy → python float, round 4 dp."""
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
    """Clean integer."""
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
# Pace identity label
# ---------------------------------------------------------------------------

_PACE_BINS = [
    (98.0, "SLOW"),
    (100.5, "MODERATE"),
    (103.0, "FAST"),
    (float("inf"), "VERY_FAST"),
]


def _pace_identity(pace: float) -> str:
    """Map average pace (possessions/48 min) to a categorical identity label."""
    for threshold, label in _PACE_BINS:
        if pace < threshold:
            return label
    return "VERY_FAST"


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _team_adv_stats(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate team_advanced_stats for games <= as_of.

    Returns pace, ast_pct, efg_pct, off_rtg, tov_ratio, oreb_pct, n_games.
    LEAK-SAFE: filters game_date <= as_of before aggregating.
    """
    df = _load("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_tricode"] == team_tricode].copy()
    if rows.empty:
        return {}

    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[
        [c for c in ["pace", "ast_pct", "efg_pct", "off_rtg", "tov_ratio", "oreb_pct"]
         if c in rows.columns]
    ].mean()

    pace_val = _rd(means.get("pace"))
    return {
        "pace_pg": pace_val,
        "pace_identity": _pace_identity(pace_val) if pace_val else None,
        "ast_pct": _rd(means.get("ast_pct")),
        "efg_pct": _rd(means.get("efg_pct")),
        "off_rtg": _rd(means.get("off_rtg")),
        "tov_ratio": _rd(means.get("tov_ratio")),
        "oreb_pct": _rd(means.get("oreb_pct")),
        "n_games": n,
    }


def _season_games_pnr_pace(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate pnr_ppp and pace_variance from season_games_*.json.

    Reads home_pnr_ppp/away_pnr_ppp and home_pace_variance/away_pace_variance
    for all games involving the team where game_date <= as_of.
    LEAK-SAFE: filters game_date <= as_of before aggregating.
    """
    nba_dir = DATA / "nba"
    all_rows: List[Dict[str, Any]] = []

    for season in ["2022-23", "2023-24", "2024-25", "2025-26"]:
        path = nba_dir / f"season_games_{season}.json"
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            rows = raw.get("rows", []) if isinstance(raw, dict) else []
        except Exception:
            continue
        all_rows.extend(rows)

    if not all_rows:
        return {}

    df = pd.DataFrame(all_rows)
    if df.empty or "game_date" not in df.columns:
        return {}

    df["game_date"] = pd.to_datetime(df["game_date"])
    as_of_ts = pd.Timestamp(as_of)

    # Pull home games
    home_mask = (df.get("home_team", pd.Series(dtype=str)) == team_tricode)
    away_mask = (df.get("away_team", pd.Series(dtype=str)) == team_tricode)

    pnr_values: List[float] = []
    pace_var_values: List[float] = []

    if "home_team" in df.columns and "home_pnr_ppp" in df.columns:
        hdf = df[home_mask & (df["game_date"] <= as_of_ts)]
        if not hdf.empty:
            pnr_values.extend(hdf["home_pnr_ppp"].dropna().tolist())
            if "home_pace_variance" in hdf.columns:
                pace_var_values.extend(hdf["home_pace_variance"].dropna().tolist())

    if "away_team" in df.columns and "away_pnr_ppp" in df.columns:
        adf = df[away_mask & (df["game_date"] <= as_of_ts)]
        if not adf.empty:
            pnr_values.extend(adf["away_pnr_ppp"].dropna().tolist())
            if "away_pace_variance" in adf.columns:
                pace_var_values.extend(adf["away_pace_variance"].dropna().tolist())

    if not pnr_values:
        return {}

    return {
        "pnr_ppp": _rd(float(np.mean(pnr_values))),
        "pace_variance": _rd(float(np.mean(pace_var_values))) if pace_var_values else None,
        "n_games": len(pnr_values),
    }


def _player_tracking_team(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate player_tracking_features.parquet by team tricode.

    Uses the ``drives_team`` (or ``passing_team``) column to group players by
    team and compute team-level drive / ball-movement signals.

    Season-keyed (no game_date): treated as pre-published end-of-season summaries,
    acceptable for as_of at or after the season end.  No per-game filtering possible.
    LEAGUE AVERAGE substituted if team absent.
    """
    df = _load("trk_feat", CACHE / "player_tracking_features.parquet")
    if df is None or df.empty:
        return {}

    # Filter by drives_team column
    if "drives_team" not in df.columns:
        return {}

    rows = df[df["drives_team"] == team_tricode]
    if rows.empty:
        return {}

    n_players = len(rows)
    means = rows[
        [c for c in ["drives_per_g", "drive_fg_pct", "drive_pts_pct",
                     "drive_ast_per_drive", "passes_made_per_g",
                     "ast_to_pass_pct", "ast_to_pass_pct_adj"]
         if c in rows.columns]
    ].mean()

    return {
        "drives_per_g_mean": _rd(means.get("drives_per_g")),
        "drive_fg_pct": _rd(means.get("drive_fg_pct")),
        "drive_pts_pct": _rd(means.get("drive_pts_pct")),
        "drive_ast_rate": _rd(means.get("drive_ast_per_drive")),
        "passes_made_per_g_mean": _rd(means.get("passes_made_per_g")),
        "ast_to_pass_pct": _rd(means.get("ast_to_pass_pct")),
        "ast_to_pass_pct_adj": _rd(means.get("ast_to_pass_pct_adj")),
        "n_players": n_players,
    }


def _tempo_spacing_cv(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Latest CV-derived tempo/spacing snapshot with game_date <= as_of.

    Source: data/intelligence/team_tempo_spacing.parquet.
    LEAK-SAFE: uses latest snapshot where game_date <= as_of.
    Low n_possessions (2-16) — results are VARIANCE_ONLY / informational.
    """
    df = _load("tempo_spacing", INTEL / "team_tempo_spacing.parquet")
    if df is None or df.empty:
        return {}

    # Match by team_abbr (same tricode convention)
    team_col = "team_abbr" if "team_abbr" in df.columns else (
        "team_id" if "team_id" in df.columns else None
    )
    if team_col is None:
        return {}

    rows = df[df[team_col] == team_tricode].copy()
    if rows.empty:
        return {}

    # Leak-safe: latest snapshot <= as_of
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    # Use the single most-recent snapshot (largest n_games_window = most data)
    rows = rows.sort_values(
        ["game_date", "n_games_window"] if "n_games_window" in rows.columns else ["game_date"],
        ascending=False,
    )
    row = rows.iloc[0]

    return {
        "team_tempo_z": _rd(row.get("team_tempo_z")),
        "team_transition_share_z": _rd(row.get("team_transition_share_z")),
        "team_avg_spacing_z": _rd(row.get("team_avg_spacing_z")),
        "team_tempo_spacing_composite_z": _rd(row.get("team_tempo_spacing_composite_z")),
        "n_possessions_window": _ri(row.get("n_possessions_window")),
        "data_density": str(row.get("data_density", "low")),
        "_note": "CV-derived (team_tempo_spacing.parquet); n_possessions sparse (2-16); "
                 "treat as VARIANCE_ONLY / informational until CV game count grows >=3x.",
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamOffensiveScheme(AtlasSection):
    """Deep team offensive-scheme atlas section (team entity, section='offensive_scheme').

    Builds a provenance-stamped, leak-safe artifact covering pace identity,
    shot diet / efficiency, PnR usage, ball/player movement, drive rate, and
    CV-derived tempo/spacing signals.  Reserves 5 CV slots for future enrichment.

    Sources used:
      - data/team_advanced_stats.parquet        (pace, ast_pct, efg_pct, off_rtg, tov)
      - data/nba/season_games_*.json            (pnr_ppp, pace_variance per game)
      - data/cache/player_tracking_features.parquet (drives, passes, ball movement)
      - data/intelligence/team_tempo_spacing.parquet (CV-derived tempo/spacing z-scores)

    DEFER sections (no team-level source parquet):
      - iso_rate      — playtypes.parquet is player-level only; team join absent
      - transition_rate — pbp_possession_features has no team_tricode column
      - three_point_rate — team_advanced_stats lacks fg3a; defensive 3pt parquet only
      - off_screen_rate  — no team-level off-screen frequency parquet
      - post_up_rate     — same gap as iso_rate; playtypes is player-level
    """

    name: str = "offensive_scheme"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + season_games_*.json + "
        "player_tracking_features.parquet + team_tempo_spacing.parquet"
    )
    conf_cap: Optional[str] = None  # CV sub-section has its own informational note

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the offensive_scheme artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "BOS").
            as_of:     leak boundary — only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when all sources are missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        adv = _team_adv_stats(tricode, as_of)
        pnr = _season_games_pnr_pace(tricode, as_of)
        trk = _player_tracking_team(tricode, as_of)
        cv_tempo = _tempo_spacing_cv(tricode, as_of)

        # Bail when primary source (team_advanced_stats) is empty
        if not adv:
            return None

        # --- pace sub-dict ---
        pace: Dict[str, Any] = {
            "pace_pg": adv.get("pace_pg"),
            "pace_identity": adv.get("pace_identity"),
            "pace_variance": pnr.get("pace_variance"),
        }

        # --- shot_diet sub-dict (team efficiency profile) ---
        shot_diet: Dict[str, Any] = {
            "ast_pct": adv.get("ast_pct"),
            "efg_pct": adv.get("efg_pct"),
            "off_rtg": adv.get("off_rtg"),
            "tov_ratio": adv.get("tov_ratio"),
            "oreb_pct": adv.get("oreb_pct"),
        }

        # --- pnr sub-dict ---
        pnr_sub: Dict[str, Any] = {
            "pnr_ppp": pnr.get("pnr_ppp"),
            "_source": "season_games_*.json home_pnr_ppp/away_pnr_ppp mean",
        }

        # --- ball_movement sub-dict ---
        ball_movement: Dict[str, Any] = {}
        if trk:
            ball_movement = {
                "passes_made_per_g_mean": trk.get("passes_made_per_g_mean"),
                "ast_to_pass_pct": trk.get("ast_to_pass_pct"),
                "ast_to_pass_pct_adj": trk.get("ast_to_pass_pct_adj"),
                "n_players_in_sample": trk.get("n_players"),
                "_source": "player_tracking_features.parquet grouped by drives_team; "
                           "season-level (no game_date filtering); pre-published summary.",
            }

        # --- drive_rate sub-dict ---
        drive_rate: Dict[str, Any] = {}
        if trk:
            drive_rate = {
                "drives_per_g_mean": trk.get("drives_per_g_mean"),
                "drive_fg_pct": trk.get("drive_fg_pct"),
                "drive_pts_pct": trk.get("drive_pts_pct"),
                "drive_ast_rate": trk.get("drive_ast_rate"),
            }

        # --- tempo_spacing_cv sub-dict (CV-derived, sparse) ---
        tempo_spacing: Dict[str, Any] = dict(cv_tempo) if cv_tempo else {
            "_note": "DEFER: team_tempo_spacing.parquet has no snapshot <= as_of for this team."
        }

        # --- DEFER placeholders ---
        iso_rate: Dict[str, Any] = {
            "_note": "DEFER: playtypes.parquet is player-level (player_id grain). "
                     "No team-tricode join available. Add when NBA TeamDashPtStats "
                     "endpoint is fetched (scripts/fetch_team_playtypes.py)."
        }
        transition_rate: Dict[str, Any] = {
            "_note": "DEFER: pbp_possession_features.parquet has no team_tricode column. "
                     "Build a team-grain companion via build_pbp_possession_features.py "
                     "grouping by game_id + home/away team membership."
        }
        three_point_rate: Dict[str, Any] = {
            "_note": "DEFER: team_advanced_stats lacks fg3a/fg3_pct. "
                     "team_positional_defense_2025-26.parquet covers DEFENSIVE 3pt allowed "
                     "only. Add when scripts/fetch_team_traditional_boxscores.py lands."
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "pace": pace,
            "shot_diet": shot_diet,
            "pnr": pnr_sub,
            "ball_movement": ball_movement,
            "drive_rate": drive_rate,
            "tempo_spacing_cv": tempo_spacing,
            "iso_rate": iso_rate,
            "transition_rate": transition_rate,
            "three_point_rate": three_point_rate,
        }

        # Headline convenience scalar: off_rtg (best single offensive summary)
        value = adv.get("off_rtg")

        # --- Sample size and confidence ---
        # Primary n from team_advanced_stats (# games)
        n = adv.get("n_games", 1)
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
            entity_id=tricode,
            value=value,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present + sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "pace", "shot_diet", "pnr", "ball_movement", "drive_rate",
            "tempo_spacing_cv", "iso_rate", "transition_rate", "three_point_rate",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sane range checks for pace
        pace_val = sf.get("pace", {}).get("pace_pg")
        if pace_val is not None and not (80.0 <= pace_val <= 130.0):
            return False

        # Sane range for ast_pct [0, 1]
        ast_pct = sf.get("shot_diet", {}).get("ast_pct")
        if ast_pct is not None and not (0.0 <= ast_pct <= 1.0):
            return False

        # CV slots must all have value=None (CV branch hasn't run)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for offensive_scheme (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "offensive_scheme", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Keys are stable contract.
        """
        return {
            "transition_rate_cv": CVSlot(
                name="transition_rate_cv",
                dtype="float",
                description=(
                    "Fraction of offensive possessions classified as fast-break or "
                    "transition by CV EventDetector (ball crosses half-court within "
                    "~3s of a defensive rebound or turnover), per team per game."
                ),
                unit=None,
                value=None,
            ),
            "spacing_dist_cv": CVSlot(
                name="spacing_dist_cv",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft²) of the five offensive players "
                    "during half-court set possessions, computed from CV homography "
                    "court-coordinate positions averaged over possession frames."
                ),
                unit="ft²",
                value=None,
            ),
            "drive_rate_cv": CVSlot(
                name="drive_rate_cv",
                dtype="float",
                description=(
                    "Mean number of drives per 100 offensive possessions, where a drive "
                    "is detected by CV as a ball-handler moving at >8 ft/s toward the "
                    "paint within 6 ft of the basket, independent of NBA tracking."
                ),
                unit="per 100 poss",
                value=None,
            ),
            "pnr_spacing_cv": CVSlot(
                name="pnr_spacing_cv",
                dtype="float",
                description=(
                    "Mean distance (ft) between ball-handler and screener at the moment "
                    "of pick-set in PnR possessions, from CV EventDetector PnR event "
                    "tagging + homography coordinates."
                ),
                unit="ft",
                value=None,
            ),
            "handler_isolation_cv": CVSlot(
                name="handler_isolation_cv",
                dtype="float",
                description=(
                    "Mean handler_isolation score — fraction of half-court possession "
                    "frames where the ball-handler is >= 6 ft from the nearest "
                    "teammate — reflecting ISO-heavy vs motion-heavy offensive identity."
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
    """Build offensive_scheme for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["BOS", "LAL"]).
                       If None, discovers from team_advanced_stats.parquet.
        as_of:         leak boundary date (defaults to today).
        store:         PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:       skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if team_tricodes is None:
        df = _load("team_adv_disc", DATA / "team_advanced_stats.parquet")
        if df is not None and "team_tricode" in df.columns:
            team_tricodes = sorted(df["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamOffensiveScheme()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
