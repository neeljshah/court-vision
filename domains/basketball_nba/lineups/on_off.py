"""Per-player ON vs OFF splits from the stint table
(data/cache/team_system/lineups/stints_2025_26.parquet, built by
pbp_lineups.py): team pts/min for+against while the player is on/off court,
a net-rating-per-48 proxy, and teammates' eFG% with the player on vs off
(the gravity-proxy input; the derived gravity metric itself lives in
gravity_spacing.py).

Keyed by (player_id, team_id) -- not player_id alone -- so a mid-window
trade never blends two teams' minutes into one row.

Only CLEAN stints (n_on_court==5, from pbp_lineups.py's own quality field)
feed this; the ~0.6%% of stints that drifted from 5 players are dropped
here rather than silently corrupting a split.

OUTPUT: data/cache/team_system/lineups/on_off_2025_26.parquet
  player_id, team_id, player_name, n_games, min_on, min_off,
  net_rating_on_per48, net_rating_off_per48, teammate_efg_on, teammate_efg_off,
  teammate_fga_on, teammate_fga_off.

NETWORK: zero. CLI: python -m domains.basketball_nba.lineups.on_off
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, _elapsed_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_2025_26.parquet"


def load_shot_events(game_json: dict[str, Any]) -> pd.DataFrame:
    game_id = game_json["game"]["gameId"]
    rows = []
    for a in game_json["game"]["actions"]:
        if a.get("actionType") in ("2pt", "3pt") and a.get("teamId") and a.get("personId"):
            made = 1 if a.get("shotResult") == "Made" else 0
            rows.append({
                "game_id": game_id, "team_id": a["teamId"], "period": a["period"],
                "elapsed_s": _elapsed_s(a["period"], a["clock"]), "person_id": a["personId"],
                "fgm": made, "fg3m": made if a["actionType"] == "3pt" else 0, "fga": 1,
            })
    return pd.DataFrame(rows)


def attach_lineup_to_shots(stints_df: pd.DataFrame, shots_df: pd.DataFrame) -> pd.DataFrame:
    """Assigns each shot the lineup_key/n_on_court of the stint whose
    [start_s, end_s) window contains it, via a per-(game,team,period)
    searchsorted (stints never overlap in time within that group)."""
    shots_df = shots_df.copy()
    shots_df["lineup_key"], shots_df["n_on_court"] = None, 0
    for (gid, tid, per), s_grp in stints_df.groupby(["game_id", "team_id", "period"]):
        mask = (shots_df["game_id"] == gid) & (shots_df["team_id"] == tid) & (shots_df["period"] == per)
        if not mask.any():
            continue
        s_grp = s_grp.sort_values("start_s")
        starts = s_grp["start_s"].to_numpy()
        idx = np.clip(np.searchsorted(starts, shots_df.loc[mask, "elapsed_s"].to_numpy(), side="right") - 1, 0, len(s_grp) - 1)
        shots_df.loc[mask, "lineup_key"] = s_grp["lineup_key"].to_numpy()[idx]
        shots_df.loc[mask, "n_on_court"] = s_grp["n_on_court"].to_numpy()[idx]
    return shots_df


def compute_on_off(stints_df: pd.DataFrame, shots_df: pd.DataFrame) -> pd.DataFrame:
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].str.split(",")
    shots_clean = shots_df[shots_df["n_on_court"] == 5].copy()
    shots_clean["players"] = shots_clean["lineup_key"].str.split(",")

    acc: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    games_seen: dict[tuple[int, int], set] = defaultdict(set)

    for (gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        roster: set = set().union(*grp["players"]) if len(grp) else set()
        shots_gt = shots_clean[(shots_clean["game_id"] == gid) & (shots_clean["team_id"] == tid)]
        on_masks = {p: grp["players"].apply(lambda ps, p=p: p in ps) for p in roster}
        shot_masks = {p: shots_gt["players"].apply(lambda ps, p=p: p in ps) for p in roster} if len(shots_gt) else {}

        for p_str in roster:
            player_id = int(p_str)
            on_rows, off_rows = grp[on_masks[p_str]], grp[~on_masks[p_str]]
            key = (player_id, tid)
            games_seen[key].add(gid)
            acc[key]["min_on"] += on_rows["elapsed_s"].sum() / 60.0
            acc[key]["min_off"] += off_rows["elapsed_s"].sum() / 60.0
            acc[key]["pts_for_on"] += on_rows["pts_for"].sum()
            acc[key]["pts_against_on"] += on_rows["pts_against"].sum()
            acc[key]["pts_for_off"] += off_rows["pts_for"].sum()
            acc[key]["pts_against_off"] += off_rows["pts_against"].sum()
            if len(shots_gt):
                mask = shot_masks[p_str]
                teammate_on = shots_gt[mask & (shots_gt["person_id"] != player_id)]
                teammate_off = shots_gt[~mask]
                acc[key]["fgm_on"] += teammate_on["fgm"].sum()
                acc[key]["fg3m_on"] += teammate_on["fg3m"].sum()
                acc[key]["fga_on"] += teammate_on["fga"].sum()
                acc[key]["fgm_off"] += teammate_off["fgm"].sum()
                acc[key]["fg3m_off"] += teammate_off["fg3m"].sum()
                acc[key]["fga_off"] += teammate_off["fga"].sum()

    rows = []
    for (player_id, team_id), v in acc.items():
        net_on = ((v["pts_for_on"] - v["pts_against_on"]) / v["min_on"] * 48.0) if v["min_on"] > 0 else float("nan")
        net_off = ((v["pts_for_off"] - v["pts_against_off"]) / v["min_off"] * 48.0) if v["min_off"] > 0 else float("nan")
        efg_on = ((v["fgm_on"] + 0.5 * v["fg3m_on"]) / v["fga_on"]) if v["fga_on"] > 0 else float("nan")
        efg_off = ((v["fgm_off"] + 0.5 * v["fg3m_off"]) / v["fga_off"]) if v["fga_off"] > 0 else float("nan")
        rows.append({
            "player_id": player_id, "team_id": team_id, "n_games": len(games_seen[(player_id, team_id)]),
            "min_on": round(v["min_on"], 2), "min_off": round(v["min_off"], 2),
            "net_rating_on_per48": round(net_on, 3) if net_on == net_on else None,
            "net_rating_off_per48": round(net_off, 3) if net_off == net_off else None,
            "teammate_efg_on": round(efg_on, 4) if efg_on == efg_on else None,
            "teammate_efg_off": round(efg_off, 4) if efg_off == efg_off else None,
            "teammate_fga_on": int(v["fga_on"]), "teammate_fga_off": int(v["fga_off"]),
        })
    return pd.DataFrame(rows)


def _attach_player_names(df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    df = df.copy()
    df["player_name"] = df["player_id"].map(names)
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA on/off splits from stint table")
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

    shot_frames = []
    for gid in game_ids:
        fp = pbp_dir / f"{gid}.json"
        if fp.exists():
            shot_frames.append(load_shot_events(json.loads(fp.read_text(encoding="utf-8"))))
    shots_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "fgm", "fg3m", "fga"]
    )
    shots_df = attach_lineup_to_shots(stints_df, shots_df)

    result = compute_on_off(stints_df, shots_df)
    result = _attach_player_names(result, pd.read_parquet(_BOX_SRC))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    print(f"players={len(result)} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
