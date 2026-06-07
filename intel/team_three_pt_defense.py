"""ARM-B atlas section: ``three_pt_defense`` — exhaustive team 3-point defense profile.

Implements :class:`AtlasSection` for the ``"three_pt_defense"`` section of a
team's persistent profile.  Every sub-field is derived from existing parquets
cited in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  opp_3pa_allowed.*   — opp_3pa_allowed_pg (opponent 3PA per game allowed),
                        opp_3pa_rate_allowed (fraction of opp FGA that are 3s),
                        opp_3p_pct_allowed (opponent 3P% against this team),
                        and opp_3p_pct_plusminus (team 3P% defense vs league norm);
                        all from data/team_positional_defense_2025-26.parquet
                        (season-level summary; treated as pre-published season snapshot,
                        no game_date filter required — same convention as player_tracking).
  def_rating.*        — def_rtg (per-game mean), def_rtg_trend (last-10 minus season),
                        from data/team_advanced_stats.parquet (per-game, all games <= as_of).
  closeout.*          — opp_closeout_speed_z (imposed z vs league), from
                        data/intelligence/opp_defensive_intensity.parquet
                        (latest snapshot <= as_of).

DEFER (no source parquet available):
  corner_vs_above_break.* — DEFER: team_positional_defense_2025-26.parquet has only one
                             aggregate ``perim_3pt_*`` zone (no corner3/above-break split).
                             Populate when scripts/fetch_team_shot_zone_defense.py lands
                             (NBA TeamDashPtShotDefend with SHOT_ZONE_AREA filter).
  run_off_line.*           — DEFER: no run-off / stunt frequency parquet exists at team level.
                             Wire when a team-level closeout/contest frequency from CV
                             EventDetector is available (avg_closeout_distance CV slot covers
                             part of this; full run-off labelling requires event tagging).

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  avg_closeout_distance_cv  — mean closeout distance (ft) at the moment of a catch-and-shoot
                               attempt by the opposing team, measured from CV frame-level
                               defender proximity + homography court coordinates.
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


def _null_proportion(v: Optional[float]) -> Optional[float]:
    """Return v if in [0, 1], else None.

    Enforces the face-validity rule for *_pct / *_rate / *_share leaves.
    perim_3pt_d_fg_pct from the source is already a decimal fraction (e.g. 0.369).
    """
    if v is None:
        return None
    if 0.0 <= v <= 1.0:
        return v
    return None


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------


def _positional_defense_3pt(team_tricode: str) -> Dict[str, Any]:
    """Extract season-level 3PT defense stats from team_positional_defense_2025-26.parquet.

    Source: data/team_positional_defense_2025-26.parquet.
    Season-level (no game_date column): treated as a pre-published season summary,
    safe for any as_of at or after the season starts (same convention as
    player_tracking_features.parquet in team_offensive_scheme).

    Returns opp_3pa_allowed_pg, opp_3pa_rate_allowed, opp_3p_pct_allowed,
    opp_3p_pct_plusminus, n_teams_in_parquet.
    """
    df = _load("pos_def", DATA / "team_positional_defense_2025-26.parquet")
    if df is None or df.empty:
        return {}

    tc_col = (
        "team_abbreviation" if "team_abbreviation" in df.columns
        else ("team_tricode" if "team_tricode" in df.columns else None)
    )
    if tc_col is None:
        return {}

    rows = df[df[tc_col] == team_tricode]
    if rows.empty:
        return {}

    row = rows.iloc[0]

    # perim_3pt_d_fga  — opponent 3PA per game allowed (perim/3pt zone attempts)
    opp_3pa_pg = _rd(row.get("perim_3pt_d_fga"))
    # overall_d_fga    — total opponent FGA per game (to compute 3PA rate)
    overall_fga = _rd(row.get("overall_d_fga"))
    # perim_3pt_freq   — fraction of opponent FGA that are 3s (0–1 from source)
    opp_3pa_rate = _rd(row.get("perim_3pt_freq"))
    # validate proportion in [0, 1]
    opp_3pa_rate = _null_proportion(opp_3pa_rate)
    # perim_3pt_d_fg_pct — opponent 3P% against this team (0–1 fraction from source)
    opp_3p_pct = _rd(row.get("perim_3pt_d_fg_pct"))
    opp_3p_pct = _null_proportion(opp_3p_pct)
    # perim_3pt_normal_fg_pct — league-average 3P% in same zone (for plus/minus)
    league_3p_pct = _rd(row.get("perim_3pt_normal_fg_pct"))
    # perim_3pt_pct_plusminus — (opp_pct - league_avg), signed diff; named with _minus_ exemption
    # We expose it directly from the source; it is already a signed difference.
    opp_3p_pct_plusminus = _rd(row.get("perim_3pt_pct_plusminus"))

    return {
        "opp_3pa_allowed_pg": opp_3pa_pg,
        "opp_3pa_rate_allowed": opp_3pa_rate,
        "opp_3p_pct_allowed": opp_3p_pct,
        "league_avg_3p_pct_vs_zone": league_3p_pct,
        "opp_3p_pct_plusminus": opp_3p_pct_plusminus,
        "_source": (
            "team_positional_defense_2025-26.parquet (perim_3pt zone); "
            "season-level — no game_date filter; treated as pre-published summary."
        ),
    }


def _team_def_rtg(team_tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Aggregate per-game def_rtg from team_advanced_stats.parquet <= as_of.

    Returns def_rtg (season mean), def_rtg_last10 (mean of last 10 games),
    def_rtg_trend (last10 minus season — signed diff, named _trend, exempt), n_games.
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

    rows = rows.sort_values("game_date")
    n = len(rows)

    if "def_rtg" not in rows.columns:
        return {}

    season_def_rtg = _rd(rows["def_rtg"].mean())
    last10 = rows.tail(10)
    def_rtg_last10 = _rd(last10["def_rtg"].mean())

    # Signed trend: negative = improving defense recently (lower = better)
    # Named *_trend to be exempt from face-validity [0,1] checks
    def_rtg_trend: Optional[float] = None
    if season_def_rtg is not None and def_rtg_last10 is not None:
        def_rtg_trend = _rd(def_rtg_last10 - season_def_rtg)

    return {
        "def_rtg": season_def_rtg,
        "def_rtg_last10": def_rtg_last10,
        "def_rtg_trend": def_rtg_trend,
        "n_games": n,
    }


def _closeout_signal(team_tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Latest closeout-speed z-score snapshot from opp_defensive_intensity.parquet <= as_of.

    Source: data/intelligence/opp_defensive_intensity.parquet (team_id = tricode).
    Returns opp_closeout_speed_z (z-score relative to league; negative = slower closeouts,
    i.e. more 3PA opportunities allowed), n_games_window, data_density.
    LEAK-SAFE: uses latest snapshot where game_date <= as_of.
    """
    df = _load("opp_def_int", INTEL / "opp_defensive_intensity.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_id"] == team_tricode].copy()
    if rows.empty:
        return {}

    if "game_date" in rows.columns:
        rows["game_date"] = pd.to_datetime(rows["game_date"])
        rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    # Use the most recent snapshot (largest game_date, then largest n_games_window)
    sort_cols = ["game_date"]
    if "n_games_window" in rows.columns:
        sort_cols.append("n_games_window")
    rows = rows.sort_values(sort_cols, ascending=False)
    row = rows.iloc[0]

    # opp_closeout_speed_z is a signed z-score — named *_z so exempt from [0,1] check
    closeout_z = _rd(row.get("opp_closeout_speed_imposed_z"))

    return {
        "opp_closeout_speed_z": closeout_z,
        "n_games_window": _ri(row.get("n_games_window")),
        "data_density": str(row.get("data_density", "low")),
        "_source": "opp_defensive_intensity.parquet (CV-derived z-scores; latest snapshot)",
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------


class TeamThreePtDefense(AtlasSection):
    """Deep team 3-point defense atlas section (team entity, section='three_pt_defense').

    Builds a provenance-stamped, leak-safe artifact covering:
      - Opponent 3PA rate allowed, opponent 3P% allowed, 3P% plusminus vs league
      - Defensive rating (season mean + last-10 trend)
      - Closeout speed z-score (CV-derived)
    Reserves 1 CV slot: avg_closeout_distance_cv.

    Sources used:
      - data/team_positional_defense_2025-26.parquet  (3pt zone positional defense)
      - data/team_advanced_stats.parquet              (def_rtg per game)
      - data/intelligence/opp_defensive_intensity.parquet (closeout speed z)

    DEFER sections (no source parquet available):
      - corner_vs_above_break — positional defense parquet has a single perim_3pt
                                aggregate zone; no corner/ATB split available
      - run_off_line tendency  — no team-level run-off / stunt event frequency parquet;
                                 partial coverage via CV avg_closeout_distance slot
    """

    name: str = "three_pt_defense"
    entity: str = "team"
    source_name: str = (
        "team_positional_defense_2025-26.parquet + "
        "team_advanced_stats.parquet + "
        "opp_defensive_intensity.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the three_pt_defense artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used.
                       Season-level parquets (team_positional_defense) are treated as
                       pre-published season summaries (same convention as offensive_scheme).

        Returns:
            AtlasArtifact or None when the primary source (team_advanced_stats)
            has no rows for this team as-of this date.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        def3 = _positional_defense_3pt(tricode)
        def_rtg = _team_def_rtg(tricode, as_of)
        closeout = _closeout_signal(tricode, as_of)

        # Bail when primary per-game source is empty (no games as-of this date)
        if not def_rtg:
            return None

        # n comes from per-game team_advanced_stats (real game count, CRITICAL LESSON 1)
        n = def_rtg.get("n_games", 0)
        if n == 0:
            return None

        # --- opp_3pa_allowed sub-dict ---
        opp_3pa: Dict[str, Any] = {
            "opp_3pa_allowed_pg": def3.get("opp_3pa_allowed_pg"),
            "opp_3pa_rate_allowed": def3.get("opp_3pa_rate_allowed"),
            "opp_3p_pct_allowed": def3.get("opp_3p_pct_allowed"),
            "league_avg_3p_pct_vs_zone": def3.get("league_avg_3p_pct_vs_zone"),
            # Signed difference: opp_3p_pct_allowed minus league avg; _minus_ in name -> exempt
            "opp_3p_pct_plusminus": def3.get("opp_3p_pct_plusminus"),
            "_source": def3.get("_source", "team_positional_defense_2025-26.parquet"),
        } if def3 else {
            "_note": (
                "DEFER: team_positional_defense_2025-26.parquet has no row for this team. "
                "Populate when the season parquet is refreshed."
            )
        }

        # Compute z-scores for 3pt defense relative to available teams (from parquet)
        # Named *_allowed_z to flag as z-score (exempt from [0,1] face-validity check)
        opp_3p_pct_allowed_z = self._compute_pct_z(tricode, "perim_3pt_d_fg_pct")
        opp_3pa_rate_allowed_z = self._compute_pct_z(tricode, "perim_3pt_freq")
        if isinstance(opp_3pa, dict) and "_note" not in opp_3pa:
            opp_3pa["opp_3p_pct_allowed_z"] = opp_3p_pct_allowed_z
            opp_3pa["opp_3pa_rate_allowed_z"] = opp_3pa_rate_allowed_z

        # --- def_rating sub-dict ---
        def_rating: Dict[str, Any] = {
            "def_rtg": def_rtg.get("def_rtg"),
            "def_rtg_last10": def_rtg.get("def_rtg_last10"),
            # Named *_trend: signed diff (last10 - season); negative = improving defense
            "def_rtg_trend": def_rtg.get("def_rtg_trend"),
            "_source": "team_advanced_stats.parquet (per-game mean <= as_of)",
        }

        # --- closeout sub-dict ---
        closeout_sub: Dict[str, Any] = dict(closeout) if closeout else {
            "_note": (
                "DEFER: opp_defensive_intensity.parquet has no snapshot <= as_of for this team."
            )
        }

        # --- DEFER: corner vs above-break ---
        corner_vs_above_break: Dict[str, Any] = {
            "_note": (
                "DEFER: team_positional_defense_2025-26.parquet aggregates all perimeter 3s "
                "into a single 'perim_3pt' zone. No corner3/above-the-break split available. "
                "Add when scripts/fetch_team_shot_zone_defense.py fetches NBA "
                "TeamDashPtShotDefend with SHOT_ZONE_AREA='Left Corner 3'/'Right Corner 3'."
            )
        }

        # --- DEFER: run-off line tendency ---
        run_off_line: Dict[str, Any] = {
            "_note": (
                "DEFER: no team-level run-off / stunt / aggressive closeout frequency parquet. "
                "Partial coverage via avg_closeout_distance_cv CV slot once the CV EventDetector "
                "catches-and-shoot tagging is complete."
            )
        }

        sub_fields: Dict[str, Any] = {
            "opp_3pa_allowed": opp_3pa,
            "def_rating": def_rating,
            "closeout": closeout_sub,
            "corner_vs_above_break": corner_vs_above_break,
            "run_off_line": run_off_line,
        }

        # Headline scalar: opp_3p_pct_allowed (best single 3PT defense summary)
        value = def3.get("opp_3p_pct_allowed") if def3 else def_rtg.get("def_rtg")

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
    def _compute_pct_z(self, team_tricode: str, col: str) -> Optional[float]:
        """Compute a cross-team z-score for a positional defense column.

        Returns the z-score for team_tricode relative to all teams in the
        season parquet (named *_z so exempt from [0,1] face-validity check).
        Returns None if the parquet is missing or the column absent.
        """
        df = _load("pos_def", DATA / "team_positional_defense_2025-26.parquet")
        if df is None or df.empty or col not in df.columns:
            return None

        tc_col = (
            "team_abbreviation" if "team_abbreviation" in df.columns
            else ("team_tricode" if "team_tricode" in df.columns else None)
        )
        if tc_col is None:
            return None

        vals = df[col].dropna()
        if len(vals) < 2:
            return None

        team_row = df[df[tc_col] == team_tricode]
        if team_row.empty:
            return None

        team_val = float(team_row.iloc[0][col])
        mean = float(vals.mean())
        std = float(vals.std())
        if std < 1e-9:
            return None

        return _rd((team_val - mean) / std)

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required sub-field keys present + sane ranges.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "opp_3pa_allowed",
            "def_rating",
            "closeout",
            "corner_vs_above_break",
            "run_off_line",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sane range: opp_3p_pct_allowed must be in [0, 1] if present
        opp_3p = sf.get("opp_3pa_allowed", {})
        pct_val = opp_3p.get("opp_3p_pct_allowed") if isinstance(opp_3p, dict) else None
        if pct_val is not None and not (0.0 <= pct_val <= 1.0):
            return False

        # Sane range: opp_3pa_rate_allowed must be in [0, 1] if present
        rate_val = opp_3p.get("opp_3pa_rate_allowed") if isinstance(opp_3p, dict) else None
        if rate_val is not None and not (0.0 <= rate_val <= 1.0):
            return False

        # Sane range: def_rtg must be in plausible NBA bounds [90, 130]
        dr = sf.get("def_rating", {})
        def_rtg_val = dr.get("def_rtg") if isinstance(dr, dict) else None
        if def_rtg_val is not None and not (85.0 <= def_rtg_val <= 135.0):
            return False

        # CV slots must all have value=None (reserved)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for three_pt_defense (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "three_pt_defense", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Key is stable contract.
        """
        return {
            "avg_closeout_distance_cv": CVSlot(
                name="avg_closeout_distance_cv",
                dtype="float",
                description=(
                    "Mean distance (ft) between the nearest defender and the catch-and-shoot "
                    "attempter at the moment of ball release on opponent 3PT attempts, "
                    "measured from CV frame-level bounding-box proximity + homography "
                    "court-coordinate transformation, averaged across all 3PT attempts "
                    "by the opposing offense in games processed by the CV pipeline."
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
    """Build three_pt_defense for a list of team tricodes and register via the bridge.

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
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        df = _load("team_adv_disc", DATA / "team_advanced_stats.parquet")
        if df is not None and "team_tricode" in df.columns:
            team_tricodes = sorted(df["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamThreePtDefense()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
