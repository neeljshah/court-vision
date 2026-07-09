"""Per (player, team, season) DEFENSIVE zone on/off splits: opponent
rim/three shot-share and eFG% allowed while the player's own lineup is on
the floor vs off, built from stints_<season>.parquet (pbp_lineups.py) + PBP
shot x/y (classify_zone, composition/zone_geometry.py -- 96.7% zone-agreement
calibration against the corpus's labeled subset).

DEFENSIVE SIDE, not offensive -- get-the-side-right: a shot action carries
teamId = the SHOOTING team; the defense is the OTHER team_id in the game
(every game here has exactly 2, verified in concession_profiles.py).
load_shot_events below sets each shot row's team_id to that DEFENDING team,
so attach_lineup_to_shots (on_off.py, reused verbatim) joins each shot
against the DEFENSE's own stint lineup, not the shooter's. Proven on a
synthetic 2-team game in test_zone_onoff.py (including a check that the
defending team's OWN offensive shots never leak into its own on/off split).

Reuses attach_lineup_to_shots + _attach_player_names from on_off.py and
classify_zone from composition/zone_geometry.py rather than reimplementing
either. Full population, no minutes floor here -- same precedent as
on_off.py; the floor (>=750 min_on/off) is applied downstream in
profiles/player_attributes.py's build_rim_pressure_def.

OUTPUT: data/cache/team_system/lineups/zone_onoff_<season>.parquet
  player_id, team_id, player_name, n_games, min_on, min_off,
  opp_fga_on/off, then per zone in ZONE_SPECS (rim, paint, mid, corner3,
  above_break_3, plus the legacy combined "three" = corner3+above_break_3):
  <zone>_fga_on/off, <zone>_fgm_on/off, <zone>_share_allowed_on/off,
  <zone>_efg_allowed_on/off. rim/paint/mid are 2pt attempts -- eFG allowed
  there equals plain FG%; corner3/above_break_3/three use 1.5x for the
  3pt eFG bump.

NETWORK: zero. CLI: python -m domains.basketball_nba.lineups.zone_onoff --season 2025_26
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import classify_zone
from domains.basketball_nba.lineups.on_off import _attach_player_names, attach_lineup_to_shots
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, _elapsed_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_PBP_BY_SEASON = {
    "2023_24": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2023_24",
    "2024_25": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25",
    "2025_26": _PBP_DIR,
}

# (column_prefix, zone_values classify_zone can emit, is_three_pt_scoring)
# "three" is the legacy combined corner3+above_break_3 bucket -- kept verbatim
# (same column names/semantics) for existing consumers (rim_pressure_def,
# test_zone_onoff.py); the 4 new prefixes are the individual zone split.
ZONE_SPECS: list[tuple[str, tuple[str, ...], bool]] = [
    ("rim", ("rim",), False),
    ("paint", ("paint",), False),
    ("mid", ("mid",), False),
    ("corner3", ("corner3",), True),
    ("above_break_3", ("above_break_3",), True),
    ("three", ("corner3", "above_break_3"), True),
]


def load_shot_events(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per shot ATTEMPT, keyed on the DEFENDING team_id (the other
    team_id in the game) -- see module docstring."""
    game_id = game_json["game"]["gameId"]
    actions = game_json["game"]["actions"]
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    rows = []
    for a in actions:
        if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId") or a.get("x") is None or not a.get("personId"):
            continue
        offense = a["teamId"]
        defense = next((t for t in team_ids if t != offense), None)
        if defense is None:
            continue
        is_3 = a["actionType"] == "3pt"
        made = 1 if a.get("shotResult") == "Made" else 0
        rows.append({
            "game_id": game_id, "team_id": defense, "period": a["period"],
            "elapsed_s": _elapsed_s(a["period"], a["clock"]), "person_id": a["personId"],
            "zone": classify_zone(float(a["x"]), float(a["y"]), is_3), "fgm": made, "fga": 1,
        })
    return pd.DataFrame(rows)


def _div(n: float, d: float) -> float:
    return (n / d) if d > 0 else float("nan")


def compute_zone_onoff(stints_df: pd.DataFrame, shots_df: pd.DataFrame) -> pd.DataFrame:
    """shots_df's team_id must already be the DEFENDING team (load_shot_events
    above sets it) -- everything here just groups by that column the same
    way on_off.py's compute_on_off groups by the offensive team_id."""
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].astype(str).str.split(",")
    shots_clean = shots_df[shots_df["n_on_court"] == 5].copy()
    shots_clean["players"] = shots_clean["lineup_key"].astype(str).str.split(",")
    for prefix, zones, _ in ZONE_SPECS:
        shots_clean[f"is_{prefix}"] = shots_clean["zone"].isin(zones).astype(int)

    acc: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    games_seen: dict[tuple[int, int], set] = defaultdict(set)

    for (gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        roster: set = set().union(*grp["players"]) if len(grp) else set()
        shots_gt = shots_clean[(shots_clean["game_id"] == gid) & (shots_clean["team_id"] == tid)]
        on_masks = {p: grp["players"].apply(lambda ps, p=p: p in ps) for p in roster}
        shot_masks = {p: shots_gt["players"].apply(lambda ps, p=p: p in ps) for p in roster} if len(shots_gt) else {}

        for p_str in roster:
            if not p_str.lstrip("-").isdigit():
                continue
            player_id = int(p_str)
            if player_id < 0:  # unresolved-lineup-slot placeholder id -- never a real player
                continue
            on_rows, off_rows = grp[on_masks[p_str]], grp[~on_masks[p_str]]
            key = (player_id, tid)
            games_seen[key].add(gid)
            acc[key]["min_on"] += on_rows["elapsed_s"].sum() / 60.0
            acc[key]["min_off"] += off_rows["elapsed_s"].sum() / 60.0
            if not len(shots_gt):
                continue
            mask = shot_masks[p_str]
            on_s, off_s = shots_gt[mask], shots_gt[~mask]
            acc[key]["opp_fga_on"] += on_s["fga"].sum()
            acc[key]["opp_fga_off"] += off_s["fga"].sum()
            for prefix, _, _ in ZONE_SPECS:
                is_col = f"is_{prefix}"
                acc[key][f"{prefix}_fga_on"] += on_s[is_col].sum()
                acc[key][f"{prefix}_fgm_on"] += (on_s[is_col] * on_s["fgm"]).sum()
                acc[key][f"{prefix}_fga_off"] += off_s[is_col].sum()
                acc[key][f"{prefix}_fgm_off"] += (off_s[is_col] * off_s["fgm"]).sum()

    rows = []
    for (player_id, team_id), v in acc.items():
        row = {
            "player_id": player_id, "team_id": team_id, "n_games": len(games_seen[(player_id, team_id)]),
            "min_on": round(v["min_on"], 2), "min_off": round(v["min_off"], 2),
            "opp_fga_on": int(v["opp_fga_on"]), "opp_fga_off": int(v["opp_fga_off"]),
        }
        for prefix, _, is_3pt in ZONE_SPECS:
            fga_on, fgm_on = v[f"{prefix}_fga_on"], v[f"{prefix}_fgm_on"]
            fga_off, fgm_off = v[f"{prefix}_fga_off"], v[f"{prefix}_fgm_off"]
            mult = 1.5 if is_3pt else 1.0
            row[f"{prefix}_fga_on"], row[f"{prefix}_fgm_on"] = int(fga_on), int(fgm_on)
            row[f"{prefix}_fga_off"], row[f"{prefix}_fgm_off"] = int(fga_off), int(fgm_off)
            row[f"{prefix}_share_allowed_on"] = round(_div(fga_on, v["opp_fga_on"]), 4)
            row[f"{prefix}_share_allowed_off"] = round(_div(fga_off, v["opp_fga_off"]), 4)
            row[f"{prefix}_efg_allowed_on"] = round(_div(mult * fgm_on, fga_on), 4)
            row[f"{prefix}_efg_allowed_off"] = round(_div(mult * fgm_off, fga_off), 4)
        rows.append(row)
    out = pd.DataFrame(rows)
    if not out.empty:
        out["player_id"] = out["player_id"].astype("int64")
        out["team_id"] = out["team_id"].astype("int64")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA defensive zone on/off splits")
    parser.add_argument("--season", type=str, default="2025_26", choices=list(_PBP_BY_SEASON))
    parser.add_argument("--stints", type=str, default=None)
    parser.add_argument("--pbp-dir", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    stints_path = Path(args.stints) if args.stints else _LINEUPS_DIR / f"stints_{args.season}.parquet"
    pbp_dir = Path(args.pbp_dir) if args.pbp_dir else _PBP_BY_SEASON[args.season]
    out_path = Path(args.out) if args.out else _LINEUPS_DIR / f"zone_onoff_{args.season}.parquet"

    stints_df = pd.read_parquet(stints_path)
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
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "zone", "fgm", "fga"]
    )
    shots_df = attach_lineup_to_shots(stints_df, shots_df)

    result = compute_zone_onoff(stints_df, shots_df)
    result = _attach_player_names(result, pd.read_parquet(_BOX_SRC))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    print(f"season={args.season} players={len(result)} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
