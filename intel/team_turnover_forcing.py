"""ARM-B atlas section: ``turnover_forcing`` — team defensive TOV-forcing identity.

Implements :class:`AtlasSection` for the ``"turnover_forcing"`` section of a
team's persistent profile.  Every sub-field is derived from existing parquets
cited in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  opp_tov.*              — opp_tov_pct_forced (fraction of opponent possessions that
                           end in a turnover, forced BY this team), opp_tov_pct_l10
                           (rolling last-10 games), opp_tov_rate_identity label
                           (PASSIVE/AVERAGE/DISRUPTIVE/ELITE) from
                           data/nba/season_games_*.json home/away_tov_pct columns.
                           LEAK-SAFE: filtered game_date <= as_of.
  own_tov.*              — own_tov_ratio (team's OWN turnover ratio — turnovers per
                           100 possession-like units), own_tov_identity label, from
                           data/team_advanced_stats.parquet per-game <= as_of.
  deflections.*          — defl_pg_proxy (mean deflections per game across rostered
                           players), n_players_in_sample from
                           data/cache/hustle_features.parquet +
                           data/cache/hustle_features_2025-26.parquet, joined to team
                           via data/cache/on_off_features.parquet (team_abbreviation).
                           NOTE: hustle data is season-level (no per-game date filter);
                           treated as pre-published season summary, safe for as_of at or
                           after season end. 33% of player rows miss a team assignment
                           (on_off coverage gap) — n_players reflects actual matched rows.
  pbp_transition.*       — transition_count_pg (mean team pbp_transition_count per game,
                           a proxy for forced fast-break opportunities generated),
                           from data/cache/pbp_possession_features.parquet joined to
                           team via data/cache/on_off_features.parquet.
                           LEAK-SAFE: filters game_date <= as_of.

DEFER (no source parquet available):
  live_ball_tov_pts.*    — DEFER: live-ball turnover (steal→layup) points per 100
                           possessions requires EventType from PBP + team scoring
                           attribution, not available from pbp_possession_features.parquet
                           which only has per-player possession counts, not steal→score
                           sequences. Populate when scripts/build_live_ball_tov_pts.py
                           is added (NBA playlog EVENTMSGTYPE=5 steal chained to
                           EVENTMSGTYPE=1 made FG within 8 seconds).
  steal_pct.*            — DEFER: team-level steals per possession require a
                           traditional boxscore parquet keyed by (team_tricode, game_id)
                           with STL column. No such team-grain boxscore parquet exists
                           (hustle_features.parquet is player-level, team_advanced_stats
                           does not include STL). Add when
                           scripts/fetch_team_traditional_boxscores.py lands.

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  avg_pressure_distance  — mean defender-to-ball-handler distance (ft) in half-court
                           possessions where the ball-handler is classified as the
                           primary handler (CV homography + player tracking, per-game
                           team aggregate). Lower values indicate higher defensive
                           pressure that forces turnovers.
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
# TOV-rate identity label
# ---------------------------------------------------------------------------

_TOV_FORCING_BINS = [
    (0.13, "PASSIVE"),
    (0.15, "AVERAGE"),
    (0.17, "DISRUPTIVE"),
    (float("inf"), "ELITE"),
]

_OWN_TOV_BINS = [
    (11.0, "CAREFUL"),
    (13.0, "AVERAGE"),
    (15.0, "LOOSE"),
    (float("inf"), "TURNOVER_PRONE"),
]


def _opp_tov_identity(rate: float) -> str:
    """Map opponent TOV rate forced [0,1] to a categorical label."""
    for threshold, label in _TOV_FORCING_BINS:
        if rate < threshold:
            return label
    return "ELITE"


def _own_tov_identity(ratio: float) -> str:
    """Map team's own TOV ratio (per-100-possession scale) to a label."""
    for threshold, label in _OWN_TOV_BINS:
        if ratio < threshold:
            return label
    return "TURNOVER_PRONE"


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _opp_tov_from_season_games(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate opponent TOV rates forced from season_games_*.json.

    For each game: when this team is HOME, the opponent is AWAY (away_tov_pct
    = opponent's turnover fraction forced by the home team's defense).  When
    AWAY, opponent's tov_pct = home_tov_pct.
    LEAK-SAFE: filters game_date <= as_of before aggregating.

    Returns opp_tov_pct_forced, opp_tov_pct_l10, opp_tov_rate_identity, n_games.
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
    df = df[df["game_date"] <= as_of_ts]
    if df.empty:
        return {}

    home_col = "home_team" if "home_team" in df.columns else None
    away_col = "away_team" if "away_team" in df.columns else None
    if home_col is None or away_col is None:
        return {}

    opp_tov_vals: List[float] = []

    # When we are HOME, opponent (AWAY) tov_pct = away_tov_pct
    if "away_tov_pct" in df.columns:
        home_games = df[df[home_col] == team_tricode]["away_tov_pct"].dropna().tolist()
        opp_tov_vals.extend(home_games)

    # When we are AWAY, opponent (HOME) tov_pct = home_tov_pct
    if "home_tov_pct" in df.columns:
        away_games = df[df[away_col] == team_tricode]["home_tov_pct"].dropna().tolist()
        opp_tov_vals.extend(away_games)

    if not opp_tov_vals:
        return {}

    n = len(opp_tov_vals)
    mean_forced = float(np.mean(opp_tov_vals))

    # Last-10-game rolling rate: take last 10 chronologically
    # Re-build in chronological order
    home_df = df[df[home_col] == team_tricode][["game_date", "away_tov_pct"]].rename(
        columns={"away_tov_pct": "opp_tov"}
    ).dropna(subset=["opp_tov"])
    away_df = df[df[away_col] == team_tricode][["game_date", "home_tov_pct"]].rename(
        columns={"home_tov_pct": "opp_tov"}
    ).dropna(subset=["opp_tov"])
    combined = pd.concat([home_df, away_df]).sort_values("game_date")
    l10_vals = combined["opp_tov"].tail(10).tolist()
    l10_mean = float(np.mean(l10_vals)) if l10_vals else None

    return {
        "opp_tov_pct_forced": _rd(mean_forced),
        "opp_tov_pct_l10": _rd(l10_mean),
        "opp_tov_rate_identity": _opp_tov_identity(mean_forced),
        "n_games": n,
        "_source": "season_games_*.json home/away_tov_pct (opponent's turnover fraction)",
    }


def _own_tov_from_team_adv(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate team's own tov_ratio from team_advanced_stats.parquet.

    tov_ratio is turnovers per 100 possession-like units — a measure of the
    team's OWN ball-security.  LEAK-SAFE: filters game_date <= as_of.
    Returns own_tov_ratio, own_tov_identity, n_games.
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
    mean_tov_ratio = float(rows["tov_ratio"].mean()) if "tov_ratio" in rows.columns else None

    if mean_tov_ratio is None:
        return {}

    return {
        "own_tov_ratio": _rd(mean_tov_ratio),
        "own_tov_identity": _own_tov_identity(mean_tov_ratio),
        "n_games": n,
        "_source": "team_advanced_stats.parquet tov_ratio (own turnovers per 100 possessions)",
    }


def _deflections_from_hustle(
    team_tricode: str,
) -> Dict[str, Any]:
    """Aggregate deflections proxy from hustle_features.parquet.

    Joins player-level hustle_deflections (per-game rate) to team via
    on_off_features.parquet (team_abbreviation = last-season team).
    hustle_deflections is a per-game rate (e.g. 2.78 deflections/game for SGA).
    Team proxy = mean across rostered players' per-game deflection rates.

    NOTE: no game_date filtering possible (hustle data is season-level, no
    game_date column).  Treated as a pre-published season summary; safe for
    as_of at or after the season end.  33% of player rows lack a team
    assignment from on_off — n_players reflects the actual matched count.

    Returns defl_pg_proxy, n_players_in_sample.
    """
    hf = _load("hustle", CACHE / "hustle_features.parquet")
    hf26 = _load("hustle26", CACHE / "hustle_features_2025-26.parquet")
    oo = _load("on_off", CACHE / "on_off_features.parquet")

    dfs: List[pd.DataFrame] = [d for d in [hf, hf26] if d is not None and not d.empty]
    if not dfs:
        return {}
    hf_all = pd.concat(dfs, ignore_index=True)

    if oo is None or oo.empty or "team_abbreviation" not in oo.columns:
        return {}

    # Best team per player = team from the most-recent season in on_off
    sort_col = "season" if "season" in oo.columns else None
    if sort_col:
        oo_latest = (
            oo.sort_values(sort_col)
            .groupby("player_id")
            .last()
            .reset_index()[["player_id", "team_abbreviation"]]
        )
    else:
        oo_latest = oo[["player_id", "team_abbreviation"]].drop_duplicates("player_id")

    merged = hf_all.merge(oo_latest, on="player_id", how="left")
    team_rows = merged[merged["team_abbreviation"] == team_tricode]

    if team_rows.empty or "hustle_deflections" not in team_rows.columns:
        return {}

    # hustle_deflections is already a per-game rate (deflections per game)
    defl_pg_mean = float(team_rows["hustle_deflections"].mean())
    n_players = len(team_rows)

    return {
        "defl_pg_proxy": _rd(defl_pg_mean),
        "n_players_in_sample": n_players,
        "_source": (
            "hustle_features.parquet hustle_deflections (per-game rate) joined to team "
            "via on_off_features.parquet team_abbreviation; season-level, no date filter."
        ),
    }


def _transition_from_pbp(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate pbp_transition_count per game from pbp_possession_features.parquet.

    pbp_transition_count is a per-player per-game count of PBP-tagged transition
    possessions.  Aggregated to team grain by joining player_id to team via
    on_off_features.parquet, then summing per game_id.
    LEAK-SAFE: filters game_date <= as_of.

    Returns transition_count_pg, n_games.
    """
    pbp = _load("pbp_poss", CACHE / "pbp_possession_features.parquet")
    oo = _load("on_off", CACHE / "on_off_features.parquet")

    if pbp is None or pbp.empty:
        return {}
    if oo is None or oo.empty or "team_abbreviation" not in oo.columns:
        return {}

    sort_col = "season" if "season" in oo.columns else None
    if sort_col:
        oo_latest = (
            oo.sort_values(sort_col)
            .groupby("player_id")
            .last()
            .reset_index()[["player_id", "team_abbreviation"]]
        )
    else:
        oo_latest = oo[["player_id", "team_abbreviation"]].drop_duplicates("player_id")

    merged = pbp.merge(oo_latest, on="player_id", how="left")
    team_rows = merged[merged["team_abbreviation"] == team_tricode].copy()

    if team_rows.empty or "pbp_transition_count" not in team_rows.columns:
        return {}

    # Leak-safe date filter
    if "game_date" in team_rows.columns:
        team_rows["game_date"] = pd.to_datetime(team_rows["game_date"])
        team_rows = team_rows[team_rows["game_date"] <= pd.Timestamp(as_of)]

    if team_rows.empty or "game_id" not in team_rows.columns:
        return {}

    # Sum player counts per game, then mean across games
    per_game = team_rows.groupby("game_id")["pbp_transition_count"].sum()
    n_games = len(per_game)
    if n_games == 0:
        return {}

    transition_pg = float(per_game.mean())

    return {
        "transition_count_pg": _rd(transition_pg),
        "n_games": n_games,
        "_source": (
            "pbp_possession_features.parquet pbp_transition_count (per-player per-game), "
            "team-joined via on_off_features; summed per game_id, averaged."
        ),
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamTurnoverForcing(AtlasSection):
    """Deep team turnover-forcing atlas section (team entity, section='turnover_forcing').

    Builds a provenance-stamped, leak-safe artifact covering opponent TOV rate
    forced, the team's own TOV ratio, deflections proxy, and PBP transition counts.
    Reserves 1 CV slot (avg_pressure_distance) for future CV enrichment.

    Sources used:
      - data/nba/season_games_*.json            (opp_tov_pct forced, per game)
      - data/team_advanced_stats.parquet        (own tov_ratio per game)
      - data/cache/hustle_features.parquet      (player-level deflections per game)
      - data/cache/hustle_features_2025-26.parquet (current season hustle)
      - data/cache/on_off_features.parquet      (player → team_abbreviation join)
      - data/cache/pbp_possession_features.parquet (transition counts per player-game)

    DEFER sections (no team-level source available):
      - live_ball_tov_pts — requires steal→score PBP chain (EVENTMSGTYPE 5→1);
                            not derivable from pbp_possession_features alone.
      - steal_pct         — no team-grain traditional boxscore parquet with STL column.
    """

    name: str = "turnover_forcing"
    entity: str = "team"
    source_name: str = (
        "season_games_*.json + team_advanced_stats.parquet + "
        "hustle_features.parquet + pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the turnover_forcing artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used
                       where per-game date columns are available.

        Returns:
            AtlasArtifact or None when the primary source (season_games opp_tov)
            is missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        opp_tov = _opp_tov_from_season_games(tricode, as_of)
        own_tov = _own_tov_from_team_adv(tricode, as_of)
        defl = _deflections_from_hustle(tricode)
        pbp_trans = _transition_from_pbp(tricode, as_of)

        # Bail if primary source is entirely missing
        if not opp_tov:
            return None

        # --- opp_tov sub-dict ---
        opp_tov_sub: Dict[str, Any] = {
            "opp_tov_pct_forced": opp_tov.get("opp_tov_pct_forced"),
            "opp_tov_pct_l10": opp_tov.get("opp_tov_pct_l10"),
            "opp_tov_rate_identity": opp_tov.get("opp_tov_rate_identity"),
            "_source": opp_tov.get("_source"),
        }

        # --- own_tov sub-dict ---
        own_tov_sub: Dict[str, Any] = {}
        if own_tov:
            own_tov_sub = {
                "own_tov_ratio": own_tov.get("own_tov_ratio"),
                "own_tov_identity": own_tov.get("own_tov_identity"),
                "_source": own_tov.get("_source"),
            }
        else:
            own_tov_sub = {
                "_note": "DEFER: team_advanced_stats.parquet missing or no rows for this team."
            }

        # --- deflections sub-dict ---
        defl_sub: Dict[str, Any] = {}
        if defl:
            defl_sub = {
                "defl_pg_proxy": defl.get("defl_pg_proxy"),
                "n_players_in_sample": defl.get("n_players_in_sample"),
                "_source": defl.get("_source"),
            }
        else:
            defl_sub = {
                "_note": (
                    "DEFER: hustle_features.parquet missing or no players "
                    "mapped to this team via on_off_features.parquet."
                )
            }

        # --- pbp_transition sub-dict ---
        pbp_trans_sub: Dict[str, Any] = {}
        if pbp_trans:
            pbp_trans_sub = {
                "transition_count_pg": pbp_trans.get("transition_count_pg"),
                "n_games": pbp_trans.get("n_games"),
                "_source": pbp_trans.get("_source"),
            }
        else:
            pbp_trans_sub = {
                "_note": (
                    "DEFER: pbp_possession_features.parquet missing or no rows "
                    "mapped to this team."
                )
            }

        # --- DEFER placeholders ---
        live_ball_tov_pts: Dict[str, Any] = {
            "_note": (
                "DEFER: live-ball-TO-to-points (steal→layup chain) requires "
                "EVENTMSGTYPE=5 steal chained to EVENTMSGTYPE=1 made FG within 8s "
                "in raw PBP. pbp_possession_features.parquet only has per-player "
                "possession counts; no steal→score sequence is captured. "
                "Add when scripts/build_live_ball_tov_pts.py lands."
            )
        }
        steal_pct: Dict[str, Any] = {
            "_note": (
                "DEFER: team-level steals per possession require a team-grain "
                "traditional boxscore parquet with STL column. "
                "team_advanced_stats lacks STL; hustle_features is player-level. "
                "Add when scripts/fetch_team_traditional_boxscores.py lands."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "opp_tov": opp_tov_sub,
            "own_tov": own_tov_sub,
            "deflections": defl_sub,
            "pbp_transition": pbp_trans_sub,
            "live_ball_tov_pts": live_ball_tov_pts,
            "steal_pct": steal_pct,
        }

        # Headline scalar: opp_tov_pct_forced (the most direct forcing measure)
        value = opp_tov.get("opp_tov_pct_forced")

        # Sample size = # games in primary source (opp_tov from season_games)
        n = opp_tov.get("n_games", 0)
        confidence = confidence_from_n(n, cap=self.conf_cap)

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
            "opp_tov", "own_tov", "deflections",
            "pbp_transition", "live_ball_tov_pts", "steal_pct",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # opp_tov_pct_forced must be in [0, 1] when present
        forced = sf.get("opp_tov", {}).get("opp_tov_pct_forced")
        if forced is not None and not (0.0 <= forced <= 1.0):
            return False

        # own_tov_ratio: a per-100-possession count; should be positive and < 30
        own_ratio = sf.get("own_tov", {}).get("own_tov_ratio")
        if own_ratio is not None and not (0.0 < own_ratio < 30.0):
            return False

        # deflections per game proxy: non-negative
        defl_pg = sf.get("deflections", {}).get("defl_pg_proxy")
        if defl_pg is not None and defl_pg < 0.0:
            return False

        # transition_count_pg: non-negative
        trans_pg = sf.get("pbp_transition", {}).get("transition_count_pg")
        if trans_pg is not None and trans_pg < 0.0:
            return False

        # CV slots must all have value=None (CV branch has not run)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for turnover_forcing (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "turnover_forcing", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Key is stable contract.
        """
        return {
            "avg_pressure_distance": CVSlot(
                name="avg_pressure_distance",
                dtype="float",
                description=(
                    "Mean defender-to-ball-handler distance (ft) in half-court possessions "
                    "where the ball-handler is the primary dribble initiator, computed from "
                    "CV homography court-coordinate positions averaged over possession frames "
                    "per team per game. Lower values indicate higher defensive pressure, "
                    "which correlates with forced turnovers."
                ),
                unit="ft",
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
    """Build turnover_forcing for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["OKC", "BOS"]).
                       If None, discovers from team_advanced_stats.parquet.
        as_of:         leak boundary date (defaults to today UTC midnight).
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

    section = TeamTurnoverForcing()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
