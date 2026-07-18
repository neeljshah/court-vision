"""NBA shooter-profile fg3_pct claim producer (shooter trait-profile family).

The trait-profile composer (intel_query/compose_profile.py) assembles a
multi-axis shooter profile from EXISTING VERIFIED claims (volume/difficulty/
gravity/context axes all already exist in nba_shooting_claims.jsonl +
nba_context_shooting_claims.jsonl + the canonical composite). The ONE axis
with no verified claim anywhere is raw fg3_pct itself -- this module closes
that gap with a single ranking claim:

    fg3_pct = fg3m / fg3a over the NBA official 3P%-title qualification
    pool (season fg3m >= 82) within the standard 329-qualifier population
    (2024-25, games>=20 AND fga>=200 -- same pool as every sibling claim).

FG3M_QUALIFY_MIN = 82 is an EXTERNAL domain standard (the NBA's own
statistical minimum), the same standard compose_best's shooter domain_filter
cites -- never a tuned threshold. This claim doubles as the composer's
qualified-pool membership source (its ranking's player_ids ARE the fg3m>=82
pool), so qualified-pool percentiles for every other axis derive from it.

CONTRACT: kind="ranking", entity_key="player_id", plain row-wise formula
("fg3m / fg3a") over the snapshot parquet, so claims_validator.py recomputes
it independently with zero custom machinery. NETWORK: zero.

CLI:
    python -m scripts.platformkit.intel_validation.nba_shooter_profile_claims
then validate independently:
    python -m scripts.platformkit.intel_validation.claims_validator \
        data/cache/intel_claims/nba_shooter_profile_claims.jsonl \
        --output data/cache/intel_claims/nba_shooter_profile_claims_validation.json
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

from domains.basketball_nba.quality_indices import (
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    QUALIFY_SEASON,
    aggregate_season,
    load_boxscores,
    qualifying_pool,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SNAPSHOT_PATH = _OUT_DIR / "nba_shooter_profile_fg3_snapshot.parquet"
_CLAIMS_OUT = _OUT_DIR / "nba_shooter_profile_claims.jsonl"

# NBA official 3P%-title statistical qualification minimum (82 made threes
# over a season). EXTERNAL standard -- identical to compose_best.py's shooter
# domain_filter (min=82); a test pins the two together so they cannot drift.
FG3M_QUALIFY_MIN = 82

_SNAPSHOT_COLS = ["player_id", "player_name", "games", "fg3m", "fg3a"]


def _pool_table(season: str) -> pd.DataFrame:
    """The same 329-qualifier pool (games>=20, fga>=200) every sibling
    shooting claim uses -- via the single-source-of-truth helpers."""
    return qualifying_pool(aggregate_season(load_boxscores(), season=season))


def _snapshot_path(season: str) -> Path:
    # QUALIFY_SEASON (2024-25) keeps the ORIGINAL fixed filename byte-stable
    # -- shooter_composite_v2_claims.py's 2024-25 path reads it by that exact
    # name. Any other season gets its own season-scoped file so a second
    # season's run can never clobber the first season's re-validation source.
    if season == QUALIFY_SEASON:
        return _SNAPSHOT_PATH
    return _SNAPSHOT_PATH.with_name(f"nba_shooter_profile_fg3_snapshot_{season.replace('-', '_')}.parquet")


def build_fg3_pct_qualified_claim(season: str = QUALIFY_SEASON) -> dict[str, Any]:
    pool = _pool_table(season)[_SNAPSHOT_COLS].copy()
    snapshot_path = _snapshot_path(season)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(pool, preserve_index=False), snapshot_path)

    qualifiers = pool[pool["fg3m"] >= FG3M_QUALIFY_MIN].copy()
    qualifiers["fg3_pct"] = qualifiers["fg3m"] / qualifiers["fg3a"]
    qualifiers = qualifiers.sort_values("fg3_pct", ascending=False).reset_index(drop=True)
    n_considered = int(len(pool))
    n_excluded = n_considered - int(len(qualifiers))

    ranking = [
        {
            "rank": i,
            "player_id": int(row.player_id),
            "player_name": str(row.player_name),
            "value": round(float(row.fg3_pct), 4),
            "n": int(row.games),
            "fg3m": int(row.fg3m),
            "fg3a": int(row.fg3a),
        }
        for i, row in enumerate(qualifiers.itertuples(index=False), start=1)
    ]

    rel_source = str(snapshot_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "claim_id": f"nba_shooter_profile_fg3_pct_qualified_{season}",
        "kind": "ranking",
        "question": (
            "Which NBA players qualifying for the official 3P% leaderboard "
            f"(fg3m>={FG3M_QUALIFY_MIN}) have the highest 3-point percentage ({season})?"
        ),
        "criteria": {
            "metric": "fg3_pct",
            "formula": "fg3m / fg3a",
            "window": f"season_{season}_nba",
            "window_spec": None,
            "aggregate": None,
            "min_sample": {"fg3m": FG3M_QUALIFY_MIN},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [rel_source],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": [
            f"min_sample floor fg3m>={FG3M_QUALIFY_MIN} is the NBA's OWN official 3P%-title "
            "statistical qualification minimum -- an external domain standard (the same one "
            "compose_best's shooter domain_filter cites), never a tuned threshold.",
            f"population: season {season} games>={QUALIFY_MIN_GAMES} AND fga>={QUALIFY_MIN_FGA} "
            "(the standard sibling-claim pool), then the fg3m floor on top; below-floor players "
            "are counted in n_excluded_below_floor, never silently dropped.",
            "fg3_pct is ONE axis of a shooter, never the whole shooter: it carries no volume, "
            "shot-difficulty, self-creation, or gravity signal (a high-difficulty high-volume "
            "creator can rank mid-pool here while being a far tougher cover). The shooter "
            "trait-profile composer reports those axes from their own sibling claims.",
            "DESCRIPTIVE ranking only -- no forecasting/market claim.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


# 2024-25 unchanged/byte-stable (boxscore-only, no atlas ingredient here) +
# 2025-26 additive (boxscores.parquet now covers the full season).
DEFAULT_SEASONS = (QUALIFY_SEASON, "2025-26")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit the NBA shooter-profile fg3_pct ranking claim(s)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    parser.add_argument("--season", type=str, default=None, help="single season override; default emits both DEFAULT_SEASONS")
    args = parser.parse_args(argv)

    seasons = [args.season] if args.season else list(DEFAULT_SEASONS)
    claims = [build_fg3_pct_qualified_claim(s) for s in seasons]
    out_path = write_claims(claims, Path(args.output))
    for claim in claims:
        top = claim["ranking"][0] if claim["ranking"] else None
        print(
            f"{claim['claim_id']}: n_considered={claim['n_considered']} "
            f"n_excluded_below_floor={claim['n_excluded_below_floor']} "
            f"top={top['player_name'] if top else None} value={top['value'] if top else None}"
        )
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
