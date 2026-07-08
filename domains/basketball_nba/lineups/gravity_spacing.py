"""Two descriptive lineup-level metrics built on top of the stint table
(pbp_lineups.py) and on/off splits (on_off.py):

  gravity_proxy   -- per (player_id, team_id): teammate_efg_on minus
    teammate_efg_off (both already computed by on_off.py). A positive value
    means teammates shoot better with this player on the floor -- a
    descriptive "gravity" proxy, not a causal claim. Floors: >=300 ON
    minutes AND >=200 teammate FGA on EACH side (on_off.py's own columns),
    so a small-sample split never ranks ahead of a real one.

  lineup_spacing  -- per (team_id, lineup_key): mean pairwise Euclidean
    distance (scipy.spatial.distance.pdist) between every shot-attempt
    (x, y) location taken while that exact 5-man lineup was on the floor,
    across every stint/game it recurred in. A higher mean distance is a
    more spread-out shot diet (proxy for floor spacing), a lower one a more
    clustered one. Floor: >=20 attributed shots for the lineup.

Both outputs are DESCRIPTIVE rankings only -- no forecasting/market claim.

OUTPUT:
  data/cache/team_system/lineups/gravity_proxy_2025_26.parquet
  data/cache/team_system/lineups/lineup_spacing_2025_26.parquet

NETWORK: zero. CLI: python -m domains.basketball_nba.lineups.gravity_spacing
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.spatial.distance import pdist

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.pbp_lineups import _BOX_SRC, _PBP_DIR, _elapsed_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_STINTS_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_ON_OFF_PATH = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "on_off_2025_26.parquet"
_GRAVITY_OUT = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "gravity_proxy_2025_26.parquet"
_SPACING_OUT = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "lineup_spacing_2025_26.parquet"

MIN_ON_MINUTES = 300.0
MIN_TEAMMATE_FGA = 200


def build_gravity(on_off_df: pd.DataFrame) -> pd.DataFrame:
    df = on_off_df.copy()
    qualifies = (
        (df["min_on"] >= MIN_ON_MINUTES)
        & (df["teammate_fga_on"] >= MIN_TEAMMATE_FGA)
        & (df["teammate_fga_off"] >= MIN_TEAMMATE_FGA)
        & df["teammate_efg_on"].notna()
        & df["teammate_efg_off"].notna()
    )
    out = df[qualifies].copy()
    out["gravity_proxy"] = (out["teammate_efg_on"] - out["teammate_efg_off"]).round(4)
    cols = ["player_id", "team_id", "player_name", "n_games", "min_on", "teammate_efg_on", "teammate_efg_off", "gravity_proxy"]
    return out[cols].sort_values("gravity_proxy", ascending=False).reset_index(drop=True)


def load_shot_events_xy(game_json: dict) -> pd.DataFrame:
    game_id = game_json["game"]["gameId"]
    rows = []
    for a in game_json["game"]["actions"]:
        if a.get("actionType") in ("2pt", "3pt") and a.get("teamId") and a.get("personId") and a.get("x") is not None:
            rows.append({
                "game_id": game_id, "team_id": a["teamId"], "period": a["period"],
                "elapsed_s": _elapsed_s(a["period"], a["clock"]), "person_id": a["personId"],
                "x": float(a["x"]), "y": float(a["y"]),
            })
    return pd.DataFrame(rows)


def build_spacing(stints_df: pd.DataFrame, shots_xy_df: pd.DataFrame, min_shots: int = 2) -> pd.DataFrame:
    """FULL POPULATION per lineup (every lineup with >=min_shots attributed
    shots, min_shots=2 is just pdist's own minimum, not a claims floor) --
    the claims producer (nba_lineup_spacing_claims.py) applies its own
    n_shots>=20 floor declaratively at claim-build time, same precedent as
    tennis_h2h_claims.py's unfiltered per-pair source parquet."""
    clean_shots = shots_xy_df[shots_xy_df["n_on_court"] == 5]
    rows = []
    for (team_id, lineup_key), grp in clean_shots.groupby(["team_id", "lineup_key"]):
        if len(grp) < min_shots:
            continue
        pts = grp[["x", "y"]].to_numpy()
        mean_dist = float(pdist(pts).mean())
        rows.append({
            "team_id": team_id, "lineup_key": lineup_key, "n_shots": len(grp),
            "spacing_mean_dist": round(mean_dist, 4),
        })
    return pd.DataFrame(rows).sort_values("spacing_mean_dist", ascending=False).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build NBA gravity-proxy + lineup-spacing claims inputs")
    parser.add_argument("--stints", type=str, default=str(_STINTS_PATH))
    parser.add_argument("--on-off", type=str, default=str(_ON_OFF_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    on_off_df = pd.read_parquet(args.on_off)
    gravity_df = build_gravity(on_off_df)
    _GRAVITY_OUT.parent.mkdir(parents=True, exist_ok=True)
    gravity_df.to_parquet(_GRAVITY_OUT, index=False)
    print(f"gravity_proxy rows={len(gravity_df)} -> {_GRAVITY_OUT}")

    stints_df = pd.read_parquet(args.stints)
    game_ids = stints_df["game_id"].unique()
    if args.limit:
        game_ids = game_ids[: args.limit]
        stints_df = stints_df[stints_df["game_id"].isin(game_ids)]

    shot_frames = []
    for gid in game_ids:
        fp = _PBP_DIR / f"{gid}.json"
        if fp.exists():
            shot_frames.append(load_shot_events_xy(json.loads(fp.read_text(encoding="utf-8"))))
    shots_xy_df = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "x", "y"]
    )
    shots_xy_df = attach_lineup_to_shots(stints_df, shots_xy_df)
    spacing_df = build_spacing(stints_df, shots_xy_df)
    spacing_df.to_parquet(_SPACING_OUT, index=False)
    print(f"lineup_spacing rows={len(spacing_df)} -> {_SPACING_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
