"""STEP 1 materialize -- coarse player position group atlas for the
positional-weight gate (LANE positional-weights).

Source: data/cache/team_system/player_roles.parquet (pid, posgroup in
{GUARD, WING, BIG}, 507 recent players -- NOT the guard/forward/center
vocabulary named in the brief; the actual on-disk enum is GUARD/WING/BIG.
Mapped 1:1 onto the brief's guard/forward/center naming (WING -> forward,
BIG -> center) since that is the closest semantic correspondence and no
finer split exists on disk. No finer split (no PG/SG/SF/PF/C).

Writes data/domains/basketball_nba/atlas_player_position.parquet:
    player_id, posgroup (guard/forward/center), as_of, corpus_id

Coverage floor: this module ALSO reports (does not gate) how much of the
329-qualifier 2024-25 population (per quality_indices qualifying_pool) is
covered by a posgroup label -- printed for the gate script to act on. If
coverage < 85%, the caller (positional_weight_gate.py) must stop with
INSUFFICIENT_COVERAGE rather than impute silently.

No LLM recall: every row here is read from an on-disk parquet file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROLES_PATH = "data/cache/team_system/player_roles.parquet"
OUT_PATH = "data/domains/basketball_nba/atlas_player_position.parquet"
CORPUS_ID = "nba_player_roles_v1"

# on-disk enum -> brief's guard/forward/center vocabulary (closest mapping;
# no finer split available)
POSGROUP_MAP = {"GUARD": "guard", "WING": "forward", "BIG": "center"}


def load_position_atlas(path: str = ROLES_PATH) -> pd.DataFrame:
    roles = pd.read_parquet(path)
    needed = ["pid", "posgroup"]
    missing = [c for c in needed if c not in roles.columns]
    if missing:
        raise ValueError(f"player_roles.parquet missing columns: {missing}")
    out = roles[needed].rename(columns={"pid": "player_id"}).copy()
    out["posgroup"] = out["posgroup"].map(POSGROUP_MAP)
    out = out.dropna(subset=["posgroup"])
    out = out.drop_duplicates(subset=["player_id"], keep="first")
    return out.reset_index(drop=True)


def coverage_report(position_atlas: pd.DataFrame, qualifier_ids: pd.Series) -> dict:
    qualifier_ids = pd.Series(qualifier_ids).unique()
    covered_mask = pd.Series(qualifier_ids).isin(position_atlas["player_id"])
    n_qual = len(qualifier_ids)
    n_covered = int(covered_mask.sum())
    return {
        "n_qualifiers": int(n_qual),
        "n_covered": n_covered,
        "coverage_pct": (n_covered / n_qual) if n_qual else 0.0,
    }


def materialize(path: str = OUT_PATH) -> pd.DataFrame:
    atlas = load_position_atlas()
    atlas["as_of"] = datetime.now(timezone.utc).isoformat()
    atlas["corpus_id"] = CORPUS_ID
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    atlas.to_parquet(p, index=False)
    return atlas


if __name__ == "__main__":
    from domains.basketball_nba.quality_indices import (
        aggregate_season,
        load_boxscores,
        qualifying_pool,
    )

    atlas = materialize()
    print(f"materialized {len(atlas)} players -> {OUT_PATH}")
    print(atlas["posgroup"].value_counts().to_dict())

    box = load_boxscores()
    agg = aggregate_season(box)
    qual = qualifying_pool(agg)
    rep = coverage_report(atlas, qual["player_id"])
    print(f"329-qualifier coverage: {rep['n_covered']}/{rep['n_qualifiers']} "
          f"= {rep['coverage_pct']:.4f}")
    if rep["coverage_pct"] < 0.85:
        print("VERDICT: INSUFFICIENT_COVERAGE -- stopping, no silent imputation")
    else:
        print("coverage clears 0.85 floor -- proceeding to gate")
