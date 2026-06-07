"""ARM-B atlas section: ``rest_b2b_splits`` — per-player rest-day split profiles.

Implements :class:`AtlasSection` for the ``"rest_b2b_splits"`` section of a
player's persistent profile.  Computes production metrics bucketed by rest-day
category (B2B = 0 days rest, 1-day = 1 day rest, 2plus = 2+ days rest) using
per-game data that is already in the repo.

**Sub-field coverage:**

REAL (populated from existing parquets):
  overall.*      — aggregate n_games / efg_pct / min_pg across all rest categories,
                   sourced from data/player_adv_stats.parquet (per-game eFG%
                   + minutes).
  b2b.*          — n_games / efg_pct / min_pg / efg_delta_vs_normal when player
                   plays the second leg of a back-to-back (rest_days == 0).
  one_day.*      — same as b2b but for exactly 1 rest day between games.
  two_plus.*     — 2+ rest days (well-rested baseline).
  fatigue_proxy.*— relative eFG and minutes drop on B2B vs the 2+ rest baseline;
                   signed fields (efg_b2b_minus_2plus, min_b2b_minus_2plus) so
                   named with ``_minus_`` to pass the signed-field exemption in
                   intel_validator.

DEFER (data gap — not available in current parquets):
  travel.*       — per-category miles_traveled + altitude; rest_travel.parquet is
                   team-level only (no player_id) and game_id → player_id linkage
                   requires the team_abbreviation column absent from player_adv_stats.
                   DEFER until a player-level travel join is pre-aggregated.

RESERVED CV SLOTS (value=None, CV branch fills later):
  speed_decay_b2b — per-frame average player speed on B2B second-leg games vs
                    well-rested baseline (ft/s), from homography-calibrated
                    Kalman velocity tracks across matched game windows.
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

# ---------------------------------------------------------------------------
# Module-level parquet cache (one load per process)
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
# Rest-category computation
# ---------------------------------------------------------------------------

_MAX_SEASON_GAP_DAYS = 100  # gaps larger than this indicate a season break, not rest


def _parse_minutes(v: Any) -> Optional[float]:
    """Parse minutes: already float in player_adv_stats (not MM:SS string)."""
    if v is None:
        return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f) or f < 0:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _efg_clean(v: Any) -> Optional[float]:
    """Clean eFG%: null values outside [0, 1.0] (>1.0 is a data artifact)."""
    f = _rd(v)
    if f is None:
        return None
    if f < 0.0 or f > 1.0:
        return None
    return f


def _rest_category_series(game_dates: pd.Series) -> pd.Series:
    """Assign rest-day categories from a sorted game_date Series.

    Categories: 'b2b' (0 days rest), '1day' (1 day rest), '2plus' (>=2 days rest).
    The first game in a player's record (no prior game) and games following a gap
    of more than _MAX_SEASON_GAP_DAYS (season breaks) are assigned '2plus' because
    the player is genuinely well-rested in those contexts.

    Args:
        game_dates: sorted pd.Series of datetime64 game dates for one player.

    Returns:
        pd.Series of category strings ('b2b', '1day', '2plus') aligned with the input.
    """
    dates = game_dates.reset_index(drop=True)
    prev = dates.shift(1)
    rest_days = (dates - prev).dt.days - 1  # days between games minus 1

    def _categorise(r: float) -> str:
        if pd.isna(r) or r > _MAX_SEASON_GAP_DAYS:
            return "2plus"  # first game or season break => well-rested
        r = int(r)
        if r <= 0:
            return "b2b"
        if r == 1:
            return "1day"
        return "2plus"

    return rest_days.apply(_categorise)


# ---------------------------------------------------------------------------
# Per-category aggregation helper
# ---------------------------------------------------------------------------

def _agg_category(
    df: pd.DataFrame, cat: str
) -> Dict[str, Any]:
    """Aggregate eFG% and minutes for games in one rest category.

    Args:
        df:  DataFrame with columns ['rest_cat', 'efg_clean', 'min_clean'].
        cat: one of 'b2b', '1day', '2plus'.

    Returns:
        dict with keys n_games (int), efg_pct (float|None), min_pg (float|None).
    """
    sub = df[df["rest_cat"] == cat]
    n = len(sub)
    efg_vals = sub["efg_clean"].dropna()
    min_vals = sub["min_clean"].dropna()
    return {
        "n_games": n,
        "efg_pct": _rd(efg_vals.mean()) if len(efg_vals) >= 2 else None,
        "min_pg": _rd(min_vals.mean()) if len(min_vals) >= 2 else None,
    }


# ---------------------------------------------------------------------------
# Main section build
# ---------------------------------------------------------------------------

def _build_rest_splits(
    pid: int, as_of: _dt.datetime
) -> Optional[Dict[str, Any]]:
    """Compute rest-category splits for player ``pid`` with data <= as_of.

    Returns a dict with keys (overall, b2b, one_day, two_plus, fatigue_proxy)
    and a 'n' key for provenance, or None if the player has no qualifying rows.

    Leak guarantee: only games with game_date <= as_of are included.
    Rest categories are derived from consecutive game-date differences within the
    player's own schedule (never from future game knowledge).
    """
    adv_df = _load("adv", DATA / "player_adv_stats.parquet")
    if adv_df is None or adv_df.empty:
        return None

    rows = adv_df[adv_df["player_id"] == pid].copy()
    if rows.empty:
        return None

    # --- Leak filter ---
    rows["game_date"] = pd.to_datetime(rows["game_date"])
    rows = rows[rows["game_date"] <= pd.Timestamp(as_of)]
    if rows.empty:
        return None

    # Sort chronologically (required for rest-day differencing)
    rows = rows.sort_values("game_date").reset_index(drop=True)
    n_total = len(rows)

    # --- Compute rest category per row (leak-safe: uses only prior dates) ---
    rows["rest_cat"] = _rest_category_series(rows["game_date"])

    # --- Clean eFG% and minutes ---
    rows["efg_clean"] = rows["effectivefieldgoalpercentage"].apply(_efg_clean)
    rows["min_clean"] = rows["minutes"].apply(_parse_minutes)

    # --- Per-category aggregates ---
    b2b_agg = _agg_category(rows, "b2b")
    one_day_agg = _agg_category(rows, "1day")
    two_plus_agg = _agg_category(rows, "2plus")

    # --- Overall aggregate (all rows) ---
    all_efg = rows["efg_clean"].dropna()
    all_min = rows["min_clean"].dropna()
    overall: Dict[str, Any] = {
        "n_games": n_total,
        "efg_pct": _rd(all_efg.mean()) if len(all_efg) >= 2 else None,
        "min_pg": _rd(all_min.mean()) if len(all_min) >= 2 else None,
    }

    # --- Fatigue proxy: signed delta (B2B minus 2+) ---
    # Named with '_minus_' suffix to be exempted from the [0,1] range check
    # in intel_validator (signed-field exemption).
    efg_b2b = b2b_agg.get("efg_pct")
    efg_2plus = two_plus_agg.get("efg_pct")
    min_b2b = b2b_agg.get("min_pg")
    min_2plus = two_plus_agg.get("min_pg")

    efg_delta: Optional[float] = None
    if efg_b2b is not None and efg_2plus is not None:
        efg_delta = _rd(efg_b2b - efg_2plus)  # negative = fatigue hurts shooting

    min_delta: Optional[float] = None
    if min_b2b is not None and min_2plus is not None:
        min_delta = _rd(min_b2b - min_2plus)  # negative = fewer minutes on B2B

    fatigue_proxy: Dict[str, Any] = {
        "efg_b2b_minus_2plus": efg_delta,  # signed diff, exempt from [0,1] check
        "min_b2b_minus_2plus": min_delta,   # signed diff, exempt from [0,1] check
        "_note": (
            "Negative values indicate fatigue degradation on B2B second leg. "
            "Signed fields (contains '_minus_') are exempt from face-validity [0,1] range."
        ),
    }

    # --- Travel splits: DEFER ---
    travel: Dict[str, Any] = {
        "_note": (
            "DEFER: rest_travel.parquet is team-level (no player_id); "
            "player-level miles/altitude requires joining via team_abbreviation "
            "which is absent from player_adv_stats. "
            "A pre-aggregated player-level travel parquet would unblock this."
        )
    }

    return {
        "overall": overall,
        "b2b": b2b_agg,
        "one_day": one_day_agg,
        "two_plus": two_plus_agg,
        "fatigue_proxy": fatigue_proxy,
        "travel": travel,
        "n": n_total,
    }


# ---------------------------------------------------------------------------
# AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerRestB2BSplits(AtlasSection):
    """Rest-day split atlas section for a player (entity='player', section='rest_b2b_splits').

    Computes per-game eFG% and playing-time by rest category (B2B / 1-day / 2+)
    and a fatigue proxy (signed deltas) using data/player_adv_stats.parquet.

    Sources:
      - data/player_adv_stats.parquet — per-game eFG%, minutes (float, NOT MM:SS)

    DEFER:
      - travel sub-fields — need a player-level travel join (team-level only today)

    Reserved CV slots:
      - speed_decay_b2b — player-speed delta between B2B and well-rested games (ft/s)
    """

    name: str = "rest_b2b_splits"
    entity: str = "player"
    source_name: str = "player_adv_stats.parquet (per-game eFG% + minutes)"
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the rest_b2b_splits artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: player_adv_stats rows are filtered to game_date <= as_of
        before any computation.  Rest categories are derived purely from the player's
        own game-date history (no future game knowledge).

        Returns None when the player has no qualifying rows in adv_stats.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        result = _build_rest_splits(pid, as_of)
        if result is None:
            return None

        n: int = result.pop("n")
        confidence = confidence_from_n(n, cap=self.conf_cap)

        sub_fields: Dict[str, Any] = {
            "overall": result["overall"],
            "b2b": result["b2b"],
            "one_day": result["one_day"],
            "two_plus": result["two_plus"],
            "fatigue_proxy": result["fatigue_proxy"],
            "travel": result["travel"],
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
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required keys present, no out-of-range proportions.

        Full leak/coverage/dedup gate is in src.loop.intel_validator.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False
        sf = artifact.sub_fields
        required = {"overall", "b2b", "one_day", "two_plus", "fatigue_proxy", "travel"}
        if not required.issubset(sf.keys()):
            return False

        # eFG% values must be in [0, 1] when present (nulled above if out-of-range)
        for cat_key in ("overall", "b2b", "one_day", "two_plus"):
            cat = sf.get(cat_key, {})
            efg = cat.get("efg_pct")
            if efg is not None and not (0.0 <= efg <= 1.0):
                return False
            min_pg = cat.get("min_pg")
            if min_pg is not None and min_pg < 0:
                return False
            n_g = cat.get("n_games")
            if n_g is not None and n_g < 0:
                return False

        # CV fields must be present and null (reserved)
        for slot_name, slot in artifact.cv_fields.items():
            if slot.value is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV slot for rest_b2b_splits (value=None — CV branch fills later).

        The ``speed_decay_b2b`` slot captures the mean per-frame player speed on
        B2B second-leg games vs well-rested games, from homography-calibrated
        Kalman velocity tracks.  It is null until the CV branch fills it.
        """
        return {
            "speed_decay_b2b": CVSlot(
                name="speed_decay_b2b",
                dtype="float",
                description=(
                    "Mean per-frame player speed (ft/s) on B2B second-leg games "
                    "minus the mean speed on 2+ rest-day games, from "
                    "homography-calibrated Kalman velocity tracks matched across "
                    "game windows. Negative = player moves slower when fatigued."
                ),
                unit="ft/s",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level build + register helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build rest_b2b_splits for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids.  If None, discovers from adv_stats.
        as_of:      leak boundary datetime (defaults to today 00:00 UTC).
        store:      optional PointInTimeStore; when provided, artifacts are written.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        adv = _load("adv_disc", DATA / "player_adv_stats.parquet")
        if adv is not None and "player_id" in adv.columns:
            player_ids = sorted(adv["player_id"].dropna().astype(int).unique().tolist())
        else:
            player_ids = []

    section = PlayerRestB2BSplits()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
