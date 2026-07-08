"""League-wide, GAME-DATED per-team OFFENSIVE shot-diet store -- zone attempt
shares (rim/paint/mid/corner3/above_break_3) plus assisted share, one row per
(game_id, team_id) offense, built from the same 1192-game 2025-26 PBP corpus
and the same zone_geometry classifier as concession_profiles.py (the DEFENSE
side) and shot_features.py (the shot-quality feature frame). Reuses
shot_features.load_raw_shots for the shot-level frame instead of re-parsing
PBP -- one source of truth for shot rows across all three composition stores.

WHY GAME-DATED, NOT A SEASON AGGREGATE: concession_profiles.py's own output
(concession_2025_26.parquet) is a season-aggregate table with no game_id or
date column -- a documented gap (binding lesson from the compose lane: season
aggregates cannot be made leak-free, since a caller can never filter to games
strictly prior to a brief date). Every new composition surface must carry
game_id + date so callers can apply the same strictly-prior-to-date filter
sections_team.py already uses for top3_fga/injuries/news.

DATE comes from data/domains/basketball_nba/games.parquet (game_id -> date),
NOT the PBP file itself -- PBP actions carry no calendar date. If games.parquet
is unavailable, date is left NaT (honest gap, never fabricated).

OUTPUT: data/cache/team_system/composition/shot_diet_2025_26.parquet.
Columns: game_id, date, team_id (offense), total_fga, <zone>_fga (x5),
<zone>_share (x5), assisted_share. NETWORK: zero.
CLI: python -m domains.basketball_nba.composition.shot_diet
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.basketball_nba.composition.shot_features import load_raw_shots
from domains.basketball_nba.composition.zone_geometry import ZONES

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "pbp"
_GAMES_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "composition" / "shot_diet_2025_26.parquet"


def _game_dates(games_src: Path) -> Optional[pd.DataFrame]:
    if not games_src.exists():
        return None
    g = pd.read_parquet(games_src)[["game_id", "date"]].copy()
    g["game_id"] = g["game_id"].astype(str)
    return g


def build_diet_table(pbp_dir: Path = _PBP_DIR, games_src: Path = _GAMES_SRC,
                      limit: int | None = None) -> pd.DataFrame:
    """One row per (game_id, team_id) offense: zone attempt counts/shares +
    assisted share. Reuses shot_features.load_raw_shots (100%-coverage zone
    classification already verified there) rather than re-parsing PBP."""
    shots = load_raw_shots(pbp_dir, limit=limit)
    if shots.empty:
        return pd.DataFrame()

    per_zone = shots.groupby(["game_id", "team_id", "zone"]).size().unstack(fill_value=0)
    for z in ZONES:
        if z not in per_zone.columns:
            per_zone[z] = 0
    per_zone = per_zone[ZONES]

    totals = per_zone.sum(axis=1)
    shares = per_zone.div(totals, axis=0)
    shares.columns = [f"{z}_share" for z in shares.columns]
    counts = per_zone.copy()
    counts.columns = [f"{z}_fga" for z in counts.columns]

    assisted = shots.groupby(["game_id", "team_id"]).agg(
        n_makes=("made", "sum"), n_assisted_makes=("assisted", "sum"),
    )
    assisted["assisted_share"] = assisted["n_assisted_makes"] / assisted["n_makes"].replace(0, pd.NA)

    out = pd.concat([counts, shares], axis=1)
    out["total_fga"] = totals
    out = out.join(assisted["assisted_share"]).reset_index()

    dates = _game_dates(games_src)
    out = out.merge(dates, on="game_id", how="left") if dates is not None else out.assign(date=pd.NaT)

    keep = (["game_id", "date", "team_id", "total_fga"]
            + [f"{z}_fga" for z in ZONES] + [f"{z}_share" for z in ZONES] + ["assisted_share"])
    return out[keep].sort_values(["date", "game_id", "team_id"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA game-dated offensive shot-diet table")
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    table = build_diet_table(limit=args.limit)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out_path, index=False)
    n_games = table["game_id"].nunique() if not table.empty else 0
    n_teams = table["team_id"].nunique() if not table.empty else 0
    print(f"rows={len(table)} games={n_games} teams={n_teams} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
