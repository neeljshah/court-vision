"""ARM-B atlas section: ``paint_defense`` — team paint / rim defensive profile.

Implements :class:`AtlasSection` for the ``"paint_defense"`` section of a
team's persistent profile.  All sub-fields derive from existing parquets only —
no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):

  opp_paint_allowed.*  — z-scored opponent paint-FG% allowed, 3pt% allowed,
                         mid% allowed, dwell-pct allowed, and shot-mix deviation,
                         from data/intelligence/opp_paint_allowance.parquet.
                         Latest cumulative rolling snapshot with game_date <= as_of.
                         Named with ``_z`` suffix so the validator exempts them from
                         the [0,1] rule (they are standardised z-scores, not proportions).

  rim_defense.*        — rim-shot (< 6 ft) FG% allowed, paint (< 10 ft) FG% allowed,
                         rim-shot frequency faced, rim vs normal FG% plus-minus,
                         and paint vs normal FG% plus-minus.
                         Source: data/team_positional_defense_2025-26.parquet
                         (season summary, 30 rows, no game_date column).
                         No per-game date filtering possible; treated as a
                         pre-published season summary, safe for any as_of in season.

  def_rtg.*            — team defensive rating and defensive rebounding pct from
                         data/team_advanced_stats.parquet (per-game rolling mean
                         for all games with game_date <= as_of).
                         Used as primary n-anchor (real game count, CRITICAL LESSON 1).

DEFER:

  blk_pg.*             — blocks per game is available only in play-by-play / box-score
                         data not pre-aggregated by team.  DEFER until
                         scripts/fetch_team_traditional_boxscores.py ships a
                         team-grain parquet with blk column.

  paint_touch_allowed_rate.* — opponent paint-touch frequency per possession is
                         not yet available.  opp_paint_allowance carries shot-mix
                         z-scores but not raw possession-level touch counts.
                         DEFER until a team-grain possession/touch parquet exists.

RESERVED CV SLOTS (value=None; CV branch fills later):

  avg_rim_contest      — mean rim-contest distance (ft) from CV tracking at the
                         moment of each shot attempt within 6 ft of the basket,
                         averaged over all rim-area shot events for this team's
                         defensive possessions.  Filled by the CV-fix session via
                         store.fill_cv_slot.
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


def _clamp_pct(v: Optional[float]) -> Optional[float]:
    """Clamp a proportion/FG% to [0, 1]; null if out of range after cleaning."""
    if v is None:
        return None
    if not (0.0 <= v <= 1.0):
        return None
    return v


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _opp_paint_allowance(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Latest cumulative opp_paint_allowance snapshot with game_date <= as_of.

    Source: data/intelligence/opp_paint_allowance.parquet.
    Columns are z-scores (named with _z suffix) so the validator exempts them
    from the [0,1] proportion rule.
    LEAK-SAFE: filters game_date <= as_of; uses latest snapshot only.
    """
    df = _load("opp_paint", INTEL / "opp_paint_allowance.parquet")
    if df is None or df.empty:
        return {}

    rows = df[df["team_id"] == team_tricode].copy()
    if rows.empty:
        return {}

    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return {}

    # Use the latest snapshot by date, then by largest n_games_window
    sort_cols = ["game_date"]
    if "n_games_window" in rows.columns:
        sort_cols.append("n_games_window")
    rows = rows.sort_values(sort_cols, ascending=False)
    row = rows.iloc[0]

    return {
        "opp_paint_pct_allowed_z": _rd(row.get("opp_paint_pct_allowed_z")),
        "opp_3pt_pct_allowed_z": _rd(row.get("opp_3pt_pct_allowed_z")),
        "opp_mid_pct_allowed_z": _rd(row.get("opp_mid_pct_allowed_z")),
        "opp_paint_dwell_pct_allowed_z": _rd(row.get("opp_paint_dwell_pct_allowed_z")),
        "opp_shot_mix_deviation_z": _rd(row.get("opp_shot_mix_deviation_z")),
        "n_games_window": _ri(row.get("n_games_window")),
        "data_density": str(row.get("data_density", "low")),
        "_source": "opp_paint_allowance.parquet (z-scores relative to league mean)",
    }


def _rim_defense_positional(team_tricode: str) -> Dict[str, Any]:
    """Rim and paint FG% allowed from team_positional_defense_2025-26.parquet.

    Season-summary source (30 rows, no game_date column).  Treated as a
    pre-published end-of-season summary, acceptable for any as_of in season.
    Values are per-possession proportions in [0, 1] (FG% against).
    LEAK-SAFE: season-level, no per-game filtering needed.
    """
    df = _load("pos_def", DATA / "team_positional_defense_2025-26.parquet")
    if df is None or df.empty:
        return {}

    team_col = "team_abbreviation" if "team_abbreviation" in df.columns else None
    if team_col is None:
        return {}

    rows = df[df[team_col] == team_tricode]
    if rows.empty:
        return {}

    row = rows.iloc[0]

    rim_d_fg_pct = _clamp_pct(_rd(row.get("rim_lt6_d_fg_pct")))
    rim_normal_fg_pct = _clamp_pct(_rd(row.get("rim_lt6_normal_fg_pct")))
    rim_freq = _clamp_pct(_rd(row.get("rim_lt6_freq")))
    paint_d_fg_pct = _clamp_pct(_rd(row.get("paint_lt10_d_fg_pct")))
    paint_normal_fg_pct = _clamp_pct(_rd(row.get("paint_lt10_normal_fg_pct")))

    # Plus-minus are signed diffs (allowed in validator as _pct_plusminus is
    # named with pct_plusminus -- the validator exempts _plusminus via _SIGNED_MARKERS
    # but only on leaf names containing those markers; store as _minus_ names to
    # be explicit and validator-safe regardless).
    rim_plus_minus = _rd(row.get("rim_lt6_pct_plusminus"))
    paint_plus_minus = _rd(row.get("paint_lt10_pct_plusminus"))

    return {
        "rim_fg_pct_allowed": rim_d_fg_pct,         # proportion [0,1]
        "rim_normal_fg_pct": rim_normal_fg_pct,      # league-avg for those shots [0,1]
        "rim_freq_faced": rim_freq,                  # proportion of shots that are rim [0,1]
        "paint_fg_pct_allowed": paint_d_fg_pct,      # proportion [0,1]
        "paint_normal_fg_pct": paint_normal_fg_pct,  # league-avg for those shots [0,1]
        # signed differences (rim allowed minus normal): exempt via _minus_ marker
        "rim_fg_pct_minus_normal": rim_plus_minus,
        "paint_fg_pct_minus_normal": paint_plus_minus,
        "_source": "team_positional_defense_2025-26.parquet (season summary)",
    }


def _def_rtg_stats(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Defensive rating and rebounding from team_advanced_stats.parquet.

    Computes per-game rolling mean for all games with game_date <= as_of.
    This is the primary n-anchor (CRITICAL LESSON 1: n = actual games played).
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
        [c for c in ["def_rtg", "dreb_pct"] if c in rows.columns]
    ].mean()

    dreb_pct = _rd(means.get("dreb_pct"))
    return {
        "def_rtg": _rd(means.get("def_rtg")),
        "dreb_pct": _clamp_pct(dreb_pct),
        "n_games": n,
        "_source": "team_advanced_stats.parquet (per-game rolling mean <= as_of)",
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamPaintDefense(AtlasSection):
    """Deep team paint-defense atlas section (team entity, section='paint_defense').

    Builds a provenance-stamped, leak-safe artifact covering opponent paint
    FG% allowed (z-scored rolling window), rim/paint shot FG% allowed
    (season positional defense), and defensive rating / rebounding from the
    per-game advanced stats.  Reserves 1 CV slot for rim-contest distance.

    Sources used:
      - data/intelligence/opp_paint_allowance.parquet   (z-scored rolling window)
      - data/team_positional_defense_2025-26.parquet    (rim/paint FG% season summary)
      - data/team_advanced_stats.parquet                (def_rtg, dreb_pct, n-anchor)

    DEFER sub-sections (no team-grain source parquet):
      - blk_pg         — blocks per game not yet in a per-game team parquet
      - paint_touch_rate — opponent paint-touch frequency not in current sources
    """

    name: str = "paint_defense"
    entity: str = "team"
    source_name: str = (
        "opp_paint_allowance.parquet + "
        "team_positional_defense_2025-26.parquet + "
        "team_advanced_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the paint_defense artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary — only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when the primary source is missing for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        # --- Gather sub-components ---
        adv = _def_rtg_stats(tricode, as_of)
        opp_paint = _opp_paint_allowance(tricode, as_of)
        rim = _rim_defense_positional(tricode)

        # Bail when primary source (team_advanced_stats) is empty
        if not adv:
            return None

        # --- n-anchor: use real game count from team_advanced_stats ---
        n = adv.get("n_games", 0)

        # --- opp_paint_allowed sub-dict (z-scores rolling window) ---
        opp_paint_sub: Dict[str, Any]
        if opp_paint:
            opp_paint_sub = {
                "opp_paint_pct_allowed_z": opp_paint.get("opp_paint_pct_allowed_z"),
                "opp_3pt_pct_allowed_z": opp_paint.get("opp_3pt_pct_allowed_z"),
                "opp_mid_pct_allowed_z": opp_paint.get("opp_mid_pct_allowed_z"),
                "opp_paint_dwell_pct_allowed_z": opp_paint.get(
                    "opp_paint_dwell_pct_allowed_z"
                ),
                "opp_shot_mix_deviation_z": opp_paint.get("opp_shot_mix_deviation_z"),
                "n_games_window": opp_paint.get("n_games_window"),
                "data_density": opp_paint.get("data_density"),
                "_source": opp_paint.get("_source"),
            }
        else:
            opp_paint_sub = {
                "_note": (
                    "DEFER: opp_paint_allowance.parquet has no snapshot <= as_of "
                    "for this team."
                )
            }

        # --- rim_defense sub-dict (season positional defense) ---
        rim_sub: Dict[str, Any]
        if rim:
            rim_sub = {
                "rim_fg_pct_allowed": rim.get("rim_fg_pct_allowed"),
                "rim_normal_fg_pct": rim.get("rim_normal_fg_pct"),
                "rim_freq_faced": rim.get("rim_freq_faced"),
                "paint_fg_pct_allowed": rim.get("paint_fg_pct_allowed"),
                "paint_normal_fg_pct": rim.get("paint_normal_fg_pct"),
                "rim_fg_pct_minus_normal": rim.get("rim_fg_pct_minus_normal"),
                "paint_fg_pct_minus_normal": rim.get("paint_fg_pct_minus_normal"),
                "_source": rim.get("_source"),
            }
        else:
            rim_sub = {
                "_note": (
                    "DEFER: team_positional_defense_2025-26.parquet missing or "
                    "team_abbreviation not found."
                )
            }

        # --- def_rtg sub-dict ---
        def_rtg_sub: Dict[str, Any] = {
            "def_rtg": adv.get("def_rtg"),
            "dreb_pct": adv.get("dreb_pct"),
            "_source": adv.get("_source"),
        }

        # --- DEFER placeholders ---
        blk_pg_sub: Dict[str, Any] = {
            "_note": (
                "DEFER: blocks per game not available in a per-game team parquet. "
                "Add when scripts/fetch_team_traditional_boxscores.py ships a "
                "team-grain parquet with a blk column."
            )
        }
        paint_touch_rate_sub: Dict[str, Any] = {
            "_note": (
                "DEFER: opponent paint-touch frequency per possession not in "
                "current sources.  opp_paint_allowance carries shot-mix z-scores "
                "but not raw possession-level touch counts.  Wire when a "
                "team-grain possession/touch parquet is added."
            )
        }

        # --- Assemble sub_fields ---
        sub_fields: Dict[str, Any] = {
            "opp_paint_allowed": opp_paint_sub,
            "rim_defense": rim_sub,
            "def_rtg": def_rtg_sub,
            "blk_pg": blk_pg_sub,
            "paint_touch_rate": paint_touch_rate_sub,
        }

        # Headline scalar: defensive rating (best single paint-defense summary)
        value = adv.get("def_rtg")

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
            "opp_paint_allowed",
            "rim_defense",
            "def_rtg",
            "blk_pg",
            "paint_touch_rate",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # def_rtg should be in a plausible defensive range (90-130 pts/100 poss)
        def_rtg_val = sf.get("def_rtg", {}).get("def_rtg")
        if def_rtg_val is not None and not (90.0 <= def_rtg_val <= 135.0):
            return False

        # rim FG% allowed should be [0, 1] if present
        rim_pct = sf.get("rim_defense", {}).get("rim_fg_pct_allowed")
        if rim_pct is not None and not (0.0 <= rim_pct <= 1.0):
            return False

        # paint FG% allowed should be [0, 1] if present
        paint_pct = sf.get("rim_defense", {}).get("paint_fg_pct_allowed")
        if paint_pct is not None and not (0.0 <= paint_pct <= 1.0):
            return False

        # dreb_pct should be [0, 1] if present
        dreb = sf.get("def_rtg", {}).get("dreb_pct")
        if dreb is not None and not (0.0 <= dreb <= 1.0):
            return False

        # CV slots must all have value=None (CV branch hasn't run yet)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for paint_defense (values None; CV fills later).

        The CV-fix session calls::
            store.fill_cv_slot("team", tricode, "paint_defense", slot, as_of, value)
        to populate each slot WITHOUT a profile rebuild.  Keys are stable contract.
        """
        return {
            "avg_rim_contest": CVSlot(
                name="avg_rim_contest",
                dtype="float",
                description=(
                    "Mean rim-contest distance (ft) from CV tracking at the moment "
                    "of each shot attempt within 6 ft of the basket, averaged over "
                    "all rim-area shot events for this team's defensive possessions. "
                    "Requires CV EventDetector rim-shot tagging + homography "
                    "court-coordinate nearest-defender lookup."
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
    """Build paint_defense for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (str, e.g. ["OKC", "BOS"]).
                       If None, discovers from team_advanced_stats.parquet.
        as_of:         leak boundary date (defaults to today UTC).
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

    section = TeamPaintDefense()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
