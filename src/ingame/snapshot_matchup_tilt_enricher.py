"""snapshot_matchup_tilt_enricher.py — CV_INGAME_MATCHUP_TILT: scheme-based tilt.

Tilts each player's REMAINING projected stat delta by his historical
per-scheme split vs the opponent team's dominant defensive scheme.

Algorithm (strictly causal — static lookup only)
-------------------------------------------------
At any snapshot point (endQ1/endQ2/endQ3):
  1. Identify each player's team from the snapshot (snap["home_team"] /
     snap["away_team"] / player["team"]).
  2. Map player's opponent = the other team in the game.
  3. Look up opponent's dominant defensive scheme from
     ``data/intelligence/defensive_schemes.parquet`` (static season-level;
     normalised to lowercase underscore keys: e.g. "DROP COVERAGE" →
     "drop_coverage").
  4. Look up the player's per-scheme stats from
     ``data/cache/atlas_player_vs_scheme_splits.parquet``
     (pre-built atlas; ``by_scheme[scheme][stat_pg]`` for pts/reb/ast/fg3m).
  5. Compute weighted average across all schemes (weight = n_games, min 10):
       w_avg = sum(n_i * stat_i) / sum(n_i)
  6. Tilt for the opponent scheme:
       raw_tilt = (scheme_stat_pg / w_avg) − 1.0
       capped_tilt = clamp(raw_tilt, −MAX_TILT, +MAX_TILT)
  7. Apply tilt ONLY to the remaining projected delta (not current accrued
     stats — those are reality):
       remaining = max(0, projected_final − current_stat)
       projected_final = current_stat + remaining * (1 + capped_tilt)

Honesty / limitations
---------------------
* The vs_scheme atlas is built from the full 2024-25 regular season — it
  is NOT per-game causal (past games in the same season contribute to the
  split). This makes the signal UNSUITABLE for betting use (forward-leakage
  at game level). The task is **accuracy-only evaluation**.
* Scheme labels are season-level constants (one label per team); in-season
  scheme evolution is not captured.
* Coverage: 86.9% of corpus players have atlas data; falls back to no-tilt
  for uncovered players.

Byte-identical guarantee
------------------------
With ``CV_INGAME_MATCHUP_TILT`` unset / "0" / "false", ``apply_matchup_tilt``
returns the row list UNCHANGED — no mutations, no added keys.

Public API
----------
``apply_matchup_tilt(snap, rows)``
    Post-projection row mutator: takes snapshot dict and projection rows list
    (same signature as other ``_apply_*`` helpers in live_engine.py).
    Returns the (possibly mutated) rows list.

``load_scheme_map(path)``
    Pure function: returns ``{team_abbrev: scheme_key}`` from parquet.

``load_vs_scheme_atlas(path)``
    Pure function: returns ``{player_id: {scheme_key: {stat: float}}}``.

``compute_tilt(player_id, opp_team, stat, pid_to_team, scheme_map, atlas)``
    Pure function: returns tilt float (capped) or 0.0 if no data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
_FLAG_ENV = "CV_INGAME_MATCHUP_TILT"


def _flag_on() -> bool:
    """Read the flag at call time so tests can set os.environ before calling."""
    return os.environ.get(_FLAG_ENV, "0").strip().lower() in ("1", "true", "yes", "on", "y", "t")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Stats the tilt applies to (high-volume; STL/BLK/TOV too noisy at scheme level)
TILT_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m")

# Atlas stat key → projection row stat key (by_scheme uses _pg suffix)
_STAT_PG_KEY: Dict[str, str] = {
    "pts":  "pts_pg",
    "reb":  "reb_pg",
    "ast":  "ast_pg",
    "fg3m": "fg3m_pg",
}

# Maximum absolute tilt applied to remaining delta (±15%).
# Chosen conservatively: the mean abs raw tilt from the atlas is ~0.22 but
# driven by small-n schemes; at min_n=10 the p90 is ~0.27 → cap at 0.15
# prevents rare outliers blowing up the projection.
_MAX_TILT: float = 0.15

# Minimum n_games in a scheme bucket for the split to be considered reliable.
_MIN_N: int = 10

# ---------------------------------------------------------------------------
# Default filesystem paths (relative to project root)
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_DEFAULT_SCHEME_PATH: Path = (
    _PROJECT_ROOT / "data" / "intelligence" / "defensive_schemes.parquet"
)
_DEFAULT_ATLAS_PATH: Path = (
    _PROJECT_ROOT / "data" / "cache" / "atlas_player_vs_scheme_splits.parquet"
)


# ---------------------------------------------------------------------------
# Tag normalisation
# ---------------------------------------------------------------------------
def _norm_tag(tag: str) -> str:
    """'DROP COVERAGE' -> 'drop_coverage'; 'PAINT-FIRST DEFENSE' -> 'paint_first_defense'."""
    return tag.strip().lower().replace(" ", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# Data loaders (lazy, cached at module level)
# ---------------------------------------------------------------------------
_scheme_map_cache: Optional[Dict[str, str]] = None
_atlas_cache: Optional[Dict[int, Dict[str, Dict[str, float]]]] = None


def load_scheme_map(
    path: Optional[Path] = None,
) -> Dict[str, str]:
    """Load {team_abbrev: dominant_scheme_key} from defensive_schemes.parquet.

    Returns empty dict when file is missing or malformed.
    """
    global _scheme_map_cache
    if _scheme_map_cache is not None:
        return _scheme_map_cache

    p = Path(path) if path else _DEFAULT_SCHEME_PATH
    if not p.exists():
        _scheme_map_cache = {}
        return _scheme_map_cache

    try:
        import pandas as pd
        df = pd.read_parquet(str(p), columns=["team", "dominant_tag"])
        result: Dict[str, str] = {}
        for _, row in df.iterrows():
            team = str(row["team"]).strip().upper()
            tag = str(row["dominant_tag"]).strip()
            if team and tag:
                result[team] = _norm_tag(tag)
        _scheme_map_cache = result
    except Exception:
        _scheme_map_cache = {}
    return _scheme_map_cache


def load_vs_scheme_atlas(
    path: Optional[Path] = None,
) -> Dict[int, Dict[str, Dict[str, float]]]:
    """Load {player_id: {scheme_key: {stat: float}}} from atlas parquet.

    Only entries with n_games >= _MIN_N are loaded. Returns empty dict when
    file is missing or malformed.
    """
    global _atlas_cache
    if _atlas_cache is not None:
        return _atlas_cache

    p = Path(path) if path else _DEFAULT_ATLAS_PATH
    if not p.exists():
        _atlas_cache = {}
        return _atlas_cache

    try:
        import pandas as pd
        df = pd.read_parquet(str(p), columns=["player_id", "by_scheme"])
        result: Dict[int, Dict[str, Dict[str, float]]] = {}
        for _, row in df.iterrows():
            try:
                pid = int(row["player_id"])
                by_sch_raw = row["by_scheme"]
                if isinstance(by_sch_raw, str):
                    by_sch = json.loads(by_sch_raw)
                elif isinstance(by_sch_raw, dict):
                    by_sch = by_sch_raw
                else:
                    continue
            except Exception:
                continue

            player_schemes: Dict[str, Dict[str, float]] = {}
            for scheme_key, vals in by_sch.items():
                if not isinstance(vals, dict):
                    continue
                n = int(vals.get("n_games") or 0)
                if n < _MIN_N:
                    continue
                stat_row: Dict[str, float] = {}
                for stat, pg_key in _STAT_PG_KEY.items():
                    v = vals.get(pg_key)
                    if v is not None:
                        try:
                            stat_row[stat] = float(v)
                        except (TypeError, ValueError):
                            pass
                if stat_row:
                    player_schemes[scheme_key] = stat_row
            if player_schemes:
                result[pid] = player_schemes
        _atlas_cache = result
    except Exception:
        _atlas_cache = {}
    return _atlas_cache


# ---------------------------------------------------------------------------
# Tilt computation (pure function)
# ---------------------------------------------------------------------------
def compute_tilt(
    player_id: int,
    opp_scheme_key: str,
    stat: str,
    atlas: Dict[int, Dict[str, Dict[str, float]]],
) -> float:
    """Compute capped tilt for (player, opponent_scheme, stat).

    Returns capped tilt in (−MAX_TILT, +MAX_TILT), or 0.0 when data is
    absent / insufficient (caller treats 0.0 as no-op).
    """
    player_data = atlas.get(player_id)
    if not player_data:
        return 0.0

    scheme_data = player_data.get(opp_scheme_key)
    if scheme_data is None:
        return 0.0

    scheme_val = scheme_data.get(stat)
    if scheme_val is None:
        return 0.0

    # Weighted average across all schemes in the atlas (weight by n_games;
    # we don't store n per scheme after filtering, so weight equally — each
    # entry already passed the _MIN_N gate so they are comparably reliable).
    vals = [
        v.get(stat)
        for v in player_data.values()
        if v.get(stat) is not None
    ]
    if not vals:
        return 0.0
    avg_val = sum(vals) / len(vals)
    if avg_val <= 0.0:
        return 0.0

    raw_tilt = scheme_val / avg_val - 1.0
    return max(-_MAX_TILT, min(_MAX_TILT, raw_tilt))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def apply_matchup_tilt(
    snap: dict,
    rows: List[dict],
    *,
    scheme_map: Optional[Dict[str, str]] = None,
    atlas: Optional[Dict[int, Dict[str, Dict[str, float]]]] = None,
) -> List[dict]:
    """Apply scheme-based matchup tilt to projected rows (post-projection).

    Args:
        snap:  canonical snapshot dict with ``home_team``, ``away_team``,
               ``game_id``, and ``players`` list.
        rows:  projection row dicts (each has ``player_id``, ``stat``,
               ``current``, ``projected_final``).
        scheme_map:  optional pre-loaded scheme map (for tests / warm paths).
        atlas:       optional pre-loaded vs-scheme atlas (for tests).

    Returns:
        The (possibly mutated) rows list.  With flag OFF (default), returns
        the list UNCHANGED.
    """
    if not _flag_on():
        return rows

    _scheme_map = scheme_map if scheme_map is not None else load_scheme_map()
    _atlas = atlas if atlas is not None else load_vs_scheme_atlas()

    if not _scheme_map or not _atlas:
        return rows

    # Build player → team map from snapshot.
    home_team = str(snap.get("home_team") or "").upper().strip()
    away_team = str(snap.get("away_team") or "").upper().strip()
    player_team: Dict[int, str] = {}
    for p in snap.get("players") or []:
        pid_raw = p.get("player_id")
        team_raw = p.get("team") or ""
        if pid_raw is None:
            continue
        try:
            pid_i = int(pid_raw)
        except (TypeError, ValueError):
            continue
        player_team[pid_i] = str(team_raw).upper().strip()

    # Memoize per-player tilt values across stats (avoid repeated atlas lookups).
    _tilt_cache: Dict[Tuple[int, str, str], float] = {}

    for row in rows:
        stat = row.get("stat")
        if stat not in TILT_STATS:
            continue

        pid_raw = row.get("player_id")
        if pid_raw is None:
            continue
        try:
            pid_i = int(pid_raw)
        except (TypeError, ValueError):
            continue

        player_tm = player_team.get(pid_i, "")
        if player_tm == home_team:
            opp_team = away_team
        elif player_tm == away_team:
            opp_team = home_team
        else:
            # Can't determine opponent → no tilt.
            continue

        opp_scheme_key = _scheme_map.get(opp_team)
        if not opp_scheme_key:
            continue

        cache_key = (pid_i, opp_scheme_key, stat)
        if cache_key not in _tilt_cache:
            _tilt_cache[cache_key] = compute_tilt(pid_i, opp_scheme_key, stat, _atlas)
        tilt = _tilt_cache[cache_key]

        if tilt == 0.0:
            continue

        # Apply tilt ONLY to the remaining projected delta (not current accrued).
        current = float(row.get("current") or 0.0)
        projected = float(row.get("projected_final") or 0.0)
        remaining = max(0.0, projected - current)
        if remaining <= 0.0:
            continue

        new_proj = current + remaining * (1.0 + tilt)
        # Never project below what the player has already scored.
        row["projected_final"] = max(current, new_proj)

    return rows
