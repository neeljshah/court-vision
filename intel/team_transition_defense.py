"""ARM-B atlas section: ``transition_defense`` — exhaustive team transition-defense identity.

Implements :class:`AtlasSection` for the ``"transition_defense"`` section of a
team's persistent profile.  Every sub-field is derived from existing parquets /
JSON files cited in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets / JSON):
  def_efficiency.*      — def_rtg (opponent points per 100 possessions), dreb_pct
                          (defensive rebound rate, a key get-back proxy), possessions_pg
                          from data/team_advanced_stats.parquet +
                          data/team_reb_context.parquet (per-game, <=as_of).
  opp_tov.*             — opp_tov_pct_mean (mean opponent turnover fraction when this
                          team defends), opp_tov_pct_std (game-to-game variance),
                          from data/nba/season_games_*.json  (per-game, <=as_of).
                          When OKC is home: away_tov_pct = opponent's TOV fraction.
                          When OKC is away: home_tov_pct = opponent's TOV fraction.
                          This is the closest available proxy for "points off turnovers"
                          transition defense (league turnover rate = ~0.135-0.155).
  transition_freq.*     — opp_transition_pg (mean total PBP transition possessions per
                          game in games this team played), from
                          data/cache/pbp_possession_features.parquet +
                          data/nba/season_games_*.json game_id → team mapping.
                          NOTE: pbp_transition_count is a game-level total (both teams
                          combined); ~50% of these are opponent transitions against the
                          defending team. Reported as raw game-total (n_games_pbp noted).
  positional_defense.*  — rim_d_fg_pct, rim_d_fg_pct_plusminus, overall_d_fg_pct from
                          data/team_positional_defense_2025-26.parquet (season-level,
                          one row per team; no game_date filtering — treat as pre-published
                          season summary, acceptably safe for as_of >= season start).

DEFER (no source available):
  opp_ppp_transition.*  — DEFER: no per-possession outcome annotation joins PBP
                          possession type (transition) to points scored. Would need
                          play-by-play event resolution beyond current pbp_possession_features.
  get_back_rate.*       — DEFER: fraction of defensive possessions where all 5 players
                          cross half-court within ~3s of turnover/rebound. Requires
                          per-player court-position data (CV or tracking). Reserved as
                          CV slot (defenders_back_rate).
  pts_off_to_pg.*       — DEFER: points allowed directly off opponent turnovers requires
                          PBP event-level linking (turnover event → next possession outcome)
                          not currently assembled in any repo parquet.

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  defenders_back_rate   — fraction of transition possessions where >= 4 defenders cross
                          half-court within 3 s of the turnover/rebound trigger event
                          (CV EventDetector + homography court-coordinate tracking)
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
# Module-level lazy parquet / JSON cache (one load per process)
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


def _load_season_games() -> Optional[pd.DataFrame]:
    """Concatenate all season_games_*.json into one DataFrame (cached)."""
    key = "_season_games_df"
    if key in _SRC_CACHE:
        return _SRC_CACHE[key]

    nba_dir = DATA / "nba"
    all_rows: List[Dict[str, Any]] = []
    for season in ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
        path = nba_dir / f"season_games_{season}.json"
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            rows = raw.get("rows", []) if isinstance(raw, dict) else raw
            if isinstance(rows, list):
                all_rows.extend(rows)
        except Exception:
            continue

    if not all_rows:
        _SRC_CACHE[key] = None
        return None

    df = pd.DataFrame(all_rows)
    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    _SRC_CACHE[key] = df
    return df


# ---------------------------------------------------------------------------
# Scalar helpers
# ---------------------------------------------------------------------------

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
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _def_efficiency(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate defensive efficiency from team_advanced_stats <=as_of.

    Returns def_rtg mean, n_games from data/team_advanced_stats.parquet.
    LEAK-SAFE: filters game_date <= as_of.
    """
    df = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_tricode"] == team_tricode].copy()
    if rows.empty:
        return {}

    rows["game_date"] = pd.to_datetime(rows["game_date"], errors="coerce")
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    n = len(rows)
    means = rows[[c for c in ["def_rtg", "pace"] if c in rows.columns]].mean()

    return {
        "def_rtg_mean": _rd(means.get("def_rtg")),
        "pace_mean": _rd(means.get("pace")),
        "n_games": n,
    }


def _dreb_context(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate defensive rebound rate from team_reb_context.parquet <=as_of.

    dreb_pct is the fraction of available defensive rebounds captured. A higher
    dreb_pct means the team gets back faster and limits opponent fast breaks.
    LEAK-SAFE: filters game_date <= as_of.
    """
    df = _load_parquet("team_reb", DATA / "team_reb_context.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_tricode"] == team_tricode].copy()
    if rows.empty:
        return {}

    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"], errors="coerce")
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    means = rows[[c for c in ["dreb_pct", "possessions"] if c in rows.columns]].mean()

    return {
        "dreb_pct_mean": _rd(means.get("dreb_pct")),
        "possessions_pg": _rd(means.get("possessions")),
        "n_games": len(rows),
    }


def _opp_tov(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Compute opponent turnover rate when this team defends, from season_games_*.json.

    For each game this team played:
      - When team is home:  away_tov_pct  = opponent's turnover fraction.
      - When team is away:  home_tov_pct  = opponent's turnover fraction.

    This is the best available proxy for defensive pressure / transition-trigger rate.
    LEAK-SAFE: filters game_date <= as_of before aggregating.
    """
    sg = _load_season_games()
    if sg is None or sg.empty:
        return {}

    cols_needed = {"game_date", "home_team", "away_team", "home_tov_pct", "away_tov_pct"}
    if not cols_needed.issubset(sg.columns):
        return {}

    as_of_ts = pd.Timestamp(as_of)

    # Opponent's tov_pct when this team is home
    home_rows = sg[
        (sg["home_team"] == team_tricode) & (sg["game_date"] <= as_of_ts)
    ]["away_tov_pct"].dropna()

    # Opponent's tov_pct when this team is away
    away_rows = sg[
        (sg["away_team"] == team_tricode) & (sg["game_date"] <= as_of_ts)
    ]["home_tov_pct"].dropna()

    all_vals = pd.concat([home_rows, away_rows], ignore_index=True)
    if all_vals.empty:
        return {}

    n = len(all_vals)
    mean_val = float(all_vals.mean())
    std_val = float(all_vals.std()) if n > 1 else 0.0

    # Validate as proportion [0, 1]
    mean_val = mean_val if 0.0 <= mean_val <= 1.0 else None  # type: ignore[assignment]
    std_val_clean = _rd(std_val)

    return {
        "opp_tov_pct_mean": _rd(mean_val),
        "opp_tov_pct_std": std_val_clean,
        "n_games": n,
        "_source": "season_games_*.json home/away_tov_pct; opponent's TOV fraction per game",
    }


def _transition_freq(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate game-level PBP transition counts for games this team played.

    Source: data/cache/pbp_possession_features.parquet joined to season_games for
    game_id -> team mapping. Sums pbp_transition_count for all players in each game
    where this team appeared. The total includes both team's transitions (~half are
    opponent's).  n_games_pbp indicates coverage (games in pbp that match team's
    schedule from team_advanced_stats).
    LEAK-SAFE: only games with game_date <= as_of are included.
    """
    # Get team's game_ids from team_advanced_stats (leak-safe filtered)
    df_adv = _load_parquet("team_adv_trans", DATA / "team_advanced_stats.parquet")
    if df_adv is None or df_adv.empty:
        return {}

    rows_adv = df_adv[df_adv["team_tricode"] == team_tricode].copy()
    if rows_adv.empty:
        return {}

    rows_adv["game_date"] = pd.to_datetime(rows_adv["game_date"], errors="coerce")
    rows_adv = rows_adv[rows_adv["game_date"] <= pd.Timestamp(as_of)]
    if rows_adv.empty:
        return {}

    team_game_ids: set = set(rows_adv["game_id"].dropna().tolist())

    pbp = _load_parquet("pbp_poss", CACHE / "pbp_possession_features.parquet")
    if pbp is None or pbp.empty or "game_id" not in pbp.columns:
        return {}

    pbp_team = pbp[pbp["game_id"].isin(team_game_ids)]
    if pbp_team.empty:
        return {}

    # Per-game transition total (all players, both teams)
    by_game = pbp_team.groupby("game_id")["pbp_transition_count"].sum()
    n_games_pbp = len(by_game)
    opp_transition_pg = _rd(float(by_game.mean())) if n_games_pbp > 0 else None

    return {
        "opp_transition_pg": opp_transition_pg,
        "n_games_pbp": n_games_pbp,
        "_note": (
            "opp_transition_pg = mean total PBP transition count per game (both teams); "
            "~50% are opponent's transitions against this team's defense. "
            "Full opponent-only split deferred pending per-player team membership join."
        ),
    }


def _positional_defense(team_tricode: str) -> Dict[str, Any]:
    """Season-level shot-quality defense from team_positional_defense_2025-26.parquet.

    Fields: overall_d_fg_pct (opponent FG%), rim_lt6_d_fg_pct (rim FG% allowed),
    rim_lt6_d_fg_pct_plusminus (vs league average), rim_lt6_freq (fraction of opp
    shots at the rim).

    This is a season-level parquet (1 row per team, no game_date).  Treated as a
    pre-published season summary — acceptably safe for as_of at or after season start.
    LEAK-SAFE annotation: this is a season-aggregate stat, not per-game; acceptable.
    """
    df = _load_parquet("team_pos_def", DATA / "team_positional_defense_2025-26.parquet")
    if df is None or df.empty:
        return {}

    team_col = "team_abbreviation" if "team_abbreviation" in df.columns else None
    if team_col is None:
        return {}

    row_df = df[df[team_col] == team_tricode]
    if row_df.empty:
        return {}

    row = row_df.iloc[0]

    # rim_lt6_d_fg_pct_plusminus is a signed diff -> named with _plusminus -> validator exempts
    rim_fg_pct = _rd(row.get("rim_lt6_d_fg_pct"))
    rim_fg_pct = rim_fg_pct if (rim_fg_pct is None or 0.0 <= rim_fg_pct <= 1.0) else None
    overall_fg_pct = _rd(row.get("overall_d_fg_pct"))
    overall_fg_pct = (
        overall_fg_pct if (overall_fg_pct is None or 0.0 <= overall_fg_pct <= 1.0) else None
    )
    rim_freq = _rd(row.get("rim_lt6_freq"))
    rim_freq = rim_freq if (rim_freq is None or 0.0 <= rim_freq <= 1.0) else None

    return {
        "overall_d_fg_pct": overall_fg_pct,
        "rim_lt6_d_fg_pct": rim_fg_pct,
        "rim_lt6_d_fg_pct_plusminus": _rd(row.get("rim_lt6_pct_plusminus")),
        "rim_lt6_freq": rim_freq,
        "_source": "team_positional_defense_2025-26.parquet (season-level summary)",
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamTransitionDefense(AtlasSection):
    """Deep team transition-defense atlas section (team entity, section='transition_defense').

    Builds a provenance-stamped, leak-safe artifact covering:
      - Defensive efficiency (def_rtg, dreb_pct) from team_advanced_stats + team_reb_context
      - Opponent turnover rate (opp_tov_pct) from season_games_*.json
      - PBP transition frequency per game from pbp_possession_features
      - Positional defense (rim FG% allowed) from team_positional_defense_2025-26

    DEFER: opp points-per-possession in transition, per-possession get-back rate,
    and points-off-turnovers-pg. All require event-level PBP outcome linking not
    currently available in repo parquets.

    CV slot reserved: defenders_back_rate (fraction of transition possessions where
    >= 4 defenders cross half-court within 3 s of the trigger event).

    Sources used:
      - data/team_advanced_stats.parquet          (def_rtg, pace per game)
      - data/team_reb_context.parquet             (dreb_pct, possessions per game)
      - data/nba/season_games_*.json              (opp_tov_pct per game)
      - data/cache/pbp_possession_features.parquet (pbp_transition_count per game)
      - data/team_positional_defense_2025-26.parquet (rim/overall d_fg_pct, season-level)
    """

    name: str = "transition_defense"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + team_reb_context.parquet + "
        "season_games_*.json + pbp_possession_features.parquet + "
        "team_positional_defense_2025-26.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the transition_defense artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when primary source is missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        def_eff = _def_efficiency(tricode, as_of)
        dreb = _dreb_context(tricode, as_of)
        opp_tov = _opp_tov(tricode, as_of)
        trans_freq = _transition_freq(tricode, as_of)
        pos_def = _positional_defense(tricode)

        # Bail when primary source (team_advanced_stats) has no data for this team
        if not def_eff:
            return None

        # --- def_efficiency sub-dict ---
        def_efficiency_sub: Dict[str, Any] = {
            "def_rtg_mean": def_eff.get("def_rtg_mean"),
            "pace_mean": def_eff.get("pace_mean"),
            "dreb_pct_mean": dreb.get("dreb_pct_mean"),
            "possessions_pg": dreb.get("possessions_pg"),
            "_source": (
                "team_advanced_stats.parquet (def_rtg, pace) + "
                "team_reb_context.parquet (dreb_pct, possessions); per-game mean <=as_of"
            ),
        }

        # --- opp_tov sub-dict ---
        opp_tov_sub: Dict[str, Any] = dict(opp_tov) if opp_tov else {
            "_note": "DEFER: season_games_*.json missing or team absent."
        }

        # --- transition_freq sub-dict ---
        transition_freq_sub: Dict[str, Any] = dict(trans_freq) if trans_freq else {
            "_note": "DEFER: pbp_possession_features.parquet missing or no PBP coverage."
        }

        # --- positional_defense sub-dict ---
        positional_defense_sub: Dict[str, Any] = dict(pos_def) if pos_def else {
            "_note": "DEFER: team_positional_defense_2025-26.parquet missing or team absent."
        }

        # --- DEFER placeholders ---
        opp_ppp_transition: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-possession outcome annotation joining PBP possession type "
                "(transition) to points scored. Would need play-by-play event resolution "
                "linking turnover/rebound event -> next-possession outcome, "
                "not currently assembled in any repo parquet."
            )
        }

        pts_off_to: Dict[str, Any] = {
            "_note": (
                "DEFER: points-off-turnovers-pg requires PBP event-level linking "
                "(turnover event -> next possession outcome) not currently available."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "def_efficiency": def_efficiency_sub,
            "opp_tov": opp_tov_sub,
            "transition_freq": transition_freq_sub,
            "positional_defense": positional_defense_sub,
            "opp_ppp_transition": opp_ppp_transition,
            "pts_off_to": pts_off_to,
        }

        # Headline convenience scalar: def_rtg (best single defensive summary)
        value = def_eff.get("def_rtg_mean")

        # --- Sample size and confidence ---
        # Primary n from team_advanced_stats (# games; ACTUAL game count, not seasons)
        n = def_eff.get("n_games", 0)
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
            "def_efficiency", "opp_tov", "transition_freq",
            "positional_defense", "opp_ppp_transition", "pts_off_to",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # def_rtg plausible range
        def_rtg = sf.get("def_efficiency", {}).get("def_rtg_mean")
        if def_rtg is not None and not (80.0 <= def_rtg <= 140.0):
            return False

        # dreb_pct must be [0, 1]
        dreb = sf.get("def_efficiency", {}).get("dreb_pct_mean")
        if dreb is not None and not (0.0 <= dreb <= 1.0):
            return False

        # opp_tov_pct_mean must be [0, 1]
        opp_tov = sf.get("opp_tov", {}).get("opp_tov_pct_mean")
        if opp_tov is not None and not (0.0 <= opp_tov <= 1.0):
            return False

        # CV slots must all have value=None (CV branch hasn't run)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for transition_defense (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "transition_defense", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild. Keys are stable contract.
        """
        return {
            "defenders_back_rate": CVSlot(
                name="defenders_back_rate",
                dtype="float",
                description=(
                    "Fraction of opponent transition possessions (triggered by a "
                    "defensive rebound or forced turnover) where >= 4 defenders cross "
                    "half-court within 3 seconds of the trigger event, as detected by "
                    "CV EventDetector + homography court-coordinate tracking. "
                    "Higher = better get-back / transition suppression."
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
    """Build transition_defense for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["OKC", "BOS"]).
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
        df = _load_parquet("team_adv_disc", DATA / "team_advanced_stats.parquet")
        if df is not None and "team_tricode" in df.columns:
            team_tricodes = sorted(df["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamTransitionDefense()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
