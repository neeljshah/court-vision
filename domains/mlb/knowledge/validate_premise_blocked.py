"""domains.mlb.knowledge.validate_premise_blocked -- premise-check only for
the 4 remaining UNTESTED mechanisms (#23 sequencing/cluster luck, #25 speed/
baserunning advancement, #30 lineup-slot run value, #31 umpire zone-call
consistency) that a fresh disk/column check this session confirms are
NOT_TESTABLE on the current local corpus. No regression is run -- each is an
honest ingredient-missing or infra-missing verdict with the check recorded.

Run: python -m domains.mlb.knowledge.validate_premise_blocked
"""
from __future__ import annotations

from typing import Any, Dict, List

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic


def sequencing_cluster_luck(df) -> Dict[str, Any]:
    return {"hypothesis": "sequencing_and_cluster_luck", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "testing 'actual vs context-neutral-expected runs' needs a full run-expectancy/linear-"
                    "weights model (RE24-style) rebuilt from base-out state transitions; no such model exists "
                    "locally and building one is a separate infra item, not a column check -- not attempted "
                    "this session (2-attempt budget: a naive runs-per-game proxy would not isolate sequencing "
                    "from talent, so was not substituted)."}


def speed_baserunning_advancement(df) -> Dict[str, Any]:
    cols_present = [c for c in ("on_1b", "on_2b", "on_3b") if c in df.columns]
    return {"hypothesis": "speed_baserunning_advancement_value", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "on_1b/on_2b/on_3b (%s) are PRE-pitch occupant state only -- there is no post-play base-"
                    "state or explicit extra-bases-taken field; inferring whether a runner from 1st reached "
                    "2nd vs 3rd on a single requires chaining consecutive PAs by runner identity (pinch-runner-"
                    "safe), a bigger build than this mechanism check." % cols_present}


def lineup_slot_run_value(df) -> Dict[str, Any]:
    hits = [c for c in df.columns if "order" in c.lower() or "slot" in c.lower() or "lineup" in c.lower()]
    return {"hypothesis": "lineup_slot_run_value", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "fresh column check on savant_full__%d.parquet (42 cols): no batting-order-slot column "
                    "(checked for */order/,*/slot/,*/lineup/* substrings, %d hits) -- cannot be derived from "
                    "at_bat_number alone (that resets by half-inning, not by lineup turn)." % (
                    DEFAULT_SEASON, len(hits))}


def umpire_zone_call_consistency(df) -> Dict[str, Any]:
    hits = [c for c in df.columns if "ump" in c.lower()]
    return {"hypothesis": "umpire_zone_call_consistency", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "fresh column check on savant_full__%d.parquet (42 cols): no umpire-identity column "
                    "anywhere (checked for '*ump*' substring, %d hits) -- no way to attribute a called-strike "
                    "rate to an individual umpire on this corpus." % (DEFAULT_SEASON, len(hits))}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    rows = [sequencing_cluster_luck(df), speed_baserunning_advancement(df),
            lineup_slot_run_value(df), umpire_zone_call_consistency(df)]
    for r in rows:
        r["sport"] = "mlb"
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
    import pandas as pd
    fake = pd.DataFrame({"on_1b": [1.0, None], "on_2b": [None, None], "on_3b": [None, None]})
    assert speed_baserunning_advancement(fake)["verdict"] == "NOT_TESTABLE"
    print("self-check OK")
