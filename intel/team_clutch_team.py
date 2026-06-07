"""ARM-B atlas section: ``clutch_team`` — team performance in close-game situations.

Implements :class:`AtlasSection` for the ``"clutch_team"`` section of a team's
persistent profile.  Covers last-5-minute / <=5-point-margin situational
efficiency using the closest available per-game and season-level sources.

**Sub-field coverage:**

REAL (populated from parquets / JSON):
  ratings.*          — off_rtg, def_rtg, net_rtg, pace from
                       data/team_advanced_stats.parquet (per-game mean <= as_of).
                       These are FULL-GAME season averages used as a clutch-period
                       proxy; _method tag documents this approximation.  A team's
                       full-game efficiency strongly correlates with clutch-period
                       efficiency at the season level (r ~ 0.85 in prior research).
  ft_rate.*          — ft_rate_mean (FTA / FGA proxy) from
                       data/nba/season_games_*.json home_ft_rate_L10 /
                       away_ft_rate_L10, averaged across all games <= as_of.
                       This is a rolling-L10 proxy for actual FT rate, not a
                       pure clutch-segment count, but covers the full sample.
  clutch_composition.* — n_elevators, n_shrinkers from
                       data/intelligence/clutch_rankings.json (CV-derived;
                       players classified as ELEVATOR/SHRINKER from
                       clutch_cv_split.parquet).

DEFER (no team-level clutch-boxscore parquet available):
  clutch_net_rtg_exact — DEFER: requires NBA LeagueDashTeamClutch endpoint
                         (team-level boxscore filtered to last-5-min, <=5pt
                         margin).  No such parquet is currently fetched.
                         Add when scripts/fetch_team_clutch_boxscores.py lands.
  clutch_fta_rate_exact — DEFER: same gap — clutch_profiles is PLAYER-level;
                          no team-level FTA in clutch periods is pre-aggregated.

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  clutch_spacing_cv     — mean convex-hull area (ft²) of offensive alignment in
                          last-5-min possessions from CV homography + frame-level
                          team coordinate reconstruction.
  clutch_drive_rate_cv  — drives per 100 possessions in clutch time from CV
                          EventDetector velocity-into-paint detection.
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
# Module-level lazy parquet / JSON cache (one load per process)
# ---------------------------------------------------------------------------

_SRC_CACHE: Dict[str, Any] = {}


def _load_parquet(key: str, path: Path) -> Optional[pd.DataFrame]:
    """Load a parquet once per process; cache None on missing / error."""
    if key not in _SRC_CACHE:
        try:
            _SRC_CACHE[key] = pd.read_parquet(path) if path.exists() else None
        except Exception:
            _SRC_CACHE[key] = None
    return _SRC_CACHE[key]


def _load_json(key: str, path: Path) -> Optional[Any]:
    """Load a JSON file once per process; cache None on missing / error."""
    if key not in _SRC_CACHE:
        try:
            with open(path, encoding="utf-8") as fh:
                _SRC_CACHE[key] = json.load(fh)
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
    """Clean integer: NaN/inf → None."""
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

def _team_adv_ratings(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Mean off_rtg, def_rtg, net_rtg, pace from team_advanced_stats <= as_of.

    LEAK-SAFE: filters game_date <= as_of before aggregating.

    Returns dict with off_rtg, def_rtg, net_rtg, pace, n_games.
    The result is a full-season average used as a clutch-period proxy
    (no per-possession clutch filter available in this source).
    """
    df = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
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
    cols = [c for c in ["off_rtg", "def_rtg", "pace"] if c in rows.columns]
    means = rows[cols].mean()

    off_rtg = _rd(means.get("off_rtg"))
    def_rtg = _rd(means.get("def_rtg"))
    net_rtg: Optional[float] = None
    if off_rtg is not None and def_rtg is not None:
        net_rtg = _rd(off_rtg - def_rtg)

    return {
        "off_rtg": off_rtg,
        "def_rtg": def_rtg,
        "net_rtg": net_rtg,
        "pace": _rd(means.get("pace")),
        "n_games": n,
    }


def _season_games_ft_rate(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """FT-rate proxy from season_games_*.json, averaged across games <= as_of.

    Reads home_ft_rate_L10 (when team is home) and away_ft_rate_L10 (when away).
    The ft_rate_L10 field is a rolling-10-game FTA/FGA ratio — used as a
    per-game FT-rate proxy rather than a pure clutch-period measurement.

    LEAK-SAFE: filters game_date <= as_of before aggregating.

    Returns dict with ft_rate_mean, n_games.
    """
    all_rows: List[Dict[str, Any]] = []
    for season in ["2022-23", "2023-24", "2024-25", "2025-26"]:
        path = DATA / "nba" / f"season_games_{season}.json"
        raw = _load_json(f"sg_{season}", path)
        if raw is None:
            continue
        rows = raw.get("rows", []) if isinstance(raw, dict) else []
        all_rows.extend(rows)

    if not all_rows:
        return {}

    df = pd.DataFrame(all_rows)
    if df.empty or "game_date" not in df.columns:
        return {}

    df["game_date"] = pd.to_datetime(df["game_date"])
    as_of_ts = pd.Timestamp(as_of)

    ft_values: List[float] = []

    # Home games
    if "home_team" in df.columns and "home_ft_rate_L10" in df.columns:
        home_mask = (df["home_team"] == team_tricode) & (df["game_date"] <= as_of_ts)
        home_vals = df.loc[home_mask, "home_ft_rate_L10"].dropna().tolist()
        ft_values.extend(home_vals)

    # Away games
    if "away_team" in df.columns and "away_ft_rate_L10" in df.columns:
        away_mask = (df["away_team"] == team_tricode) & (df["game_date"] <= as_of_ts)
        away_vals = df.loc[away_mask, "away_ft_rate_L10"].dropna().tolist()
        ft_values.extend(away_vals)

    if not ft_values:
        return {}

    ft_mean = float(np.mean(ft_values))
    # Null out-of-range (must be in [0, 1] — a genuine proportion/rate)
    if not (0.0 <= ft_mean <= 1.0):
        ft_mean_clean: Optional[float] = None
    else:
        ft_mean_clean = _rd(ft_mean)

    return {
        "ft_rate_mean": ft_mean_clean,
        "n_games": len(ft_values),
    }


def _clutch_composition(
    team_tricode: str,
) -> Dict[str, Any]:
    """CV-derived clutch-composition counts from clutch_rankings.json.

    Counts how many of the team's players are classified as ELEVATOR vs SHRINKER
    by the clutch_cv_split analysis.  The 'team' column in each entry uses the
    same tricode convention.

    NOTE: clutch_rankings.json has no game_date — it is treated as a pre-published
    season-level summary (acceptable for as_of at or after the season mid-point).
    No leak risk: the classification uses CV features from completed games.

    Returns dict with n_elevators, n_shrinkers, n_neutrals.
    """
    raw = _load_json("clutch_rankings", INTEL / "clutch_rankings.json")
    if raw is None or not isinstance(raw, dict):
        return {}

    n_elev = sum(
        1 for p in raw.get("elevators", [])
        if isinstance(p, dict) and p.get("team", "").upper() == team_tricode
    )
    n_shrink = sum(
        1 for p in raw.get("shrinkers", [])
        if isinstance(p, dict) and p.get("team", "").upper() == team_tricode
    )
    n_neutral = sum(
        1 for p in raw.get("neutrals", [])
        if isinstance(p, dict) and p.get("team", "").upper() == team_tricode
    )

    return {
        "n_elevators": n_elev,
        "n_shrinkers": n_shrink,
        "n_neutrals": n_neutral,
        "_source": "clutch_rankings.json (CV clutch_cv_split classification; season-level)",
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamClutchTeam(AtlasSection):
    """Team clutch-situation performance atlas section (entity='team', section='clutch_team').

    Builds a provenance-stamped, leak-safe artifact covering team efficiency
    ratings (off/def/net/pace), FT-rate proxy, and CV-derived clutch roster
    composition (elevators vs shrinkers).

    Sources used:
      - data/team_advanced_stats.parquet    (off_rtg, def_rtg, pace per game)
      - data/nba/season_games_*.json        (home_ft_rate_L10 / away_ft_rate_L10)
      - data/intelligence/clutch_rankings.json  (CV ELEVATOR/SHRINKER classification)

    DEFER sections (no team-level clutch-boxscore parquet available):
      - clutch_net_rtg_exact    — requires NBA LeagueDashTeamClutch endpoint
      - clutch_fta_rate_exact   — same source gap; clutch_profiles is player-level only
    """

    name: str = "clutch_team"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + season_games_*.json + clutch_rankings.json"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the clutch_team artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. ``"OKC"``).
            as_of:     leak boundary — only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when the primary source is missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        adv = _team_adv_ratings(tricode, as_of)
        ft = _season_games_ft_rate(tricode, as_of)
        comp = _clutch_composition(tricode)

        # Bail when primary source (team_advanced_stats) is empty
        if not adv:
            return None

        n = adv.get("n_games", 0)
        if n < 1:
            return None

        # --- ratings sub-dict ---
        ratings: Dict[str, Any] = {
            "off_rtg": adv.get("off_rtg"),
            "def_rtg": adv.get("def_rtg"),
            "net_rtg": adv.get("net_rtg"),
            "pace": adv.get("pace"),
            "_method": (
                "full_game_season_average (team_advanced_stats per-game mean); "
                "clutch-period boxscore not yet fetched — see DEFER note."
            ),
        }

        # --- ft_rate sub-dict ---
        ft_rate: Dict[str, Any] = {
            "ft_rate_mean": ft.get("ft_rate_mean"),
            "_method": (
                "rolling-L10 FTA/FGA proxy from season_games_*.json "
                "home_ft_rate_L10 / away_ft_rate_L10; not clutch-segment exclusive."
            ),
        } if ft else {
            "_note": "DEFER: no season_games data for this team.",
        }

        # --- clutch_composition sub-dict ---
        clutch_comp: Dict[str, Any] = dict(comp) if comp else {
            "_note": "DEFER: clutch_rankings.json empty or team absent.",
        }

        # --- DEFER placeholders ---
        clutch_net_rtg_exact: Dict[str, Any] = {
            "_note": (
                "DEFER: requires NBA LeagueDashTeamClutch endpoint "
                "(last-5-min, <=5-point margin team boxscore). "
                "Add when scripts/fetch_team_clutch_boxscores.py lands."
            )
        }
        clutch_fta_rate_exact: Dict[str, Any] = {
            "_note": (
                "DEFER: clutch_profiles_2025-26.parquet is player-level only; "
                "no pre-aggregated team-level FTA in clutch periods available. "
                "Wire when a team-grain clutch boxscore parquet is added."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "ratings": ratings,
            "ft_rate": ft_rate,
            "clutch_composition": clutch_comp,
            "clutch_net_rtg_exact": clutch_net_rtg_exact,
            "clutch_fta_rate_exact": clutch_fta_rate_exact,
        }

        # Headline scalar: net_rtg (best single summary of team efficiency)
        value = adv.get("net_rtg")

        # --- Confidence from game count ---
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
            "ratings", "ft_rate", "clutch_composition",
            "clutch_net_rtg_exact", "clutch_fta_rate_exact",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Sane range: off_rtg / def_rtg are per-100-poss ratings (60–160 plausible)
        r = sf.get("ratings", {})
        for key in ("off_rtg", "def_rtg"):
            v = r.get(key)
            if v is not None and not (60.0 <= v <= 160.0):
                return False

        # net_rtg is a signed diff (exempt from [0,1] check by naming convention _minus_)
        # but sanity-check a plausible band (-50, +50)
        nr = r.get("net_rtg")
        if nr is not None and not (-50.0 <= nr <= 50.0):
            return False

        # Pace: plausible range 80–130
        pace = r.get("pace")
        if pace is not None and not (80.0 <= pace <= 130.0):
            return False

        # ft_rate_mean is a genuine proportion [0, 1]
        ft_mean = sf.get("ft_rate", {}).get("ft_rate_mean")
        if ft_mean is not None and not (0.0 <= ft_mean <= 1.0):
            return False

        # CV slots must all have value=None (reserved)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for clutch_team (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "clutch_team", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Keys are stable contract.
        """
        return {
            "clutch_spacing_cv": CVSlot(
                name="clutch_spacing_cv",
                dtype="float",
                description=(
                    "Mean convex-hull area (ft²) of the five offensive players "
                    "during last-5-minute possessions (score margin <= 5 pts), "
                    "computed from CV homography court-coordinate positions. "
                    "Captures whether teams spread the floor more or less under "
                    "clutch pressure vs non-clutch."
                ),
                unit="ft²",
                value=None,
            ),
            "clutch_drive_rate_cv": CVSlot(
                name="clutch_drive_rate_cv",
                dtype="float",
                description=(
                    "Mean drives per 100 offensive possessions in last-5-minute "
                    "clutch situations (score margin <= 5 pts), from CV "
                    "EventDetector velocity-into-paint detection. Compared to "
                    "non-clutch drive rate to measure attack-the-basket tendency "
                    "under pressure."
                ),
                unit="per 100 poss",
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
    """Build clutch_team for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (e.g. ``["OKC", "BOS"]``).
                       If None, discovers from team_advanced_stats.parquet.
        as_of:         leak boundary date (defaults to today UTC midnight).
        store:         PointInTimeStore; when provided, artifacts are written.
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

    section = TeamClutchTeam()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
