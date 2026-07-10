"""domains.soccer.knowledge.validate_replication_wave1 -- second-corpus
(disjoint competition-group) replication of the 2 strongest research-wave
CONFIRMED_LOCALs:

  #35 xg_supremacy_persistence (validate_referee_xg_fouls.py) -- original
      pooled ALL 6 divisions (E0/E1/F1/D1/I1/SP1) and split-half by date;
      never isolated a single league group as its own test population.
  #37 substitution_timing_moderates_shift (validate_research_wave2.py) --
      original pooled the FULL StatsBomb event cache with zero competition
      awareness (iter_all_event_files() reads every cached match file, no
      filter); this replication newly joins match_meta_full.parquet (a data
      dependency the original never used) to carve out disjoint competition
      groups.

Each hypothesis is replicated on TWO disjoint groups (the two groups
together ARE the second-corpus independence -- no extra split-half needed
on top). Ponytail: imports and calls the ORIGINAL validator functions and
thresholds unchanged, just feeds them a group-filtered slice of the same
underlying data -- same bars, no loosening.

Outcomes (RAILS vocabulary): REPLICATED (clears the original's own bar on a
disjoint group) / FAILED_REPLICATION (does not) / NOT_REPLICABLE_NO_CORPUS
(the group's backing data does not exist locally).

Run: python -m domains.soccer.knowledge.validate_replication_wave1
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from domains.soccer.knowledge._data import EVENTS_DIR, LEDGER_PATH, extract_match_facts
from domains.soccer.knowledge.validate_referee_xg_fouls import (
    load_match_stats, load_xg_proxy, xg_supremacy_persistence)
from domains.soccer.knowledge.validate_research_wave2 import _accumulate, _score_sub_timing, _verdict
from scripts.platformkit.io_atomic import append_jsonl_atomic

# #35: two disjoint league groups from match_stats.parquet's `div` column --
# neither was ever isolated by the original pooled-all-6-divs test.
XG_SUPREMACY_GROUPS = {
    "english_pyramid": ["E0", "E1"],
    "continental_top4": ["D1", "F1", "I1", "SP1"],
}

# #37: disjoint competition groups from match_meta_full.parquet's
# `competition` field, a data dependency the original event-cache scan
# never joined at all.
MATCH_META_FULL_PATH = Path("data/cache/statsbomb/match_meta_full.parquet")
BIG4_2015_16 = ["Serie_A_2015_2016", "La_Liga_2015_2016",
                "Premier_League_2015_2016", "Ligue_1_2015_2016"]


def _not_replicable(hyp: str, group: str, note: str) -> Dict[str, Any]:
    return {"hypothesis": "%s__replication_%s" % (hyp, group), "verdict": "NOT_REPLICABLE_NO_CORPUS",
            "n": 0, "note": note}


def replicate_xg_supremacy_persistence(group: str, divs: List[str]) -> Dict[str, Any]:
    """#35 on a disjoint div subset -- same xg_supremacy_persistence()
    unchanged (same |r|>=0.20/p<0.01 bar)."""
    ms = load_match_stats()
    sub_ms = ms[ms["div"].isin(divs)]
    if sub_ms.empty:
        return _not_replicable("xg_supremacy_persistence", group, "no rows for div in %s" % divs)
    axg = load_xg_proxy()
    original = xg_supremacy_persistence(axg, sub_ms)
    verdict = "REPLICATED" if original["verdict"] == "CONFIRMED_LOCAL" else "FAILED_REPLICATION"
    return {"hypothesis": "xg_supremacy_persistence__replication_%s" % group,
            "verdict": verdict, "n": original["n"], "effect": original["effect"], "p": original["p"],
            "note": "disjoint-competition-group replication, div in %s: %s" % (divs, original["note"])}


def replicate_substitution_timing(group: str, competitions: List[str]) -> Dict[str, Any]:
    """#37 on a disjoint StatsBomb competition subset (per match_meta_full.
    parquet) -- same _accumulate/_score_sub_timing design and |eff|>=0.02/
    p<0.01 bar as the original pooled event-cache scan."""
    if not MATCH_META_FULL_PATH.exists():
        return _not_replicable("substitution_timing_moderates_shift", group,
                                "match_meta_full.parquet does not exist locally")
    mm = pd.read_parquet(MATCH_META_FULL_PATH)
    group_ids = set(mm.loc[mm["competition"].isin(competitions), "match_id"].astype(str))
    if not group_ids:
        return _not_replicable("substitution_timing_moderates_shift", group,
                                "no matches for competition in %s" % competitions)
    acc: Dict[str, List[float]] = {k: [] for k in ("early_shift", "late_shift", "trailing_rate", "tied_rate")}
    n_matches = 0
    for fp in glob.glob(str(EVENTS_DIR / "*.json")):
        match_id = Path(fp).stem
        if match_id not in group_ids:
            continue
        with open(fp, encoding="utf-8") as f:
            events = json.load(f)
        _accumulate(extract_match_facts(events), acc)
        n_matches += 1
    eff, p = _score_sub_timing(acc)
    verdict_local = _verdict(p, eff)
    verdict = "REPLICATED" if verdict_local == "CONFIRMED_LOCAL" else "FAILED_REPLICATION"
    return {"hypothesis": "substitution_timing_moderates_shift__replication_%s" % group,
            "verdict": verdict, "n": len(acc["early_shift"]) + len(acc["late_shift"]),
            "effect": round(eff, 5), "p": float(p),
            "note": "disjoint-competition-group replication (n_matches=%d, early n=%d, late n=%d), "
                    "competition in %s" % (n_matches, len(acc["early_shift"]), len(acc["late_shift"]), competitions)}


def run() -> List[Dict[str, Any]]:
    rows = [replicate_xg_supremacy_persistence(g, d) for g, d in XG_SUPREMACY_GROUPS.items()]
    if MATCH_META_FULL_PATH.exists():
        mm = pd.read_parquet(MATCH_META_FULL_PATH)
        rest = [c for c in sorted(mm["competition"].unique()) if c not in BIG4_2015_16]
        rows.append(replicate_substitution_timing("big4_2015_16", BIG4_2015_16))
        rows.append(replicate_substitution_timing("rest_competitions", rest))
    else:
        rows.append(_not_replicable("substitution_timing_moderates_shift", "big4_2015_16",
                                     "match_meta_full.parquet does not exist locally"))
        rows.append(_not_replicable("substitution_timing_moderates_shift", "rest_competitions",
                                     "match_meta_full.parquet does not exist locally"))
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "disjoint_competition_group"
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
    NOT_REPLICABLE_NO_CORPUS instead of raising when a group has zero rows."""
    r = _not_replicable("xg_supremacy_persistence", "empty_group", "no rows for div in []")
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r["hypothesis"] == "xg_supremacy_persistence__replication_empty_group"
    print("self-check OK")
