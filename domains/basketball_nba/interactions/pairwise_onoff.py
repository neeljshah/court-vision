"""Pairwise teammate "who elevates whom" matrix from the same stint table
(pbp_lineups.py) and shot events (on_off.py's load_shot_events) already used
by the single-player on/off split. For every DIRECTED pair (X, Y) who ever
shared a team roster in a game: holding X on the floor fixed, splits X's own
minutes into "Y also on" vs "Y off", and reports both (a) the lineup's own
pts/min in each split and (b) X's own eFG on his shots in each split. A
positive delta on either means Y's presence measurably lifts X -- pairwise
gravity, directional (X,Y) != (Y,X) because the eFG side is always X's own.

Floors (fail-closed, both required): min_together (X&Y both on) >= 200 min
AND min_x_without_y (X on, Y off) >= 100 min. Rows below either are dropped
from the output entirely and only counted, mirroring gravity_spacing.py's
own MIN_ON_MINUTES precedent (a product-level floor, not a claims-level one
-- this module feeds face-validity/inspection, not a claims store).

METHOD: plain per-game roster loop (not vectorized) -- pair count is
O(stints * roster_size) and O(shots * roster_size), roster_size ~9-12 a
game, this season's corpus (1192 games) runs in low tens of seconds.
# ponytail: python-loop accumulation, not numpy-vectorized; fine at
# 1192-game scale, revisit with a numpy/groupby rewrite if the corpus grows
# an order of magnitude.

OUTPUT: data/cache/team_system/interactions/pairwise_onoff_2025_26.parquet
  team_id, player_x, player_y, player_x_name, player_y_name,
  min_together, min_x_without_y, lineup_ppm_with_y_on, lineup_ppm_without_y,
  x_efg_with_y_on, x_efg_without_y, ppm_delta, efg_delta.

NETWORK: zero. CLI: python -m domains.basketball_nba.interactions.pairwise_onoff
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots, load_shot_events
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "interactions" / "pairwise_onoff_2025_26.parquet"

MIN_TOGETHER_MINUTES = 200.0
MIN_X_WITHOUT_Y_MINUTES = 100.0


def compute_pairwise(stints_df: pd.DataFrame, shots_df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].str.split(",")
    shots_clean = shots_df[shots_df["n_on_court"] == 5].copy()
    shots_clean["players"] = shots_clean["lineup_key"].str.split(",")

    acc: dict[tuple[int, int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for (gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        roster = sorted(set().union(*grp["players"])) if len(grp) else []
        for s, e, pf in zip(grp["players"], grp["elapsed_s"], grp["pts_for"]):
            on = set(s)
            for x in on:
                for y in roster:
                    if y == x:
                        continue
                    key = (tid, int(x), int(y))
                    if y in on:
                        acc[key]["min_together_s"] += e
                        acc[key]["pts_together"] += pf
                    else:
                        acc[key]["min_x_without_y_s"] += e
                        acc[key]["pts_x_without_y"] += pf

        shots_gt = shots_clean[(shots_clean["game_id"] == gid) & (shots_clean["team_id"] == tid)]
        if not len(shots_gt):
            continue
        for s, scorer, fgm, fg3m, fga in zip(
            shots_gt["players"], shots_gt["person_id"], shots_gt["fgm"], shots_gt["fg3m"], shots_gt["fga"]
        ):
            scorer_s = str(int(scorer))
            if scorer_s not in roster:
                continue
            on = set(s)
            for y in roster:
                if y == scorer_s:
                    continue
                key = (tid, int(scorer_s), int(y))
                bucket = "with_y" if y in on else "without_y"
                acc[key][f"x_fgm_{bucket}"] += fgm
                acc[key][f"x_fg3m_{bucket}"] += fg3m
                acc[key][f"x_fga_{bucket}"] += fga

    n_pairs_total = len(acc)
    rows = []
    for (tid, xid, yid), v in acc.items():
        min_together = v["min_together_s"] / 60.0
        min_without = v["min_x_without_y_s"] / 60.0
        if min_together < MIN_TOGETHER_MINUTES or min_without < MIN_X_WITHOUT_Y_MINUTES:
            continue
        ppm_with = v["pts_together"] / min_together if min_together > 0 else float("nan")
        ppm_without = v["pts_x_without_y"] / min_without if min_without > 0 else float("nan")
        efg_with = (
            (v["x_fgm_with_y"] + 0.5 * v["x_fg3m_with_y"]) / v["x_fga_with_y"] if v["x_fga_with_y"] > 0 else float("nan")
        )
        efg_without = (
            (v["x_fgm_without_y"] + 0.5 * v["x_fg3m_without_y"]) / v["x_fga_without_y"]
            if v["x_fga_without_y"] > 0 else float("nan")
        )
        rows.append({
            "team_id": tid, "player_x": xid, "player_y": yid,
            "min_together": round(min_together, 2), "min_x_without_y": round(min_without, 2),
            "lineup_ppm_with_y_on": round(ppm_with, 4) if ppm_with == ppm_with else None,
            "lineup_ppm_without_y": round(ppm_without, 4) if ppm_without == ppm_without else None,
            "x_efg_with_y_on": round(efg_with, 4) if efg_with == efg_with else None,
            "x_efg_without_y": round(efg_without, 4) if efg_without == efg_without else None,
            "ppm_delta": round(ppm_with - ppm_without, 4) if ppm_with == ppm_with and ppm_without == ppm_without else None,
            "efg_delta": round(efg_with - efg_without, 4) if efg_with == efg_with and efg_without == efg_without else None,
        })
    return pd.DataFrame(rows), n_pairs_total


def _attach_names(df: pd.DataFrame, box_df: pd.DataFrame) -> pd.DataFrame:
    names = box_df.drop_duplicates(subset=["player_id"]).set_index("player_id")["player_name"]
    df = df.copy()
    df["player_x_name"] = df["player_x"].map(names)
    df["player_y_name"] = df["player_y"].map(names)
    return df


def _load_all_shots(stints_df: pd.DataFrame, game_ids: Any, pbp_dir: Path | None = None) -> pd.DataFrame:
    pbp_dir = pbp_dir or _PBP_DIR
    frames = []
    for gid in game_ids:
        fp = pbp_dir / f"{gid}.json"
        if fp.exists():
            frames.append(load_shot_events(json.loads(fp.read_text(encoding="utf-8"))))
    shots_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "fgm", "fg3m", "fga"]
    )
    return attach_lineup_to_shots(stints_df, shots_df)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA pairwise on/off gravity matrix")
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

    shots_df = _load_all_shots(stints_df, game_ids, pbp_dir)
    result, n_pairs_total = compute_pairwise(stints_df, shots_df)
    result = _attach_names(result, pd.read_parquet(_BOX_SRC))
    cols = [
        "team_id", "player_x", "player_y", "player_x_name", "player_y_name",
        "min_together", "min_x_without_y", "lineup_ppm_with_y_on", "lineup_ppm_without_y",
        "x_efg_with_y_on", "x_efg_without_y", "ppm_delta", "efg_delta",
    ]
    result = result[cols].sort_values("efg_delta", ascending=False).reset_index(drop=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    n_excluded = n_pairs_total - len(result)
    print(f"pairs_qualified={len(result)} pairs_excluded_below_floor={n_excluded} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
