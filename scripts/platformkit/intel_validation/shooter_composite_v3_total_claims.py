"""shooter_composite_v3_total -- the TOTAL-shooter season ranking: the
boxscore trio (volume/accuracy/FT touch) PLUS pressure, defensive attention,
and shot-creation, every ingredient recomputable for 2025-26 from OUR OWN
event/lineup stores (none of the blocked 2024-25 atlas snapshots):

  fg3a_per_game            boxscore   3PA volume
  fg3_pct                  boxscore   3P accuracy
  ft_pct                   boxscore   FT touch
  clutch_efg               profiles   eFG under clutch pressure (own events)
  gravity                  profiles   lineup-derived defensive-attention proxy
  self_created_3_share     profiles   1 - assisted share on above-break 3s
                                      (pull-up/difficulty proxy)

Each ingredient -> percentile (rank pct*100) within the SAME qualified pool
as shooter_composite_v2_asof_approx (games>=20 AND fga>=200), equal-weight
mean over whatever is present (skipna), requires >=4/6 present.

STATUS: DESCRIPTIVE season-retrospective. The three profile ingredients are
season-window aggregates with NO as-of variant, so a leak-free walk-forward
test cannot be run for them (same season-aggregate ceiling declared for
atlas gravity in predictive_validity/nba_adapters.py). For "who WAS the
best total shooter of a finished season" that is the correct, sufficient
grade; only the leaner v2_asof_approx carries the PREDICTIVE_VERIFIED
forward receipt. Never conflate the two.

CLI: python -m scripts.platformkit.intel_validation.shooter_composite_v3_total_claims
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_nba.quality_claim_builders import rank_of
from domains.basketball_nba.quality_indices import (
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    aggregate_season,
    load_boxscores,
    qualifying_pool,
)
from scripts.platformkit.intel_validation.shooter_composite_v2_claims import (
    REPO_ROOT,
    _CLAIMS_DIR,
    _rel,
)

_SNAPSHOT_PATH = _CLAIMS_DIR / "shooter_composite_v3_total_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "shooter_composite_v3_total_claims.jsonl"
_PROFILES_PATH = REPO_ROOT / "data" / "cache" / "profiles" / "nba_player_profiles.parquet"

_BOX_COLS = ["fg3a_per_game", "fg3_pct", "ft_pct"]
_PROFILE_ATTRS = {"clutch_efg": "clutch_efg",
                   "gravity": "gravity",
                   "zone_assisted_share_above_break_3": "assisted_3_share"}
_INGREDIENT_COLS = _BOX_COLS + ["clutch_efg", "gravity", "self_created_3_share"]
MIN_INGREDIENTS_PRESENT = 4  # >=4/6, same coverage bar as the full v2 index

SEASON_AGGREGATE_CAVEAT = (
    "DESCRIPTIVE season-retrospective ONLY: clutch_efg/gravity/self_created_3_share are "
    "season-window profile aggregates with no as-of variant, so no leak-free walk-forward "
    "receipt can exist for this index (season-aggregate ceiling, same as atlas gravity in "
    "predictive_validity/nba_adapters.py). Forward-skill claims belong exclusively to "
    "shooter_composite_v2_asof_approx (PREDICTIVE_VERIFIED). No market/edge claim."
)


def _profile_window(season: str) -> str:
    return "season_" + season.replace("-", "_")


def load_profile_ingredients(season: str, path: Path = _PROFILES_PATH) -> pd.DataFrame:
    """(player_id, clutch_efg, gravity, assisted_3_share) for the season window."""
    df = pd.read_parquet(path, columns=["entity_id", "attribute", "window", "raw_value"])
    df = df[(df["window"] == _profile_window(season))
            & (df["attribute"].isin(_PROFILE_ATTRS))]
    wide = df.pivot_table(index="entity_id", columns="attribute",
                           values="raw_value", aggfunc="first")
    wide = wide.rename(columns=_PROFILE_ATTRS).reset_index()
    return wide.rename(columns={"entity_id": "player_id"})


def load_raw(season: str) -> pd.DataFrame:
    box = load_boxscores()
    pool = qualifying_pool(aggregate_season(box, season=season),
                            min_games=QUALIFY_MIN_GAMES, min_fga=QUALIFY_MIN_FGA)
    out = pool[["player_id", "player_name", "games"]].copy()
    out["fg3a_per_game"] = pool["fg3a_pg"]
    out["fg3_pct"] = (pool["fg3m"] / pool["fg3a"]).replace(
        [float("inf"), float("-inf")], float("nan"))
    out["ft_pct"] = pool["ft_pct"]
    prof = load_profile_ingredients(season)
    out = out.merge(prof, on="player_id", how="left")
    # left-merge floats player_id (profiles side is float64) -- recast so the
    # snapshot the validator recomputes from carries the same int ids claimed.
    out["player_id"] = out["player_id"].astype("int64")
    out["self_created_3_share"] = 1.0 - out.get("assisted_3_share", pd.Series(dtype=float))
    return out


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: percentile-per-ingredient + equal-weight skipna mean."""
    df = raw.copy()
    for col in _INGREDIENT_COLS:
        if col not in df.columns:
            df[col] = float("nan")
    df["n_present"] = df[_INGREDIENT_COLS].notna().sum(axis=1)
    for col in _INGREDIENT_COLS:
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    pctl_cols = [f"pctl_{c}" for c in _INGREDIENT_COLS]
    df["shooter_composite_v3_total"] = df[pctl_cols].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_INGREDIENTS_PRESENT,
           "shooter_composite_v3_total"] = float("nan")
    return df


def _write_snapshot(df: pd.DataFrame, path: Path = _SNAPSHOT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def build_claim(snap: pd.DataFrame, season: str,
                snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors = snap[snap["n_present"] >= MIN_INGREDIENTS_PRESENT].sort_values(
        "shooter_composite_v3_total", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(survivors)
    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.shooter_composite_v3_total), 4),
         "n": int(r.games), "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    curry_rank = rank_of(
        snap.rename(columns={"shooter_composite_v3_total": "_rk"}), "_rk", "Stephen Curry")
    season_id = season.replace("-", "_")
    return {
        "claim_id": f"shooter_composite_v3_total_full_season_{season_id}",
        "kind": "ranking",
        "question": "Who was the best TOTAL shooter (volume + accuracy + FT touch "
                     "+ clutch pressure + gravity + self-creation)?",
        "criteria": {
            "metric": "shooter_composite_v3_total",
            "formula": "shooter_composite_v3_total",
            "min_sample": {"n_present": MIN_INGREDIENTS_PRESENT},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
            "window": season,
        },
        "ranking": ranking,
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": curry_rank,
            "n_qualifying": n_considered,
        },
        # snapshot ONLY: the validator recomputes the ranking from source_files;
        # listing the profiles parquet too made it join/float ids (profiles
        # provenance is declared in the caveat + module docstring instead).
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [SEASON_AGGREGATE_CAVEAT],
    }


def write_claims(claim: dict[str, Any], path: Path = _CLAIMS_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(claim, ensure_ascii=True) + "\n")
    return path


def main(season: str = "2025-26") -> dict[str, Any]:
    snap = compute_snapshot(load_raw(season))
    snapshot_path = _write_snapshot(snap)
    claim = build_claim(snap, season, snapshot_path)
    out = write_claims(claim)
    print(f"shooter_composite_v3_total: n_considered={claim['n_considered']} "
          f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
          f"top={claim['ranking'][0]['player_name'] if claim['ranking'] else 'NONE'} -> {out}")
    return claim


if __name__ == "__main__":
    main()
