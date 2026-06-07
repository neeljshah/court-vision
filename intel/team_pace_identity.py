"""ARM-B atlas section: ``pace_identity`` -- team tempo and possession-rhythm profile.

Implements :class:`AtlasSection` for the ``"pace_identity"`` section of a team's
persistent profile.  Every sub-field is derived from existing parquets cited in
spec_features.md / spec_intel_memory.md -- no re-derivation.

**Sub-field coverage:**

REAL (populated from parquets):
  tempo.*           -- pace_pg (possessions/48 min), secs_per_poss (derived as
                       (48*60)/pace_pg), pace_identity label (SLOW/MODERATE/FAST/VERY_FAST),
                       pace_variance (game-to-game pace variability) from
                       data/team_advanced_stats.parquet (per-game rolling mean <=as_of) and
                       data/nba/season_games_*.json (home_pace_variance/away_pace_variance).
  efficiency.*      -- off_rtg, tov_ratio (turnovers per 100 possessions), oreb_pct,
                       efg_pct from data/team_advanced_stats.parquet (per-game, <=as_of).
  ft_rate_proxy.*   -- home_ft_rate_L10 / away_ft_rate_L10 (rolling L10 free-throw
                       rate) from data/nba/season_games_*.json; used as a proxy for
                       push-after-make aggressiveness (fast-break FT attempts correlate
                       with early-offense intent).  Averaged as team_ft_rate_l10.
  pace_variance.*   -- game-to-game pace standard deviation (home_pace_variance mean +
                       away_pace_variance mean) from season_games_*.json.

DEFER (no source parquet available):
  early_offense.*   -- DEFER: no per-game early-offense possession count parquet exists.
                       Proxy via ft_rate_l10 (wired); true early-offense rate requires
                       PBP-anchored possession tagging (gated on scoreboard_ocr fix).
  push_after_make.* -- DEFER: no per-game push-after-make / push-after-miss possession
                       log.  Requires PBP EventDetector tagging at the possession level.
  push_after_miss.* -- DEFER: same gap as push_after_make.
  push_after_to.*   -- DEFER: same gap; secondary-break / push-after-turnover rate needs
                       PBP-possession labeling (EventDetector TOV -> fast-break window).
  transition_rate.* -- DEFER: pbp_possession_features.parquet has no team_tricode column;
                       wire when build_pbp_possession_features.py emits a team-grain
                       companion with push/early-offense possession type labels.

RESERVED CV SLOTS (value=None; CV branch fills later via store.fill_cv_slot):
  avg_court_advance_speed -- mean court-advance speed (ft/s) of ball-handler following
                              a made FG, missed FG, or defensive rebound in the first
                              3 s of an offensive possession (CV velocity + homography).
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


def _clamp_pct(v: Optional[float], hi: float = 1.0) -> Optional[float]:
    """Null out proportions that are out-of-range rather than shipping invalid data."""
    if v is None:
        return None
    if not (0.0 <= v <= hi):
        return None
    return v


# ---------------------------------------------------------------------------
# Pace-identity label
# ---------------------------------------------------------------------------

_PACE_BINS: List[tuple] = [
    (98.0, "SLOW"),
    (100.5, "MODERATE"),
    (103.0, "FAST"),
    (float("inf"), "VERY_FAST"),
]


def _pace_label(pace: float) -> str:
    """Map average pace (possessions/48 min) to categorical identity label."""
    for threshold, label in _PACE_BINS:
        if pace < threshold:
            return label
    return "VERY_FAST"


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _team_adv_tempo(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate tempo/efficiency from team_advanced_stats.parquet <=as_of.

    Returns pace_pg, secs_per_poss, off_rtg, tov_ratio, oreb_pct, efg_pct, n_games.
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
    cols = [c for c in ["pace", "off_rtg", "tov_ratio", "oreb_pct", "efg_pct"]
            if c in rows.columns]
    means = rows[cols].mean()

    pace_val = _rd(means.get("pace"))
    secs = _rd((48.0 * 60.0) / pace_val) if pace_val else None

    # tov_ratio is turnovers per 100 possessions -- unbounded, NOT a proportion.
    # oreb_pct / efg_pct are proportions in [0,1] (validated via _clamp_pct).
    return {
        "pace_pg": pace_val,
        "secs_per_poss": secs,
        "pace_identity_label": _pace_label(pace_val) if pace_val else None,
        "off_rtg": _rd(means.get("off_rtg")),
        "tov_ratio": _rd(means.get("tov_ratio")),   # turnovers per 100 possessions
        "oreb_pct": _clamp_pct(_rd(means.get("oreb_pct"))),
        "efg_pct": _clamp_pct(_rd(means.get("efg_pct")), hi=1.6),
        "n_games": n,
    }


def _season_games_pace(
    team_tricode: str, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Aggregate pace_variance and ft_rate_l10 from season_games_*.json <=as_of.

    Reads home_pace_variance / away_pace_variance (game-to-game pace variability)
    and home_ft_rate_L10 / away_ft_rate_L10 (rolling FT-rate, proxy for push-after-make
    aggressiveness) for all games involving the team where game_date <= as_of.
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

    home_mask = df.get("home_team", pd.Series(dtype=str)) == team_tricode
    away_mask = df.get("away_team", pd.Series(dtype=str)) == team_tricode

    pace_var_vals: List[float] = []
    ft_rate_vals: List[float] = []

    if "home_team" in df.columns:
        hdf = df[home_mask & (df["game_date"] <= as_of_ts)]
        if not hdf.empty:
            if "home_pace_variance" in hdf.columns:
                pace_var_vals.extend(hdf["home_pace_variance"].dropna().tolist())
            if "home_ft_rate_L10" in hdf.columns:
                ft_rate_vals.extend(hdf["home_ft_rate_L10"].dropna().tolist())

        adf = df[away_mask & (df["game_date"] <= as_of_ts)]
        if not adf.empty:
            if "away_pace_variance" in adf.columns:
                pace_var_vals.extend(adf["away_pace_variance"].dropna().tolist())
            if "away_ft_rate_L10" in adf.columns:
                ft_rate_vals.extend(adf["away_ft_rate_L10"].dropna().tolist())

    result: Dict[str, Any] = {}
    if pace_var_vals:
        result["pace_variance_mean"] = _rd(float(np.mean(pace_var_vals)))
        result["n_pace_var_games"] = len(pace_var_vals)
    if ft_rate_vals:
        ft_mean = _rd(float(np.mean(ft_rate_vals)))
        # ft_rate_L10 is a free-throw rate in [0,1]; null out-of-range values
        result["ft_rate_l10"] = _clamp_pct(ft_mean)

    return result


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class TeamPaceIdentity(AtlasSection):
    """Deep team pace-identity atlas section (team entity, section='pace_identity').

    Builds a provenance-stamped, leak-safe artifact covering:
      - tempo: pace_pg (poss/48), secs_per_poss, pace_identity_label, pace_variance
      - efficiency: off_rtg, tov_ratio, oreb_pct, efg_pct
      - ft_rate_proxy: ft_rate_l10 as early-offense/push-after-make proxy
      - DEFER stubs: early_offense, push_after_make, push_after_miss, push_after_to,
                     transition_rate (all gated on PBP-anchoring / EventDetector)

    Reserves 1 CV slot: avg_court_advance_speed (CV velocity + homography).

    Sources used:
      - data/team_advanced_stats.parquet       (pace, off_rtg, tov_ratio, oreb_pct, efg_pct)
      - data/nba/season_games_*.json           (pace_variance, ft_rate_L10 proxy)
    """

    name: str = "pace_identity"
    entity: str = "team"
    source_name: str = (
        "team_advanced_stats.parquet + season_games_*.json"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the pace_identity artifact for team ``entity_id`` as-of ``as_of``.

        Args:
            entity_id: team tricode (str, e.g. "OKC").
            as_of:     leak boundary -- only data with game_date <= as_of is used.

        Returns:
            AtlasArtifact or None when the primary source has no data for this team.
        """
        tricode = str(entity_id).upper()
        as_of_str = as_of.date().isoformat()

        adv = _team_adv_tempo(tricode, as_of)
        sg = _season_games_pace(tricode, as_of)

        if not adv:
            return None

        # --- tempo sub-dict ---
        tempo: Dict[str, Any] = {
            "pace_pg": adv.get("pace_pg"),
            "secs_per_poss": adv.get("secs_per_poss"),
            "pace_identity_label": adv.get("pace_identity_label"),
            "pace_variance_mean": sg.get("pace_variance_mean"),
            "_source": "team_advanced_stats.parquet (pace); season_games_*.json (variance)",
        }

        # --- efficiency sub-dict ---
        # tov_ratio is turnovers-per-100-possessions (NOT a proportion, not _pct suffix)
        efficiency: Dict[str, Any] = {
            "off_rtg": adv.get("off_rtg"),
            "tov_ratio": adv.get("tov_ratio"),
            "oreb_pct": adv.get("oreb_pct"),
            "efg_pct": adv.get("efg_pct"),
        }

        # --- ft_rate_proxy sub-dict (push-after-make aggressiveness proxy) ---
        ft_rate_proxy: Dict[str, Any] = {
            "ft_rate_l10": sg.get("ft_rate_l10"),
            "_source": "season_games_*.json home/away_ft_rate_L10 rolling mean",
            "_note": (
                "ft_rate_l10 is a rolling L10 free-throw rate; used as a proxy for "
                "early-offense / push-after-make aggressiveness until PBP-anchored "
                "possession tagging is unblocked by scoreboard_ocr fix."
            ),
        }

        # --- DEFER placeholders ---
        early_offense: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game early-offense possession count parquet exists. "
                "True early-offense rate requires PBP-anchored possession tagging "
                "(gated on scoreboard_ocr.py fix for clock/period OCR)."
            )
        }
        push_after_make: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game push-after-made-FG possession log. Requires "
                "PBP EventDetector tagging: made FG -> fast-break window (<4 s)."
            )
        }
        push_after_miss: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game push-after-missed-FG possession log. Requires "
                "PBP EventDetector: DREB -> transition window classification."
            )
        }
        push_after_to: Dict[str, Any] = {
            "_note": (
                "DEFER: no per-game push-after-turnover possession log. Requires "
                "PBP EventDetector: TOV -> secondary-break window (<5 s)."
            )
        }
        transition_rate: Dict[str, Any] = {
            "_note": (
                "DEFER: pbp_possession_features.parquet has no team_tricode column. "
                "Wire when build_pbp_possession_features.py emits a team-grain companion."
            )
        }

        sub_fields: Dict[str, Any] = {
            "tempo": tempo,
            "efficiency": efficiency,
            "ft_rate_proxy": ft_rate_proxy,
            "early_offense": early_offense,
            "push_after_make": push_after_make,
            "push_after_miss": push_after_miss,
            "push_after_to": push_after_to,
            "transition_rate": transition_rate,
        }

        # Headline convenience scalar: pace_pg
        value = adv.get("pace_pg")

        n = adv.get("n_games", 1)
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
        required = {
            "tempo", "efficiency", "ft_rate_proxy",
            "early_offense", "push_after_make", "push_after_miss",
            "push_after_to", "transition_rate",
        }
        if not required.issubset(sf.keys()):
            return False

        # Pace must be in a plausible range
        pace = sf.get("tempo", {}).get("pace_pg")
        if pace is not None and not (80.0 <= pace <= 130.0):
            return False

        # secs_per_poss: at pace 80-130 this is 22-36 seconds
        secs = sf.get("tempo", {}).get("secs_per_poss")
        if secs is not None and not (20.0 <= secs <= 45.0):
            return False

        # oreb_pct in [0, 1]
        oreb = sf.get("efficiency", {}).get("oreb_pct")
        if oreb is not None and not (0.0 <= oreb <= 1.0):
            return False

        # efg_pct in [0, 1.6] (efg ceiling)
        efg = sf.get("efficiency", {}).get("efg_pct")
        if efg is not None and not (0.0 <= efg <= 1.6):
            return False

        # ft_rate_l10 in [0, 1] if present
        ft_rate = sf.get("ft_rate_proxy", {}).get("ft_rate_l10")
        if ft_rate is not None and not (0.0 <= ft_rate <= 1.0):
            return False

        # CV slots must all be reserved (value=None)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for pace_identity (values None; CV fills later).

        avg_court_advance_speed: mean court-advance speed (ft/s) of ball-handler
        following a made FG, missed FG, or defensive rebound in the first 3 seconds
        of an offensive possession.  Derived from CV velocity tracking + homography
        court-coordinate transforms (the ``avg_court_advance_speed`` pipeline slot).
        """
        return {
            "avg_court_advance_speed": CVSlot(
                name="avg_court_advance_speed",
                dtype="float",
                description=(
                    "Mean court-advance speed (ft/s) of the ball-handler in the first "
                    "3 seconds following a made FG, missed FG rebound, or turnover "
                    "recovery -- captures how aggressively the team pushes in transition "
                    "regardless of whether the possession is classified as fast-break. "
                    "Derived from CV velocity tracking + homography court coordinates."
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
    """Build pace_identity for a list of team tricodes and register via the bridge.

    Args:
        team_tricodes: list of NBA team tricodes (e.g. ["OKC", "BOS"]).
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

    section = TeamPaceIdentity()
    artifacts = []
    for tri in team_tricodes:
        try:
            art = section.build(tri, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
