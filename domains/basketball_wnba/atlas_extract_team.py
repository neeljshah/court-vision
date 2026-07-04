"""domains.basketball_wnba.atlas_extract_team -- season-aggregate TEAM atlas
parquets from the 168-game CDN backfill corpus (zero new fetch).

Builds one row per team (season 2026, single-season corpus -- see truth-spec
limit #4) across FOUR atlas parquets, mirroring the NBA atlas convention:

  atlas_wnba_team_pace_shooting   -- dim 3/6/7: pace proxy + opponent-allowed
      3pt/paint rate (closes pace_possessions; 3pt/paint-D are a documented
      PARTIAL -- raw allowed-rate, no opponent-strength adjustment attempted)
  atlas_wnba_team_bench_hustle    -- dim 9/10/11/14: bench production, reb
      scheme, turnover forcing, FT/foul environment (closes bench_production)
  atlas_wnba_team_rotation        -- dim 38: top-5 minutes share, built from
      atlas_extract_player's rotation table (closes rotation_minutes_concentration)
  atlas_wnba_team_officials_venue -- dim 48/49: referee-crew foul rate +
      arena/attendance (closes referee_crew_tendencies, arena_attendance_context)

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_team.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import (
    CORPUS_ID, SEASON, atlas_write_path, iter_backfilled_games, team_pace_proxy,
)
from domains.basketball_wnba.atlas_extract_player import build_player_game_frame

logger = logging.getLogger(__name__)

_SIDES = ("homeTeam", "awayTeam")
_OTHER_SIDE = {"homeTeam": "awayTeam", "awayTeam": "homeTeam"}


def _team_game_rows(game_id: str, box_game: dict) -> List[Dict[str, Any]]:
    """One row per team-side (both home+away) for *box_game*, including the
    OPPONENT's stat line (needed for allowed-side defense proxies). Pure
    function, no I/O. Never raises -- a malformed side is skipped."""
    rows: List[Dict[str, Any]] = []
    officials = box_game.get("officials") or []
    crew_ids = tuple(sorted(str(o.get("personId")) for o in officials if isinstance(o, dict)))
    attendance = box_game.get("attendance")
    arena = box_game.get("arena") or {}
    for side in _SIDES:
        team = box_game.get(side) or {}
        opp = box_game.get(_OTHER_SIDE[side]) or {}
        team_id = team.get("teamId")
        if team_id is None:
            continue
        stats = team.get("statistics") or {}
        opp_stats = opp.get("statistics") or {}
        rows.append({
            "game_id": str(game_id),
            "team_id": str(team_id),
            "team_tricode": team.get("teamTricode"),
            "fga": stats.get("fieldGoalsAttempted"),
            "fta": stats.get("freeThrowsAttempted"),
            "oreb": stats.get("reboundsOffensive"),
            "dreb": stats.get("reboundsDefensive"),
            "turnovers": stats.get("turnoversTotal"),
            "bench_points": stats.get("benchPoints"),
            "points_from_turnovers": stats.get("pointsFromTurnovers"),
            "fouls_personal": stats.get("foulsPersonal"),
            "fouls_team": stats.get("foulsTeam"),
            "freethrows_attempted": stats.get("freeThrowsAttempted"),
            "opp_fg3a": opp_stats.get("threePointersAttempted"),
            "opp_fg3m": opp_stats.get("threePointersMade"),
            "opp_paint_pts": opp_stats.get("pointsInThePaint"),
            "opp_paint_att": opp_stats.get("pointsInThePaintAttempted"),
            "officials_crew": crew_ids,
            "attendance": attendance,
            "arena_city": arena.get("arenaCity"),
            "sellout": box_game.get("sellout"),
        })
    return rows


def build_team_game_frame() -> pd.DataFrame:
    """Every team-game row (both sides) across the backfilled corpus."""
    all_rows: List[Dict[str, Any]] = []
    n_games = 0
    for gid, pair in iter_backfilled_games():
        rows = _team_game_rows(gid, pair["boxscore"])
        if rows:
            all_rows.extend(rows)
            n_games += 1
    logger.info("atlas_extract_team: %d team-game rows from %d games", len(all_rows), n_games)
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)


def _confidence(n_games: int) -> str:
    if n_games >= 15:
        return "high"
    if n_games >= 5:
        return "medium"
    return "low"


def build_pace_shooting(tg: pd.DataFrame) -> pd.DataFrame:
    """Closes: pace_possessions. Also reports opponent-allowed 3pt/paint rate
    as a PARTIAL, un-adjusted proxy for three_point_defense/paint_defense
    (raw allowed rate, not a schedule/opponent-strength-adjusted rating --
    stated honestly, not claimed as the full atlas_team_three_pt_defense
    concept)."""
    if tg.empty:
        return pd.DataFrame()
    rows = []
    for tid, g in tg.groupby("team_id"):
        n = len(g)
        pace_vals = [team_pace_proxy(r.fga, r.fta, r.oreb, r.turnovers) for r in g.itertuples()]
        pace_vals = [v for v in pace_vals if v is not None]
        pace_mean = round(sum(pace_vals) / len(pace_vals), 4) if pace_vals else None
        opp_fg3a = g["opp_fg3a"].fillna(0).sum()
        opp_fg3m = g["opp_fg3m"].fillna(0).sum()
        opp_paint_pts = g["opp_paint_pts"].fillna(0).sum()
        rows.append({
            "team_id": tid,
            "team_tricode": g["team_tricode"].iloc[-1],
            "n_games": n,
            "pace_proxy_per_game": pace_mean,
            "opp_fg3_pct_allowed": round(opp_fg3m / opp_fg3a, 4) if opp_fg3a > 0 else None,
            "opp_paint_pts_allowed_per_game": round(opp_paint_pts / n, 4),
            "value": pace_mean if pace_mean is not None else 0.0,
            "n": n,
            "confidence": _confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def build_bench_hustle(tg: pd.DataFrame) -> pd.DataFrame:
    """Closes: bench_production. Also carries rebounding_scheme/turnover_
    forcing/ft_foul_environment raw team-game aggregates (documented as
    counting-stat aggregates, not opponent-adjusted scheme identities)."""
    if tg.empty:
        return pd.DataFrame()
    rows = []
    for tid, g in tg.groupby("team_id"):
        n = len(g)
        bench_pts = g["bench_points"].fillna(0).sum()
        rows.append({
            "team_id": tid,
            "team_tricode": g["team_tricode"].iloc[-1],
            "n_games": n,
            "bench_points_per_game": round(bench_pts / n, 4),
            "oreb_per_game": round(g["oreb"].fillna(0).sum() / n, 4),
            "dreb_per_game": round(g["dreb"].fillna(0).sum() / n, 4),
            "turnovers_forced_pts_per_game": round(g["points_from_turnovers"].fillna(0).sum() / n, 4),
            "fouls_personal_per_game": round(g["fouls_personal"].fillna(0).sum() / n, 4),
            "ft_attempted_per_game": round(g["freethrows_attempted"].fillna(0).sum() / n, 4),
            "value": round(bench_pts / n, 4),
            "n": n,
            "confidence": _confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def build_rotation_concentration(pg: pd.DataFrame) -> pd.DataFrame:
    """Closes: rotation_minutes_concentration (team-level). Top-5 minutes
    share per team, built from the player-game frame (reuses atlas_
    extract_player.build_player_game_frame -- SAME source rows, no
    reload/re-derivation)."""
    if pg.empty:
        return pd.DataFrame()
    played = pg[pg["played"]].copy()
    if played.empty:
        return pd.DataFrame()
    rows = []
    for (gid, tid), g in played.groupby(["game_id", "team_id"]):
        team_minutes = g["minutes"].fillna(0)
        total = team_minutes.sum()
        if total <= 0:
            continue
        top5 = team_minutes.sort_values(ascending=False).head(5).sum()
        rows.append({"game_id": gid, "team_id": tid,
                      "top5_minutes_share": round(top5 / total, 4)})
    if not rows:
        return pd.DataFrame()
    game_level = pd.DataFrame(rows)
    out = []
    for tid, g in game_level.groupby("team_id"):
        n = len(g)
        mean_share = round(g["top5_minutes_share"].mean(), 4)
        out.append({
            "team_id": tid,
            "n_games": n,
            "top5_minutes_share_mean": mean_share,
            "value": mean_share,
            "n": n,
            "confidence": _confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(out)


def build_officials_venue(tg: pd.DataFrame) -> pd.DataFrame:
    """Closes: referee_crew_tendencies (crew-level foul-rate aggregation),
    arena_attendance_context (per-team attendance/sellout aggregate).
    Two separate grains in one table (crew rows have team_id=None)."""
    if tg.empty:
        return pd.DataFrame()
    rows = []
    # crew-level foul rate: dedupe by (game_id, officials_crew) since each
    # game contributes ONE crew but TWO team-side rows (avoid double count).
    crew_games = tg.drop_duplicates(subset=["game_id"])[["game_id", "officials_crew"]]
    crew_fouls = tg.groupby("game_id")["fouls_personal"].sum()
    crew_map: Dict[Tuple[str, ...], List[float]] = {}
    for _, r in crew_games.iterrows():
        crew = r["officials_crew"]
        if not crew:
            continue
        crew_map.setdefault(crew, []).append(crew_fouls.get(r["game_id"], 0.0) or 0.0)
    for crew, fouls_list in crew_map.items():
        n = len(fouls_list)
        rows.append({
            "team_id": None, "grain": "officials_crew",
            "officials_crew": ",".join(crew),
            "n_games": n,
            "total_fouls_per_game_mean": round(sum(fouls_list) / n, 4),
            "value": round(sum(fouls_list) / n, 4),
            "n": n,
            "confidence": _confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    # per-team attendance/arena context
    for tid, g in tg.groupby("team_id"):
        n = len(g)
        att = g["attendance"].dropna()
        # sellout is observed as either a raw string ('0'/'1') or int on this
        # CDN feed (schema is not fully consistent across games) -- coerce
        # numerically, honest-skip (not zero-fill) whatever fails to parse.
        sellout_numeric = pd.to_numeric(g["sellout"], errors="coerce")
        rows.append({
            "team_id": tid, "grain": "team_venue",
            "officials_crew": None,
            "n_games": n,
            "attendance_mean": round(att.mean(), 2) if not att.empty else None,
            "sellout_rate": round(sellout_numeric.mean(), 4) if sellout_numeric.notna().any() else None,
            "value": round(att.mean(), 2) if not att.empty else 0.0,
            "n": n,
            "confidence": _confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def run_extract_team_atlas() -> Dict[str, int]:
    """Build + write all four team atlas parquets. Returns {table: n_rows}."""
    tg = build_team_game_frame()
    pg = build_player_game_frame()
    out: Dict[str, int] = {}
    tables = {
        "team_pace_shooting": build_pace_shooting(tg),
        "team_bench_hustle": build_bench_hustle(tg),
        "team_rotation": build_rotation_concentration(pg),
        "team_officials_venue": build_officials_venue(tg),
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
    print(json.dumps(run_extract_team_atlas(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "build_team_game_frame", "build_pace_shooting", "build_bench_hustle",
    "build_rotation_concentration", "build_officials_venue", "run_extract_team_atlas",
]
