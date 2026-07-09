"""domains.basketball_wnba.lineups.lineup_exposure_wnba -- team lineup-exposure
atlas RE-DERIVED from the full-game stint keystone (data/cache/team_system/
lineups/stints_wnba_2026.parquet, built by pbp_lineups_wnba.py: 8,324 stints,
thin adapter over the NBA substitution-replay engine), replacing the old
checkpoint-string recipe (lineup_stints.py + atlas_extract_lineup.py, built
off the superseded 3-checkpoint cdn_backfill_states corpus) per
docs/analytics/wnba.md's queued item: "Re-derive lineup_exposure_descriptors
from the new stint-level lineup_key instead of the stale 3-checkpoint-based
recipe."

WHY A NEW FILE INSTEAD OF EDITING atlas_extract_lineup.py: that module's
build_lineup_exposure_frame is wired to lineup_stints.Stint objects (the old
checkpoint-replay reconstruction). The new keystone's stint rows
(pbp_lineups_wnba.build_game_stints_wnba output, already materialized to
parquet) have a different shape (lineup_key comma-string, elapsed_s,
n_on_court quality flag) -- reshaping every row into a Stint just to reshape
it back would be pure overhead. This module aggregates the new stint rows
directly: same groupby-and-sum shape as the old builder, same output
schema/path, so nothing downstream needs to change.

OUTPUT: SAME path/schema as the superseded atlas (wnba_lineup_exposure_claims.py
needs zero changes) -- data/cache/atlas_wnba_team_lineup_exposure.parquet:
lineup_id, team_id, lineup_player_ids, lineup_player_names, n_games, minutes,
minutes_share, pts_for, pts_against, net_pts, value, n, confidence, as_of,
corpus_id -- PLUS first_game_date/last_game_date (real dates carried from
player_boxscores.parquet's game_date column, never fabricated) so every
aggregate row stays traceable to the games it was built from.

CLEAN STINTS ONLY: n_on_court==5 rows feed this (same convention as
on_off.py -- the stints that drifted from 5 players are dropped, not
corrupting an aggregate).

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/lineups/test_lineup_exposure_wnba.py -q
CLI:
  python -m domains.basketball_wnba.lineups.lineup_exposure_wnba
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import CORPUS_ID, SEASON, atlas_write_path
from domains.basketball_wnba.atlas_extract_lineup import _confidence

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_wnba_2026.parquet"
_BOX_SRC = REPO_ROOT / "data" / "domains" / "wnba" / "player_boxscores.parquet"


def _player_name_map(box_df: pd.DataFrame) -> Dict[str, str]:
    """personId (str) -> display name, last-seen wins. Empty box -> empty map
    (names degrade to raw ids, never a crash)."""
    if box_df.empty or "player_id" not in box_df.columns:
        return {}
    return dict(zip(box_df["player_id"].astype(str), box_df["player_name"]))


def _game_date_map(box_df: pd.DataFrame) -> Dict[str, str]:
    if box_df.empty or "game_date" not in box_df.columns:
        return {}
    return dict(zip(box_df["game_id"].astype(str), box_df["game_date"].astype(str)))


def build_lineup_exposure_frame_from_stints(
    stints_df: Optional[pd.DataFrame] = None, box_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """One row per (team_id, lineup) aggregated over CLEAN (n_on_court==5)
    stints from the stint-level keystone. Empty frame if no clean stints."""
    stints_df = stints_df if stints_df is not None else pd.read_parquet(_STINTS_PATH)
    box_df = box_df if box_df is not None else (
        pd.read_parquet(_BOX_SRC) if _BOX_SRC.exists() else pd.DataFrame()
    )
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    if clean.empty:
        return pd.DataFrame()

    clean["team_id"] = clean["team_id"].astype("int64")
    clean["game_id"] = clean["game_id"].astype(str)
    clean["minutes"] = clean["elapsed_s"] / 60.0

    team_total_minutes = clean.groupby("team_id")["minutes"].sum().to_dict()
    names = _player_name_map(box_df)
    game_dates = _game_date_map(box_df)

    out_rows = []
    for (team_id, lineup_key), g in clean.groupby(["team_id", "lineup_key"]):
        lineup = tuple(lineup_key.split(","))
        n_games = int(g["game_id"].nunique())
        minutes = round(float(g["minutes"].sum()), 4)
        pts_for = round(float(g["pts_for"].sum()), 4)
        pts_against = round(float(g["pts_against"].sum()), 4)
        team_minutes = team_total_minutes.get(team_id, 0.0)
        minutes_share = round(minutes / team_minutes, 4) if team_minutes > 0 else None
        seen_dates = sorted({game_dates[gid] for gid in g["game_id"].unique() if gid in game_dates})
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
            "first_game_date": seen_dates[0] if seen_dates else None,
            "last_game_date": seen_dates[-1] if seen_dates else None,
        })
    return pd.DataFrame(out_rows)


def run_extract_lineup_exposure_from_stints() -> Dict[str, int]:
    df = build_lineup_exposure_frame_from_stints()
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
    print(json.dumps(run_extract_lineup_exposure_from_stints(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build_lineup_exposure_frame_from_stints", "run_extract_lineup_exposure_from_stints"]
