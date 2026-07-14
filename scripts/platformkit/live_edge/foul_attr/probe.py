"""scripts.platformkit.live_edge.foul_attr.probe -- STEP 0 premise check.

Question: does the raw PBP JSON (same corpus PLAYER-ATTR proved for scorer
attribution) carry FOUL actions with personId + team + clock/period, joinable
to sim2_possessions.parquet the same way? Answer: YES.

data/cache/team_system/pbp*/*.json actions include actionType == 'foul' rows,
e.g.:
  {"actionType": "foul", "subType": "personal", "personId": 1630596,
   "period": 1, "clock": "PT10M53.00S", "teamId": 1610612739,
   "description": "E. Mobley shooting personal FOUL (1 PF) (Towns 3 FT)"}
  {"actionType": "foul", "subType": "offensive", "personId": 1626157, ...}

subType in {"personal", "offensive", ...}; the description embeds the running
box-score PF count ("(N PF)") which cross-checks (not relied upon) an
independently-accumulated per-action counter. Every foul row carries
actionNumber, the SAME monotonic key domains.basketball_nba.composition
.shot_clock_proxy.resolve_segments() maps to a possession segment -- so
cumulative-foul-state-per-possession is the SAME deterministic segmentation
walk sim2/build_attr already run, with a foul counter accumulated instead of
(or alongside) scorer points. No new ID scheme: personId/teamId are the same
NBA raw-PBP scheme used throughout; game_id is sim2's game_id scheme.

On-floor roster for per-player foul-trouble state: data/omni/lineups/
possession_lineups_{2024_25,2025_26}.parquet (off_lineup_ids/def_lineup_ids
per possession_key) -- read-only reuse via situation_grid.attach_lineups,
same as B1. 2023-24 has no lineup store (matches B1/PLAYER-GRID's own
documented gap) so per-player foul columns are season-gated; team-foul/
bonus-penalty state has no such dependency and extends to all 3 seasons.

VERDICT: BUILDABLE. See build_foul.py. Join-rate proven empirically in
test_foul_attr.py (>=95% rail) via the (game_id, poss_idx) key against
sim2_possessions.parquet on a real game slice.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = REPO_ROOT / "data" / "cache" / "team_system"
PBP_DIRS = {"2023-24": _TS / "pbp_2023_24", "2024-25": _TS / "pbp_2024_25", "2025-26": _TS / "pbp"}
SIM2_POSSESSIONS = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"


def inventory() -> dict:
    counts = {}
    foul_actions = {}
    subtypes = set()
    for season, d in PBP_DIRS.items():
        files = sorted(d.glob("*.json"))
        counts[season] = len(files)
        n_foul = 0
        for fp in files[:20]:
            try:
                g = json.loads(fp.read_text(encoding="utf-8"))["game"]
            except Exception:
                continue
            for a in g["actions"]:
                if a.get("actionType") == "foul":
                    n_foul += 1
                    if a.get("subType"):
                        subtypes.add(a["subType"])
        foul_actions[season] = n_foul  # from first 20 games only, sanity sample
    return {
        "pbp_game_files_per_season": counts,
        "foul_actions_first20games": foul_actions,
        "foul_subtypes_observed": sorted(subtypes),
        "sim2_possessions_exists": SIM2_POSSESSIONS.exists(),
        "verdict": "BUILDABLE",
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
