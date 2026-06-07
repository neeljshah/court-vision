"""ARM-B atlas section: ``transition_halfcourt_splits`` — exhaustive per-team
offensive tempo and possession-type profile.

Implements :class:`AtlasSection` for the ``"transition_halfcourt_splits"`` section
of a team's persistent profile.  Every sub-field comes from existing parquets listed
in spec_features.md / spec_intel_memory.md — no re-derivation.

**Sub-field coverage:**

REAL (populated from existing parquets):
  pace.*                  — season-average pace, off_rtg, def_rtg from
                            data/team_advanced_stats.parquet filtered to <= as_of.
                            Includes: pace_mean, pace_std, pace_min, pace_max,
                            pace_trend (latest 5 vs earliest 5 games), off_rtg_mean,
                            def_rtg_mean, n_games.
  tempo_z.*               — CV-derived z-score signals from
                            data/intelligence/team_tempo_spacing.parquet filtered to
                            <= as_of (latest snapshot). Includes: team_tempo_z,
                            team_transition_share_z, team_possession_duration_z,
                            team_avg_spacing_z, team_paint_dwell_z,
                            team_tempo_spacing_composite_z, n_possessions_window,
                            data_density.
  cv_pace.*               — raw CV pace in seconds per 100 possessions from
                            data/intelligence/cv_pace_per_game.parquet filtered to
                            <= as_of. Includes: cv_pace_mean, cv_pace_std,
                            cv_pace_n_games, cv_pace_latest.
  pbp_possession_mix.*    — per-game average possession type counts from
                            data/cache/pbp_possession_features.parquet joined to
                            team via data/team_advanced_stats.parquet on game_id,
                            filtered to <= as_of. Includes: pbp_transition_pg,
                            pbp_halfcourt_pg (iso + pnr + post_up), pbp_iso_pg,
                            pbp_pnr_pg, pbp_post_up_pg, pbp_transition_share,
                            pbp_halfcourt_share, n_games_pbp.

DEFER (data gap — not available in current parquets):
  transition_pts_per_possession — scoring efficiency specifically in transition;
                                  DEFER: no per-possession outcome annotation
                                  joining PBP shot result to possession type.
  halfcourt_ppp               — points-per-possession in halfcourt sets;
                                DEFER: same — outcome per possession-type not in repo.
  early_offense_share         — fraction of halfcourt possessions initiated within
                                4 s of half-court crossing; DEFER: no clock-keyed
                                possession-entry annotation.

RESERVED CV SLOTS (value=None; CV branch fills later):
  transition_velocity_mean  — mean player velocity at transition-possession frames,
                              measured from CV tracking data.
  halfcourt_setup_duration  — mean seconds from half-court cross to first shot
                              attempt in halfcourt sets, from CV clock + EventDetector.
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


def _filter_as_of(df: pd.DataFrame, date_col: str, as_of: _dt.datetime) -> pd.DataFrame:
    """Return rows with date_col <= as_of (leak guard)."""
    if date_col not in df.columns:
        return df
    col = pd.to_datetime(df[date_col], errors="coerce")
    return df[col <= pd.Timestamp(as_of)].copy()


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _pace_from_adv(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Pace and rating profile from team_advanced_stats.parquet, filtered to <= as_of.

    Aggregates all games for the team up to the as_of boundary.
    Returns pace_mean, pace_std, pace_min, pace_max, pace_trend (delta between
    latest-5 and earliest-5), off_rtg_mean, def_rtg_mean, n_games.
    """
    df = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_tricode"] == tricode].copy()
    if rows.empty:
        return {}
    rows = _filter_as_of(rows, "game_date", as_of)
    if rows.empty:
        return {}

    rows = rows.sort_values("game_date")
    n = len(rows)
    pace = rows["pace"].dropna()
    off_rtg = rows["off_rtg"].dropna() if "off_rtg" in rows.columns else pd.Series([], dtype=float)
    def_rtg = rows["def_rtg"].dropna() if "def_rtg" in rows.columns else pd.Series([], dtype=float)

    pace_trend: Optional[float] = None
    if n >= 10:
        early = pace.iloc[: n // 5].mean()
        late = pace.iloc[-(n // 5) :].mean()
        pace_trend = _rd(late - early)

    return {
        "pace_mean": _rd(pace.mean()),
        "pace_std": _rd(pace.std()),
        "pace_min": _rd(pace.min()),
        "pace_max": _rd(pace.max()),
        "pace_trend": pace_trend,
        "off_rtg_mean": _rd(off_rtg.mean()),
        "def_rtg_mean": _rd(def_rtg.mean()),
        "n_games": n,
    }


def _tempo_z_from_parquet(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """CV-derived tempo/transition z-scores from team_tempo_spacing.parquet.

    Selects the latest snapshot with game_date <= as_of (highest n_games_window
    snapshot, then latest date). CV-coverage-limited: data_density is low/med.
    """
    df = _load_parquet("team_tempo", INTEL / "team_tempo_spacing.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_abbr"] == tricode].copy()
    if rows.empty:
        return {}
    rows = _filter_as_of(rows, "game_date", as_of)
    if rows.empty:
        return {}
    # Pick the snapshot with the most possessions (highest CV coverage), then latest date
    if "n_possessions_window" in rows.columns:
        rows = rows.sort_values(["n_possessions_window", "game_date"], ascending=[False, False])
    else:
        rows = rows.sort_values("game_date", ascending=False)
    row = rows.iloc[0]

    return {
        "team_tempo_z": _rd(row.get("team_tempo_z")),
        "team_transition_share_z": _rd(row.get("team_transition_share_z")),
        "team_possession_duration_z": _rd(row.get("team_possession_duration_z")),
        "team_avg_spacing_z": _rd(row.get("team_avg_spacing_z")),
        "team_paint_dwell_z": _rd(row.get("team_paint_dwell_z")),
        "team_tempo_spacing_composite_z": _rd(row.get("team_tempo_spacing_composite_z")),
        "n_possessions_window": _ri(row.get("n_possessions_window")),
        "data_density": str(row.get("data_density", "low")) if row.get("data_density") else "low",
        "_as_of_src": str(row.get("game_date", ""))[:10],
    }


def _cv_pace_from_parquet(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Raw CV pace summary from cv_pace_per_game.parquet, filtered to <= as_of.

    cv_pace is mean seconds per 100 possessions (lower = faster team).
    """
    df = _load_parquet("cv_pace", INTEL / "cv_pace_per_game.parquet")
    if df is None or df.empty:
        return {}
    rows = df[df["team_abbrev"] == tricode].copy()
    if rows.empty:
        return {}
    rows = _filter_as_of(rows, "game_date", as_of)
    if rows.empty:
        return {}

    pace_col = rows["cv_pace"].dropna()
    n = len(pace_col)
    if n == 0:
        return {}

    rows_sorted = rows.sort_values("game_date")
    latest_pace = _rd(rows_sorted["cv_pace"].dropna().iloc[-1]) if not rows_sorted["cv_pace"].dropna().empty else None

    return {
        "cv_pace_mean": _rd(pace_col.mean()),
        "cv_pace_std": _rd(pace_col.std()),
        "cv_pace_n_games": n,
        "cv_pace_latest": latest_pace,
    }


def _pbp_possession_mix(tricode: str, as_of: _dt.datetime) -> Dict[str, Any]:
    """Per-game PBP possession type mix from pbp_possession_features joined to team.

    Join path: pbp_possession_features.game_id <-> team_advanced_stats.game_id
    where team_advanced_stats.team_tricode == tricode, then aggregate per-game
    sums of pbp_transition_count, pbp_iso_poss_count, pbp_pnr_ball_handler,
    pbp_post_up_count.

    pbp_halfcourt_count = pbp_iso_poss_count + pbp_pnr_ball_handler + pbp_post_up_count
    pbp_transition_share = pbp_transition_count / (pbp_transition_count + pbp_halfcourt_count)
    """
    pbp = _load_parquet("pbp_poss", CACHE / "pbp_possession_features.parquet")
    adv = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
    if pbp is None or adv is None or pbp.empty or adv.empty:
        return {}

    # Get game_ids for the team up to as_of
    team_adv = adv[adv["team_tricode"] == tricode].copy()
    team_adv = _filter_as_of(team_adv, "game_date", as_of)
    if team_adv.empty:
        return {}
    team_game_ids = set(team_adv["game_id"].unique())

    # Filter PBP to those game_ids
    pbp_team = pbp[pbp["game_id"].isin(team_game_ids)].copy()
    # Apply game_date leak guard via pbp's own game_date column
    pbp_team = _filter_as_of(pbp_team, "game_date", as_of)
    if pbp_team.empty:
        return {}

    # Aggregate to per-game totals (sum all players on the team per game)
    sum_cols = [
        c for c in [
            "pbp_transition_count", "pbp_iso_poss_count",
            "pbp_pnr_ball_handler", "pbp_post_up_count",
        ]
        if c in pbp_team.columns
    ]
    if not sum_cols:
        return {}

    per_game = pbp_team.groupby("game_id")[sum_cols].sum()
    n_games = len(per_game)
    if n_games == 0:
        return {}

    means = per_game.mean()
    t_pg = _rd(means.get("pbp_transition_count"))
    iso_pg = _rd(means.get("pbp_iso_poss_count"))
    pnr_pg = _rd(means.get("pbp_pnr_ball_handler"))
    post_pg = _rd(means.get("pbp_post_up_count"))

    hc_pg: Optional[float] = None
    if iso_pg is not None and pnr_pg is not None and post_pg is not None:
        hc_pg = round(iso_pg + pnr_pg + post_pg, 4)

    t_share: Optional[float] = None
    hc_share: Optional[float] = None
    if t_pg is not None and hc_pg is not None and (t_pg + hc_pg) > 0:
        total = t_pg + hc_pg
        t_share = round(t_pg / total, 4)
        hc_share = round(hc_pg / total, 4)

    return {
        "pbp_transition_pg": t_pg,
        "pbp_halfcourt_pg": hc_pg,
        "pbp_iso_pg": iso_pg,
        "pbp_pnr_pg": pnr_pg,
        "pbp_post_up_pg": post_pg,
        "pbp_transition_share": t_share,
        "pbp_halfcourt_share": hc_share,
        "n_games_pbp": n_games,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamTransitionHalfcourtSplits(AtlasSection):
    """Deep team transition vs halfcourt tempo atlas section.

    Implements the ``transition_halfcourt_splits`` profile section for a team,
    covering frequency and pace split between transition and halfcourt play.

    Sub-field hierarchy:
      - pace:               NBA pace + rating from team_advanced_stats.parquet
      - tempo_z:            CV tempo/transition z-scores (team_tempo_spacing.parquet)
      - cv_pace:            raw CV pace (cv_pace_per_game.parquet)
      - pbp_possession_mix: PBP possession type counts/shares

    DEFER:
      - transition_pts_per_possession: no per-possession outcome annotation
      - halfcourt_ppp:                 no per-possession outcome annotation
      - early_offense_share:           no clock-keyed possession-entry annotation

    CV slots reserved (value=None, CV branch fills later):
      - transition_velocity_mean:  mean player velocity at transition frames (ft/s)
      - halfcourt_setup_duration:  mean seconds from half-court entry to first shot (s)
    """

    name: str = "transition_halfcourt_splits"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + team_tempo_spacing.parquet + "
        "cv_pace_per_game.parquet + pbp_possession_features.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the transition_halfcourt_splits artifact for a team as-of ``as_of``.

        Leak guarantee:
          - team_advanced_stats: filtered to game_date <= as_of.
          - team_tempo_spacing: latest snapshot with game_date <= as_of.
          - cv_pace_per_game: games with game_date <= as_of.
          - pbp_possession_features: game_date <= as_of, joined via game_ids whose
            team_advanced_stats game_date is also <= as_of.

        Args:
            entity_id: team tricode string (e.g. "BOS", "LAL").
            as_of:     datetime representing the decision boundary (leak cutoff).

        Returns:
            AtlasArtifact with populated sub_fields and reserved cv_fields,
            or None if no source has data for this team.
        """
        tricode = str(entity_id).upper().strip()
        as_of_str = as_of.date().isoformat()

        pace = _pace_from_adv(tricode, as_of)
        tempo_z = _tempo_z_from_parquet(tricode, as_of)
        cv_pace = _cv_pace_from_parquet(tricode, as_of)
        pbp_mix = _pbp_possession_mix(tricode, as_of)

        # Bail if all sources are empty
        if not pace and not tempo_z and not cv_pace and not pbp_mix:
            return None

        sub_fields: Dict[str, Any] = {
            "pace": pace or {},
            "tempo_z": tempo_z or {},
            "cv_pace": cv_pace or {},
            "pbp_possession_mix": pbp_mix or {},
            # DEFER sub-fields
            "transition_pts_per_possession": {
                "_note": (
                    "DEFER: no per-possession outcome annotation joining PBP shot "
                    "result to possession type available in repo."
                )
            },
            "halfcourt_ppp": {
                "_note": (
                    "DEFER: points-per-possession in halfcourt sets requires "
                    "outcome-tagged possession parquet not currently in repo."
                )
            },
            "early_offense_share": {
                "_note": (
                    "DEFER: fraction of halfcourt possessions initiated within 4 s "
                    "of half-court crossing requires clock-keyed possession-entry "
                    "annotation not currently available."
                )
            },
        }

        # Determine representative n: prefer adv-stats game count (largest sample)
        n_candidates: List[int] = []
        if pace.get("n_games"):
            n_candidates.append(int(pace["n_games"]))
        if pbp_mix.get("n_games_pbp"):
            n_candidates.append(int(pbp_mix["n_games_pbp"]))
        if cv_pace.get("cv_pace_n_games"):
            n_candidates.append(int(cv_pace["cv_pace_n_games"]))
        if tempo_z.get("n_possessions_window"):
            n_candidates.append(int(tempo_z["n_possessions_window"]))
        n = max(n_candidates) if n_candidates else 1

        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        # Headline value: transition share from PBP if available, else tempo_z composite
        headline: Any = None
        if pbp_mix.get("pbp_transition_share") is not None:
            headline = pbp_mix["pbp_transition_share"]
        elif tempo_z.get("team_transition_share_z") is not None:
            headline = tempo_z["team_transition_share_z"]

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=tricode,
            value=headline,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, pace values plausible.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {
            "pace", "tempo_z", "cv_pace", "pbp_possession_mix",
            "transition_pts_per_possession", "halfcourt_ppp", "early_offense_share",
        }
        if not required_keys.issubset(sf.keys()):
            return False

        # Pace: if populated, sanity-check the value range (NBA pace ~85-115)
        pace = sf.get("pace", {})
        if pace.get("pace_mean") is not None:
            if not (70.0 <= pace["pace_mean"] <= 140.0):
                return False

        # Transition share: if available, must be 0–1
        pbp = sf.get("pbp_possession_mix", {})
        if pbp.get("pbp_transition_share") is not None:
            if not (0.0 <= pbp["pbp_transition_share"] <= 1.0):
                return False

        # CV fields: all values must be None (CV branch hasn't run yet)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema (values None — CV branch fills later).

        The CV-fix session calls
        ``store.fill_cv_slot("team", tricode, "transition_halfcourt_splits", slot,
        as_of, value)`` to populate these WITHOUT a profile rebuild.

        Slots:
          transition_velocity_mean  — mean player velocity at transition frames (ft/s)
          halfcourt_setup_duration  — seconds from half-court crossing to first shot (s)
        """
        return {
            "transition_velocity_mean": CVSlot(
                name="transition_velocity_mean",
                dtype="float",
                description=(
                    "Mean player velocity (ft/s) measured across all frames tagged as "
                    "transition-possession by the CV EventDetector "
                    "(fast_break_flag_any=1 in possession_cv_state). "
                    "Indicates how fast the team pushes in transition."
                ),
                unit="ft/s",
                value=None,
            ),
            "halfcourt_setup_duration": CVSlot(
                name="halfcourt_setup_duration",
                dtype="float",
                description=(
                    "Mean duration in seconds from the moment the ball crosses half-court "
                    "to the first shot attempt within halfcourt possessions, measured "
                    "via CV clock anchoring + EventDetector shot events. "
                    "Lower values indicate quicker halfcourt setup offenses."
                ),
                unit="s",
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
    """Build transition_halfcourt_splits for all teams and register via the bridge.

    Args:
        team_tricodes: list of 3-letter team tricodes.  If None, discovers from
                       team_advanced_stats.parquet (all available teams).
        as_of:        leak boundary date (defaults to today midnight UTC).
        store:        PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:      skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if team_tricodes is None:
        adv = _load_parquet("team_adv", DATA / "team_advanced_stats.parquet")
        if adv is not None and not adv.empty and "team_tricode" in adv.columns:
            team_tricodes = sorted(adv["team_tricode"].dropna().unique().tolist())
        else:
            team_tricodes = []

    section = TeamTransitionHalfcourtSplits()
    artifacts: List[AtlasArtifact] = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
