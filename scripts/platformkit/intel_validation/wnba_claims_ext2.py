"""WNBA DESCRIPTIVE ranking claims producer, PART 3 (lane wnba-atlas).

Second sibling module -- wnba_claims.py (3 claims) + wnba_claims_ext.py (3
claims) + this module (2 claims) split three ways to keep each file <=300
LOC (per human-gated-paths rail). Reuses wnba_claims's _rel()/_full_
population_ranking() helpers + SEASON_WINDOW/MIN_N_GAMES_PLAYER constants
(single source of truth, no duplication); wnba_claims.main() is the
combined CLI entry point.

TWO DIMENSIONS from the NEW domains/wnba/atlas_extract.py parquets (same
zero-new-fetch discipline as wnba_claims.py/wnba_claims_ext.py): player_ft_
profile (FT% reliability, atlas_wnba_player_ft_profile.parquet, floor
n_games_played>=10) and team_defense_allowed (opponent paint-pts-allowed/
game, atlas_wnba_team_defense_allowed.parquet, floor n_games>=10).

HARD RAIL (same as wnba_claims.py, ratified power audit): WNBA earns
DESCRIPTIVE extraction ONLY at current sample sizes -- no gate, no
predictive/calibration claim, no verdict-kind claim, no market/$ edge.

NETWORK: zero. Pure pandas over already-materialized parquets.

CLI (standalone, this module's 2 claims only -- prefer wnba_claims.main()
for the combined 8-claim CLI):
    python -m scripts.platformkit.intel_validation.wnba_claims_ext2
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.intel_validation.wnba_claims import (
    MIN_N_GAMES_PLAYER, REPO_ROOT, SEASON_WINDOW, _full_population_ranking,
    _rel, write_claims,
)

_FT_PROFILE_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_ft_profile.parquet"
_TEAM_DEFENSE_ALLOWED_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_team_defense_allowed.parquet"

MIN_N_GAMES_TEAM = 10  # team-grain floor, mirrors atlas_extract.py's own confidence convention

_EXT2_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "wnba_claims_ext2.jsonl"


def build_player_ft_profile_claim() -> dict[str, Any]:
    df = pd.read_parquet(_FT_PROFILE_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="ft_pct_season", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_ft_profile_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players have the best free-throw percentage "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "ft_pct_season",
            "formula": "ft_pct_season",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_FT_PROFILE_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "ft_pct_season = season free-throw makes / attempts, from "
            f"data/cache/atlas_wnba_player_ft_profile.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/wnba/atlas_extract.py); companion column "
            "fta_per_game (FT-drawing rate/volume) travels alongside but is not the ranked metric.",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts whose FT% is noisy at very low attempt counts.",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def build_team_defense_allowed_claim() -> dict[str, Any]:
    df = pd.read_parquet(_TEAM_DEFENSE_ALLOWED_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="opp_paint_pts_allowed_per_game", entity_key="team_id", entity_col="team_id",
        name_col="team_tricode", min_n_col="n_games", min_n=MIN_N_GAMES_TEAM,
    )
    return {
        "claim_id": f"wnba_team_defense_allowed_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA teams allow the most opponent paint points per game "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "opp_paint_pts_allowed_per_game",
            "formula": "opp_paint_pts_allowed_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games": MIN_N_GAMES_TEAM},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "team_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_TEAM_DEFENSE_ALLOWED_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "opp_paint_pts_allowed_per_game = opponent points-in-the-paint / games, from "
            f"data/cache/atlas_wnba_team_defense_allowed.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/wnba/atlas_extract.py); companion column "
            "opp_fg3_pct_allowed travels alongside but is not the ranked metric.",
            f"min_sample floor n_games>={MIN_N_GAMES_TEAM} -- excludes the 2-game JNT/NGR "
            "small-sample team rows.",
            "RAW, UN-ADJUSTED allowed rate -- no opponent-strength/schedule adjustment attempted "
            "(same honest partial documented for pace_possessions/three_point_defense upstream "
            "in atlas_extract_team.py).",
            "FULL POPULATION: every team clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def all_ext2_claims() -> list[dict[str, Any]]:
    """This module's two claims, in a stable order -- shared by both this
    module's standalone CLI and wnba_claims.main()'s combined CLI."""
    return [
        build_player_ft_profile_claim(),
        build_team_defense_allowed_claim(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit WNBA DESCRIPTIVE ranking claims part 3 (no gate)")
    parser.add_argument("--output", type=str, default=str(_EXT2_OUT))
    args = parser.parse_args(argv)

    claims = all_ext2_claims()
    out_path = write_claims(claims, out_path=Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n={c['n_considered']} "
              f"excluded={c['n_excluded_below_floor']} top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = [
    "build_player_ft_profile_claim", "build_team_defense_allowed_claim",
    "all_ext2_claims", "main",
]
