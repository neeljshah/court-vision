"""Injury-impact primitive: for each team's top-3 season-FGA player P, splits
the team's own clean 5-man stints into "P on the floor" vs "P off", then
reports every teammate Q's shot-diet share (fraction of team FGA) and eFG in
each split -- whose usage rises when P sits, and at what efficiency. This is
literally "what happens to the offense when the high-usage player is out",
the primitive an injury feed later conditions on; no injury data is read
here, just the on/off shot redistribution.

TOP-USAGE RANKING SOURCE: ranked directly off THIS SEASON's own shot events
(shots_df, numeric team_id already attached from the PBP feed) -- not off
player_boxscores.parquet. That file has NO 2023-24 rows at all (its `season`
column is only 2024-25/2025-26) and, unfiltered by season, would silently
blend a player's 2024-25+2025-26 FGA together when ranking either season in
isolation -- both wrong for a per-season top-3-usage cut. The season's own
shot volume is already loaded for the redistribution computation itself and
is season-correct by construction, so it doubles as the ranking input.

Floors (fail-closed): the high-usage player needs >=200 min WITH-floor
minutes AND >=50 min WITHOUT-floor minutes to be included at all (stars sit
rarely -- 50 is deliberately looser than the 100 used elsewhere in this
lane); a reported teammate row additionally needs >0 FGA in the bucket being
reported, else the share/eFG for that side is null, not zero (an unplayed
bucket is missing data, not a real zero). `teammate_fga_joint` (fga_with +
fga_without) is carried through as a plain column so a claims layer can
apply its own joint-shot-exposure floor without re-deriving it.

OUTPUT: data/cache/team_system/interactions/usage_redistribution_2025_26.parquet
  player_id, team_id, player_name (the high-usage player), teammate_id,
  teammate_name, min_with, min_without, fga_share_with, fga_share_without,
  share_delta, efg_with, efg_without, efg_delta, teammate_fga_with,
  teammate_fga_without, teammate_fga_joint.

NETWORK: zero. CLI: python -m domains.basketball_nba.interactions.usage_redistribution
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots, load_shot_events
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "interactions" / "usage_redistribution_2025_26.parquet"

TOP_N_USAGE = 3
MIN_MINUTES_WITH = 200.0
MIN_MINUTES_WITHOUT = 50.0


def top_usage_players(shots_df: pd.DataFrame) -> pd.DataFrame:
    """Top-N FGA players per team_id, ranked off THIS SEASON's own shot
    events (person_id, team_id, fga already numeric/season-scoped -- see
    module docstring for why this replaced a player_boxscores.parquet+
    tricode-map path)."""
    agg = shots_df.groupby(["person_id", "team_id"])["fga"].sum().reset_index()
    agg = agg.rename(columns={"person_id": "player_id"})
    agg["rank"] = agg.groupby("team_id")["fga"].rank(method="first", ascending=False)
    return agg[agg["rank"] <= TOP_N_USAGE][["player_id", "team_id", "fga"]].reset_index(drop=True)


def _team_bucket_shares(shots_team: pd.DataFrame, mask_with: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["fgm", "fg3m", "fga"]
    with_grp = shots_team[mask_with].groupby("person_id")[cols].sum()
    without_grp = shots_team[~mask_with].groupby("person_id")[cols].sum()
    return with_grp, without_grp


def compute_usage_redistribution(
    stints_df: pd.DataFrame, shots_df: pd.DataFrame, usage_df: pd.DataFrame, box_df: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    clean_stints = stints_df[stints_df["n_on_court"] == 5].copy()
    clean_stints["players"] = clean_stints["lineup_key"].str.split(",")
    clean_shots = shots_df[shots_df["n_on_court"] == 5].copy()
    clean_shots["players"] = clean_shots["lineup_key"].str.split(",")
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]

    rows = []
    n_excluded_players = 0
    for player_id, team_id in zip(usage_df["player_id"], usage_df["team_id"]):
        pid_s = str(int(player_id))
        stints_team = clean_stints[clean_stints["team_id"] == team_id]
        mask_with = stints_team["players"].apply(lambda ps, p=pid_s: p in ps)
        min_with = stints_team.loc[mask_with, "elapsed_s"].sum() / 60.0
        min_without = stints_team.loc[~mask_with, "elapsed_s"].sum() / 60.0
        if min_with < MIN_MINUTES_WITH or min_without < MIN_MINUTES_WITHOUT:
            n_excluded_players += 1
            continue

        shots_team = clean_shots[clean_shots["team_id"] == team_id]
        mask_shots_with = shots_team["players"].apply(lambda ps, p=pid_s: p in ps)
        with_grp, without_grp = _team_bucket_shares(shots_team, mask_shots_with)
        total_fga_with = with_grp["fga"].sum()
        total_fga_without = without_grp["fga"].sum()

        # parens required: `-` binds tighter than `|` for sets, so an
        # unparenthesized `A | B - {x}` only drops x from B, not the union --
        # the player himself was leaking through as his own "teammate" row.
        teammates = sorted((set(with_grp.index) | set(without_grp.index)) - {int(player_id)})
        for q in teammates:
            fga_w = with_grp["fga"].get(q, 0.0)
            fga_wo = without_grp["fga"].get(q, 0.0)
            share_w = fga_w / total_fga_with if total_fga_with > 0 and fga_w > 0 else None
            share_wo = fga_wo / total_fga_without if total_fga_without > 0 and fga_wo > 0 else None
            efg_w = (
                (with_grp["fgm"].get(q, 0.0) + 0.5 * with_grp["fg3m"].get(q, 0.0)) / fga_w if fga_w > 0 else None
            )
            efg_wo = (
                (without_grp["fgm"].get(q, 0.0) + 0.5 * without_grp["fg3m"].get(q, 0.0)) / fga_wo if fga_wo > 0 else None
            )
            rows.append({
                "player_id": int(player_id), "team_id": int(team_id), "teammate_id": q,
                "min_with": round(min_with, 2), "min_without": round(min_without, 2),
                "fga_share_with": round(share_w, 4) if share_w is not None else None,
                "fga_share_without": round(share_wo, 4) if share_wo is not None else None,
                "share_delta": round(share_w - share_wo, 4) if share_w is not None and share_wo is not None else None,
                "efg_with": round(efg_w, 4) if efg_w is not None else None,
                "efg_without": round(efg_wo, 4) if efg_wo is not None else None,
                "efg_delta": round(efg_w - efg_wo, 4) if efg_w is not None and efg_wo is not None else None,
                "teammate_fga_with": int(fga_w), "teammate_fga_without": int(fga_wo),
                "teammate_fga_joint": int(fga_w + fga_wo),
            })

    result = pd.DataFrame(rows)
    if len(result):
        result["player_name"] = result["player_id"].map(names)
        result["teammate_name"] = result["teammate_id"].map(names)
    return result, n_excluded_players


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA usage-redistribution (on/off shot-diet) table")
    parser.add_argument("--stints", type=str, default=str(_STINTS_PATH))
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    parser.add_argument("--pbp-dir", type=str, default=None, help="override input dir (default: team_system/pbp)")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_DIR
    stints_df = pd.read_parquet(args.stints)
    game_ids = stints_df["game_id"].unique()
    if args.limit:
        game_ids = game_ids[: args.limit]
        stints_df = stints_df[stints_df["game_id"].isin(game_ids)]

    box_df = pd.read_parquet(_BOX_SRC)

    shot_frames = []
    for gid in game_ids:
        fp = pbp_dir / f"{gid}.json"
        if fp.exists():
            shot_frames.append(load_shot_events(json.loads(fp.read_text(encoding="utf-8"))))
    shots_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "fgm", "fg3m", "fga"]
    )
    shots_df = attach_lineup_to_shots(stints_df, shots_df)
    usage_df = top_usage_players(shots_df)

    result, n_excluded_players = compute_usage_redistribution(stints_df, shots_df, usage_df, box_df)
    result = result.sort_values("share_delta", ascending=False).reset_index(drop=True) if len(result) else result

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    n_players_qualified = len(usage_df) - n_excluded_players
    print(
        f"high_usage_players_considered={len(usage_df)} qualified={n_players_qualified} "
        f"excluded_below_floor={n_excluded_players} teammate_rows={len(result)} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
