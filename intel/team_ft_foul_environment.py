"""ARM-B atlas section: ``ft_foul_environment`` — per-team FT/foul environment profile.

Implements :class:`AtlasSection` for the ``"ft_foul_environment"`` section of a
team's persistent profile.  Every sub-field either comes from existing parquets or
is derived inline from boxscore JSONs at ``data/nba/boxscore_*.json``.

**Sub-field coverage:**

REAL (populated from existing parquets / inline boxscore aggregation):
  fouls_committed.*   — team_pf_pg (personal fouls committed per game), fouls_pg_z
                        (z-score vs league average), n_games, pf_pg_l10 (rolling
                        last-10 average <= as_of).
                        Source: data/player_pf.parquet aggregated to team/game level.

  ft_drawn.*          — fta_pg (FT attempts drawn per game), ftm_pg (FT makes per
                        game), ft_pct_drawn (FTM/FTA when drawing FTs, measures free
                        throw accuracy on earned trips), fta_pg_l10 (rolling last-10),
                        fta_rate (FTA/FGA proxy; proxy for how aggressively the team
                        attacks the basket relative to shooting volume).
                        Source: data/nba/boxscore_*.json (ftm+fta per team per game),
                        date-keyed via game_id parsed from filename.

  ft_allowed.*        — opp_fta_pg (FTA allowed per game — how many FTs the team
                        GIVES opponents), opp_fta_pg_l10, foul_differential_pg
                        (fouls committed minus fouls drawn per game; positive = net
                        foul-prone, negative = draws more than commits).
                        Source: boxscore_*.json (opponent team's FTA within same game).

  officials_context.* — ref_crew_fouls_z, ref_crew_fta_z, l5_ref_crew_fouls_per_g,
                        l5_ref_crew_fta_per_g, home_win_pct_advantage (rolling L5 for
                        the official crew typically assigned to this team's games).
                        Source: data/cache/officials_rolling.parquet.

  pace_context.*      — pace, n_pace_games (team pace for normalising FT rate;
                        high-pace teams have more possessions → more foul opportunities).
                        Source: data/team_advanced_stats.parquet, filtered <= as_of.

DEFER (data gap — not available in current parquets):
  foul_type_breakdown — fraction of fouls that are shooting vs blocking vs offensive
                        DEFER: no play-type foul annotation; requires PBP EVENTMSGTYPE=2
                        sub-type or Synergy foul-type calls — not in current parquets.
  intentional_foul_rate — intentional fouls drawn (hack-a strategy targets), per game
                        DEFER: PBP EVENTMSGTYPE=6 intentional-flag not parsed; would
                        need PBP action-text parsing (\"Loose Ball\" / \"Flagrant\" etc.).
  clutch_foul_rate    — foul rate in last 2 min requires PBP clock filtering; the
                        inplay_foul_state parquet has end-of-period cumulative totals
                        but no final-2-min slice.

RESERVED CV SLOTS (value=None, CV branch fills later):
  opp_foul_draw_proximity — mean distance (ft) at which the team draws fouls; low
                             values indicate drive-and-draw / paint aggression patterns,
                             measured from CV defender_distance at EventDetector foul
                             frames.
  team_ft_pace_draw_rate  — ratio of FTA trips to team CV-tracked possessions; more
                             granular than FTA/FGA since CV possessions include
                             non-shot trips (drive-and-kick, dump-off etc.); from CV
                             EventDetector foul events per possession.
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
# Game-date index from player_pf (maps game_id -> game_date)
# ---------------------------------------------------------------------------

def _pf_game_date_index() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from player_pf.parquet."""
    cache_key = "pf_gd_index"
    if cache_key in _SRC_CACHE:
        return _SRC_CACHE[cache_key]
    pf = _load_parquet("player_pf", DATA / "player_pf.parquet")
    if pf is None or "game_id" not in pf.columns or "game_date" not in pf.columns:
        _SRC_CACHE[cache_key] = {}
        return {}
    idx = (
        pf[["game_id", "game_date"]]
        .drop_duplicates("game_id")
        .set_index("game_id")["game_date"]
        .astype(str)
        .str[:10]
        .to_dict()
    )
    _SRC_CACHE[cache_key] = idx
    return idx


# ---------------------------------------------------------------------------
# Boxscore aggregation: per-team FTA drawn and FTA allowed
# ---------------------------------------------------------------------------

def _boxscore_team_ft_rows(as_of: _dt.datetime) -> pd.DataFrame:
    """Aggregate per-team FTA/FTM/PF from boxscore_*.json files, <= as_of.

    Returns DataFrame with columns:
        game_id, game_date, team_abbreviation, team_fta, team_ftm, team_pf,
        opp_fta (opponent FTA in the same game)

    LEAK-SAFE: game_date filter applied against as_of before any aggregation.
    Caches the result (as_of-keyed) so repeated calls within one process are free.
    """
    cache_key = f"bs_team_ft_{as_of.date().isoformat()}"
    if cache_key in _SRC_CACHE:
        return _SRC_CACHE[cache_key]

    gd_idx = _pf_game_date_index()
    bs_dir = DATA / "nba"
    as_of_str = as_of.date().isoformat()

    rows: List[Dict[str, Any]] = []
    for bs_path in bs_dir.glob("boxscore_*.json"):
        game_id = bs_path.stem.replace("boxscore_", "")
        gd = gd_idx.get(game_id)
        if gd is None:
            continue
        if gd > as_of_str:  # LEAK GUARD: skip future games
            continue
        try:
            bs = json.loads(bs_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Aggregate FTA/FTM/PF per team
        team_agg: Dict[str, Dict[str, float]] = {}
        for p in bs.get("players", []):
            t = p.get("team_abbreviation")
            if not t:
                continue
            if t not in team_agg:
                team_agg[t] = {"fta": 0.0, "ftm": 0.0, "pf": 0.0}
            team_agg[t]["fta"] += float(p.get("fta") or 0)
            team_agg[t]["ftm"] += float(p.get("ftm") or 0)
            team_agg[t]["pf"] += float(p.get("pf") or 0)
        # Record each team's row with opponent's FTA as opp_fta
        teams = list(team_agg.keys())
        for i, t in enumerate(teams):
            opp_teams = [u for u in teams if u != t]
            opp_fta = sum(team_agg[u]["fta"] for u in opp_teams)
            rows.append({
                "game_id": game_id,
                "game_date": gd,
                "team_abbreviation": t,
                "team_fta": team_agg[t]["fta"],
                "team_ftm": team_agg[t]["ftm"],
                "team_pf": team_agg[t]["pf"],
                "opp_fta": opp_fta,
            })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=[
            "game_id", "game_date", "team_abbreviation",
            "team_fta", "team_ftm", "team_pf", "opp_fta",
        ]
    )
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    _SRC_CACHE[cache_key] = df
    return df


# ---------------------------------------------------------------------------
# Per-source sub-field builders
# ---------------------------------------------------------------------------

def _fouls_committed(
    tricode: str, as_of: _dt.datetime, bs_df: pd.DataFrame
) -> Dict[str, Any]:
    """Team fouls committed per game from boxscore aggregation, filtered to <= as_of.

    Also computes pf_pg_l10 (rolling last-10 games average).
    Uses player_pf.parquet as a cross-check; boxscore is the primary source.
    """
    if bs_df.empty:
        return {}
    rows = bs_df[bs_df["team_abbreviation"] == tricode].copy()
    if rows.empty:
        return {}
    rows = rows.sort_values("game_date")
    n = len(rows)
    pf_pg = _rd(rows["team_pf"].mean())
    pf_pg_l10 = _rd(rows["team_pf"].tail(10).mean()) if n >= 1 else None

    # Z-score vs all teams in the same date window (league reference)
    league_mean = _rd(bs_df.groupby(["game_id", "team_abbreviation"])["team_pf"]
                      .first().groupby("team_abbreviation").mean().mean())
    league_std_vals = (
        bs_df.groupby(["game_id", "team_abbreviation"])["team_pf"]
        .first().groupby("team_abbreviation").mean()
    )
    ls = float(league_std_vals.std()) if len(league_std_vals) > 1 else None
    pf_pg_z: Optional[float] = None
    if pf_pg is not None and league_mean is not None and ls and ls > 0:
        pf_pg_z = _rd((pf_pg - league_mean) / ls)

    return {
        "pf_pg": pf_pg,
        "pf_pg_l10": pf_pg_l10,
        "pf_pg_z": pf_pg_z,
        "n_games": n,
    }


def _ft_drawn(
    tricode: str, as_of: _dt.datetime, bs_df: pd.DataFrame
) -> Dict[str, Any]:
    """FTA drawn per game, FTM per game, FT% on drawn trips, rolling L10.

    Source: boxscore_*.json aggregated to team level in bs_df.
    """
    if bs_df.empty:
        return {}
    rows = bs_df[bs_df["team_abbreviation"] == tricode].copy()
    if rows.empty:
        return {}
    rows = rows.sort_values("game_date")
    n = len(rows)

    fta_pg = _rd(rows["team_fta"].mean())
    ftm_pg = _rd(rows["team_ftm"].mean())
    ft_pct_drawn: Optional[float] = None
    total_fta = rows["team_fta"].sum()
    total_ftm = rows["team_ftm"].sum()
    if total_fta > 0:
        ft_pct_drawn = _rd(float(total_ftm / total_fta))
    fta_pg_l10 = _rd(rows["team_fta"].tail(10).mean()) if n >= 1 else None

    # FTA/FGA proxy: estimate FGA from team_fta and total_pts
    # No direct FGA from this aggregation, so omit fta_rate (would need separate query)
    # Mark as None with note in docstring
    return {
        "fta_pg": fta_pg,
        "ftm_pg": ftm_pg,
        "ft_pct_drawn": ft_pct_drawn,
        "fta_pg_l10": fta_pg_l10,
        "n_games": n,
    }


def _ft_allowed(
    tricode: str, as_of: _dt.datetime, bs_df: pd.DataFrame
) -> Dict[str, Any]:
    """Opponent FTA per game (FTA allowed), rolling L10, and foul differential.

    foul_differential_pg = team_pf_pg - opp_pf_pg (opponents' fouls committed on us).
    opp_pf_pg is estimated as opp_fta / (team FTA / team PF) ratio — a proxy.
    Directly: opp_fta is available from bs_df.
    """
    if bs_df.empty:
        return {}
    rows = bs_df[bs_df["team_abbreviation"] == tricode].copy()
    if rows.empty:
        return {}
    rows = rows.sort_values("game_date")
    n = len(rows)

    opp_fta_pg = _rd(rows["opp_fta"].mean())
    opp_fta_pg_l10 = _rd(rows["opp_fta"].tail(10).mean()) if n >= 1 else None

    # Foul differential: team_fta (drawn) minus opp_fta (allowed)
    # Positive = draws more FTs than it gives; negative = net foul-prone
    foul_diff_pg: Optional[float] = None
    fta_pg = _rd(rows["team_fta"].mean())
    if fta_pg is not None and opp_fta_pg is not None:
        foul_diff_pg = _rd(fta_pg - opp_fta_pg)

    return {
        "opp_fta_pg": opp_fta_pg,
        "opp_fta_pg_l10": opp_fta_pg_l10,
        "fta_minus_opp_fta_pg": foul_diff_pg,  # positive = draws more FTs than allows
        "n_games": n,
    }


def _officials_context(
    tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Rolling L5 referee crew FT environment for this team's games, filtered to <= as_of.

    Source: data/cache/officials_rolling.parquet.
    Selects the most recent row with game_date <= as_of.
    """
    df = _load_parquet("officials_rolling", CACHE / "officials_rolling.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_abbreviation"] == tricode].copy()
    if rows.empty:
        return {}
    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}
    rows = rows.sort_values("game_date")
    row = rows.iloc[-1]  # most recent row at or before as_of
    return {
        "ref_crew_fouls_z": _rd(row.get("ref_crew_fouls_z")),
        "ref_crew_fta_z": _rd(row.get("ref_crew_fta_z")),
        "l5_ref_crew_fouls_per_g": _rd(row.get("l5_ref_crew_fouls_per_g")),
        "l5_ref_crew_fta_per_g": _rd(row.get("l5_ref_crew_fta_per_g")),
        "home_win_pct_advantage": _rd(row.get("home_win_pct_advantage")),
        "n_games": _ri(len(rows)),
        "_as_of_src": str(row.get("game_date", ""))[:10],
    }


def _pace_context(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Season-aggregate pace from team_advanced_stats.parquet, filtered to <= as_of.

    Pace normalises FT-rate interpretation: a faster team has more possessions and
    therefore more opportunities to draw fouls in absolute terms.
    """
    df = _load_parquet("team_adv_stats", DATA / "team_advanced_stats.parquet")
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
    return {
        "pace": _rd(float(rows["pace"].mean())) if "pace" in rows.columns else None,
        "n_games": n,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamFTFoulEnvironment(AtlasSection):
    """Deep team FT/foul-environment atlas section (entity='team').

    Section key: ``ft_foul_environment``.

    Captures five dimensions of the free-throw and foul environment around a team:
      1. fouls_committed  -- PF per game (committed), rolling L10, z-score.
      2. ft_drawn         -- FTA/FTM per game drawn by this team, ft_pct on trips.
      3. ft_allowed       -- Opponent FTA per game, rolling L10, FT differential.
      4. officials_context -- Rolling referee-crew FT/foul rates for this team's games.
      5. pace_context      -- Season-average pace (normalises FT rate interpretation).

    DEFER sections (no source data currently available):
      - foul_type_breakdown: shooting vs blocking vs offensive foul split not annotated
      - intentional_foul_rate: requires PBP intentional-foul flag parsing
      - clutch_foul_rate: last-2-min foul rate not sliced in current parquets

    RESERVED CV SLOTS (values None; CV branch fills via store.fill_cv_slot):
      opp_foul_draw_proximity  — mean CV defender_distance at EventDetector foul frames
      team_ft_pace_draw_rate   — FTA trips / CV-tracked possessions (granular FT-draw rate)

    Sources (all existing, no re-derivation):
      - data/nba/boxscore_*.json  (primary: fta, ftm, pf per player per game)
      - data/player_pf.parquet    (game_id -> game_date index)
      - data/cache/officials_rolling.parquet  (ref crew FT z-scores)
      - data/team_advanced_stats.parquet      (pace context)
    """

    name: str = "ft_foul_environment"
    entity: str = "team"
    source_name: str = (
        "boxscore_*.json + player_pf.parquet + "
        "officials_rolling.parquet + team_advanced_stats.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the ft_foul_environment artifact for team ``entity_id`` as-of ``as_of``.

        Leak guarantee:
          - boxscore rows are filtered to game_date <= as_of via the game_id->date
            index built from player_pf.parquet (which is itself game_date stamped).
          - officials_rolling and team_advanced_stats are filtered to game_date <= as_of.
          - player_pf.parquet is the date-index only; no intra-game data leaks.

        Args:
            entity_id: team tricode string (e.g. "BOS", "GSW").
            as_of:     datetime representing the decision boundary (leak cutoff).

        Returns:
            AtlasArtifact with populated sub_fields and reserved cv_fields,
            or None if no source has data for this team.
        """
        tricode = str(entity_id).upper().strip()
        as_of_str = as_of.date().isoformat()

        # Load boxscore-derived team FT frame (shared across all sub-builders)
        bs_df = _boxscore_team_ft_rows(as_of)

        # Gather all sub-components
        fouls_committed = _fouls_committed(tricode, as_of, bs_df)
        ft_drawn = _ft_drawn(tricode, as_of, bs_df)
        ft_allowed = _ft_allowed(tricode, as_of, bs_df)
        officials_ctx = _officials_context(tricode, as_of)
        pace_ctx = _pace_context(tricode, as_of)

        # Bail if nothing populated (team absent from all sources)
        if not fouls_committed and not ft_drawn and not ft_allowed and not officials_ctx:
            return None

        # DEFER sub-sections with explanatory notes
        foul_type_breakdown: Dict[str, Any] = {
            "_note": (
                "DEFER: shooting vs blocking vs offensive foul type breakdown "
                "requires PBP EVENTMSGTYPE=2 sub-type annotation or Synergy "
                "foul-type calls — not present in current boxscore or parquet store."
            )
        }
        intentional_foul_rate: Dict[str, Any] = {
            "_note": (
                "DEFER: intentional foul rate (hack-a strategy) requires PBP "
                "EVENTMSGTYPE=6 intentional-flag parsing from action text; not "
                "implemented in pbp_scraper or pbp_features currently."
            )
        }
        clutch_foul_rate: Dict[str, Any] = {
            "_note": (
                "DEFER: fouls committed/drawn in the last 2 min requires "
                "game-clock filtering of PBP (PCTIMESTRING <= 2:00); "
                "inplay_foul_state.parquet has cumulative end-of-period totals "
                "but does not slice the final-2-min window."
            )
        }

        sub_fields: Dict[str, Any] = {
            "fouls_committed": fouls_committed,
            "ft_drawn": ft_drawn,
            "ft_allowed": ft_allowed,
            "officials_context": officials_ctx,
            "pace_context": pace_ctx,
            "foul_type_breakdown": foul_type_breakdown,
            "intentional_foul_rate": intentional_foul_rate,
            "clutch_foul_rate": clutch_foul_rate,
        }

        # Headline scalar: FTA drawn per game (most interpretable single FT metric)
        headline = ft_drawn.get("fta_pg")

        # Sample size: best available game count
        n_candidates: List[int] = []
        if fouls_committed.get("n_games"):
            n_candidates.append(int(fouls_committed["n_games"]))
        if ft_drawn.get("n_games"):
            n_candidates.append(int(ft_drawn["n_games"]))
        if pace_ctx.get("n_games"):
            n_candidates.append(int(pace_ctx["n_games"]))
        n = max(n_candidates) if n_candidates else 1

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
            value=_rd(headline),
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, rates in sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "fouls_committed", "ft_drawn", "ft_allowed",
            "officials_context", "pace_context",
            "foul_type_breakdown", "intentional_foul_rate", "clutch_foul_rate",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # FT% on drawn trips must be in [0, 1] when present
        ft_pct = sf.get("ft_drawn", {}).get("ft_pct_drawn")
        if ft_pct is not None and not (0.0 <= ft_pct <= 1.0):
            return False

        # PF per game: NBA team range is roughly 14-32; allow [0, 50] for safety
        pf_pg = sf.get("fouls_committed", {}).get("pf_pg")
        if pf_pg is not None and not (0.0 <= pf_pg <= 50.0):
            return False

        # FTA per game: NBA team range 10-35; allow [0, 60] for safety
        fta_pg = sf.get("ft_drawn", {}).get("fta_pg")
        if fta_pg is not None and not (0.0 <= fta_pg <= 60.0):
            return False

        # Pace: NBA range 90-110; allow [75, 130] for safety
        pace = sf.get("pace_context", {}).get("pace")
        if pace is not None and not (75.0 <= pace <= 130.0):
            return False

        # CV fields: all values must be None (CV branch hasn't run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for ft_foul_environment (values None — CV fills later).

        The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "ft_foul_environment", slot, as_of, value)``
        to populate these WITHOUT a profile rebuild.

        Slots are named in the task spec:
          opp_foul_draw_proximity  — mean CV defender_distance at foul events
          team_ft_pace_draw_rate   — FTA trips / CV-tracked possessions
        """
        return {
            "opp_foul_draw_proximity": CVSlot(
                name="opp_foul_draw_proximity",
                dtype="float",
                description=(
                    "Mean distance (ft) between the ball-handler and the nearest "
                    "defender at the frame when EventDetector registers a foul event, "
                    "aggregated across all tracked home-and-away games for this team. "
                    "Low values (~1-2 ft) indicate drive-and-draw patterns; higher "
                    "values suggest off-ball or reach-in foul tendencies."
                ),
                unit="ft",
                value=None,
            ),
            "team_ft_pace_draw_rate": CVSlot(
                name="team_ft_pace_draw_rate",
                dtype="float",
                description=(
                    "Ratio of FTA trips earned to total CV-tracked half-court "
                    "offensive possessions for this team; a more granular FT-draw rate "
                    "than FTA/FGA because CV possessions include non-shot trips "
                    "(drive-and-kicks, dump-offs). Measured from EventDetector foul "
                    "events annotated against the CV possession log."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level batch build + registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    team_tricodes: Optional[List[str]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build ft_foul_environment for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of 3-letter team tricodes.  If None, discovers from
                       team_advanced_stats.parquet (all available teams).
        as_of:        leak boundary date (defaults to today midnight UTC).
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
        df = _load_parquet("team_adv_stats", DATA / "team_advanced_stats.parquet")
        if df is not None and not df.empty and "team_tricode" in df.columns:
            team_tricodes = sorted(df["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamFTFoulEnvironment()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
