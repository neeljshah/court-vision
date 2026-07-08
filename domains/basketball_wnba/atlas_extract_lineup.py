"""domains.basketball_wnba.atlas_extract_lineup -- team lineup-exposure atlas,
DESCRIPTIVE ONLY (census rank 10: "only non-NBA lineup data; opens the
lineup class in a second sport").

Builds one row per (team, 5-player lineup) across the 168-game CDN backfill
corpus (zero new fetch -- pure aggregation over
domains.basketball_wnba.lineup_stints.build_all_stints(), the full-game
substitution-replay stint reconstruction): total minutes played together,
minutes_share of that team's total tracked minutes, and points-for/against
while that exact five shared the floor. Mirrors the existing atlas
convention (value/n/confidence/as_of/corpus_id columns, atlas_write_path
naming from atlas_extract_common.py) so this slots into the same family as
atlas_extract_team.py/atlas_extract_player.py rather than inventing a new
output shape.

HONEST GAP: only lineups reconstructed from a CLEAN full 5-man oncourt
replay survive (lineup_stints.Stint already drops any stint where the
reconstructed oncourt set was ever != 5 -- see that module's docstring);
this atlas simply sums whatever clean stints exist, it does not backfill or
interpolate gaps.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_lineup.py -q
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import (
    CORPUS_ID, SEASON, atlas_write_path, iter_backfilled_games,
)
from domains.basketball_wnba.lineup_stints import Stint, build_all_stints

logger = logging.getLogger(__name__)

MIN_GAMES_LINEUP = 3  # floor: a 5-man combo must recur across >=3 distinct games


def _confidence(n_games: int) -> str:
    if n_games >= 15:
        return "high"
    if n_games >= 5:
        return "medium"
    return "low"


def _player_name_map() -> Dict[str, str]:
    """personId -> display name, built once from every backfilled boxscore's
    players[] list (stable across games; last-seen name wins). Best-effort;
    an empty map (no backfill on disk) degrades names to raw personIds."""
    names: Dict[str, str] = {}
    for _gid, pair in iter_backfilled_games():
        box = pair["boxscore"]
        for side in ("homeTeam", "awayTeam"):
            for p in (box.get(side) or {}).get("players") or []:
                if isinstance(p, dict) and p.get("personId") is not None:
                    names[str(p["personId"])] = str(p.get("name") or p.get("personId"))
    return names


def build_lineup_exposure_frame(stints: Optional[List[Stint]] = None) -> pd.DataFrame:
    """One row per (team_id, lineup) with summed minutes/pts across every
    game the exact 5-man combo appeared in clean. Empty frame if no stints."""
    stints = stints if stints is not None else build_all_stints()
    if not stints:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "team_id": str(s.team_id), "lineup": s.lineup, "game_id": s.game_id,
        "minutes": s.minutes, "pts_for": s.pts_for, "pts_against": s.pts_against,
    } for s in stints])

    team_total_minutes = df.groupby("team_id")["minutes"].sum().to_dict()
    names = _player_name_map()

    out_rows = []
    for (team_id, lineup), g in df.groupby(["team_id", "lineup"]):
        n_games = int(g["game_id"].nunique())
        minutes = round(float(g["minutes"].sum()), 4)
        pts_for = round(float(g["pts_for"].sum()), 4)
        pts_against = round(float(g["pts_against"].sum()), 4)
        team_minutes = team_total_minutes.get(team_id, 0.0)
        minutes_share = round(minutes / team_minutes, 4) if team_minutes > 0 else None
        out_rows.append({
            "lineup_id": f"{team_id}__{'_'.join(lineup)}",
            "team_id": team_id,
            "lineup_player_ids": ",".join(lineup),
            "lineup_player_names": ",".join(names.get(p, p) for p in lineup),
            "n_games": n_games,
            "minutes": minutes,
            "minutes_share": minutes_share,
            "pts_for": pts_for,
            "pts_against": pts_against,
            "net_pts": round(pts_for - pts_against, 4),
            "value": minutes_share if minutes_share is not None else 0.0,
            "n": n_games,
            "confidence": _confidence(n_games),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(out_rows)


def run_extract_lineup_atlas() -> Dict[str, int]:
    df = build_lineup_exposure_frame()
    if df.empty:
        return {"team_lineup_exposure": 0}
    path = atlas_write_path("team_lineup_exposure")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return {"team_lineup_exposure": len(df)}


def _main() -> int:
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_extract_lineup_atlas(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_lineup_exposure_frame", "run_extract_lineup_atlas", "MIN_GAMES_LINEUP"]
