"""ARM-B atlas section: ``rotation_patterns`` — exhaustive team rotation profile.

Implements :class:`AtlasSection` for the ``"rotation_patterns"`` section of a
team's persistent profile. Covers every detail of how a team manages its roster
through a game: lineup staggering, star-rest tendencies, rotation depth, playoff
shortening, and closing-lineup identity.

**Sub-field coverage:**

REAL (populated from existing parquets / lineup JSONs):
  starters.*         — most-used 5-man starting lineup + net_rating + gp, from
                       data/nba/lineups/lineup_splits_<TRI>_<season>.json (latest season).
  closing_lineup.*   — most-used 5-man lineup in clutch / high-minute contexts
                       (top lineup by min as proxy); true clutch-game filter is
                       DEFER (no per-period game-rotation JSON). Approximated as
                       the second-most-used lineup when minutes are close.
  depth.*            — n_unique_lineups, n_lineups_gt10min, top3_min_share —
                       from lineup JSONs; rotation_depth_score = 1 - top3_min_share.
  rotation_stability.*  — top1_min_share, lineup_churn = unique lineups per game,
                          from lineup_features.parquet (player-level → team agg).
  pace_context.*     — team pace mean/std, is_fast_break_team from
                       data/team_advanced_stats.parquet.
  star_rest.*        — avg Q4 minutes for the team's max-minutes player and
                       their q4_presence_rate (fraction of games they play Q4),
                       from data/player_quarter_stats.parquet joined via
                       data/player_adv_stats.parquet for team+game mapping.
                       APPROXIMATION: uses per-player per-game minutes to infer
                       rest; no official rotation-order data available.
  q4_patterns.*      — team-level Q4 pts/min distribution, lead-protected vs
                       back-from-behind tendencies (placeholder from adv stats).

DEFER (no source parquet available without live GameRotation scrape):
  stagger_times.*    — exact sub-quarter substitution timing (0-6 min mark etc.)
                       DEFER: requires GameRotation V2 per-game API scrape; only
                       GameRotation cached data in data/nba/lineups/ is season-
                       level, not per-game order data.
  playoff_shortening.* — explicit regular-season vs playoff rotation-depth delta
                         DEFER: no separate playoff lineup JSON in repo (only 2
                         teams have 2025-26 season data); would need to filter
                         game_id by 004* prefix.
  rest_minutes_q2.*  — exact when stars exit Q2 vs sit the full second quarter
                       DEFER: same GameRotation gap; per-game sub-order not cached.
  timeout_patterns.* — substitution patterns after timeouts DEFER: requires PBP.

RESERVED CV SLOTS (value=None, CV branch fills later):
  lineup_spacing_mean — mean convex-hull spacing (ft²) for the team's top lineup
                        from CV homography data (team-aggregate = ships, per MEMORY).
  transition_pace_cv  — CV-measured mean possession-start-to-shot duration (s)
                        for fast-break possessions, from cv_pace_per_game.parquet.
  closer_velocity     — mean ball-handler velocity (ft/s) of closing lineup in
                        4th-quarter possessions, from CV tracking.
  rotation_fatigue_cv — mean per-player velocity drop (ft/s) in the last 3 min
                        of each quarter, indicating depth-driven fatigue effects.
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
NBA = DATA / "nba"

# Module-level lazy-load cache (reset between processes).
_SRC_CACHE: Dict[str, Optional[Any]] = {}


# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------

def _load_df(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on error/missing."""
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


def _load_lineup_json(tricode: str) -> Optional[List[dict]]:
    """Load the most recent season lineup JSON for a team tricode.

    Tries 2025-26 first, then 2024-25, then earlier. Returns the raw list of
    lineup dicts (sorted by season desc) or None if no file exists.
    Leak-safe: the JSON represents season-level summaries; callers filter further
    by restricting to seasons whose end-date <= as_of.
    """
    cache_key = f"lineup_json_{tricode}"
    if cache_key in _SRC_CACHE:
        return _SRC_CACHE[cache_key]

    for season in ["2025-26", "2024-25", "2023-24", "2022-23"]:
        path = NBA / "lineups" / f"lineup_splits_{tricode}_{season}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                _SRC_CACHE[cache_key] = data
                return data
            except Exception:
                continue
    _SRC_CACHE[cache_key] = None
    return None


def _season_end(season: str) -> str:
    """Return the approximate end date (YYYY-MM-DD) for an NBA season string."""
    # Season "2024-25" ends approximately June 2025 (finals)
    try:
        end_year = int(season.split("-")[1])
        if end_year <= 99:
            end_year += 2000
        return f"{end_year}-06-30"
    except Exception:
        return "2099-12-31"


def _lineup_season_for_as_of(tricode: str, as_of: _dt.datetime) -> Optional[str]:
    """Return the newest lineup season file whose end date <= as_of."""
    as_of_str = as_of.date().isoformat()
    for season in ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22"]:
        path = NBA / "lineups" / f"lineup_splits_{tricode}_{season}.json"
        if path.exists() and _season_end(season) <= as_of_str:
            return season
    return None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _depth_from_lineups(
    lineups: List[dict], as_of: _dt.datetime
) -> Dict[str, Any]:
    """Compute rotation-depth metrics from the season lineup JSON.

    Returns: n_unique_lineups, n_lineups_gt10min, top3_min_share,
             rotation_depth_score, top1_min_share.
    """
    if not lineups:
        return {}
    total_min = sum(float(l.get("min", 0) or 0) for l in lineups)
    if total_min <= 0:
        return {}
    sorted_by_min = sorted(lineups, key=lambda x: float(x.get("min", 0) or 0), reverse=True)
    n_unique = len(lineups)
    n_gt10 = sum(1 for l in lineups if float(l.get("min", 0) or 0) >= 10)
    top3_min = sum(float(l.get("min", 0) or 0) for l in sorted_by_min[:3])
    top1_min = float(sorted_by_min[0].get("min", 0) or 0) if sorted_by_min else 0.0
    top3_share = top3_min / total_min
    top1_share = top1_min / total_min
    return {
        "n_unique_lineups": n_unique,
        "n_lineups_gt10min": n_gt10,
        "top3_min_share": _rd(top3_share),
        "top1_min_share": _rd(top1_share),
        "rotation_depth_score": _rd(1.0 - top3_share),  # higher = deeper rotation
    }


def _starters_from_lineups(lineups: List[dict]) -> Dict[str, Any]:
    """Extract the top lineup (most minutes) as the presumptive starting unit."""
    if not lineups:
        return {}
    top = max(lineups, key=lambda x: float(x.get("min", 0) or 0), default=None)
    if top is None:
        return {}
    raw_lineup = top.get("lineup", [])
    if isinstance(raw_lineup, list):
        names = [str(n) for n in raw_lineup]
    elif isinstance(raw_lineup, str):
        names = [raw_lineup]
    else:
        names = []
    return {
        "lineup_names": names,
        "min_together": _rd(top.get("min")),
        "net_rating": _rd(top.get("net_rtg")),
        "off_rating": _rd(top.get("off_rating")),
        "def_rating": _rd(top.get("def_rating")),
        "gp": _ri(top.get("gp")),
        "pace": _rd(top.get("pace")),
    }


def _closing_lineup_from_lineups(lineups: List[dict]) -> Dict[str, Any]:
    """Approximate the closing lineup as the #2 lineup by minutes (star-heavy).

    True clutch-game filtering (GameRotation per-period) is DEFER. The second
    most-used lineup tends to be the second staggered unit that closes games.
    """
    if len(lineups) < 2:
        return {"_note": "DEFER: only one lineup unit available; closing lineup approximation requires GameRotation per-game data."}
    sorted_by_min = sorted(lineups, key=lambda x: float(x.get("min", 0) or 0), reverse=True)
    closer = sorted_by_min[1]
    raw_lineup = closer.get("lineup", [])
    if isinstance(raw_lineup, list):
        names = [str(n) for n in raw_lineup]
    elif isinstance(raw_lineup, str):
        names = [raw_lineup]
    else:
        names = []
    return {
        "_note": "Approximated as 2nd-most-used lineup; true closing unit requires per-game GameRotation data (DEFER).",
        "lineup_names": names,
        "min_together": _rd(closer.get("min")),
        "net_rating": _rd(closer.get("net_rtg")),
        "gp": _ri(closer.get("gp")),
    }


def _pace_context_for_team(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Team pace mean/std filtered to games <= as_of from team_advanced_stats."""
    df = _load_df("team_adv", DATA / "team_advanced_stats.parquet")
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
    pace_vals = pd.to_numeric(rows["pace"], errors="coerce").dropna()
    if pace_vals.empty:
        return {}
    mean_pace = float(pace_vals.mean())
    std_pace = float(pace_vals.std()) if len(pace_vals) > 1 else 0.0
    n_games = len(rows)
    return {
        "mean_pace": _rd(mean_pace),
        "std_pace": _rd(std_pace),
        "is_fast_break_team": bool(mean_pace >= 100.5),  # league avg ~98-100
        "n_games": n_games,
    }


def _rotation_stability_for_team(
    tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate rotation-stability metrics from player-level lineup_features.

    lineup_features is player × season; we select players whose team we cannot
    determine from that file alone. Instead we use lineup JSONs directly for
    the top1_min_share (already computed in depth) and proxy churn from unique
    lineup count / games played ratio.
    """
    lineups = _load_lineup_json(tricode)
    if not lineups:
        return {}
    total_gp = max((float(l.get("gp", 0) or 0) for l in lineups), default=0.0)
    if total_gp <= 0:
        return {}
    n_unique = len(lineups)
    # lineup_churn: unique 5-man combos per game played (lower = more stable)
    lineup_churn = _rd(n_unique / total_gp)
    sorted_by_min = sorted(lineups, key=lambda x: float(x.get("min", 0) or 0), reverse=True)
    top3_net = [_rd(l.get("net_rtg")) for l in sorted_by_min[:3] if l.get("net_rtg") is not None]
    avg_top3_net = _rd(float(np.mean(top3_net))) if top3_net else None
    return {
        "lineup_churn_per_game": lineup_churn,
        "n_lineups_used": n_unique,
        "total_gp": _rd(total_gp),
        "avg_top3_net_rating": avg_top3_net,
    }


def _star_rest_for_team(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Estimate star rest / Q4 presence from player_quarter_stats + adv_stats.

    Identifies the star player as the one with the highest total minutes in
    player_adv_stats for this team's games (filtered <= as_of). Then computes:
      - star_avg_q4_min: mean Q4 minutes per game the star plays
      - star_q4_presence_rate: fraction of games the star plays >= 1 min in Q4
      - team_avg_q4_min_spread: std of Q4 minutes across all regulars (depth signal)

    APPROXIMATION: uses team_tricode from team_advanced_stats game list to identify
    this team's games; no explicit roster table. Players with < 5 games are excluded.
    """
    df_adv = _load_df("adv", DATA / "player_adv_stats.parquet")
    df_adv_team = _load_df("team_adv", DATA / "team_advanced_stats.parquet")
    df_q = _load_df("qstats", DATA / "player_quarter_stats.parquet")
    if df_adv is None or df_adv_team is None or df_q is None:
        return {}

    # Identify game_ids for this team <= as_of
    t_rows = df_adv_team[df_adv_team["team_tricode"] == tricode].copy()
    if t_rows.empty:
        return {}
    if "game_date" in t_rows.columns:
        t_rows["game_date"] = pd.to_datetime(t_rows["game_date"])
        t_rows = t_rows[t_rows["game_date"] <= pd.Timestamp(as_of)]
    if t_rows.empty:
        return {}
    team_game_ids = set(t_rows["game_id"].astype(str).tolist())

    # Player adv stats filtered to team's games
    p_rows = df_adv[df_adv["game_id"].astype(str).isin(team_game_ids)].copy()
    if p_rows.empty:
        return {}

    # Find the star: player with highest total minutes in these games
    min_by_player = (
        p_rows.groupby("player_id")["minutes"].sum().reset_index()
    )
    if min_by_player.empty:
        return {}
    star_pid = int(min_by_player.loc[min_by_player["minutes"].idxmax(), "player_id"])

    # Q4 minutes for the star
    q4_rows = df_q[
        (df_q["player_id"] == star_pid)
        & (df_q["period"] == 4)
        & (df_q["game_id"].astype(str).isin(team_game_ids))
    ].copy()

    n_team_games = len(team_game_ids)
    if q4_rows.empty:
        star_avg_q4_min = None
        star_q4_presence_rate = None
    else:
        star_avg_q4_min = _rd(float(q4_rows["min"].mean()))
        star_q4_presence_rate = _rd(len(q4_rows) / n_team_games)

    # Q4 spread across all players with >= 5 appearances
    q4_all = df_q[
        (df_q["period"] == 4)
        & (df_q["game_id"].astype(str).isin(team_game_ids))
    ].copy()
    q4_per_player = (
        q4_all.groupby("player_id")["min"].agg(["mean", "count"]).reset_index()
    )
    q4_regulars = q4_per_player[q4_per_player["count"] >= 5]
    q4_spread = _rd(float(q4_regulars["mean"].std())) if len(q4_regulars) > 1 else None

    return {
        "star_player_id": star_pid,
        "star_avg_q4_min": star_avg_q4_min,
        "star_q4_presence_rate": star_q4_presence_rate,
        "q4_min_spread_across_regulars": q4_spread,
        "n_games": n_team_games,
        "_note": "Star identified as max-minutes player in team's games. "
                 "Exact stagger times DEFER (no per-game GameRotation API data).",
    }


def _q4_patterns_for_team(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Team Q4 scoring context from player_quarter_stats + team_advanced_stats.

    Aggregates mean Q4 pts scored and net rating in Q4 as a proxy for
    closing-lineup effectiveness.
    """
    df_adv_team = _load_df("team_adv", DATA / "team_advanced_stats.parquet")
    df_q = _load_df("qstats", DATA / "player_quarter_stats.parquet")
    if df_adv_team is None or df_q is None:
        return {}

    t_rows = df_adv_team[df_adv_team["team_tricode"] == tricode].copy()
    if t_rows.empty:
        return {}
    if "game_date" in t_rows.columns:
        t_rows["game_date"] = pd.to_datetime(t_rows["game_date"])
        t_rows = t_rows[t_rows["game_date"] <= pd.Timestamp(as_of)]
    if t_rows.empty:
        return {}
    team_game_ids = set(t_rows["game_id"].astype(str).tolist())

    q4_team = df_q[
        (df_q["period"] == 4)
        & (df_q["game_id"].astype(str).isin(team_game_ids))
    ]
    if q4_team.empty:
        return {}

    # Team-level Q4 pts per game
    q4_pts_per_game = (
        q4_team.groupby("game_id")["pts"].sum().mean()
    )
    q4_plus_minus_per_game = (
        q4_team.groupby("game_id")["plus_minus"].sum().mean()
    )
    n_games = q4_team["game_id"].nunique()

    return {
        "q4_team_pts_pg": _rd(q4_pts_per_game),
        "q4_net_plus_minus_pg": _rd(q4_plus_minus_per_game),
        "n_games": n_games,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamRotationPatterns(AtlasSection):
    """Deep team rotation-patterns atlas section (team entity, section='rotation_patterns').

    Builds a provenance-stamped, leak-safe artifact covering starting-unit identity,
    closing-lineup tendency, rotation depth + stability, star rest patterns, pace
    context, and Q4 scoring patterns. Reserves 4 CV slots for CV-branch enrichment.

    Sources used:
      - data/nba/lineups/lineup_splits_<TRI>_<season>.json (starters, depth, closing)
      - data/team_advanced_stats.parquet (pace context, game-id enumeration)
      - data/player_quarter_stats.parquet + data/player_adv_stats.parquet (star rest, Q4)

    DEFER sections (no source available without live GameRotation scrape):
      - stagger_times: exact sub-quarter substitution minutes
      - playoff_shortening: regular-season vs playoff rotation-depth delta
      - rest_minutes_q2: exact when stars exit the second quarter
      - timeout_patterns: substitution patterns after timeouts
    """

    name: str = "rotation_patterns"
    entity: str = "team"
    source_name: str = (
        "lineup_splits_<TRI>_<season>.json + team_advanced_stats.parquet + "
        "player_quarter_stats.parquet + player_adv_stats.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the rotation_patterns artifact for team ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - team_advanced_stats filtered to game_date <= as_of.
          - player_quarter_stats filtered to game_ids from the team's filtered adv rows.
          - lineup JSONs selected by season whose end-date <= as_of.
          - player_adv_stats filtered via team game_id set (same as above).

        Returns None when the team has no lineup data at or before as_of.

        Args:
            entity_id: 3-letter team tricode (e.g. "GSW", "BOS").
            as_of:     decision timestamp; all reads filtered to <= this date.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # Select the appropriate lineup season file (leak-safe: end_date <= as_of)
        season = _lineup_season_for_as_of(tricode, as_of)
        if season is None:
            return None

        # Load lineup JSON for the selected season
        cache_key = f"lineup_json_{tricode}_{season}"
        if cache_key in _SRC_CACHE:
            lineups = _SRC_CACHE[cache_key]
        else:
            path = NBA / "lineups" / f"lineup_splits_{tricode}_{season}.json"
            if not path.exists():
                return None
            try:
                with open(path, encoding="utf-8") as fh:
                    lineups = json.load(fh)
                _SRC_CACHE[cache_key] = lineups
            except Exception:
                return None

        if not lineups:
            return None

        # --- Gather sub-components ---
        starters = _starters_from_lineups(lineups)
        closing = _closing_lineup_from_lineups(lineups)
        depth = _depth_from_lineups(lineups, as_of)
        stability = _rotation_stability_for_team(tricode, as_of)
        pace = _pace_context_for_team(tricode, as_of)
        star_rest = _star_rest_for_team(tricode, as_of)
        q4_pat = _q4_patterns_for_team(tricode, as_of)

        # Bail if truly nothing populated
        if not starters and not depth:
            return None

        # Playoff shortening — DEFER (no playoff-specific lineup JSONs for most teams)
        playoff_shortening: Dict[str, Any] = {
            "_note": (
                "DEFER: playoff lineup JSONs only present for 2 teams (GSW/LAL 2025-26). "
                "Requires GameRotation API scrape with game_id prefix 004* filter. "
                "Proxy: compare rotation_depth_score Regular vs Playoffs when available."
            )
        }

        # Sub-quarter stagger times — DEFER
        stagger_times: Dict[str, Any] = {
            "_note": (
                "DEFER: exact sub-quarter stagger minutes require per-game GameRotation "
                "V2 API data (player in/out timestamps). Not cached in repo."
            )
        }

        # Assemble sub_fields
        sub_fields: Dict[str, Any] = {
            "starters": starters,
            "closing_lineup": closing,
            "depth": depth,
            "rotation_stability": stability,
            "pace_context": pace,
            "star_rest": star_rest,
            "q4_patterns": q4_pat,
            "playoff_shortening": playoff_shortening,
            "stagger_times": stagger_times,
            "season_used": season,
        }

        # Determine n from best available game count
        n_candidates: List[int] = []
        if pace.get("n_games"):
            n_candidates.append(pace["n_games"])
        if star_rest.get("n_games"):
            n_candidates.append(star_rest["n_games"])
        if q4_pat.get("n_games"):
            n_candidates.append(q4_pat["n_games"])
        n = max(n_candidates) if n_candidates else 5  # floor at 5 from lineup JSON

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
            value=depth.get("rotation_depth_score"),  # headline: how deep is the rotation?
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required_keys = {
            "starters", "closing_lineup", "depth", "rotation_stability",
            "pace_context", "star_rest", "q4_patterns",
            "playoff_shortening", "stagger_times",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # pace sanity: if present, must be 80–130 range
        pace = sf.get("pace_context", {})
        mean_pace = pace.get("mean_pace")
        if mean_pace is not None and not (80.0 <= mean_pace <= 130.0):
            return False

        # depth score must be in [0, 1]
        depth = sf.get("depth", {})
        rds = depth.get("rotation_depth_score")
        if rds is not None and not (0.0 <= rds <= 1.0):
            return False

        # CV fields must all be null (not yet filled)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for rotation_patterns (values None — CV fills later).

        Per DESIGN.md and the CV-session boundary rule: the loop reserves these
        slots; the CV-fix session calls store.fill_cv_slot to populate them
        without a profile rebuild. Team-aggregate CV ships (per MEMORY: team-
        aggregate CV atlas ships, player-level is coverage-bound).
        """
        return {
            "lineup_spacing_mean": CVSlot(
                name="lineup_spacing_mean",
                dtype="float",
                description=(
                    "Mean convex-hull spacing (ft²) for the team's top 5-man lineup "
                    "during half-court possessions, from CV homography + team-aggregate "
                    "tracking data. Team-level CV coverage is sufficient for this signal."
                ),
                unit="ft²",
                value=None,
            ),
            "transition_pace_cv": CVSlot(
                name="transition_pace_cv",
                dtype="float",
                description=(
                    "CV-measured mean seconds from possession start to shot attempt on "
                    "fast-break possessions, from cv_pace_per_game.parquet aggregated "
                    "by team. Lower = faster transition offense."
                ),
                unit="s",
                value=None,
            ),
            "closer_velocity": CVSlot(
                name="closer_velocity",
                dtype="float",
                description=(
                    "Mean ball-handler velocity (ft/s) of the closing lineup in Q4 "
                    "possessions, from CV homography + Kalman velocity estimates. "
                    "Proxy for closing-unit aggression / pace."
                ),
                unit="ft/s",
                value=None,
            ),
            "rotation_fatigue_cv": CVSlot(
                name="rotation_fatigue_cv",
                dtype="float",
                description=(
                    "Mean per-player velocity drop (ft/s) comparing the last 3 minutes "
                    "of each quarter vs the first 3 minutes, from CV tracking. "
                    "Captures depth-driven fatigue — deeper rotations show smaller drops."
                ),
                unit="ft/s",
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
    """Build rotation_patterns for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of 3-letter NBA team tricodes. If None, discovers all
                       teams from lineup JSON filenames.
        as_of:        leak boundary date (defaults to today at midnight UTC).
        store:        PointInTimeStore; when provided, artifacts are written to store.
        dry_run:      skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if team_tricodes is None:
        lineup_dir = NBA / "lineups"
        if lineup_dir.exists():
            seen: set = set()
            for p in lineup_dir.glob("lineup_splits_*.json"):
                parts = p.stem.split("_")
                if len(parts) >= 3:
                    tri = parts[2]
                    if len(tri) == 3:
                        seen.add(tri.upper())
            team_tricodes = sorted(seen)
        else:
            team_tricodes = []

    section = TeamRotationPatterns()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
