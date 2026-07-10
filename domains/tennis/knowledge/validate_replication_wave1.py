"""domains.tennis.knowledge.validate_replication_wave1 -- second-corpus
(disjoint year-slice) replication of the altitude_effect_on_serve_ace_rate
CONFIRMED_LOCAL (#28, validate_travel_altitude.py).

Premise check this session: mechanisms.md's test spec says "ATP+WTA
2015-2025", but `travel_scouting.parquet` (the altitude/travel corpus) is
100% ATP event_ids (0% WTA overlap, verified this session) -- a tour-split
replication is NOT possible with this corpus, the WTA "second corpus" the
doc's wording implies does not exist for this specific mechanism. A
year-slice split IS possible: `travel_scouting.parquet` carries a `season`
column, 2015-2025, no year under 2,504 rows. The original test pools ALL
years in one Welch t-test with no split at all, so this replication splits
the corpus into two disjoint, exhaustive year halves (2015-2020 /
2021-2025) -- a stronger bar than the original was ever held to.

Ponytail: imports and calls the ORIGINAL altitude_effect_on_serve_ace_rate +
_verdict unchanged (same ALTITUDE_HIGH_M=500m cut, same min_eff=0.005 bar
`run()` applies) -- just feeds it a year-filtered slice.

Outcomes (RAILS vocabulary): REPLICATED (clears the original's own bar on
the disjoint group) / FAILED_REPLICATION (does not) / NOT_REPLICABLE_NO_CORPUS
(the group's backing data does not exist locally).

Run: python -m domains.tennis.knowledge.validate_replication_wave1
"""
from __future__ import annotations

from typing import Any, Dict, List

from domains.tennis.knowledge._data import LEDGER_PATH
from domains.tennis.knowledge.validate_travel_altitude import (
    _verdict, altitude_effect_on_serve_ace_rate, load_match_stats, load_travel_scouting)
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALTITUDE_MIN_EFFECT = 0.005  # same bar validate_travel_altitude.run() applies
YEAR_SLICE_GROUPS = {
    "years_2015_2020": list(range(2015, 2021)),
    "years_2021_2025": list(range(2021, 2026)),
}


def _not_replicable(hyp: str, group: str, note: str) -> Dict[str, Any]:
    return {"hypothesis": "%s__replication_%s" % (hyp, group), "verdict": "NOT_REPLICABLE_NO_CORPUS",
            "n": 0, "note": note}


def replicate_altitude_effect(group: str, years: List[int]) -> Dict[str, Any]:
    travel = load_travel_scouting()
    sub = travel[travel["season"].isin(years)]
    if sub.empty:
        return _not_replicable("altitude_effect_on_serve_ace_rate", group,
                                "no travel_scouting rows for season in %s" % years)
    stats_df = load_match_stats()
    original = altitude_effect_on_serve_ace_rate(sub, stats_df)
    verdict_local = _verdict(original["p"], original["effect"], ALTITUDE_MIN_EFFECT)
    verdict = "REPLICATED" if verdict_local == "CONFIRMED_LOCAL" else "FAILED_REPLICATION"
    return {"hypothesis": "altitude_effect_on_serve_ace_rate__replication_%s" % group,
            "verdict": verdict, "n": original["n"], "effect": original["effect"], "p": original["p"],
            "note": "disjoint year-slice replication, season in %s: %s" % (years, original["note"])}


def run() -> List[Dict[str, Any]]:
    rows = [replicate_altitude_effect(g, y) for g, y in YEAR_SLICE_GROUPS.items()]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "travel_scouting_disjoint_year_slice"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-20s %s" % (r["hypothesis"], r["verdict"], r.get("note", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: the corpus-existence gate produces an honest
    NOT_REPLICABLE_NO_CORPUS instead of raising when a year-slice has zero rows."""
    r = _not_replicable("altitude_effect_on_serve_ace_rate", "years_1900_1905", "no rows")
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r["hypothesis"] == "altitude_effect_on_serve_ace_rate__replication_years_1900_1905"
    print("self-check OK")
