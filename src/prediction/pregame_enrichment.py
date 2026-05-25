"""pregame_enrichment.py -- Cycle 107b (loop 5).

Enriches live snapshots with pregame rolling features (l5/l20 per stat,
l20_min, position) so period-specific LightGBM heads receive real values
instead of NaN at inference time.

WHY: cycle 106a wired period_specific_heads into live_engine.  Those heads
were trained with 12 features including l5_stat, l20_stat, l20_min, and
three position dummies.  At live inference time the snapshot only carries
current in-game stats (pts, reb, ast, …); the four pregame features are
absent → LightGBM falls to unconditional default splits, collapsing the
model toward fallback_mean.  This module closes the gap.

Architecture
------------
- Lazy-loads gamelog JSON files from data/nba/gamelog_<pid>_<season>.json
  for the two most recent seasons (current + prior).
- Filters to games strictly before `date_iso` (point-in-time safe).
- Computes l5 / l20 rolling means over the 5 / 20 most recent played games.
- Loads position from data/player_positions.parquet (cached after first read).
- All results are cached per (player_id, date_iso) so repeated calls from
  the live polling loop pay the cost once per game, not once per snapshot.

Back-compat: if a gamelog file is absent or a player has <5 prior games the
key is omitted from the dict.  _apply_period_heads already tolerates
absent keys (passes None → NaN branch in build_feature_row).

API
---
    enrich_snapshot_with_pregame_features(snap, date_iso=None) -> snap
        Mutates (in-place) the player dicts inside snap.  Returns snap for
        chaining.  Thread-safe at module level (pure dict + parquet reads).

    clear_cache() -> None
        Flush all internal caches (useful in tests or after dataset refresh).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import date as _date, datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_POSITIONS_PATH = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")

# Gamelog column names (UPPER_SNAKE from nba_api)
_COL: Dict[str, str] = {
    "pts": "PTS", "reb": "REB", "ast": "AST",
    "fg3m": "FG3M", "stl": "STL", "blk": "BLK",
    "tov": "TOV", "min": "MIN",
}
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Module-level caches.
_GAMELOG_CACHE: Dict[int, List[dict]] = {}     # player_id -> sorted played games
_POSITION_MAP: Dict[int, str] = {}             # player_id -> raw position string
_ENRICHED_CACHE: Dict[Tuple[int, str], dict] = {}  # (pid, date_iso) -> feature dict
_POSITIONS_LOADED = False


# ── position loader ───────────────────────────────────────────────────────────

def _load_positions() -> None:
    global _POSITIONS_LOADED
    if _POSITIONS_LOADED:
        return
    if not os.path.exists(_POSITIONS_PATH):
        _POSITIONS_LOADED = True
        return
    try:
        import pandas as pd
        df = pd.read_parquet(_POSITIONS_PATH)
        # Column may be 'position' or 'POSITION'.
        pos_col = next((c for c in df.columns if c.lower() == "position"), None)
        id_col = next((c for c in df.columns if c.lower() in ("player_id", "id")), None)
        if pos_col and id_col:
            for _, row in df.iterrows():
                try:
                    pid = int(row[id_col])
                    _POSITION_MAP[pid] = str(row[pos_col] or "")
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    _POSITIONS_LOADED = True


def _position_for(player_id: int) -> str:
    _load_positions()
    return _POSITION_MAP.get(player_id, "")


# ── gamelog loader ────────────────────────────────────────────────────────────

def _parse_game_date(raw: str) -> Optional[str]:
    """Parse gamelog GAME_DATE to 'YYYY-MM-DD' string. Returns None on failure."""
    if not raw:
        return None
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _load_gamelog(player_id: int) -> List[dict]:
    """Return sorted (ascending by date) list of played game dicts for player."""
    if player_id in _GAMELOG_CACHE:
        return _GAMELOG_CACHE[player_id]
    pattern = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_*.json")
    games: List[Tuple[str, dict]] = []
    for path in glob.glob(pattern):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for g in data:
            raw_date = _parse_game_date(g.get("GAME_DATE") or g.get("game_date") or "")
            if raw_date is None:
                continue
            try:
                raw_min = float(g.get("MIN") or g.get("min") or 0)
            except (TypeError, ValueError):
                raw_min = 0.0
            if raw_min < 1.0:
                continue  # DNP or not yet played
            games.append((raw_date, g))
    games.sort(key=lambda t: t[0])
    result = [g for _, g in games]
    _GAMELOG_CACHE[player_id] = result
    return result


def _prior_games(player_id: int, date_iso: str) -> List[dict]:
    """Games for player_id strictly before date_iso."""
    return [g for g in _load_gamelog(player_id) if _parse_game_date(
        g.get("GAME_DATE") or g.get("game_date") or ""
    ) < date_iso]


# ── feature computation ───────────────────────────────────────────────────────

def _safe_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else x


def _rolling_mean(games: List[dict], col: str, n: int) -> Optional[float]:
    """Mean of col over the last n games. Returns None if no games available."""
    vals = [_safe_float(g.get(col)) for g in games[-n:]]
    return sum(vals) / len(vals) if vals else None


def _features_for(player_id: int, date_iso: str) -> dict:
    """Compute pregame features for one (player, date) pair."""
    cache_key = (player_id, date_iso)
    if cache_key in _ENRICHED_CACHE:
        return _ENRICHED_CACHE[cache_key]
    prior = _prior_games(player_id, date_iso)
    feats: dict = {}
    for stat in _STATS:
        col = _COL[stat]
        l5 = _rolling_mean(prior, col, 5)
        l20 = _rolling_mean(prior, col, 20)
        if l5 is not None:
            feats[f"l5_{stat}"] = l5
        if l20 is not None:
            feats[f"l20_{stat}"] = l20
    l20_min = _rolling_mean(prior, _COL["min"], 20)
    if l20_min is not None:
        feats["l20_min"] = l20_min
    pos = _position_for(player_id)
    if pos:
        feats["position"] = pos
    _ENRICHED_CACHE[cache_key] = feats
    return feats


# ── public API ────────────────────────────────────────────────────────────────

def enrich_snapshot_with_pregame_features(
    snap: dict,
    date_iso: Optional[str] = None,
) -> dict:
    """Inject l5/l20/position pregame features into each player dict in snap.

    Mutates and returns snap.  Keys injected (when computable):
        l5_pts, l5_reb, l5_ast, l5_fg3m, l5_stl, l5_blk, l5_tov
        l20_pts, l20_reb, l20_ast, l20_fg3m, l20_stl, l20_blk, l20_tov
        l20_min
        position

    Already-present keys are NOT overwritten (caller-supplied values win).
    """
    if date_iso is None:
        date_iso = _date.today().isoformat()
    for p in snap.get("players") or []:
        pid_raw = p.get("player_id")
        if pid_raw is None:
            continue
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            continue
        feats = _features_for(pid, date_iso)
        for k, v in feats.items():
            if k not in p:
                p[k] = v
    return snap


def clear_cache() -> None:
    """Flush all module-level caches (useful in tests)."""
    global _POSITIONS_LOADED
    _GAMELOG_CACHE.clear()
    _ENRICHED_CACHE.clear()
    _POSITION_MAP.clear()
    _POSITIONS_LOADED = False


__all__ = [
    "enrich_snapshot_with_pregame_features",
    "clear_cache",
]
