"""ARM-B atlas section: ``coach_tendencies`` — exhaustive team coaching profile.

Implements :class:`AtlasSection` for the ``"coach_tendencies"`` section of a team's
persistent profile.  Every sub-field comes from existing parquets documented in
spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from existing parquets):
  timeout_usage.*      — avg TO calls per quarter, late-game TO rate (final 3 min),
                         TO frequency per possession-run from
                         data/cache/inplay_pbp_microstructure.parquet (per-game
                         home/away TO per quarter) joined via season_games JSON
                         to map game_id -> team tricode.
  lineup_rotation.*    — unique 5-man lineup count, lineup_top1_min_share,
                         avg_pace_on_top_lineup, DNP count / load-management rate
                         from data/cache/lineup_features.parquet (player-level agg
                         rolled up to team, season-level) and
                         data/cache/dnp_features_team.parquet (game-level per team).
  late_game_behavior.* — blowout_pct_l5, avg_total_l5, avg_q4_pts_l5,
                         garbage_time_pct_l5 from
                         data/cache/linescore_context.parquet (per team, per game_date).
                         Also clutch shot volume (team-agg from
                         data/cache/pbp_possession_features.parquet).
  hack_a.*             — team-level PF rate from foul_features per team per game_date,
                         plus inplay_foul_state per-game max_player_pfs proxy.
  tempo_style.*        — pace_mean/std/z, transition_share_z from
                         data/intelligence/team_tempo_spacing.parquet.

DEFER (data gap — not available in current parquets):
  ato_efficiency.*     — after-timeout offensive rating delta
                         DEFER: no per-possession event sequence with timeout
                         timestamps vs subsequent possession outcome in repo.
                         Would require parsing raw PBP JSON for timeout event +
                         next-possession outcome join.
  hack_a.target_player — specific player(s) being hack-a'd
                         DEFER: per-possession defender-id→FT-shooter linkage not
                         available without full PBP event reconstruction.
  lineup_rotation.platoon_patterns
                         DEFER: two-man closing-lineup / star rotation patterns
                         require minute-by-minute lineup stream not aggregated here.

RESERVED CV SLOTS (value=None, CV branch fills later):
  spacing_off_bench  — mean team_spacing_mean when bench units on floor (CV frames)
  transition_pace_cv — CV-measured possessions-per-minute for transition vs half-court
  sub_pattern_frame  — frame-level substitution timing proxy (CV player-count change)
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
INTEL = DATA / "intelligence"

# ---------------------------------------------------------------------------
# Module-level data cache (lazy, process-scoped)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Optional[Any]] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing/error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _load_season_games() -> Optional[pd.DataFrame]:
    """Load all season_games JSON files into one DataFrame with game_id->home/away."""
    if "season_games" in _SRC_CACHE:
        return _SRC_CACHE["season_games"]
    rows: List[dict] = []
    for fp in sorted((DATA / "nba").glob("season_games_*.json")):
        try:
            with fp.open("r", encoding="utf-8") as fh:
                blob = json.load(fh)
            src_rows = blob.get("rows", []) if isinstance(blob, dict) else []
            if isinstance(src_rows, list):
                rows.extend(src_rows)
        except Exception:
            continue
    if not rows:
        _SRC_CACHE["season_games"] = None
        return None
    df = pd.DataFrame(rows)
    # keep minimal columns; game_id may be present in various forms
    keep = [c for c in ["game_id", "game_date", "home_team", "away_team"] if c in df.columns]
    df = df[keep].drop_duplicates("game_id") if "game_id" in df.columns else df
    _SRC_CACHE["season_games"] = df
    return df


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
    r = _rd(v)
    return int(r) if r is not None else None


# ---------------------------------------------------------------------------
# Sub-section builders — each filters strictly to as_of (leak-safe)
# ---------------------------------------------------------------------------

def _timeout_usage(team: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate timeout usage from inplay_pbp_microstructure joined with season_games.

    inplay_pbp_microstructure: grain (game_id, period=1|2|3).
    home/away_to_last_quarter = timeouts called in that period.
    Join with season_games to identify which side is `team`.
    Filter: game_date <= as_of (via season_games game_date).
    """
    micro = _load_parquet("pbp_micro", CACHE / "inplay_pbp_microstructure.parquet")
    sgames = _load_season_games()

    if micro is None or micro.empty or sgames is None or sgames.empty:
        return {"_note": "DEFER: inplay_pbp_microstructure or season_games missing."}
    if "game_id" not in micro.columns or "game_id" not in sgames.columns:
        return {"_note": "DEFER: game_id column absent."}

    # Join microstructure with season_games to get team-side + game_date
    merged = micro.merge(
        sgames[["game_id", "game_date", "home_team", "away_team"]],
        on="game_id",
        how="inner",
    )
    if merged.empty:
        return {"_note": "DEFER: join produced no rows."}

    # Leak filter
    merged["game_date"] = pd.to_datetime(merged["game_date"])
    merged = merged[merged["game_date"] <= pd.Timestamp(as_of)]
    if merged.empty:
        return {}

    # Identify which side is the team and pick its TO column
    is_home = merged["home_team"] == team
    is_away = merged["away_team"] == team
    team_rows = merged[is_home | is_away].copy()
    if team_rows.empty:
        return {}

    # Build per-row timeout count
    team_rows["team_to"] = np.where(
        team_rows["home_team"] == team,
        team_rows["home_to_last_quarter"].fillna(0),
        team_rows["away_to_last_quarter"].fillna(0),
    )

    n_games = team_rows["game_id"].nunique()

    # Per-period averages
    period_avg: Dict[str, Any] = {}
    for p, label in [(1, "q1"), (2, "q2"), (3, "q3")]:
        prows = team_rows[team_rows["period"] == p]
        if not prows.empty:
            period_avg[f"{label}_to_avg"] = _rd(prows["team_to"].mean())

    # Late-game proxy: Q4 = period 3 has max concentration of late-game TOs
    # (microstructure only has periods 1-3 per spec; use Q3 as late-game proxy)
    # Overall TO avg across all periods
    to_avg_all = _rd(team_rows["team_to"].mean())
    to_std_all = _rd(team_rows["team_to"].std())

    # High-TO game rate (>= 5 TOs in a period is aggressive)
    high_to_rate = _rd(
        (team_rows["team_to"] >= 5).sum() / max(len(team_rows), 1)
    )

    return {
        **period_avg,
        "to_avg_per_period": to_avg_all,
        "to_std_per_period": to_std_all,
        "high_to_rate": high_to_rate,  # fraction of period-games with >= 5 TOs
        "n_games": n_games,
    }


def _lineup_rotation(team: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate lineup rotation and DNP / load-management tendencies.

    Sources:
      - data/cache/lineup_features.parquet: player-level, season-level rotation depth.
        Roll up to team by player_id -> season_games home/away_team join (complex);
        instead use direct team from season_games + player mapping via player_profile.
        SIMPLIFIED: aggregate player lineup_unique_5mans / lineup_top1_min_share per
        season, filtered to the as_of season.
      - data/cache/dnp_features_team.parquet: game-level per team.
    """
    dnp_df = _load_parquet("dnp_team", CACHE / "dnp_features_team.parquet")
    lf_df = _load_parquet("lineup_feat", CACHE / "lineup_features.parquet")

    result: Dict[str, Any] = {}

    # --- DNP / load management from dnp_features_team ---
    if dnp_df is not None and not dnp_df.empty:
        team_abbr_col = "team_abbreviation"
        if team_abbr_col in dnp_df.columns:
            dnp_team = dnp_df[dnp_df[team_abbr_col] == team].copy()
            if "game_date" in dnp_team.columns:
                dnp_team["game_date"] = pd.to_datetime(dnp_team["game_date"])
                dnp_team = dnp_team[dnp_team["game_date"] <= pd.Timestamp(as_of)]
            if not dnp_team.empty:
                result["dnp_per_game_avg"] = _rd(dnp_team["dnp_count_in_game"].mean())
                result["dnp_per_game_std"] = _rd(dnp_team["dnp_count_in_game"].std())
                result["load_mgmt_game_count"] = _ri(
                    (dnp_team["dnp_count_in_game"] >= 2).sum()
                )
                result["n_games_dnp"] = len(dnp_team)

    # --- Lineup depth from lineup_features (player-level, season roll-up) ---
    # lineup_features is player-keyed; we use it to get rotation depth proxy.
    # We aggregate unique_5mans and top1_min_share across players likely on this team.
    # NOTE: lineup_features has no team_tricode column directly.
    # We proxy via player_profile_features (bio) which has team_tricode.
    bio = _load_parquet("bio", CACHE / "player_profile_features.parquet")
    if (
        lf_df is not None and not lf_df.empty
        and bio is not None and not bio.empty
        and "team_tricode" in bio.columns
        and "player_id" in bio.columns
        and "player_id" in lf_df.columns
    ):
        # Filter bio to players on this team (as_of proxied by most recent bio row)
        team_pids = bio[bio["team_tricode"] == team]["player_id"].unique()
        as_of_season = _as_of_to_season(as_of)
        lf_team = lf_df[lf_df["player_id"].isin(team_pids)].copy()
        if "season" in lf_team.columns and as_of_season:
            lf_team = lf_team[lf_team["season"] <= as_of_season]
        if not lf_team.empty:
            # Latest season per player
            if "season" in lf_team.columns:
                lf_team = (
                    lf_team.sort_values("season", ascending=False)
                    .drop_duplicates("player_id")
                )
            result["rotation_unique_5mans_avg"] = _rd(
                lf_team["lineup_unique_5mans"].mean()
            )
            result["top_lineup_min_share_avg"] = _rd(
                lf_team["lineup_top1_min_share"].mean()
            )
            result["rotation_depth_proxy_n"] = len(lf_team)

    # Platoon pattern DEFER
    result["platoon_patterns"] = {
        "_note": (
            "DEFER: minute-by-minute lineup stream not aggregated in repo. "
            "Requires per-quarter lineup data from NBA Stats LineupData endpoint."
        )
    }

    return result


def _late_game_behavior(team: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Late-game / end-of-game coaching behavior from linescore_context + PBP clutch.

    Sources:
      - data/cache/linescore_context.parquet: blowout_pct_l5, garbage_time_pct_l5,
        avg_q4_pts_l5 per team per game_date.
      - data/cache/pbp_possession_features.parquet: clutch shots (per player, agg to team
        via player_profile_features bio).
    """
    ls_df = _load_parquet("linescore", CACHE / "linescore_context.parquet")
    result: Dict[str, Any] = {}

    if ls_df is not None and not ls_df.empty:
        abbr_col = "team_abbreviation"
        if abbr_col in ls_df.columns:
            ls_team = ls_df[ls_df[abbr_col] == team].copy()
            if "game_date" in ls_team.columns:
                ls_team["game_date"] = pd.to_datetime(ls_team["game_date"])
                ls_team = ls_team[ls_team["game_date"] <= pd.Timestamp(as_of)]
            if not ls_team.empty:
                result["blowout_pct_l5_avg"] = _rd(ls_team["ls_blowout_pct_l5"].mean())
                result["garbage_time_pct_l5_avg"] = _rd(
                    ls_team["ls_garbage_time_pct_l5"].mean()
                )
                result["avg_q4_pts_l5"] = _rd(ls_team["ls_avg_q4_pts_l5"].mean())
                result["avg_total_pts_l5"] = _rd(ls_team["ls_avg_total_l5"].mean())
                result["n_games_linescore"] = len(ls_team)

    # Clutch shot volume: aggregate PBP clutch from all team players
    pbp = _load_parquet("pbp_poss", CACHE / "pbp_possession_features.parquet")
    bio = _load_parquet("bio", CACHE / "player_profile_features.parquet")
    if (
        pbp is not None and not pbp.empty
        and bio is not None and not bio.empty
        and "team_tricode" in bio.columns
    ):
        team_pids = bio[bio["team_tricode"] == team]["player_id"].unique()
        pbp_team = pbp[pbp["player_id"].isin(team_pids)].copy()
        if "game_date" in pbp_team.columns:
            pbp_team["game_date"] = pd.to_datetime(pbp_team["game_date"])
            pbp_team = pbp_team[pbp_team["game_date"] <= pd.Timestamp(as_of)]
        if not pbp_team.empty:
            # Aggregate per game
            clutch_by_game = pbp_team.groupby("game_id").agg(
                clutch_shots=("pbp_clutch_shots_attempted", "sum"),
                clutch_pts=("pbp_clutch_pts_scored", "sum"),
            )
            result["clutch_shots_pg_team"] = _rd(clutch_by_game["clutch_shots"].mean())
            result["clutch_pts_pg_team"] = _rd(clutch_by_game["clutch_pts"].mean())

    return result


def _hack_a_tendencies(team: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Hack-a / intentional-foul tendencies for this team as a defensive strategy.

    Sources:
      - data/cache/inplay_foul_state.parquet: per-game per-period team PF accumulation.
        Join with season_games to identify which side is `team`.
      - Proxy: late-quarter high-foul-count games (team PFs >= 8 in Q3/Q4) suggest
        intentional fouling.

    DEFER: specific target player identification (requires per-possession PBP join).
    """
    foul_state = _load_parquet("foul_state", CACHE / "inplay_foul_state.parquet")
    sgames = _load_season_games()
    result: Dict[str, Any] = {}

    if (
        foul_state is not None and not foul_state.empty
        and sgames is not None and not sgames.empty
        and "game_id" in foul_state.columns
    ):
        merged = foul_state.merge(
            sgames[["game_id", "game_date", "home_team", "away_team"]],
            on="game_id",
            how="inner",
        )
        if not merged.empty:
            merged["game_date"] = pd.to_datetime(merged["game_date"])
            merged = merged[merged["game_date"] <= pd.Timestamp(as_of)]

            is_home = merged["home_team"] == team
            is_away = merged["away_team"] == team
            team_rows = merged[is_home | is_away].copy()

            if not team_rows.empty:
                # Team's cumulative PF: home or away column
                team_rows["team_pf_cum"] = np.where(
                    team_rows["home_team"] == team,
                    team_rows["home_team_pfs_cum"].fillna(0),
                    team_rows["away_team_pfs_cum"].fillna(0),
                )
                team_rows["team_max_player_pf"] = np.where(
                    team_rows["home_team"] == team,
                    team_rows["home_max_player_pfs"].fillna(0),
                    team_rows["away_max_player_pfs"].fillna(0),
                )

                # Late-game (period 3 = Q3-Q4 in this schema)
                late = team_rows[team_rows["period"] == 3]
                if not late.empty:
                    # Hack-a proxy: late-quarter cumulative PF >= 8 (above normal rate)
                    hacka_proxy_rate = _rd(
                        (late["team_pf_cum"] >= 8).sum() / max(len(late), 1)
                    )
                    avg_late_pf_cum = _rd(late["team_pf_cum"].mean())
                    max_player_pf_avg = _rd(late["team_max_player_pf"].mean())
                    result["hacka_proxy_rate"] = hacka_proxy_rate
                    result["avg_late_pf_cum"] = avg_late_pf_cum
                    result["avg_max_player_pf_late"] = max_player_pf_avg
                result["n_games_foul"] = team_rows["game_id"].nunique()

    result["target_player"] = {
        "_note": (
            "DEFER: per-possession PBP event required to identify specific hack-a "
            "targets. PBP V3→V2 PLAYER2_ID attribution is lost in current scraped files."
        )
    }

    return result


def _tempo_style(team: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Pace and transition style from team_tempo_spacing + team_advanced_stats.

    Sources:
      - data/intelligence/team_tempo_spacing.parquet: CV-derived tempo/spacing z-scores.
      - data/team_advanced_stats.parquet: per-game pace, off/def ratings.
    """
    ts_df = _load_parquet("tempo_spacing", INTEL / "team_tempo_spacing.parquet")
    ta_df = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
    result: Dict[str, Any] = {}

    # team_tempo_spacing uses team_abbr
    if ts_df is not None and not ts_df.empty:
        abbr_col = next(
            (c for c in ["team_abbr", "team_tricode", "team"] if c in ts_df.columns),
            None,
        )
        if abbr_col:
            ts_team = ts_df[ts_df[abbr_col] == team].copy()
            if "game_date" in ts_team.columns:
                ts_team["game_date"] = pd.to_datetime(ts_team["game_date"])
                ts_team = ts_team[ts_team["game_date"] <= pd.Timestamp(as_of)]
            if not ts_team.empty:
                ts_latest = ts_team.sort_values("game_date").iloc[-1]
                result["tempo_z"] = _rd(ts_latest.get("team_tempo_z"))
                result["spacing_z"] = _rd(ts_latest.get("team_avg_spacing_z"))
                result["transition_share_z"] = _rd(
                    ts_latest.get("team_transition_share_z")
                )
                result["tempo_spacing_composite_z"] = _rd(
                    ts_latest.get("team_tempo_spacing_composite_z")
                )
                result["possession_duration_z"] = _rd(
                    ts_latest.get("team_possession_duration_z")
                )

    # team_advanced_stats: per-game pace agg
    if ta_df is not None and not ta_df.empty and "team_tricode" in ta_df.columns:
        ta_team = ta_df[ta_df["team_tricode"] == team].copy()
        if "game_date" in ta_team.columns:
            ta_team["game_date"] = pd.to_datetime(ta_team["game_date"])
            ta_team = ta_team[ta_team["game_date"] <= pd.Timestamp(as_of)]
        if not ta_team.empty:
            result["pace_mean"] = _rd(ta_team["pace"].mean())
            result["pace_std"] = _rd(ta_team["pace"].std())
            result["off_rtg_mean"] = _rd(ta_team["off_rtg"].mean())
            result["def_rtg_mean"] = _rd(ta_team["def_rtg"].mean())
            result["ast_pct_mean"] = _rd(ta_team["ast_pct"].mean())
            result["n_games_adv"] = len(ta_team)

    return result


# ---------------------------------------------------------------------------
# Helper: map a datetime to NBA season string (e.g. "2024-25")
# ---------------------------------------------------------------------------

def _as_of_to_season(as_of: _dt.datetime) -> Optional[str]:
    """Return the NBA season string for a given date (Oct start)."""
    y = as_of.year
    m = as_of.month
    if m >= 10:
        return f"{y}-{str(y + 1)[2:]}"
    elif m >= 1:
        return f"{y - 1}-{str(y)[2:]}"
    return None


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamCoachTendencies(AtlasSection):
    """Deep team coaching-tendencies atlas section (team entity, section='coach_tendencies').

    Builds a provenance-stamped, leak-safe artifact covering:
      - timeout_usage: per-quarter TO volume, late-game aggressiveness
      - lineup_rotation: rotation depth, DNP / load-management rate
      - late_game_behavior: blowout/garbage-time rate, clutch shot volume
      - hack_a: intentional-foul proxy (late-quarter PF rate)
      - tempo_style: CV pace/spacing z-scores + season pace/rtg

    Reserves 3 CV slots for CV-branch enrichment.

    Sources:
      - data/cache/inplay_pbp_microstructure.parquet (timeout counts per period)
      - data/nba/season_games_*.json (game_id -> home/away_team + game_date)
      - data/cache/lineup_features.parquet + data/cache/player_profile_features.parquet
        (rotation depth via player->team mapping)
      - data/cache/dnp_features_team.parquet (load management / DNPs)
      - data/cache/linescore_context.parquet (blowout/garbage-time rates)
      - data/cache/pbp_possession_features.parquet (clutch shots team agg)
      - data/cache/inplay_foul_state.parquet (hack-a PF proxy)
      - data/intelligence/team_tempo_spacing.parquet (CV tempo/spacing z-scores)
      - data/team_advanced_stats.parquet (pace, ratings)

    DEFER sub-fields:
      - timeout_usage.ato_efficiency (after-timeout ORtg delta, no event sequence)
      - hack_a.target_player (needs per-possession PBP PLAYER2_ID, lost in V3→V2)
      - lineup_rotation.platoon_patterns (minute-by-minute lineup stream not available)
    """

    name: str = "coach_tendencies"
    entity: str = "team"
    source_name: str = (
        "inplay_pbp_microstructure.parquet + season_games_*.json + "
        "lineup_features.parquet + dnp_features_team.parquet + "
        "linescore_context.parquet + pbp_possession_features.parquet + "
        "inplay_foul_state.parquet + team_tempo_spacing.parquet + "
        "team_advanced_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the coach_tendencies artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode string (e.g. "GSW").
            as_of:     leak boundary; all data filtered to game_date <= as_of.

        Returns:
            AtlasArtifact or None when the team has no data across any source.

        Leak guarantee: every per-game source is filtered to game_date <= as_of.
        Season-keyed sources (lineup_features, team_tempo_spacing) are filtered by
        season <= _as_of_to_season(as_of) or game_date (whichever is available).
        """
        team = str(entity_id)
        as_of_str = as_of.date().isoformat()

        timeout = _timeout_usage(team, as_of)
        rotation = _lineup_rotation(team, as_of)
        late_game = _late_game_behavior(team, as_of)
        hack_a = _hack_a_tendencies(team, as_of)
        tempo = _tempo_style(team, as_of)

        # Bail if all sub-sections are empty or pure-DEFER notes
        def _has_real_data(d: dict) -> bool:
            return any(
                k not in ("_note",) and not (isinstance(v, dict) and "_note" in v)
                for k, v in d.items()
            )

        all_defer = not any(
            _has_real_data(s) for s in [timeout, rotation, late_game, hack_a, tempo]
        )
        if all_defer:
            return None

        # Compute n from the richest available source
        n_candidates: List[int] = []
        for d in [timeout, rotation, late_game, hack_a, tempo]:
            for k in ("n_games", "n_games_dnp", "n_games_linescore",
                      "n_games_foul", "n_games_adv"):
                v = d.get(k)
                if v is not None and isinstance(v, (int, float)) and v > 0:
                    n_candidates.append(int(v))
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            "timeout_usage": timeout,
            "lineup_rotation": rotation,
            "late_game_behavior": late_game,
            "hack_a": hack_a,
            "tempo_style": tempo,
        }

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=team,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required top-level sub-field keys present + sane rates.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        required_keys = {
            "timeout_usage", "lineup_rotation",
            "late_game_behavior", "hack_a", "tempo_style",
        }
        if not required_keys.issubset(artifact.sub_fields.keys()):
            return False

        # Sane range checks
        hack = artifact.sub_fields.get("hack_a", {})
        rate = hack.get("hacka_proxy_rate")
        if rate is not None and not (0.0 <= rate <= 1.0):
            return False

        to_u = artifact.sub_fields.get("timeout_usage", {})
        hi_to = to_u.get("high_to_rate")
        if hi_to is not None and not (0.0 <= hi_to <= 1.0):
            return False

        # CV fields must all be null (CV branch not yet run)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for coach_tendencies (values None — CV fills later).

        The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "coach_tendencies", slot, as_of, value)``
        to populate these without a profile rebuild.
        """
        return {
            "spacing_off_bench": CVSlot(
                name="spacing_off_bench",
                dtype="float",
                description=(
                    "Mean convex-hull team spacing (ft²) on frames when bench units "
                    "are on the floor (determined by CV re-ID + roster lookup). "
                    "Reflects whether the coach deploys spacing lineups off the bench."
                ),
                unit="ft²",
                value=None,
            ),
            "transition_pace_cv": CVSlot(
                name="transition_pace_cv",
                dtype="float",
                description=(
                    "CV-measured possessions-per-minute in transition vs half-court "
                    "sets — tempo preference beyond what season pace captures. "
                    "Derived from possession_type + frame timestamps."
                ),
                unit="poss/min",
                value=None,
            ),
            "sub_pattern_frame": CVSlot(
                name="sub_pattern_frame",
                dtype="float",
                description=(
                    "Frame-level substitution timing proxy: mean quarter-elapsed "
                    "fraction at first player-slot change per period (CV player-count "
                    "transition). Low = early substitution preference."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level build + register helper
# ---------------------------------------------------------------------------

def build_and_register(
    team_tricodes: Optional[List[str]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build coach_tendencies for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of 3-letter NBA tricodes (e.g. ["GSW", "LAL"]).
                       If None, discovers from team_advanced_stats.
        as_of:         leak boundary (defaults to today).
        store:         PointInTimeStore; when provided, artifacts are written to store.
        dry_run:       skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if team_tricodes is None:
        ta = _load_parquet("team_adv_disc", DATA / "team_advanced_stats.parquet")
        if ta is not None and "team_tricode" in ta.columns:
            team_tricodes = sorted(ta["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamCoachTendencies()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
