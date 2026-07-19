"""NBA shooter_composite_v2 -- basketball-smart "who is the best shooter"
composite ranking claim (VOLUME + EFFICIENCY + DIFFICULTY + GRAVITY together).

WHY: efficiency-only and volume-only answers are basketball-wrong.
shooter_quality_v1 (nba_quality_claims.jsonl, TS%/eFG%/FT%-flavored pillars)
puts Kevin Durant/Zach LaVine/Norman Powell top-3 -- efficient FINISHERS, not
volume 3-point shooters. Raw efficiency alone (fg3_pct) over-ranks
low-volume catch-and-shoot rim-adjacent players; raw volume alone
(fg3a_per_game) over-ranks high-usage chuckers (LaMelo-shaped). "Best
shooter" needs all four axes together.

DECLARED COMPOSITION (frozen before running; not retuned after seeing
output -- see FROZEN_WEIGHTS below):
  qualification floor: fg3a_per_game >= 4.0 (shooting-volume floor)
  percentile (0-100, rank(pct=True)*100) within the QUALIFIED pool, per
  ingredient, then a weighted sum:
    fg3a_per_game 0.25, fg3_pct 0.25, pullup_combined_freq 0.10,
    unassisted_share_3pm 0.10, gravity_score 0.15, ft_reliability 0.15
  Any ingredient missing for a qualified player (gravity_score has thin
  coverage) -- redistribute ITS weight PRO-RATA (proportional to declared
  weight) across the ingredients that ARE present for that player. Require
  >=4/6 ingredients present, else exclude (counted honestly in
  n_excluded_below_floor).

INGREDIENT SOURCES: the task named data/cache/profiles/nba_player_profiles.
parquet as the ingredient source. A column-pruned scan (columns=["attribute"]
only) found that file is a DIFFERENT long-format player-profile dossier (61
distinct attributes: clutch/zone/spacing/rebounding/defense-allowed dims,
plus a "gravity" attribute sourced from team_system/lineups/gravity_proxy_*)
-- it does NOT carry fg3a_per_game, fg3_pct, pullup_combined_freq,
unassisted_share_3pm, gravity_score, or ft_reliability under those or any
equivalent name. This module instead reads the six ingredients from the
SAME already-VERIFIED per-metric snapshot parquets nba_shooting_claims.jsonl
/ nba_shooter_profile_claims.jsonl already cite (identical recipe, zero
re-derivation, zero numeric drift from the VERIFIED sibling claims):
  fg3a_per_game        <- nba_boxscore_agg_snapshot.parquet (sum(fg3a)/count(game_id))
  fg3_pct              <- nba_shooter_profile_fg3_snapshot.parquet (fg3m/fg3a)
  pullup_combined_freq <- nba_pullup_combined_freq_snapshot.parquet
  unassisted_share_3pm <- nba_unassisted_share_3pm_snapshot.parquet
  gravity_score        <- nba_gravity_score_snapshot.parquet
  ft_reliability        <- nba_ft_reliability_snapshot.parquet
All six are keyed to the same 329-qualifier (season 2024-25, games>=20 AND
fga>=200) population that nba_shooter_profile_fg3_snapshot.parquet itself IS.

CONTRACT: kind="ranking", entity_key="player_id". Per-row EFFECTIVE weights
differ when an ingredient is missing (pro-rata redistribution), so a single
static arithmetic formula cannot re-derive the score from raw columns alone
-- the final weighted composite is PRECOMPUTED as a column
("shooter_composite_v2") in this module's own snapshot parquet, and
criteria.formula is an IDENTITY read of that column: same
tautological-by-construction contract as soccer_team_venue_split_claims.py's
precomputed diff columns. claims_validator.py recomputes independently by
re-applying the min_sample floors and reading the column back.

DESCRIPTIVE/SCOUTING ONLY -- no forecast, no market claim. NETWORK: zero.

CLI:
    python -m scripts.platformkit.intel_validation.shooter_composite_v2_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/shooter_composite_v2_claims.jsonl \
        --output data/cache/intel_claims/shooter_composite_v2_claims_validation.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_nba.quality_claim_builders import rank_of
from domains.basketball_nba.quality_indices import QUALIFY_SEASON
from scripts.platformkit.predictive_validity.validity_ladder import ladder_caveat

REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAIMS_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT_PATH = _CLAIMS_DIR / "shooter_composite_v2_snapshot.parquet"
_CLAIMS_OUT = _CLAIMS_DIR / "shooter_composite_v2_claims.jsonl"

FG3A_PER_GAME_FLOOR = 4.0
MIN_INGREDIENTS_PRESENT = 4

# FROZEN pre-registered weights (docstring above) -- never retuned post-hoc.
FROZEN_WEIGHTS: dict[str, float] = {
    "fg3a_per_game": 0.25,
    "fg3_pct": 0.25,
    "pullup_combined_freq": 0.10,
    "unassisted_share_3pm": 0.10,
    "gravity_score": 0.15,
    "ft_reliability": 0.15,
}
assert abs(sum(FROZEN_WEIGHTS.values()) - 1.0) < 1e-9
_INGREDIENT_COLS = list(FROZEN_WEIGHTS.keys())

# ingredient -> sibling snapshot parquet it is read from (already VERIFIED
# sources; fg3a_per_game/fg3_pct assembled separately below).
_INGREDIENT_SNAPSHOTS = {
    "pullup_combined_freq": "nba_pullup_combined_freq_snapshot.parquet",
    "unassisted_share_3pm": "nba_unassisted_share_3pm_snapshot.parquet",
    "gravity_score": "nba_gravity_score_snapshot.parquet",
    "ft_reliability": "nba_ft_reliability_snapshot.parquet",
}


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT)).replace("\\", "/")


def load_raw() -> pd.DataFrame:
    """Assemble one row per player_id (the 329-qualifier pool) with the six
    RAW ingredient columns, column-pruned reads throughout (laptop RAM
    rule)."""
    pool = pd.read_parquet(
        _CLAIMS_DIR / "nba_shooter_profile_fg3_snapshot.parquet",
        columns=["player_id", "player_name", "games", "fg3m", "fg3a"],
    )
    pool["fg3_pct"] = (pool["fg3m"] / pool["fg3a"]).replace([float("inf"), float("-inf")], float("nan"))

    box = pd.read_parquet(
        _CLAIMS_DIR / "nba_boxscore_agg_snapshot.parquet", columns=["player_id", "game_id", "fg3a"],
    )
    box_agg = box.groupby("player_id").agg(fg3a_sum=("fg3a", "sum"), n_games=("game_id", "count"))
    box_agg["fg3a_per_game"] = box_agg["fg3a_sum"] / box_agg["n_games"]

    df = pool.merge(box_agg[["fg3a_per_game"]], on="player_id", how="left")
    for ingredient, fname in _INGREDIENT_SNAPSHOTS.items():
        side = pd.read_parquet(_CLAIMS_DIR / fname, columns=["player_id", ingredient])
        df = df.merge(side, on="player_id", how="left")
    return df


def compute_snapshot(raw: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: qualification floor + within-pool percentiles +
    pro-rata weight redistribution + the final identity-read composite
    column. Takes/returns a plain DataFrame -- no file I/O, so tests drive
    this directly with synthetic frames."""
    df = raw.copy()
    df["n_present"] = df[_INGREDIENT_COLS].notna().sum(axis=1)
    qualified_mask = df["fg3a_per_game"] >= FG3A_PER_GAME_FLOOR

    for col in _INGREDIENT_COLS:
        pctl = pd.Series(float("nan"), index=df.index, dtype="float64")
        pctl.loc[qualified_mask] = df.loc[qualified_mask, col].rank(pct=True) * 100.0
        df[f"pctl_{col}"] = pctl

    def _composite(row: pd.Series) -> float:
        if row["fg3a_per_game"] < FG3A_PER_GAME_FLOOR or row["n_present"] < MIN_INGREDIENTS_PRESENT:
            return float("nan")
        present = [c for c in _INGREDIENT_COLS if pd.notna(row[c])]
        present_weight = sum(FROZEN_WEIGHTS[c] for c in present)
        score = sum(float(row[f"pctl_{c}"]) * (FROZEN_WEIGHTS[c] / present_weight) for c in present)
        return round(score, 4)

    df["shooter_composite_v2"] = df.apply(_composite, axis=1)
    return df


def _write_snapshot(df: pd.DataFrame, path: Path = _SNAPSHOT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def build_claim(snap: pd.DataFrame, season: str = QUALIFY_SEASON, snapshot_path: Path = _SNAPSHOT_PATH) -> dict[str, Any]:
    n_considered = len(snap)
    survivors_mask = (snap["fg3a_per_game"] >= FG3A_PER_GAME_FLOOR) & (snap["n_present"] >= MIN_INGREDIENTS_PRESENT)
    survivors = snap[survivors_mask].sort_values("shooter_composite_v2", ascending=False).reset_index(drop=True)
    n_excluded = n_considered - len(survivors)

    ranking = [
        {
            "rank": i,
            "player_id": int(r.player_id),
            "player_name": str(r.player_name),
            "value": round(float(r.shooter_composite_v2), 4),
            "n": int(r.games),
            "n_present": int(r.n_present),
        }
        for i, r in enumerate(survivors.itertuples(index=False), start=1)
    ]
    curry_rank = rank_of(snap.rename(columns={"shooter_composite_v2": "_rk"}), "_rk", "Stephen Curry")

    season_id = season.replace("-", "_")
    return {
        "claim_id": f"shooter_composite_v2_full_season_{season_id}",
        "kind": "ranking",
        "question": "Who is the best NBA shooter (multi-axis composite: volume + efficiency + difficulty + gravity)?",
        "criteria": {
            "metric": "shooter_composite_v2",
            "formula": "shooter_composite_v2",
            "weights": dict(FROZEN_WEIGHTS),
            "min_sample": {"fg3a_per_game": FG3A_PER_GAME_FLOOR, "n_present": MIN_INGREDIENTS_PRESENT},
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
            "weights_frozen_note: composition DECLARED and FROZEN before this claim was ever run "
            "(fg3a_per_game 0.25, fg3_pct 0.25, pullup_combined_freq 0.10, unassisted_share_3pm 0.10, "
            "gravity_score 0.15, ft_reliability 0.15) -- never retuned after seeing the output ranking.",
            f"weights (verbatim): {json.dumps(FROZEN_WEIGHTS)}",
            f"qualification floor: fg3a_per_game >= {FG3A_PER_GAME_FLOOR} (shooting-volume floor) over the "
            "329-qualifier (season 2024-25 games>=20 AND fga>=200) population every sibling shooting claim uses.",
            "each ingredient is a PERCENTILE (rank(pct=True)*100) within the qualified pool, then combined by "
            "the weighted sum above -- so no single raw-unit ingredient (e.g. a 0-1 rate vs a per-game count) "
            "dominates the score by scale.",
            "MISSING-INGREDIENT REDISTRIBUTION: gravity_score (and any other ingredient) has thinner coverage "
            "than fg3a_per_game/fg3_pct; when missing for a qualified player, its declared weight is "
            "redistributed PRO-RATA (proportional to declared weight) across that player's PRESENT ingredients "
            "so weights still sum to 1.0 for every ranked player. Players with fewer than "
            f"{MIN_INGREDIENTS_PRESENT}/6 ingredients present are excluded, counted in n_excluded_below_floor.",
            "SOURCE NOTE: data/cache/profiles/nba_player_profiles.parquet (named as the source in the build "
            "task) does not carry these six ingredient attributes under these or equivalent names -- confirmed "
            "by a column-pruned scan of its 'attribute' column (61 distinct values, none matching). This claim "
            "instead reads each ingredient from the same per-metric snapshot parquet its VERIFIED sibling claim "
            "in nba_shooting_claims.jsonl / nba_shooter_profile_claims.jsonl already uses.",
            "RECOMPUTABILITY: criteria.formula is an IDENTITY read of the precomputed shooter_composite_v2 "
            "column in this claim's own snapshot parquet (per-row effective weights vary with redistribution, "
            "so a single static arithmetic formula cannot re-derive the score from raw columns alone) -- same "
            "pattern as soccer_team_venue_split_claims.py's precomputed diff columns.",
            "DESCRIPTIVE/SCOUTING ranking only -- no forecast, no market claim, no dollar edge.",
            ladder_caveat("shooter_composite_v2"),
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit the shooter_composite_v2 ranking claim")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default=QUALIFY_SEASON)
    args = parser.parse_args(argv)

    snap = compute_snapshot(load_raw())
    _write_snapshot(snap)
    claim = build_claim(snap, args.season)
    out_path = write_claims([claim], Path(args.output))

    print(f"{claim['claim_id']}: n_considered={claim['n_considered']} n_excluded_below_floor={claim['n_excluded_below_floor']}")
    for r in claim["ranking"][:10]:
        print(f"  #{r['rank']} {r['player_name']} value={r['value']}")
    print(f"stephen_curry_rank={claim['face_validity_diagnostic']['stephen_curry_rank']}")
    print(f"wrote snapshot -> {_SNAPSHOT_PATH}")
    print(f"wrote 1 claim -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
