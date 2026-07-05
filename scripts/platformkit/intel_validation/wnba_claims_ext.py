"""WNBA DESCRIPTIVE ranking claims producer, PART 2 (lane wnba-atlas).

Sibling module to wnba_claims.py (+ wnba_claims_ext2.py) -- three-way split
to keep each file <=300 LOC (per human-gated-paths rail). Reuses wnba_
claims's _rel()/_full_population_ranking() helpers + SEASON_WINDOW/
MIN_N_GAMES_PLAYER constants (single source of truth, no duplication);
wnba_claims.main() is the combined CLI entry point that merges all three
modules' claims into one 8-claim output.

THREE DIMENSIONS from the NEW domains/wnba/atlas_extract.py parquets (same
zero-new-fetch discipline: derived from atlas_wnba_player_box_profile /
_shooting_profile, no cdn_backfill re-walk): player_playmaking (assists/
game), player_defense_activity (steals+blocks "stocks"/game), player_usage_
volume (FGA/game). All floor n_games_played>=10. The remaining two new
dims (player_ft_profile, team_defense_allowed) live in wnba_claims_ext2.py.

HARD RAIL (same as wnba_claims.py, ratified power audit): WNBA earns
DESCRIPTIVE extraction ONLY at current sample sizes -- no gate, no
predictive/calibration claim, no verdict-kind claim, no market/$ edge.

NETWORK: zero. Pure pandas over already-materialized parquets.

CLI (standalone, this module's 3 claims only -- prefer wnba_claims.main()
for the combined 8-claim CLI):
    python -m scripts.platformkit.intel_validation.wnba_claims_ext
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

_PLAYMAKING_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_playmaking.parquet"
_DEFENSE_ACTIVITY_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_defense_activity.parquet"
_USAGE_VOLUME_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_usage_volume.parquet"

_EXT_OUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "wnba_claims_ext.jsonl"


def build_player_playmaking_claim() -> dict[str, Any]:
    df = pd.read_parquet(_PLAYMAKING_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="assists_per_game", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_playmaking_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players average the most assists per game "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "assists_per_game",
            "formula": "assists_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_PLAYMAKING_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "assists_per_game = total assists / games played, from "
            f"data/cache/atlas_wnba_player_playmaking.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/wnba/atlas_extract.py, derived from "
            "domains/basketball_wnba's own atlas_wnba_player_box_profile.parquet).",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts.",
            "Raw assist COUNTING stat only -- no assist-network/secondary-assist graph "
            "(same honest partial documented in atlas_extract_player.py's playmaking_network gap).",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def build_player_defense_activity_claim() -> dict[str, Any]:
    df = pd.read_parquet(_DEFENSE_ACTIVITY_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="stocks_per_game", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_defense_activity_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players generate the most steals+blocks ('stocks') per game "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "stocks_per_game",
            "formula": "steals_per_game + blocks_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_DEFENSE_ACTIVITY_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "stocks_per_game = (steals+blocks) / games played, from "
            f"data/cache/atlas_wnba_player_defense_activity.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/wnba/atlas_extract.py).",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts.",
            "Raw box-score counting-stat composite only -- no defender-matchup/opponent-strength "
            "adjustment (same honest partial documented for defensive_profile_player upstream).",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def build_player_usage_volume_claim() -> dict[str, Any]:
    df = pd.read_parquet(_USAGE_VOLUME_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="fga_per_game", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_usage_volume_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players attempt the most field goals per game "
            f"(shot-volume/usage, full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "fga_per_game",
            "formula": "fga_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_USAGE_VOLUME_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "fga_per_game = field goal attempts / games played, from "
            f"data/cache/atlas_wnba_player_usage_volume.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/wnba/atlas_extract.py).",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts.",
            "Raw shot-VOLUME counting stat -- a distinct descriptive question from shot QUALITY "
            "(ts_pct, ranked separately in wnba_player_shot_quality_ts_full).",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def all_ext_claims() -> list[dict[str, Any]]:
    """This module's three claims, in a stable order -- shared by both this
    module's standalone CLI and wnba_claims.main()'s combined CLI."""
    return [
        build_player_playmaking_claim(),
        build_player_defense_activity_claim(),
        build_player_usage_volume_claim(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit WNBA DESCRIPTIVE ranking claims part 2 (no gate)")
    parser.add_argument("--output", type=str, default=str(_EXT_OUT))
    args = parser.parse_args(argv)

    claims = all_ext_claims()
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
    "build_player_playmaking_claim", "build_player_defense_activity_claim",
    "build_player_usage_volume_claim", "all_ext_claims", "main",
]
