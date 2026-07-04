"""domains.basketball_wnba.atlas_extract_pbp -- season-aggregate PLAYER atlas
parquets built from the playbyplay action log (not the boxscore), closing the
dimensions that need shot x/y or per-action score state (build_queue rank 1,
see WNBA_TRUTH_SPEC_2026-07-04.md Section 3 priority 1).

  atlas_wnba_player_shot_zones   -- dim 18: shot location/zones. Uniquely,
      WNBA's playbyplay carries true shot x/y + named zone ('area') on every
      2pt/3pt action -- a richer raw substrate than NBA's own shot_profile
      (a DEFER stub per the NBA spec). Closes: shot_location_zones.
  atlas_wnba_player_clutch_margin -- dims 20/23/25: score-margin splits and
      clutch scoring (last 5min, |margin|<=5, using each action's own
      scoreHome/scoreAway + clock/period fields -- leak-free, since these are
      the game's own final immutable log, not a live-in-progress read).
      Closes: score_margin_splits, clutch_scoring.

HONEST GAP NOT CLOSED: scoring_creation_unassisted_share (dim 20 in the team-
sense.. actually player dim) needs an explicit assist-qualifier tag on scoring
actions; this corpus's qualifiers set (sampled: deadball/2ndchance/
2freethrow/3freethrow/fastbreak/pointsinthepaint/inpenalty/startperiod/
1freethrow/mandatory/fromturnover/team) has NO assist-adjacent tag -- stays
GAP, not fabricated from an assists box-score count (that would double as
playmaking_network's existing field, not a real "unassisted share").

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_pbp.py -q
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import (
    CORPUS_ID, SEASON, atlas_write_path, iter_backfilled_games,
)

logger = logging.getLogger(__name__)

_CLK = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")  # same convention as ingame_live_cdn.clock_to_sec
CLUTCH_MARGIN_MAX = 5
CLUTCH_PERIOD = 4          # regulation Q4 (WNBA is 4x10min, see truth-spec Section 0)
CLUTCH_CLOCK_SEC_MAX = 5 * 60.0  # last 5 minutes

# Per-action point value keyed off actionType. NOTE: the raw CDN action's own
# "pointsTotal" field is NOT this shot's points -- it is the SCORING PLAYER'S
# CUMULATIVE in-game point total (verified against the real corpus, game
# 1012600001: player Clark's makes show pointsTotal 2, 5, 6, 7 -- monotonic
# running sum, not 2, 3, 1, 1). Using it directly would corrupt both the
# pre-shot-margin subtraction and any points aggregate. Basketball's own rules
# fix the per-action value unambiguously, so derive it from actionType instead
# (cross-checked against this action's own scoreHome/scoreAway delta from the
# prior action of the same actionType in the same corpus sample).
_ACTION_POINTS = {"2pt": 2, "3pt": 3, "freethrow": 1}


def _zone_col(area: Any) -> str:
    """'Mid-Range' -> 'mid_range', 'In The Paint (Non-RA)' -> 'in_the_paint_non_ra'.
    Sanitizes a raw CDN 'area' string into a safe parquet column-name suffix."""
    s = str(area).lower()
    for ch in (" ", "-", "(", ")"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _clock_to_sec(clock: Optional[str]) -> float:
    if not clock:
        return 0.0
    m = _CLK.match(str(clock))
    if not m:
        return 0.0
    return float(m.group(1) or 0) * 60.0 + float(m.group(2) or 0)


def _shot_zone_rows(game_id: str, pbp_game: dict) -> List[Dict[str, Any]]:
    """One row per made-or-missed 2pt/3pt shot action with a named zone."""
    rows: List[Dict[str, Any]] = []
    for a in pbp_game.get("actions") or []:
        if not isinstance(a, dict) or a.get("actionType") not in ("2pt", "3pt"):
            continue
        pid = a.get("personId")
        if pid is None:
            continue
        rows.append({
            "game_id": str(game_id),
            "player_id": str(pid),
            "player_name": a.get("playerName"),
            "action_type": a.get("actionType"),
            "area": a.get("area"),
            "shot_distance": a.get("shotDistance"),
            "made": a.get("shotResult") == "Made",
            "x": a.get("x"),
            "y": a.get("y"),
        })
    return rows


def _clutch_margin_rows(game_id: str, pbp_game: dict, home_team_id: Any) -> List[Dict[str, Any]]:
    """One row per scoring action (2pt/3pt made, or freethrow made) tagged
    with whether it occurred in the CLUTCH window (period==CLUTCH_PERIOD,
    clock remaining <= CLUTCH_CLOCK_SEC_MAX, |margin BEFORE the shot| <= 5).
    Margin-before is derived from the action's OWN post-shot scoreHome/
    scoreAway minus this action's OWN point value (from actionType via
    _ACTION_POINTS -- NOT the raw pointsTotal field, which is the scorer's
    cumulative running total, not this shot's points), subtracted from
    whichever side (home/away) actually scored -- *home_team_id* (read from
    the paired boxscore, since playbyplay actions carry teamId but not a
    home/away side label) resolves that. Never peeks at a later action's
    score."""
    rows: List[Dict[str, Any]] = []
    for a in pbp_game.get("actions") or []:
        if not isinstance(a, dict):
            continue
        action_type = a.get("actionType")
        if action_type not in _ACTION_POINTS:
            continue
        if a.get("shotResult") != "Made":
            continue
        pid = a.get("personId")
        if pid is None:
            continue
        try:
            score_home = float(a.get("scoreHome"))
            score_away = float(a.get("scoreAway"))
        except (TypeError, ValueError):
            continue
        pts = _ACTION_POINTS[action_type]
        team_id = a.get("teamId")
        post_margin = score_home - score_away
        # subtract this made basket's points from the scorer's own side
        # before computing the margin, so pre_margin reflects state BEFORE
        # the shot (honest pre-shot state, never a peek at a later action).
        pre_margin = post_margin - pts if team_id == home_team_id else post_margin + pts
        period = a.get("period")
        clock_sec = _clock_to_sec(a.get("clock"))
        is_clutch = (period == CLUTCH_PERIOD and clock_sec <= CLUTCH_CLOCK_SEC_MAX
                     and abs(pre_margin) <= CLUTCH_MARGIN_MAX)
        rows.append({
            "game_id": str(game_id),
            "player_id": str(pid),
            "player_name": a.get("playerName"),
            "points": pts,
            "period": period,
            "clock_sec_remaining": clock_sec,
            "pre_shot_margin_abs": abs(pre_margin),
            "is_clutch": is_clutch,
        })
    return rows


def build_shot_zone_frame() -> pd.DataFrame:
    all_rows: List[Dict[str, Any]] = []
    n_games = 0
    for gid, pair in iter_backfilled_games():
        rows = _shot_zone_rows(gid, pair["playbyplay"])
        if rows:
            all_rows.extend(rows)
            n_games += 1
    logger.info("atlas_extract_pbp shot_zones: %d shot rows from %d games", len(all_rows), n_games)
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def build_clutch_margin_frame() -> pd.DataFrame:
    all_rows: List[Dict[str, Any]] = []
    n_games = 0
    for gid, pair in iter_backfilled_games():
        home_team_id = (pair["boxscore"].get("homeTeam") or {}).get("teamId")
        rows = _clutch_margin_rows(gid, pair["playbyplay"], home_team_id)
        if rows:
            all_rows.extend(rows)
            n_games += 1
    logger.info("atlas_extract_pbp clutch_margin: %d scoring rows from %d games", len(all_rows), n_games)
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def _confidence(n_games: int) -> str:
    if n_games >= 15:
        return "high"
    if n_games >= 5:
        return "medium"
    return "low"


def build_player_shot_zones_atlas(shots: pd.DataFrame) -> pd.DataFrame:
    """Season-aggregate FG% by named zone per player (wide: one column per
    zone's attempt count + make count). Closes: shot_location_zones."""
    if shots.empty:
        return pd.DataFrame()
    rows = []
    for pid, g in shots.groupby("player_id"):
        n_games_proxy = g["game_id"].nunique()
        by_zone = g.groupby("area").agg(attempts=("made", "size"), makes=("made", "sum"))
        zone_pct = {f"zone_{_zone_col(z)}_fg_pct":
                    round(r.makes / r.attempts, 4) if r.attempts > 0 else None
                    for z, r in by_zone.iterrows()}
        total_attempts = int(g.shape[0])
        total_makes = int(g["made"].sum())
        row = {
            "player_id": pid,
            "player_name": g["player_name"].iloc[-1],
            "n_shots_total": total_attempts,
            "fg_pct_overall": round(total_makes / total_attempts, 4) if total_attempts > 0 else None,
            "value": round(total_makes / total_attempts, 4) if total_attempts > 0 else 0.0,
            "n": n_games_proxy,
            "confidence": _confidence(n_games_proxy),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        }
        row.update(zone_pct)
        rows.append(row)
    return pd.DataFrame(rows)


def build_player_clutch_margin_atlas(cm: pd.DataFrame) -> pd.DataFrame:
    """Season-aggregate clutch scoring rate per player. Closes:
    score_margin_splits (via pre_shot_margin_abs distribution), clutch_
    scoring (via is_clutch points share)."""
    if cm.empty:
        return pd.DataFrame()
    rows = []
    for pid, g in cm.groupby("player_id"):
        n_games_proxy = g["game_id"].nunique()
        total_pts = g["points"].sum()
        clutch_pts = g.loc[g["is_clutch"], "points"].sum()
        rows.append({
            "player_id": pid,
            "player_name": g["player_name"].iloc[-1],
            "n_scoring_actions": int(len(g)),
            "total_points_from_scoring_actions": int(total_pts),
            "clutch_points": int(clutch_pts),
            "clutch_points_share": round(clutch_pts / total_pts, 4) if total_pts > 0 else None,
            "mean_pre_shot_margin_abs": round(g["pre_shot_margin_abs"].mean(), 4),
            "value": round(clutch_pts / total_pts, 4) if total_pts > 0 else 0.0,
            "n": n_games_proxy,
            "confidence": _confidence(n_games_proxy),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def run_extract_pbp_atlas() -> Dict[str, int]:
    """Build + write both PBP-derived player atlas parquets."""
    shots = build_shot_zone_frame()
    cm = build_clutch_margin_frame()
    out: Dict[str, int] = {}
    tables = {
        "player_shot_zones": build_player_shot_zones_atlas(shots),
        "player_clutch_margin": build_player_clutch_margin_atlas(cm),
    }
    for name, df in tables.items():
        out[name] = len(df)
        if not df.empty:
            path = atlas_write_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(path)
    return out


def _main() -> int:
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_extract_pbp_atlas(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "build_shot_zone_frame", "build_clutch_margin_frame",
    "build_player_shot_zones_atlas", "build_player_clutch_margin_atlas",
    "run_extract_pbp_atlas", "CLUTCH_MARGIN_MAX", "CLUTCH_PERIOD", "CLUTCH_CLOCK_SEC_MAX",
]
