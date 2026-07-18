"""2025-26 sibling of shooter_composite_v2_claims.py -- the BOXSCORE-ONLY
'_asof_approx' variant, not the full 6-ingredient index.

WHY a different variant, not the same recipe re-run on 2025-26: 4 of the 6
FROZEN_WEIGHTS ingredients (pullup_combined_freq, unassisted_share_3pm,
gravity_score, ft_reliability) are read from atlas_player_*.parquet
snapshots, which are single-season 2024-25-era snapshots with NO season
column and cannot be re-harvested (NBA API blocked) -- unavailable for
2025-26. Nulling them for every 2025-26 player collapses MIN_INGREDIENTS_
PRESENT (needs >=4/6) to 0 qualifiers, an empty ranking (never emitted --
see domains/mlb/profiles/claims.py's skip idiom). Instead this module emits
the SAME formula scripts/platformkit/predictive_validity/nba_adapters.py's
shooter_composite_v2_test already carries a PREDICTIVE_VERIFIED-lane receipt
for: an equal-weight percentile mean of fg3a_per_game, fg3_pct, ft_pct
(strictly boxscore-derived, no atlas ingredient at all).

INGREDIENTS (boxscore-only, season aggregate over the same 329-qualifier-
style pool: games>=QUALIFY_MIN_GAMES AND fga>=QUALIFY_MIN_FGA):
  fg3a_per_game = sum(fg3a)/games
  fg3_pct       = sum(fg3m)/sum(fg3a)
  ft_pct        = sum(ftm)/sum(fta)
Each is a percentile (rank(pct=True)*100) within the qualified pool, then
combined by an EQUAL-WEIGHT mean (pandas .mean(skipna=True) -- a player
missing one ingredient is scored on the mean of whichever ARE present,
same redistribution effect nba_adapters.py's _shooter_composite_v2_asof_
metric relies on). Requires >=2/3 ingredients present, else excluded.

CONTRACT: kind="ranking", entity_key="player_id", tautological identity
formula over this module's own snapshot parquet -- same pattern as
shooter_composite_v2_claims.py's full-index claim.

DESCRIPTIVE/SCOUTING ONLY -- no forecast, no market claim. NETWORK: zero.

CLI: python -m scripts.platformkit.intel_validation.shooter_composite_v2_asof_approx_claims
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
    write_claims as write_claims_to,
)

_SNAPSHOT_PATH = _CLAIMS_DIR / "shooter_composite_v2_asof_approx_snapshot.parquet"
# own store (2026-07-19 review fix): this module and shooter_composite_v2_
# claims.py both used to write shooter_composite_v2_claims.jsonl, silently
# clobbering each other's claims (last-writer-wins -- same anti-pattern
# fixed for player_intel_shooting_claims.py in 8ec45e5c). This producer now
# writes ONLY its own 2025-26 asof_approx claim to its own store; the full-
# index claim stays shooter_composite_v2_claims.py's exclusive output.
_CLAIMS_OUT = _CLAIMS_DIR / "shooter_composite_v2_asof_approx_claims.jsonl"

_INGREDIENT_COLS = ["fg3a_per_game", "fg3_pct", "ft_pct"]
MIN_INGREDIENTS_PRESENT = 2  # >=2/3, same ~2/3 coverage bar as the full index's 4/6

ATLAS_GAP_CAVEAT = (
    "ATLAS-UNAVAILABLE-2025-26: shooter_composite_v2's other 4 ingredients "
    "(pullup_combined_freq, unassisted_share_3pm, gravity_score, ft_reliability) need "
    "atlas_player_*.parquet, single-season 2024-25-era snapshots with no season column, "
    "unavailable for 2025-26 (NBA API blocked, cannot re-harvest) -- never silently reused. "
    "This claim instead reuses the boxscore-only 'shooter_composite_v2_asof_approx' formula "
    "scripts/platformkit/predictive_validity/nba_adapters.py's shooter_composite_v2_test "
    "already carries a PREDICTIVE_VERIFIED-lane receipt for (equal-weight percentile mean of "
    "fg3a_per_game/fg3_pct/ft_pct), not the full 6-ingredient index."
)


def load_raw(season: str) -> pd.DataFrame:
    df = load_boxscores()
    pool = qualifying_pool(aggregate_season(df, season=season),
                            min_games=QUALIFY_MIN_GAMES, min_fga=QUALIFY_MIN_FGA)
    out = pool[["player_id", "player_name", "games"]].copy()
    out["fg3a_per_game"] = pool["fg3a_pg"]
    out["fg3_pct"] = (pool["fg3m"] / pool["fg3a"]).replace([float("inf"), float("-inf")], float("nan"))
    out["ft_pct"] = pool["ft_pct"]
    return out


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    """Pure transform, no file I/O -- percentile-per-ingredient + an
    equal-weight mean (skipna), matching nba_adapters.py's asof metric."""
    df = raw.copy()
    df["n_present"] = df[_INGREDIENT_COLS].notna().sum(axis=1)
    for col in _INGREDIENT_COLS:
        df[f"pctl_{col}"] = df[col].rank(pct=True) * 100.0
    pctl_cols = [f"pctl_{c}" for c in _INGREDIENT_COLS]
    df["shooter_composite_v2_asof_approx"] = df[pctl_cols].mean(axis=1, skipna=True).round(4)
    df.loc[df["n_present"] < MIN_INGREDIENTS_PRESENT, "shooter_composite_v2_asof_approx"] = float("nan")
    return df


def _write_snapshot(df: pd.DataFrame, path: Path = _SNAPSHOT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def build_claim(snap: pd.DataFrame, season: str, snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors_mask = snap["n_present"] >= MIN_INGREDIENTS_PRESENT
    survivors = snap[survivors_mask].sort_values(
        "shooter_composite_v2_asof_approx", ascending=False
    ).reset_index(drop=True)
    n_excluded = n_considered - len(survivors)

    ranking = [
        {"rank": i, "player_id": int(r.player_id), "player_name": str(r.player_name),
         "value": round(float(r.shooter_composite_v2_asof_approx), 4),
         "n": int(r.games), "n_present": int(r.n_present)}
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    curry_rank = rank_of(
        snap.rename(columns={"shooter_composite_v2_asof_approx": "_rk"}), "_rk", "Stephen Curry",
    )

    season_id = season.replace("-", "_")
    return {
        "claim_id": f"shooter_composite_v2_asof_approx_full_season_{season_id}",
        "kind": "ranking",
        "question": "Who is the best NBA shooter (boxscore-only approximation: "
                     "volume + efficiency + FT reliability)?",
        "criteria": {
            "metric": "shooter_composite_v2_asof_approx",
            "formula": "shooter_composite_v2_asof_approx",
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
        "source_files": [_rel(snapshot_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            ATLAS_GAP_CAVEAT,
            "each ingredient is a PERCENTILE (rank(pct=True)*100) within the qualified "
            f"({QUALIFY_MIN_GAMES}+ games, {QUALIFY_MIN_FGA}+ fga) pool, combined by an EQUAL-"
            "WEIGHT mean(skipna=True) -- a player missing one ingredient is scored on the mean "
            f"of whichever ARE present. Players below {MIN_INGREDIENTS_PRESENT}/3 present are "
            "excluded, counted in n_excluded_below_floor.",
            "RECOMPUTABILITY: criteria.formula is an IDENTITY read of the precomputed "
            "shooter_composite_v2_asof_approx column in this claim's own snapshot parquet.",
            "DESCRIPTIVE/SCOUTING ranking only -- no forecast, no market claim, no dollar edge.",
        ],
    }


def build_season_claim(season: str) -> dict[str, Any]:
    snap = compute_snapshot(load_raw(season))
    _write_snapshot(snap)
    return build_claim(snap, season)


def main() -> int:
    claims = [build_season_claim("2025-26")]
    out_path = write_claims_to(claims, _CLAIMS_OUT)

    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']}")
        for r in c["ranking"][:5]:
            print(f"  #{r['rank']} {r['player_name']} value={r['value']}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
