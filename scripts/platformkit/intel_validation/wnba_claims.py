"""WNBA DESCRIPTIVE ranking claims producer (lane soccer-wnba-fullpop).
Emits FULL-population ranking claims (every entity above its stated floor,
no top-N cap) for WNBA dimensions whose corpus already exists on disk, in
the SAME claims contract shape as scripts/platformkit/intel_validation's
other producers (mlb_pitcher_claims.py / soccer_intl_strength_claims.py),
zero code sharing with the independent claims_validator.py.

HARD RAIL (ratified power audit, docs/research/intel-layer/wnba_truth_spec.json
+ domains/basketball_wnba/atlas_extract_context.py's own docstring: "the power
audit forbids any WNBA gate this wave"): WNBA earns DESCRIPTIVE extraction
ONLY at current sample sizes (n<=172 games in 2026, close corpus is
TODAY-ONLY per pregame_gate_verdict.json's close_comparison=PENDING). This
module emits PLAIN RANKINGS ONLY -- no hypothesis test, no predictive gate,
no calibration/Brier claim, no verdict-kind claim. Every ranking is a
descriptive box-score/officiating aggregate with a stated provenance + floor,
exactly like the MLB/tennis/soccer_intl ranking producers.

THREE DIMENSIONS, each an on-disk WNBA corpus already computed to a
ranking-ready (value/n/entity_id) shape by domains/basketball_wnba's
zero-new-fetch atlas extraction (read-only consumption here; that builder
module lives under domains/ and is untouched by this task):

  referee_crew_foul_rate  -- per-official personal fouls-called/game,
      data/domains/wnba/referee_crew_foul_rate.parquet (168-game CDN PBP
      corpus). Floor n_games>=10, mirrors the corpus's own CREW_CLAIM_FLOOR.
  player_shot_quality_ts  -- per-player True Shooting %,
      data/cache/atlas_wnba_player_shooting_profile.parquet (season-2026 CDN
      boxscore corpus). Floor n_games_played>=10.
  player_rebounding_profile -- per-player total rebounds/game,
      data/cache/atlas_wnba_player_box_profile.parquet (same corpus). Floor
      n_games_played>=10.

All three floors are plain, row-wise columns already present in the source
parquet -- claims_validator's whitelist formula evaluator recomputes each
metric directly from the declared source_files, no aggregate grammar needed
(the atlas builder already did the per-entity aggregation; that computation
is independently reproducible by re-running domains/basketball_wnba's own
per-file tests, not by this validator, which validates the DECLARED
parquet-to-ranking step only, exactly as it does for every other sport).

LEAK DISCIPLINE: purely descriptive/retrospective (completed-game box-score
and officiating aggregates over the 2026 season-to-date) -- no forecasting
claim, no leak-risk window, no market comparison.

NETWORK: zero. Pure pandas over already-materialized parquets.
DESCRIPTIVE ONLY -- NO MARKET EDGE CLAIMED, NO GATE, NO CALIBRATION CLAIM.

CLI:
    python -m scripts.platformkit.intel_validation.wnba_claims
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]

_REFEREE_SRC = REPO_ROOT / "data" / "domains" / "wnba" / "referee_crew_foul_rate.parquet"
_SHOOTING_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_shooting_profile.parquet"
_BOX_SRC = REPO_ROOT / "data" / "cache" / "atlas_wnba_player_box_profile.parquet"

_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_CLAIMS_OUT = _OUT_DIR / "wnba_claims.jsonl"

SEASON_WINDOW = "2026"  # single on-disk WNBA CDN season (truth-spec limit #4)
MIN_N_GAMES_REFEREE = 10  # mirrors atlas_extract_context.py's own CREW_CLAIM_FLOOR
MIN_N_GAMES_PLAYER = 10  # same floor convention applied to player-game corpora


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _full_population_ranking(
    df: pd.DataFrame, *, metric_col: str, entity_key: str, entity_col: str, name_col: str,
    min_n_col: str, min_n: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """Full-population ranking (no top-N cap): every row clearing min_n_col
    >= min_n is ranked desc by metric_col. Returns (ranking, n_considered,
    n_excluded_below_floor). Below-floor rows are counted, never dropped
    silently. The ranking dict key for the entity id is entity_key ITSELF
    (matching criteria.entity_key) -- claims_validator reads claimed_row.get
    (entity_key) directly, so the dict key must equal the declared entity_key,
    not a fixed cross-sport alias."""
    n_considered = len(df)
    qualifiers = df[df[min_n_col] >= min_n].copy()
    qualifiers = qualifiers.dropna(subset=[metric_col])
    n_excluded = n_considered - len(qualifiers)
    qualifiers = qualifiers.sort_values(metric_col, ascending=False).reset_index(drop=True)

    ranking = []
    for i, row in enumerate(qualifiers.itertuples(index=False), start=1):
        ranking.append({
            "rank": i,
            entity_key: str(getattr(row, entity_col)),
            "player_name": str(getattr(row, name_col)),  # ask()'s cross-sport display key
            "value": round(float(getattr(row, metric_col)), 4),
            "n": int(getattr(row, min_n_col)),
        })
    return ranking, n_considered, n_excluded


def build_referee_crew_claim() -> dict[str, Any]:
    df = pd.read_parquet(_REFEREE_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="fouls_per_game", entity_key="official_id", entity_col="official_id",
        name_col="official_name", min_n_col="n_games", min_n=MIN_N_GAMES_REFEREE,
    )
    return {
        "claim_id": f"wnba_referee_crew_foul_rate_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA officials call the most personal fouls per game "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "fouls_per_game",
            "formula": "fouls_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games": MIN_N_GAMES_REFEREE},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "official_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_REFEREE_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            f"fouls_per_game = total personal fouls called / games officiated, from "
            f"data/domains/wnba/referee_crew_foul_rate.parquet (168-game 2026 CDN "
            "play-by-play corpus, per-official attribution via officialId).",
            f"min_sample floor n_games>={MIN_N_GAMES_REFEREE} (mirrors the corpus's own "
            "CREW_CLAIM_FLOOR in domains/basketball_wnba/atlas_extract_context.py).",
            "FULL POPULATION: every official clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score/officiating aggregate ONLY -- NOT a gate, NOT a "
            "predictive/calibration claim, no market/$ edge claimed. Per the ratified "
            "power audit, WNBA earns descriptive extraction only at current sample sizes.",
        ],
    }


def build_player_shot_quality_claim() -> dict[str, Any]:
    df = pd.read_parquet(_SHOOTING_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="ts_pct", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_shot_quality_ts_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players have the best True Shooting % "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "ts_pct",
            "formula": "ts_pct",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_SHOOTING_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "ts_pct = True Shooting % (points / (2*(fga+0.44*fta))), from "
            f"data/cache/atlas_wnba_player_shooting_profile.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/basketball_wnba/atlas_extract_player.py).",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts whose TS% is noisy at very low game counts.",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def build_player_rebounding_claim() -> dict[str, Any]:
    df = pd.read_parquet(_BOX_SRC)
    ranking, n_considered, n_excluded = _full_population_ranking(
        df, metric_col="reb_per_game", entity_key="player_id", entity_col="player_id",
        name_col="player_name", min_n_col="n_games_played", min_n=MIN_N_GAMES_PLAYER,
    )
    return {
        "claim_id": f"wnba_player_rebounding_full_{SEASON_WINDOW}",
        "kind": "ranking",
        "question": (
            f"Which WNBA players rebound the most per game "
            f"(full population above floor, season={SEASON_WINDOW})?"
        ),
        "criteria": {
            "metric": "reb_per_game",
            "formula": "reb_per_game",
            "window": f"season_{SEASON_WINDOW}_wnba",
            "window_spec": {"kind": "season", "season": SEASON_WINDOW, "n": None, "order_by": None},
            "min_sample": {"n_games_played": MIN_N_GAMES_PLAYER},
            "direction": "desc",
            "value_precision": 4,
            "entity_key": "player_id",
        },
        "ranking": ranking,
        "source_files": [_rel(_BOX_SRC)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "caveats": [
            "reb_per_game = (oreb+dreb) total rebounds / games played, from "
            f"data/cache/atlas_wnba_player_box_profile.parquet (season-{SEASON_WINDOW} "
            "168-game CDN boxscore corpus, domains/basketball_wnba/atlas_extract_player.py).",
            f"min_sample floor n_games_played>={MIN_N_GAMES_PLAYER} -- excludes small-sample "
            "call-ups/late-season debuts.",
            "FULL POPULATION: every player clearing the floor is ranked, no top-N cap.",
            "DESCRIPTIVE box-score aggregate ONLY -- NOT a gate, NOT a predictive/calibration "
            "claim, no market/$ edge claimed. Per the ratified power audit, WNBA earns "
            "descriptive extraction only at current sample sizes.",
        ],
    }


def write_claims(claims: list[dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit WNBA DESCRIPTIVE ranking claims (no gate)")
    parser.add_argument("--output", type=str, default=str(_CLAIMS_OUT))
    args = parser.parse_args(argv)

    claims = [
        build_referee_crew_claim(),
        build_player_shot_quality_claim(),
        build_player_rebounding_claim(),
    ]
    out_path = write_claims(claims, Path(args.output))
    for c in claims:
        print(f"{c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded_below_floor={c['n_excluded_below_floor']} "
              f"top1={c['ranking'][0] if c['ranking'] else None}")
    print(f"wrote {len(claims)} claims -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
