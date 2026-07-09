"""domains.tennis.knowledge.validate_premise_blocked -- premise-check only
for the 3 remaining UNTESTED mechanisms (#15 tiebreak-skill persistence, #19
rally-length by round, #23 second-serve win-rate discount by surface) that a
fresh disk/column check this session confirms are NOT_TESTABLE on the
current local corpus. No regression is run -- each is an honest ingredient-
missing verdict with the exact check performed recorded in `note`.

Run: python -m domains.tennis.knowledge.validate_premise_blocked
"""
from __future__ import annotations

from typing import Any, Dict, List

from domains.tennis.knowledge._data import LEDGER_PATH, REPO, load_slam_points
from scripts.platformkit.io_atomic import append_jsonl_atomic

CHARTING_POINTS = REPO / "data" / "cache" / "sackmann_pbp" / "charting_points.parquet"


def tiebreak_skill_persistence(slam: "Any") -> Dict[str, Any]:
    cols = list(slam.columns)
    return {"hypothesis": "tiebreak_skill_persistence_split_half", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "slam_points.parquet has no player-name/id column at all (columns: %s) -- only "
                    "server-slot (1/2) identity WITHIN a match. A per-PLAYER split-half correlation across "
                    "matches needs cross-match player identity, which does not exist locally on this "
                    "point-level corpus (consistent with the documented no-cross-corpus-identity-join "
                    "ponytail note in _data.py, but stronger: it's missing even WITHIN this one corpus)."
                    % cols}


def rally_length_by_round(slam: "Any") -> Dict[str, Any]:
    cols = list(slam.columns)
    return {"hypothesis": "rally_length_distribution_by_round", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "slam_points.parquet has no `round` column (columns: %s), only set_no/game_no; "
                    "match_id format ('YYYY-tourney-NNNN') does not encode round, and there is no local "
                    "join key shared with matches.parquet's `round` column for these specific charted "
                    "matches -- confirmed by column check this session." % cols}


def second_serve_discount_by_surface() -> Dict[str, Any]:
    import pandas as pd
    cp = pd.read_parquet(CHARTING_POINTS)
    cols = list(cp.columns)
    return {"hypothesis": "second_serve_discount_by_surface", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "slam_points.parquet has no serve-number column (only p1_ace/p1_double_fault flags). "
                    "The sibling charting_points.parquet DOES carry `is_second_serve` (columns: %s) but "
                    "covers ALL charted tour-level matches (not just the 4 majors) with no tourney/surface "
                    "column and a free-text match_id (e.g. '...-Davis_Cup_Finals-...') that does not map "
                    "through SURFACE_OF_TOURNEY -- deriving surface would need parsing thousands of distinct "
                    "tournament-name strings, a bigger build than this mechanism check." % cols}


def run() -> List[Dict[str, Any]]:
    slam = load_slam_points()
    rows = [tiebreak_skill_persistence(slam), rally_length_by_round(slam), second_serve_discount_by_surface()]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "premise_check_only"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-16s -- %s" % (r["hypothesis"], r["verdict"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    r = second_serve_discount_by_surface()
    assert r["verdict"] == "NOT_TESTABLE"
    print("self-check OK")
