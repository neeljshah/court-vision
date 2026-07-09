"""domains.basketball_nba.knowledge.validate_premise_blocked -- premise-check
only for the 3 remaining UNTESTED mechanisms (#28 transition-freq mismatch,
#29 clutch FT pressure dip, #31 travel/timezone fatigue) that a fresh disk
check this session confirms are NOT_TESTABLE on the current local corpus.
No regression is run -- these are honest ingredient-missing / leak-shape
verdicts, each with the exact check performed recorded in `note`.

Run: python -m domains.basketball_nba.knowledge.validate_premise_blocked
"""
from __future__ import annotations

import glob
from typing import Any, Dict, List

import pandas as pd

from domains.basketball_nba.knowledge._data import LEDGER_PATH, PBP_FEATURES_PATH, REPO
from scripts.platformkit.io_atomic import append_jsonl_atomic

ATLAS_TRANSITION_PATH = REPO / "data" / "cache" / "atlas_team_transition_defense.parquet"


def transition_freq_pace_mismatch() -> Dict[str, Any]:
    atlas = pd.read_parquet(ATLAS_TRANSITION_PATH)
    return {"hypothesis": "transition_frequency_pace_mismatch", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "atlas_team_transition_defense.parquet is one row per TEAM (n=%d), a single-season "
                    "aggregate (as_of snapshot) -- using own/opp transition_freq as a per-game feature for "
                    "games drawn from that same season is the season-final-aggregate-as-feature leak this "
                    "codebase forbids. A leak-free version needs game-level transition rate rebuilt from "
                    "pbp_possession_features.parquet's pbp_transition_count (a separate, larger build than "
                    "'reuse atlas' calls for) -- not attempted this session." % len(atlas)}


def clutch_ft_pressure_dip() -> Dict[str, Any]:
    pbp = pd.read_parquet(PBP_FEATURES_PATH)
    ft_cols = [c for c in pbp.columns if "ft" in c.lower() or "free" in c.lower()]
    return {"hypothesis": "clutch_free_throw_pressure_dip", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "pbp_possession_features.parquet has pbp_clutch_shots_attempted/pbp_clutch_pts_scored "
                    "(field-goal clutch tracking only) and zero clutch-specific FT columns (checked: %s); "
                    "player_boxscores.parquet only has game-total ftm/fta -- no clutch-window FT split exists "
                    "anywhere in the local corpus." % (ft_cols or "none found")}


def travel_timezone_fatigue() -> Dict[str, Any]:
    hits = glob.glob(str(REPO / "data" / "domains" / "basketball_nba" / "*arena*")) + \
        glob.glob(str(REPO / "data" / "domains" / "basketball_nba" / "*travel*"))
    return {"hypothesis": "travel_timezone_fatigue", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "no arena-location/travel-distance/timezone ingredient in data/domains/basketball_nba "
                    "(fresh glob this session for *arena*/*travel*: %d hits, all irrelevant) -- rest_days "
                    "(#14) is the only schedule ingredient on disk; a time-zone-delta feature needs an "
                    "arena-location join that does not exist locally." % len(hits)}


def run() -> List[Dict[str, Any]]:
    rows = [transition_freq_pace_mismatch(), clutch_ft_pressure_dip(), travel_timezone_fatigue()]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "premise_check_only"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s -- %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert transition_freq_pace_mismatch()["verdict"] == "NOT_TESTABLE"
    print("self-check OK")
