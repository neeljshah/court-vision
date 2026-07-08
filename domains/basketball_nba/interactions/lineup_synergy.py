"""Lineup chemistry residual: for every distinct 5-man lineup, its own actual
net rating per48 (from the stint table) minus the EXPECTED net rating you'd
get by just averaging its 5 members' individual on/off net ratings (from
on_off.py's own on_off_2025_26.parquet). The residual is what the 5 players
do TOGETHER that their individual on-court numbers don't already explain --
the chemistry term (positive = the whole beats the sum of its individually-
rated parts; negative = it doesn't).

Weighting note: "minutes-weighted sum of members' individual on-off net" is
an unweighted MEAN of the 5 members here by construction -- every member of
one specific lineup shares the exact same on-court minutes for that lineup
(they're on the floor together), so a minutes weight would be identical (1)
for all 5 members and cancel out. It only becomes a genuine weighted-average
question if a member's OWN net_rating_on_per48 (the thing being averaged)
came from a mix of different lineups -- which it does, but that mixing
already happened once inside on_off.py's per-player aggregate; re-weighting
it again here would double-count.

This module emits the FULL, unfiltered population (every lineup with any
clean minutes at all, `qualifies` computed but never used to drop rows) --
same precedent as on_off.py's own output and nba_gravity_proxy_claims.py's
comment on why: the claims producer must be able to reapply the floor on
raw columns itself and get a real n_excluded_below_floor, not trust a
pre-filtered file.

Floors (fail-closed): lineup needs >=100 clean minutes; EVERY one of the 5
members needs its own min_on>=100 (on_off.py's per-player floor for this
module) and a non-null net_rating_on_per48, else expected/residual are null
and qualifies=False (counted, not dropped).

OUTPUT: data/cache/team_system/interactions/lineup_synergy_2025_26.parquet
  team_id, lineup_key, n_games, min, net_per48, expected_net_per48,
  synergy_residual, n_members_qualified, qualifies, min_member_id (smallest
  raw id in lineup_key -- a claims-layer floor to drop lineups containing an
  unresolved/negative placeholder id).

Claims: scripts/platformkit/intel_validation/nba_lineup_synergy_claims.py
(descriptive ranking on synergy_residual, floor reapplied independently).

NETWORK: zero. CLI: python -m domains.basketball_nba.interactions.lineup_synergy
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_ON_OFF_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_2025_26.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "interactions" / "lineup_synergy_2025_26.parquet"

MIN_LINEUP_MINUTES = 100.0
MIN_MEMBER_MINUTES = 100.0


def build_lineup_actuals(stints_df: pd.DataFrame) -> pd.DataFrame:
    clean = stints_df[stints_df["n_on_court"] == 5]
    grp = clean.groupby(["team_id", "lineup_key"]).agg(
        n_games=("game_id", "nunique"), elapsed_s=("elapsed_s", "sum"),
        pts_for=("pts_for", "sum"), pts_against=("pts_against", "sum"),
    ).reset_index()
    grp["min"] = grp["elapsed_s"] / 60.0
    grp["net_per48"] = (grp["pts_for"] - grp["pts_against"]) / grp["min"] * 48.0
    return grp[["team_id", "lineup_key", "n_games", "min", "net_per48"]]


def attach_expected(lineup_df: pd.DataFrame, on_off_df: pd.DataFrame) -> pd.DataFrame:
    member_net = on_off_df.set_index(["player_id", "team_id"])["net_rating_on_per48"]
    member_min = on_off_df.set_index(["player_id", "team_id"])["min_on"]

    expected, n_qualified, residual = [], [], []
    for lineup_key, team_id in zip(lineup_df["lineup_key"], lineup_df["team_id"]):
        members = [int(p) for p in lineup_key.split(",")]
        nets = []
        n_ok = 0
        for m in members:
            key = (m, team_id)
            net = member_net.get(key)
            mins = member_min.get(key)
            if net is not None and net == net and mins is not None and mins >= MIN_MEMBER_MINUTES:
                nets.append(net)
                n_ok += 1
        n_qualified.append(n_ok)
        expected.append(sum(nets) / len(nets) if n_ok == 5 else None)

    lineup_df = lineup_df.copy()
    lineup_df["expected_net_per48"] = expected
    lineup_df["n_members_qualified"] = n_qualified
    lineup_df["synergy_residual"] = [
        round(a - e, 4) if e is not None else None
        for a, e in zip(lineup_df["net_per48"], lineup_df["expected_net_per48"])
    ]
    lineup_df["expected_net_per48"] = lineup_df["expected_net_per48"].apply(
        lambda e: round(e, 4) if e is not None else None
    )
    lineup_df["net_per48"] = lineup_df["net_per48"].round(4)
    lineup_df["min"] = lineup_df["min"].round(2)
    lineup_df["qualifies"] = (lineup_df["min"] >= MIN_LINEUP_MINUTES) & lineup_df["synergy_residual"].notna()
    # min_member_id: smallest raw id in the 5-man lineup_key -- some seasons'
    # stint reconstruction fills an unresolved roster slot with a negative
    # placeholder id (pbp_lineups.py's build_team_stints); >=0 here is a
    # ready-made claims-layer floor to exclude those unresolved lineups.
    lineup_df["min_member_id"] = lineup_df["lineup_key"].apply(lambda s: min(int(p) for p in s.split(",")))
    return lineup_df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA lineup synergy-residual table")
    parser.add_argument("--stints", type=str, default=str(_STINTS_PATH))
    parser.add_argument("--on-off", type=str, default=str(_ON_OFF_PATH))
    parser.add_argument("--out", type=str, default=str(_OUT_PATH))
    args = parser.parse_args(argv)

    stints_df = pd.read_parquet(args.stints)
    on_off_df = pd.read_parquet(args.on_off)

    lineup_df = build_lineup_actuals(stints_df)
    result = attach_expected(lineup_df, on_off_df)
    cols = [
        "team_id", "lineup_key", "n_games", "min", "net_per48",
        "expected_net_per48", "synergy_residual", "n_members_qualified", "qualifies", "min_member_id",
    ]
    result = result[cols].sort_values("synergy_residual", ascending=False, na_position="last").reset_index(drop=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    n_qualifies = int(result["qualifies"].sum())
    print(f"lineups_total={len(result)} qualifies={n_qualifies} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
