"""ARM-B atlas section: ``shot_clock_scoring`` — per-player scoring by shot-clock bucket.

Implements :class:`AtlasSection` for the ``"shot_clock_scoring"`` section of a player's
persistent profile.  Shot-clock buckets: early (>18s), mid (7-18s), late (<7s).

**Sub-field coverage:**

REAL (populated from parquets):
  late_clock.*    — late-clock (<7s) shot frequency (shots_pg, rate), from
                    data/cache/pbp_possession_features.parquet (pbp_late_clock_shots,
                    per-game agg, player_id + game_date, leak-safe as_of filter).
  overall.*       — season-aggregate eFG%, TS%, usage_pct from
                    data/player_adv_stats.parquet (per-game agg, game_date filter).
  shot_quality.*  — overall efficiency proxies (eFG, TS) as shot-quality context.

DEFER (data gap — source parquets lack per-bucket eFG/freq by player_id):
  early.*         — early (>18s) shots: freq + eFG + shot quality
                    DEFER: data/intelligence/shot_clock_buckets.parquet uses jersey-number
                    pkey (not player_id); no direct linkage available for most players.
                    CV will populate via contest_by_clock slot.
  mid.*           — mid (7-18s) shots: freq + eFG + shot quality
                    DEFER: same source constraint as early.*.

RESERVED CV SLOTS (value=None, CV branch fills later):
  contest_by_clock — per-bucket (early/mid/late) contest rate (fraction contested)
                     from CV EventDetector + defender proximity at shot release.
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


# ---------------------------------------------------------------------------
# Data-loading helpers (lazy, module-level cache)
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


def _clamp_rate(v: Optional[float]) -> Optional[float]:
    """Null values outside [0, 1] (validator rejects *_rate out of this range)."""
    if v is None:
        return None
    if not (0.0 <= v <= 1.0):
        return None
    return v


def _clamp_pct(v: Optional[float], ceil: float = 1.0) -> Optional[float]:
    """Null values outside [0, ceil] (validator rejects *_pct out of range)."""
    if v is None:
        return None
    if not (0.0 <= v <= ceil):
        return None
    return v


# ---------------------------------------------------------------------------
# Per-source aggregation helpers
# ---------------------------------------------------------------------------

def _pbp_late_clock_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Late-clock (<7s) shot frequency from pbp_possession_features, filtered <= as_of.

    Returns per-game mean of pbp_late_clock_shots and total game count.
    Leak-safe: filters game_date <= as_of (game_date is 'YYYY-MM-DD' string in the parquet).
    """
    path = CACHE / "pbp_possession_features.parquet"
    df = _load("pbp_poss_sc", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter: keep only games on or before as_of
    if "game_date" in rows.columns:
        rows["_gd"] = pd.to_datetime(rows["game_date"], errors="coerce")
        rows = rows[rows["_gd"].notna() & (rows["_gd"] <= pd.Timestamp(as_of))]

    if rows.empty:
        return {}

    n_games = len(rows)
    late_shots_mean = float(rows["pbp_late_clock_shots"].mean())
    # Derive late_clock_rate as fraction of per-game total shots proxy:
    # pbp_late_clock_shots is an absolute count per game; we express the rate as
    # late_pg / (late_pg + mid_pg + early_pg) proxy -- but we only have late here.
    # Use total_possessions proxy (all pbp counts combined) as denominator.
    poss_cols = [
        "pbp_iso_poss_count", "pbp_pnr_ball_handler", "pbp_pnr_screener_proxy",
        "pbp_post_up_count", "pbp_transition_count",
    ]
    avail = [c for c in poss_cols if c in rows.columns]
    late_rate: Optional[float] = None
    if avail and "pbp_late_clock_shots" in rows.columns:
        total_poss_mean = float(rows[avail].sum(axis=1).mean())
        if total_poss_mean > 0:
            raw_rate = late_shots_mean / total_poss_mean
            late_rate = _clamp_rate(round(raw_rate, 4))

    result: Dict[str, Any] = {
        "n_games": n_games,
        "late_shots_pg": _rd(late_shots_mean),
    }
    if late_rate is not None:
        result["late_clock_rate"] = late_rate

    return result


def _adv_efficiency_for_player(
    pid: int, as_of: _dt.datetime
) -> Dict[str, Any]:
    """Season-aggregate efficiency from player_adv_stats, filtered to games <= as_of.

    Returns efg_pct, ts_pct (overall), and usage_pct as shot-quality context.
    Columns in parquet: effectivefieldgoalpercentage, trueshootingpercentage,
    usagepercentage — stored as fractions in [0, 1].
    """
    path = DATA / "player_adv_stats.parquet"
    df = _load("adv_sc", path)
    if df is None or df.empty:
        return {}

    rows = df[df["player_id"] == pid].copy()
    if rows.empty:
        return {}

    # Leak filter: game_date is 'YYYY-MM-DD' string in this parquet
    if "game_date" in rows.columns:
        rows["_gd"] = pd.to_datetime(rows["game_date"], errors="coerce")
        rows = rows[rows["_gd"].notna() & (rows["_gd"] <= pd.Timestamp(as_of))]

    if rows.empty:
        return {}

    n_games = len(rows)
    efg_raw = _rd(rows["effectivefieldgoalpercentage"].mean()) if "effectivefieldgoalpercentage" in rows.columns else None
    ts_raw = _rd(rows["trueshootingpercentage"].mean()) if "trueshootingpercentage" in rows.columns else None
    usg_raw = _rd(rows["usagepercentage"].mean()) if "usagepercentage" in rows.columns else None

    # eFG ceil is 1.6 (per validator spec for "efg" in leaf); TS same treatment
    efg = _clamp_pct(efg_raw, ceil=1.6)
    ts = _clamp_pct(ts_raw, ceil=1.6)
    usg = _clamp_pct(usg_raw, ceil=1.0)

    return {
        "n_games": n_games,
        "efg_pct": efg,
        "ts_pct": ts,
        "usage_pct": usg,
    }


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerShotClockScoring(AtlasSection):
    """Shot-clock scoring profile atlas section (player entity, section='shot_clock_scoring').

    Covers late-clock (<7s) shot frequency from PBP, overall efficiency context from
    advanced boxscores, and reserves CV slots for per-bucket contest rates.  Early and
    mid buckets are DEFER pending a player_id-keyed shot-clock-bucket source.

    Sources:
      - data/cache/pbp_possession_features.parquet (late-clock shots, per-game, leak-safe)
      - data/player_adv_stats.parquet (eFG%/TS%/usage, per-game, leak-safe)

    DEFER:
      - early (>18s) freq + eFG: shot_clock_buckets uses jersey pkey, not player_id.
      - mid (7-18s) freq + eFG: same source constraint.
      - per-bucket eFG by bucket: no parquet with (player_id, bucket, efg_pct).

    CV slots (reserved, value=None):
      - contest_by_clock: per-bucket contest rate (early/mid/late) from CV EventDetector.
    """

    name: str = "shot_clock_scoring"
    entity: str = "player"
    source_name: str = (
        "pbp_possession_features.parquet + player_adv_stats.parquet"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the shot_clock_scoring artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: both sources are filtered to game_date <= as_of before any
        aggregation.  The stamped provenance n is the ACTUAL per-game row count from
        pbp_possession_features (primary source), falling back to adv_stats row count.

        Returns None when both sources are missing for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        late_clock = _pbp_late_clock_for_player(pid, as_of)
        adv_eff = _adv_efficiency_for_player(pid, as_of)

        # Bail if nothing was populated
        if not late_clock and not adv_eff:
            return None

        # ----------------------------------------------------------------
        # late_clock sub-dict (REAL from PBP)
        # ----------------------------------------------------------------
        late_clock_data: Dict[str, Any] = {
            "shots_pg": late_clock.get("late_shots_pg"),
            "late_clock_rate": late_clock.get("late_clock_rate"),
            "_note": (
                "late = <7s on shot clock; shots_pg from pbp_late_clock_shots "
                "(pbp_possession_features.parquet); late_clock_rate = shots_pg / "
                "total_possessions proxy."
            ),
        }

        # ----------------------------------------------------------------
        # early / mid sub-dicts (DEFER — no player_id-keyed bucket source)
        # ----------------------------------------------------------------
        early_data: Dict[str, Any] = {
            "_note": (
                "DEFER: shot_clock_buckets.parquet uses jersey-number pkey, not "
                "player_id; player_id linkage unavailable for most players. CV "
                "branch will populate contest_by_clock slot (early/mid/late rates)."
            ),
            "shots_pg": None,
            "efg_pct": None,
        }
        mid_data: Dict[str, Any] = {
            "_note": (
                "DEFER: same pkey constraint as early bucket. Will be populated "
                "when a player_id-keyed shot-clock-by-bucket parquet is available."
            ),
            "shots_pg": None,
            "efg_pct": None,
        }

        # ----------------------------------------------------------------
        # overall shot-quality context (REAL from adv_stats)
        # ----------------------------------------------------------------
        shot_quality: Dict[str, Any] = {
            "efg_pct": adv_eff.get("efg_pct"),
            "ts_pct": adv_eff.get("ts_pct"),
            "usage_pct": adv_eff.get("usage_pct"),
        }

        # ----------------------------------------------------------------
        # Assemble sub_fields
        # ----------------------------------------------------------------
        sub_fields: Dict[str, Any] = {
            "early": early_data,
            "mid": mid_data,
            "late": late_clock_data,
            "shot_quality": shot_quality,
        }

        # ----------------------------------------------------------------
        # Provenance n: ACTUAL game-row count (NOT n_seasons)
        # Prefer pbp n_games (per-game rows, most granular); fall back to adv.
        # ----------------------------------------------------------------
        n_candidates: List[int] = []
        if late_clock.get("n_games"):
            n_candidates.append(int(late_clock["n_games"]))
        if adv_eff.get("n_games"):
            n_candidates.append(int(adv_eff["n_games"]))
        n = max(n_candidates) if n_candidates else 0

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
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    # ------------------------------------------------------------------
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity: required keys present; proportions in range; CV slots null.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {"early", "mid", "late", "shot_quality"}
        if not required_keys.issubset(sf.keys()):
            return False

        # efg_pct / ts_pct must be in [0, 1.6] (or None)
        sq = sf.get("shot_quality", {})
        for key in ("efg_pct", "ts_pct"):
            v = sq.get(key)
            if v is not None and not (0.0 <= v <= 1.6):
                return False

        # usage_pct must be in [0, 1] (or None)
        usg = sq.get("usage_pct")
        if usg is not None and not (0.0 <= usg <= 1.0):
            return False

        # late_clock_rate must be in [0, 1] (or None)
        late = sf.get("late", {})
        lcr = late.get("late_clock_rate")
        if lcr is not None and not (0.0 <= lcr <= 1.0):
            return False

        # shots_pg must be non-negative (or None)
        shots_pg = late.get("shots_pg")
        if shots_pg is not None and shots_pg < 0:
            return False

        # CV slots must all be reserved (value=None)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for shot_clock_scoring (values None until CV fills).

        The CV branch calls
        ``store.fill_cv_slot("player", pid, "shot_clock_scoring", slot, as_of, value)``
        to populate these WITHOUT a profile rebuild.
        """
        return {
            "contest_by_clock": CVSlot(
                name="contest_by_clock",
                dtype="dist",
                description=(
                    "Per-bucket (early >18s / mid 7-18s / late <7s) fraction of shot "
                    "attempts classified as contested (nearest defender <= 4 ft at "
                    "release), from CV EventDetector + homography coordinates.  "
                    "Shape: {'early': float, 'mid': float, 'late': float}, each in "
                    "[0, 1].  Null until CV branch fills."
                ),
                unit=None,
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration helper (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build shot_clock_scoring for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids (int).  If None, discovers from pbp parquet.
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        pbp_path = CACHE / "pbp_possession_features.parquet"
        df = _load("pbp_poss_disc", pbp_path)
        if df is not None and not df.empty and "player_id" in df.columns:
            player_ids = sorted(df["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerShotClockScoring()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
