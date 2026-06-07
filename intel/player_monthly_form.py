"""ARM-B atlas section: ``monthly_form`` — month-by-month + last-15-game trend slopes.

Implements :class:`AtlasSection` for the ``"monthly_form"`` section of a player's
persistent profile.  Builds per-month averages and last-15-game OLS trend slopes
for core counting stats.

**Sub-field coverage:**

REAL (populated from parquets):
  monthly.*   — per-month averages (pts/reb/ast/fg3m/stl/blk/tov/min) keyed
                "YYYY-MM"; from combined leaguegamelog (cv_fix) + player_quarter_stats
                (aggregated per-game with game_date joined from player_adv_stats).
  last15.*    — last-15-game OLS slope + mean for each core stat; named with
                _slope suffix (signed, OLS units = pts-per-game per game-index).
  summary.*   — overall season averages and game count from the same source.

DEFER:
  monthly.fg_pct  — raw FGM/FGA not in player_quarter_stats; leaguegamelog has it
                    but only for the current season; DEFER cross-season fg%.
  last15.min      — minutes in player_quarter_stats is total across all periods but
                    MIN in leaguegamelog is integer (no sub-minute precision);
                    reported as-is, no additional processing.

RESERVED CV SLOTS: none — monthly form is pure box-score, no CV enrichment needed.

Sources (in priority order):
  1. data/cache/cv_fix/leaguegamelog_regular_season.parquet
  2. data/cache/cv_fix/leaguegamelog_playoffs.parquet
  3. data/player_quarter_stats.parquet (aggregated to game level)
  4. data/player_adv_stats.parquet  (game_id -> game_date mapping for source 3)
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

# Core box-score statistics we track month-to-month
_CORE_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_MIN_GAMES_FOR_SLOPE = 5  # need at least 5 games for a meaningful slope

# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process)
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


# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------

def _load_gamelog_combined() -> Optional[pd.DataFrame]:
    """Load and standardise leaguegamelog (regular + playoffs) as one DataFrame.

    Returns columns: player_id, game_id, game_date (datetime), pts, reb, ast,
    fg3m, stl, blk, tov.  MIN is kept as float minutes.
    """
    reg = _load("glog_reg", CACHE / "cv_fix" / "leaguegamelog_regular_season.parquet")
    ply = _load("glog_ply", CACHE / "cv_fix" / "leaguegamelog_playoffs.parquet")

    parts = [df for df in [reg, ply] if df is not None and not df.empty]
    if not parts:
        return None

    raw = pd.concat(parts, ignore_index=True)
    rename_map = {
        "PLAYER_ID": "player_id",
        "GAME_ID": "game_id",
        "GAME_DATE": "game_date",
        "PTS": "pts",
        "REB": "reb",
        "AST": "ast",
        "FG3M": "fg3m",
        "STL": "stl",
        "BLK": "blk",
        "TOV": "tov",
        "MIN": "min_played",
    }
    keep = [c for c in rename_map if c in raw.columns]
    df = raw[keep].rename(columns=rename_map).copy()
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    return df


def _load_pqs_gamelog() -> Optional[pd.DataFrame]:
    """Aggregate player_quarter_stats to game level and join game_date from adv_stats.

    Returns columns: player_id, game_id, game_date (datetime), pts, reb, ast,
    fg3m, stl, blk, tov.
    """
    pqs = _load("pqs", DATA / "player_quarter_stats.parquet")
    adv = _load("adv", DATA / "player_adv_stats.parquet")
    if pqs is None or pqs.empty:
        return None

    agg = (
        pqs.groupby(["player_id", "game_id"], as_index=False)
        .agg(
            pts=("pts", "sum"),
            reb=("reb", "sum"),
            ast=("ast", "sum"),
            fg3m=("fg3m", "sum"),
            stl=("stl", "sum"),
            blk=("blk", "sum"),
            tov=("tov", "sum"),
        )
    )
    # Join game_date from adv_stats
    if adv is not None and "game_date" in adv.columns and "game_id" in adv.columns:
        gdate_map = (
            adv[["game_id", "game_date"]]
            .drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
        )
        agg["game_date"] = agg["game_id"].map(gdate_map)
    else:
        agg["game_date"] = np.nan

    agg["game_date"] = pd.to_datetime(agg["game_date"], errors="coerce")
    return agg[agg["game_date"].notna()].copy()


def _build_player_gamelog(pid: int, as_of: _dt.datetime) -> pd.DataFrame:
    """Combine both sources into a deduplicated, leak-safe game log for one player.

    Priority: leaguegamelog rows win on duplicate (game_id, player_id) because they
    are directly sourced from the NBA API with integer-typed box stats.

    Leak filter: only rows with game_date <= as_of are included.

    Args:
        pid:    NBA player_id (int).
        as_of:  leak boundary datetime.

    Returns:
        DataFrame with columns [game_id, game_date, pts, reb, ast, fg3m, stl, blk, tov],
        sorted by game_date ascending.  Empty DataFrame if no data found.
    """
    as_of_ts = pd.Timestamp(as_of)

    parts: List[pd.DataFrame] = []

    # Source 1: leaguegamelog
    glog = _load_gamelog_combined()
    if glog is not None:
        p_glog = glog[glog["player_id"] == pid].copy()
        p_glog = p_glog[p_glog["game_date"] <= as_of_ts]
        parts.append(p_glog[["game_id", "game_date"] + _CORE_STATS])

    # Source 2: player_quarter_stats aggregated
    pqs_agg = _load_pqs_gamelog()
    if pqs_agg is not None:
        p_pqs = pqs_agg[pqs_agg["player_id"] == pid].copy()
        p_pqs = p_pqs[p_pqs["game_date"] <= as_of_ts]
        parts.append(p_pqs[["game_id", "game_date"] + _CORE_STATS])

    if not parts:
        return pd.DataFrame(columns=["game_id", "game_date"] + _CORE_STATS)

    # Deduplicate: leaguegamelog rows win (first in concat)
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.drop_duplicates(subset=["game_id"], keep="first")
    combined = combined.sort_values("game_date").reset_index(drop=True)

    # Coerce stats to float
    for col in _CORE_STATS:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    return combined


# ---------------------------------------------------------------------------
# Monthly aggregation helpers
# ---------------------------------------------------------------------------

def _compute_monthly(games: pd.DataFrame) -> Dict[str, Any]:
    """Compute per-month averages of core stats.

    Args:
        games: deduplicated, sorted game-level DataFrame.

    Returns:
        Dict mapping ``"YYYY-MM"`` strings to per-stat averages.
        Only months with at least 1 game are included.
    """
    if games.empty:
        return {}

    games = games.copy()
    games["ym"] = games["game_date"].dt.to_period("M")
    monthly: Dict[str, Any] = {}

    for period, grp in games.groupby("ym"):
        n = len(grp)
        ym_str = str(period)  # e.g. "2025-11"
        avgs: Dict[str, Any] = {"n_games": n}
        for stat in _CORE_STATS:
            if stat in grp.columns:
                avgs[f"{stat}_pg"] = _rd(grp[stat].mean())
        monthly[ym_str] = avgs

    return monthly


# ---------------------------------------------------------------------------
# Last-15-game trend (OLS slope)
# ---------------------------------------------------------------------------

def _compute_last15(games: pd.DataFrame) -> Dict[str, Any]:
    """Compute OLS slope + mean for core stats over the last 15 games.

    The slope is named with ``_slope`` suffix (signed: positive = improving trend).
    Units: [stat units] per game index (e.g. pts per 1-game step in the last 15).

    Uses numpy.polyfit for speed; falls back to None if fewer than
    ``_MIN_GAMES_FOR_SLOPE`` games are available.

    Args:
        games: deduplicated, sorted game-level DataFrame.

    Returns:
        Dict with keys ``{stat}_slope``, ``{stat}_mean``, and ``n_games``.
    """
    last15 = games.tail(15).copy()
    n = len(last15)
    out: Dict[str, Any] = {"n_games": n}

    if n < _MIN_GAMES_FOR_SLOPE:
        for stat in _CORE_STATS:
            out[f"{stat}_slope"] = None
            out[f"{stat}_mean"] = None
        return out

    x = np.arange(n, dtype=float)
    for stat in _CORE_STATS:
        if stat not in last15.columns:
            out[f"{stat}_slope"] = None
            out[f"{stat}_mean"] = None
            continue
        y = last15[stat].values.astype(float)
        valid_mask = np.isfinite(y)
        if valid_mask.sum() < _MIN_GAMES_FOR_SLOPE:
            out[f"{stat}_slope"] = None
            out[f"{stat}_mean"] = None
            continue
        try:
            coeffs = np.polyfit(x[valid_mask], y[valid_mask], 1)
            out[f"{stat}_slope"] = _rd(float(coeffs[0]))
        except Exception:
            out[f"{stat}_slope"] = None
        out[f"{stat}_mean"] = _rd(float(np.nanmean(y)))

    return out


# ---------------------------------------------------------------------------
# Summary averages
# ---------------------------------------------------------------------------

def _compute_summary(games: pd.DataFrame) -> Dict[str, Any]:
    """Overall averages across all games in the leak-safe window.

    Args:
        games: deduplicated, sorted game-level DataFrame.

    Returns:
        Dict with per-stat per-game averages and total game count.
    """
    n = len(games)
    out: Dict[str, Any] = {"n_games": n}
    for stat in _CORE_STATS:
        if stat in games.columns:
            out[f"{stat}_pg"] = _rd(games[stat].mean())
    return out


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------

class PlayerMonthlyForm(AtlasSection):
    """Month-by-month and last-15-game trend form for a player (entity='player').

    Section key: ``"monthly_form"``.

    Builds leak-safe monthly stat averages and last-15-game OLS trend slopes from
    per-game box score data.  Two parquet sources are combined and deduplicated:
      - data/cache/cv_fix/leaguegamelog_{regular_season,playoffs}.parquet
      - data/player_quarter_stats.parquet (aggregated per-game, date from adv_stats)

    Slope fields are named with ``_slope`` suffix so the validator correctly exempts
    them from the [0,1] proportion rule (signed fields, units: stat per game index).

    No CV slots reserved — monthly form is pure box-score signal with no CV dimension.
    """

    name: str = "monthly_form"
    entity: str = "player"
    source_name: str = (
        "leaguegamelog_regular_season.parquet + leaguegamelog_playoffs.parquet "
        "+ player_quarter_stats.parquet (adv_stats date join)"
    )
    conf_cap: Optional[str] = None

    # ------------------------------------------------------------------
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the monthly_form artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: all per-game rows are filtered to game_date <= as_of.
        Monthly and last-15 windows are computed entirely from the filtered set.

        Returns None if fewer than ``_MIN_GAMES_FOR_SLOPE`` games are found
        (insufficient for any meaningful trend).

        Args:
            entity_id: NBA player_id (int or str-convertible).
            as_of:     leak boundary datetime.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        games = _build_player_gamelog(pid, as_of)
        n_total = len(games)

        if n_total < _MIN_GAMES_FOR_SLOPE:
            return None

        monthly = _compute_monthly(games)
        last15 = _compute_last15(games)
        summary = _compute_summary(games)

        sub_fields: Dict[str, Any] = {
            "monthly": monthly,
            "last15": last15,
            "summary": summary,
        }

        confidence = confidence_from_n(n_total, cap=self.conf_cap)
        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n_total,
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
        """Face-validity: required sub-dicts present and per-game rates non-negative.

        Slope fields are exempt from the non-negative rule (they are signed).
        Full leak/coverage/dedup gate is in ``src.loop.intel_validator``.
        """
        if artifact.section != self.name:
            return False
        if artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        if not {"monthly", "last15", "summary"}.issubset(sf.keys()):
            return False

        # Per-game averages in summary must be non-negative
        summary = sf.get("summary", {})
        for stat in _CORE_STATS:
            v = summary.get(f"{stat}_pg")
            if v is not None and v < 0:
                return False

        # All CV slot values must be None (reserved, not yet filled)
        for slot in artifact.cv_fields.values():
            if slot.value is not None:
                return False

        return True

    # ------------------------------------------------------------------
    def cv_fields(self) -> Dict[str, CVSlot]:
        """No CV slots — monthly form is pure box-score, no CV enrichment needed.

        Returns an empty dict; the validator accepts this as a valid empty schema.
        """
        return {}


# ---------------------------------------------------------------------------
# Module-level build + registration helper
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build monthly_form for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids.  If None, discovers from leaguegamelog.
        as_of:      leak boundary (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, write_atlas is called per artifact.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    if player_ids is None:
        # Discover from leaguegamelog sources
        glog = _load_gamelog_combined()
        pqs_agg = _load_pqs_gamelog()
        ids_set: set = set()
        if glog is not None and "player_id" in glog.columns:
            ids_set.update(glog["player_id"].dropna().astype(int).unique().tolist())
        if pqs_agg is not None and "player_id" in pqs_agg.columns:
            ids_set.update(pqs_agg["player_id"].dropna().astype(int).unique().tolist())
        player_ids = sorted(ids_set)

    section = PlayerMonthlyForm()
    artifacts: List[AtlasArtifact] = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
