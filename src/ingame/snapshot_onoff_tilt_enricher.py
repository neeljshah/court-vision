"""snapshot_onoff_tilt_enricher.py — CV_INGAME_ONOFF_TILT: lineup net-rtg tilt.

Adjusts each on-court player's ``projected_final`` by the net_rtg delta of
the current 5-man lineup relative to the team's season-weighted average.

Algorithm (strictly causal)
---------------------------
At snapshot point endQN:
  1. Read ``data/cache/quarter_box/{game_id}_q{N+1}.json`` and extract the
     starters of quarter N+1 (``start_position != ""``). These starters are
     exactly the 5 players on the floor at the end of quarter N — verified
     against the 40-game PBP-overlap subset; the NBA assigns start_position
     to those who opened the quarter, which is the closing lineup of the prior
     quarter.
  2. Match the 5-man set by player-ID frozenset against the season lineup
     index from ``data/nba/lineups/lineup_splits_{TEAM}_{season}.json``.
  3. ``lineup_delta = lineup_net_rtg − team_minutes_weighted_avg_net_rtg``
     (team average computed once at load time from the same file).
  4. For each projected row where ``player_id`` is in the oncourt set:
       ``projected_final *= 1 + clamp(TILT_SCALE × lineup_delta / 100,
                                      −MAX_TILT, +MAX_TILT)``
     Only PTS, REB, AST are tilted (STL/BLK/TOV/FG3M too noisy at lineup
     granularity).  Bench players are untouched.

Coverage
--------
* 2024-25 season (889 / 956 corpus games): lineup JSON for all 30 teams present
  → near-100% match rate on tested games.
* 2025-26 season (67 / 956 corpus games): only 2 teams have files → graceful
  no-op for unmatched games.
* 5-man unit not in index (rare sub-minute rotation): graceful no-op.
* Missing quarter-box file: graceful no-op.

Byte-identical guarantee
------------------------
With ``CV_INGAME_ONOFF_TILT`` unset / "0" / "false", ``apply_onoff_tilt``
returns the row list UNCHANGED — no mutations, no added keys.

Public API
----------
``apply_onoff_tilt(snap, rows)``
    Post-projection row mutator: takes the snapshot dict and the projection
    rows list (same signature as other ``_apply_*`` helpers in live_engine.py).
    Returns the (possibly mutated) rows list.

``reconstruct_oncourt_pids(game_id, point, quarter_box_dir)``
    Pure function: returns a frozenset of player_id ints on the floor at
    end-of-``point``, read from the next quarter's box starters.

``compute_tilt_map(game_id, point, home_team, away_team, lineup_dir,
                   quarter_box_dir)``
    Pure function: returns ``{player_id: float multiplier}`` for all oncourt
    players.  Multiplier == 1.0 means no tilt.  Useful for offline testing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------
_FLAG_ENV = "CV_INGAME_ONOFF_TILT"


def _flag_on() -> bool:
    """Read the flag at call time so tests can set os.environ before calling."""
    return os.environ.get(_FLAG_ENV, "0").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TILT_SCALE: float = 0.02          # per net_rtg point per 100 possessions
TILT_STATS: Tuple[str, ...] = ("pts", "reb", "ast")
_MAX_TILT: float = 0.12           # cap at ±12% (guards high-variance small-sample units)

_POINT_TO_NEXT_Q: Dict[str, int] = {
    "endQ1": 2,
    "endQ2": 3,
    "endQ3": 4,
}

# ---------------------------------------------------------------------------
# Default filesystem paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_DEFAULT_QB_DIR: Path = _PROJECT_ROOT / "data" / "cache" / "quarter_box"
_DEFAULT_LU_DIR: Path = _PROJECT_ROOT / "data" / "nba" / "lineups"


# ---------------------------------------------------------------------------
# Season detection from game_id
# ---------------------------------------------------------------------------

def _season_of(game_id: str) -> str:
    """Infer season string (e.g. '2024-25') from NBA game_id prefix.

    Game IDs: 002{YY}{GGG…} where YY is the fall year of the season.
    e.g. '0022400001' → '2024-25', '0022500001' → '2025-26'.
    """
    gid = str(game_id).strip()
    try:
        yr = int(gid[3:5])   # 2-digit fall year
        return f"20{yr:02d}-{(yr + 1):02d}"
    except (ValueError, IndexError):
        return "2024-25"


# ---------------------------------------------------------------------------
# Lineup index (lazy, cached per (team, season))
# ---------------------------------------------------------------------------

# Module-level cache: (team, season) -> (pid_set_to_net_rtg, team_weighted_avg)
_LINEUP_INDEX_CACHE: Dict[Tuple[str, str], Tuple[Dict[FrozenSet[int], float], float]] = {}


def _build_lineup_index(
    team: str,
    season: str,
    lineup_dir: Path,
) -> Tuple[Dict[FrozenSet[int], float], float]:
    """Parse the lineup split JSON and return (index, team_avg_net_rtg).

    index: frozenset-of-5-player-ids -> observed net_rtg.
    team_avg: minutes-weighted mean net_rtg across all 5-man units.

    Returns ({}, 0.0) when the file is missing or malformed.
    """
    path = lineup_dir / f"lineup_splits_{team}_{season}.json"
    if not path.exists():
        return {}, 0.0
    try:
        with open(path, encoding="utf-8") as fh:
            lineups = json.load(fh)
    except Exception:
        return {}, 0.0

    index: Dict[FrozenSet[int], float] = {}
    total_min = 0.0
    weighted_sum = 0.0

    for lu in lineups:
        # group_id: '-pid1-pid2-pid3-pid4-pid5-' (all 5 player IDs, any order)
        gid_str = str(lu.get("group_id") or "").strip("-")
        if not gid_str:
            continue
        try:
            pids: FrozenSet[int] = frozenset(
                int(x) for x in gid_str.split("-") if x.strip()
            )
        except (ValueError, TypeError):
            continue
        if len(pids) != 5:
            continue

        nr = lu.get("net_rtg") if lu.get("net_rtg") is not None else lu.get("net_rating")
        if nr is None:
            continue
        try:
            net_rtg = float(nr)
        except (TypeError, ValueError):
            continue

        mins = float(lu.get("min") or lu.get("minutes") or 0.0)
        index[pids] = net_rtg
        total_min += mins
        weighted_sum += net_rtg * mins

    team_avg = weighted_sum / total_min if total_min > 0.0 else 0.0
    return index, team_avg


def _get_lineup_index(
    team: str,
    season: str,
    lineup_dir: Path,
) -> Tuple[Dict[FrozenSet[int], float], float]:
    """Cached accessor: avoid re-parsing the same file for every snapshot."""
    key = (team, season)
    if key not in _LINEUP_INDEX_CACHE:
        _LINEUP_INDEX_CACHE[key] = _build_lineup_index(team, season, lineup_dir)
    return _LINEUP_INDEX_CACHE[key]


# ---------------------------------------------------------------------------
# Quarter-box starters reader
# ---------------------------------------------------------------------------

def reconstruct_oncourt_pids(
    game_id: str,
    point: str,
    quarter_box_dir: Path,
) -> Dict[str, FrozenSet[int]]:
    """Read the starters of Q(N+1) → the oncourt set at end of Q(N).

    Returns ``{"HOME_TRI": frozenset({pid, ...}), "AWAY_TRI": frozenset({...})}``.
    Returns empty dict when the file is missing or starters are incomplete.
    """
    next_q = _POINT_TO_NEXT_Q.get(point)
    if next_q is None:
        return {}

    path = quarter_box_dir / f"{game_id}_q{next_q}.json"
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}

    starters_by_team: Dict[str, list] = {}
    for player in data.get("players") or []:
        if not player.get("start_position"):
            continue  # bench player (did not start this quarter)
        team = str(player.get("team_abbreviation") or "").strip()
        pid_raw = player.get("player_id")
        if not team or pid_raw is None:
            continue
        try:
            pid = int(pid_raw)
        except (TypeError, ValueError):
            continue
        starters_by_team.setdefault(team, []).append(pid)

    result: Dict[str, FrozenSet[int]] = {}
    for team, pids in starters_by_team.items():
        if len(pids) == 5:
            result[team] = frozenset(pids)
        # Fewer than 5 starters: file is incomplete for this team — skip.

    return result


# ---------------------------------------------------------------------------
# Tilt map computation
# ---------------------------------------------------------------------------

def compute_tilt_map(
    game_id: str,
    point: str,
    home_team: str,
    away_team: str,
    lineup_dir: Optional[Path] = None,
    quarter_box_dir: Optional[Path] = None,
) -> Dict[int, float]:
    """Return per-player tilt multipliers.

    For each oncourt player identified by the quarter-box starters, compute:
        raw_tilt  = TILT_SCALE * (lineup_net_rtg − team_avg) / 100
        tilt      = clamp(raw_tilt, −MAX_TILT, +MAX_TILT)
        mult      = 1.0 + tilt

    Returns:
        Dict[player_id (int), multiplier (float)].
        Players NOT on the floor, or when data is unavailable, are absent
        (implicitly multiplier == 1.0, i.e. no tilt).
    """
    _qb_dir = Path(quarter_box_dir) if quarter_box_dir is not None else _DEFAULT_QB_DIR
    _lu_dir = Path(lineup_dir) if lineup_dir is not None else _DEFAULT_LU_DIR

    season = _season_of(game_id)
    oncourt_by_team = reconstruct_oncourt_pids(game_id, point, _qb_dir)
    if not oncourt_by_team:
        return {}

    result: Dict[int, float] = {}

    for team in (home_team, away_team):
        if not team:
            continue
        pid_set = oncourt_by_team.get(team)
        if pid_set is None:
            continue  # team not found in next quarter box (e.g. 2025-26 file absent)

        lu_index, team_avg = _get_lineup_index(team, season, _lu_dir)
        if not lu_index:
            continue   # no lineup file for this team/season

        lu_net_rtg = lu_index.get(pid_set)
        if lu_net_rtg is None:
            continue   # this exact 5-man unit not in the season data

        delta = lu_net_rtg - team_avg
        raw = TILT_SCALE * delta / 100.0
        tilt = max(-_MAX_TILT, min(_MAX_TILT, raw))
        mult = 1.0 + tilt

        for pid in pid_set:
            result[pid] = mult

    return result


# ---------------------------------------------------------------------------
# Public entry point — post-projection row mutator
# ---------------------------------------------------------------------------

def apply_onoff_tilt(
    snap: dict,
    rows: List[dict],
    *,
    quarter_box_dir: Optional[Path] = None,
    lineup_dir: Optional[Path] = None,
) -> List[dict]:
    """Apply lineup net-rtg tilt to projection rows (post-projection hook).

    **When ``CV_INGAME_ONOFF_TILT`` is OFF** (the default), returns ``rows``
    UNCHANGED — byte-identical guarantee, no key mutations.

    **When ON:**
    1. Infers snapshot point from ``snap["period"]`` and ``snap["clock"]``.
    2. Computes per-player tilt multipliers via ``compute_tilt_map``.
    3. For each row where ``stat in TILT_STATS`` and the player is on the floor:
       ``row["projected_final"] *= multiplier``
       ``row["onoff_tilt_mult"]  = multiplier``  (diagnostic; non-destructive)
    Bench players, rows with stat not in TILT_STATS, and rows with missing
    ``projected_final`` are untouched.

    Graceful: any per-row exception silently falls through (no tilt applied
    for that row).

    Args:
        snap: canonical snapshot dict (read-only; not mutated by this function).
        rows: list of projection dicts (mutated in-place for oncourt players).
        quarter_box_dir: override default quarter_box directory (tests only).
        lineup_dir: override default lineup directory (tests only).

    Returns:
        The (possibly mutated) rows list.
    """
    if not _flag_on():
        return rows   # byte-identical when flag OFF

    game_id = str(snap.get("game_id") or "")
    home_team = str(snap.get("home_team") or "")
    away_team = str(snap.get("away_team") or "")
    if not game_id or not home_team or not away_team:
        return rows

    point = _infer_point(snap)
    if point is None:
        return rows   # mid-period snapshot — lineup tilt not applicable

    try:
        tilt_map = compute_tilt_map(
            game_id, point, home_team, away_team,
            lineup_dir=lineup_dir,
            quarter_box_dir=quarter_box_dir,
        )
    except Exception:
        return rows   # data error — safe no-op

    if not tilt_map:
        return rows   # no lineup found — pass through unchanged

    for r in rows:
        try:
            stat = r.get("stat")
            if stat not in TILT_STATS:
                continue
            pid_raw = r.get("player_id")
            if pid_raw is None:
                continue
            pid = int(pid_raw)
            mult = tilt_map.get(pid)
            if mult is None:
                continue   # bench or unmatched — no tilt
            proj = r.get("projected_final")
            if proj is None:
                continue
            r["projected_final"] = float(proj) * mult
            # Diagnostic field (non-destructive — do not overwrite if already set).
            if "onoff_tilt_mult" not in r:
                r["onoff_tilt_mult"] = mult
        except Exception:
            continue   # per-row safety net

    return rows


# ---------------------------------------------------------------------------
# Snapshot-point inference helper
# ---------------------------------------------------------------------------

def _infer_point(snap: dict) -> Optional[str]:
    """Return 'endQ1' / 'endQ2' / 'endQ3' when the snapshot is at a quarter
    boundary (period N+1, clock near 12:00).  Returns None otherwise.

    ``retro_inplay_mae.build_snapshot`` sets ``period = N+1``, ``clock = "12:00"``
    for every endQN snapshot.  We accept clocks within 10 s of 12:00 to be robust
    to any rounding in live snapshots.
    """
    period = int(snap.get("period") or 0)
    clock_str = str(snap.get("clock") or "").strip()
    if not clock_str:
        remaining = 720.0  # assume full period remaining (conservative)
    else:
        try:
            mm_str, ss_str = clock_str.split(":", 1)
            remaining = float(mm_str) * 60.0 + float(ss_str)
        except (ValueError, TypeError):
            remaining = 0.0

    # Only apply tilt at or very near period-start (= prior-quarter end).
    if remaining < 710.0:
        return None

    return {2: "endQ1", 3: "endQ2", 4: "endQ3"}.get(period)
