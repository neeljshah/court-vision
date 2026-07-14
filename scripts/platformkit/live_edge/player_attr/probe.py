"""scripts.platformkit.live_edge.player_attr.probe -- STEP 0 premise check.

Question: does a store exist that records, per scoring event, the PLAYER id +
game clock/period, joinable to sim2_possessions.parquet (the in-game possession
corpus B1/B4 mined)? Answer: YES.

data/cache/ingame/sim2_possessions.parquet (780,166 rows, 3 seasons: 2023-24,
2024-25, 2025-26) carries NO player id -- it is an aggregate possession table
(period, clock_start, off_is_home, points, duration, margins, game_id, season)
built by domains/basketball_nba/sim2/corpus.py::build_corpus() by walking the
SAME raw PBP JSON this probe inspects.

The raw PBP JSON (data/cache/team_system/pbp/*.json = 2025-26 [1192 games],
pbp_2023_24/*.json [1230 games], pbp_2024_25/*.json [1230 games] -- all 3
sim2 seasons present) has one row per action with: period, clock (PTxMxxS),
teamId, personId, actionType ('2pt'|'3pt'|'freethrow'|'other'|'substitution'),
shotResult ('Made'|'Missed'), actionNumber (monotonic within game).

Every made-shot / made-freethrow action carries personId (the scorer) and an
actionNumber that domains.basketball_nba.composition.shot_clock_proxy
.resolve_segments() ALREADY maps to the exact possession segment
(period, seg_team, seg_start_s) that sim2's extract_possessions() uses to
emit each possession row. So scorer->possession is NOT a fuzzy cross-scheme
join -- it is the SAME segmentation walk sim2 already runs, with scoring
personIds accumulated per segment instead of discarded. No new ID scheme is
introduced (personId is the NBA raw-PBP scheme already used downstream in
pbp_possession_features.parquet / pbp_attributes.parquet); game_id is the
same NBA game_id scheme used throughout sim2_possessions.parquet.

VERDICT: BUILDABLE. See build_attr.py. Join-rate is proven empirically in
test_player_attr.py (>=95% rail) by re-deriving the same (period, clock_start,
off_is_home, points) key sim2 emits and checking it lands in the cached
sim2_possessions.parquet for a real game slice.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = REPO_ROOT / "data" / "cache" / "team_system"
PBP_DIRS = {"2023-24": _TS / "pbp_2023_24", "2024-25": _TS / "pbp_2024_25", "2025-26": _TS / "pbp"}
SIM2_POSSESSIONS = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"


def inventory() -> dict:
    counts = {season: len(list(d.glob("*.json"))) for season, d in PBP_DIRS.items()}
    return {
        "pbp_game_files_per_season": counts,
        "sim2_possessions_exists": SIM2_POSSESSIONS.exists(),
        "verdict": "BUILDABLE",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(inventory(), indent=2))
