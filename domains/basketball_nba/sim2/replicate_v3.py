"""domains.basketball_nba.sim2.replicate_v3 -- replication check for the sim2 v3
lineup-composite conditioner (task 45, ledger row 96, verdict MATTERS_PROVISIONAL).

PREREGISTERED (ledger row 'sim2_v3_lineup_composite_conditioner_REPLICATION',
verdict PREREGISTERED, appended BEFORE this ran) -- see that row for the exact
declared fold design and pass/fail thresholds. Summary:

CROSS-SEASON SECOND FOLD REJECTED (checked empirically, not just asserted): only
3 NBA seasons on disk; the composite needs a STRICT prior-season profile
(cond_composite.PRIOR_WINDOW), and 2023-24 has no prior year on disk. A fit=
2023-24-only/test=2024-25 fold would need comp_thresholds fit on 2023-24
possessions, but all_game_comp_diff(["2023-24"]) is EMPTY (0 games) ->
build_comp_thresholds collapses to the degenerate symmetric [0.0, 0.0] split
(verified in _check_cross_season_fold_invalid below) -- not a fair test of the
composite hypothesis. No fully independent second season-level fold exists.

EVIDENCE RUN INSTEAD (both declared pre-registered, lower tier than a fresh
season-level fold, labelled honestly as such):
  (1) MULTI-SEED stability of the ORIGINAL fold (fit 2023-24+2024-25, test
      2025-26): same fit models, 5 independent MC seed offsets.
  (2) WITHIN-SEASON temporal split of the same 2025-26 test season into
      first-half / second-half by calendar date, same fixed fit models.

INVARIANTS: domains-only; <=300 LOC; ASCII; local only; no $/edge claim; reuses
validate_v3.fit_v3/_panel_pit_crps (not reimplemented).
CLI: cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.sim2.replicate_v3
Test: python -m pytest domains/basketball_nba/sim2/test_replicate_v3.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.validate_v3 import fit_v3, _panel_pit_crps, NAMED, LEDGER
from domains.basketball_nba.sim2.cond_composite import all_game_comp_diff, build_comp_thresholds

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_v3_replication.json"
SEED_OFFSETS = [0, 101, 202, 303, 404]
POOLED_TOL = 0.0005
IMPROVED_NAMED = ["P3|m3", "P2|m1"]   # the 2 buckets that improved in the original fold


def check_cross_season_fold_invalid() -> Dict[str, Any]:
    """Empirically confirm the fit=2023-24-only fold cannot fairly test the
    composite (no prior-season profile for 2023-24 -> degenerate thresholds)."""
    gcd_2324 = all_game_comp_diff(["2023-24"])
    thr = build_comp_thresholds(
        pd.DataFrame({"game_id": ["_dummy"], "off_is_home": [True]}), gcd_2324)
    return {"gcd_2023_24_games": len(gcd_2324), "resulting_thresholds": thr,
            "valid_fold": len(gcd_2324) > 0 and thr != [0.0, 0.0]}


def multi_seed_check(art: Dict[str, Any]) -> Dict[str, Any]:
    runs = []
    for off in SEED_OFFSETS:
        panel = _panel_pit_crps(art["test_poss"], art["wide"], art["pcdf2"], art["pcdf3"],
                                 art["dcdf"], art["gcd"], art["comp_thr"], seed_offset=off)
        runs.append({"seed_offset": off, "pooled": panel["pooled"], "named": panel["named"]})
    return {"runs": runs}


def temporal_split_check(art: Dict[str, Any]) -> Dict[str, Any]:
    games = pd.read_parquet(_REPO / "data" / "domains" / "basketball_nba" / "games.parquet")
    games["game_id"] = games["game_id"].astype(str)
    games["date"] = pd.to_datetime(games["date"])
    test_ids = set(art["test_poss"]["game_id"].astype(str).unique())
    g = games[games["game_id"].isin(test_ids)].sort_values("date")
    median_date = g["date"].quantile(0.5, interpolation="nearest")
    first_ids = set(g.loc[g["date"] <= median_date, "game_id"])
    second_ids = set(g.loc[g["date"] > median_date, "game_id"])
    halves = {}
    for name, ids in (("first_half", first_ids), ("second_half", second_ids)):
        sub = art["test_poss"][art["test_poss"]["game_id"].astype(str).isin(ids)]
        panel = _panel_pit_crps(sub, art["wide"], art["pcdf2"], art["pcdf3"],
                                 art["dcdf"], art["gcd"], art["comp_thr"])
        halves[name] = {"n_games": len(ids), "pooled": panel["pooled"], "named": panel["named"]}
    return halves


def _seed_sign_ok(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """>=4/5 seeds must keep each improved-named bucket improved, and pooled v3
    must not exceed pooled v2 by more than POOLED_TOL in any seed."""
    per_bucket_pass = {}
    for k in IMPROVED_NAMED:
        improved = sum(1 for r in runs if r["named"].get(k) and
                       r["named"][k]["pit_dev_v3"] < r["named"][k]["pit_dev_v2"])
        per_bucket_pass[k] = {"seeds_improved": improved, "of": len(runs),
                              "pass": improved >= 4}
    pooled_ok = all(r["pooled"]["pit_dev_v3"] <= r["pooled"]["pit_dev_v2"] + POOLED_TOL
                    for r in runs)
    return {"per_bucket": per_bucket_pass, "pooled_within_tol": pooled_ok,
            "pass": all(v["pass"] for v in per_bucket_pass.values()) and pooled_ok}


def _temporal_sign_ok(halves: Dict[str, Any]) -> Dict[str, Any]:
    """Improved-named buckets must not fully reverse sign in BOTH halves; pooled
    dev must not degrade in either half."""
    per_bucket_pass = {}
    for k in IMPROVED_NAMED:
        signs = []
        for h in ("first_half", "second_half"):
            b = halves[h]["named"].get(k)
            signs.append(b["pit_dev_v3"] < b["pit_dev_v2"] if b else None)
        per_bucket_pass[k] = {"first_half_improved": signs[0], "second_half_improved": signs[1],
                              "pass": any(s for s in signs if s is not None)}
    pooled_ok = all(halves[h]["pooled"]["pit_dev_v3"] <= halves[h]["pooled"]["pit_dev_v2"] + POOLED_TOL
                    for h in ("first_half", "second_half"))
    return {"per_bucket": per_bucket_pass, "pooled_within_tol": pooled_ok,
            "pass": all(v["pass"] for v in per_bucket_pass.values()) and pooled_ok}


def replication_verdict(seed_verdict: Dict[str, Any], temporal_verdict: Dict[str, Any],
                        cross_season: Dict[str, Any]) -> "tuple[str, str]":
    if seed_verdict["pass"] and temporal_verdict["pass"]:
        return "REPLICATED", ("MC-seed and within-season-temporal-split checks both hold the "
                              "sign of the 2 improved named buckets and do not degrade pooled fit.")
    reasons = []
    if not seed_verdict["pass"]:
        reasons.append("seed-unstable: named-bucket improvement or pooled fit did not hold "
                       "across independent MC seeds")
    if not temporal_verdict["pass"]:
        reasons.append("temporal-unstable: named-bucket improvement fully reversed within-season "
                       "or pooled fit degraded in a half")
    return "NULL", ("replication FAILED -- " + "; ".join(reasons) + ". Downgrading from "
                    "MATTERS_PROVISIONAL: the original single-fold bucket improvements do not "
                    "survive seed/temporal robustness checks (likely small-n PIT noise, n~130-330 "
                    "per named bucket).")


def run() -> Dict[str, Any]:
    cross_season = check_cross_season_fold_invalid()
    art = fit_v3()
    seeds = multi_seed_check(art)
    halves = temporal_split_check(art)
    seed_verdict = _seed_sign_ok(seeds["runs"])
    temporal_verdict = _temporal_sign_ok(halves)
    verdict, lesson = replication_verdict(seed_verdict, temporal_verdict, cross_season)

    doc = {
        "hypothesis": "sim2_v3_lineup_composite_conditioner_REPLICATION",
        "edge_claimed": False,
        "evidence_tier": "multi_seed + within_season_temporal_split (no independent "
                         "season-level fold constructible -- see cross_season_fold_check)",
        "cross_season_fold_check": cross_season,
        "multi_seed": {"seed_offsets": SEED_OFFSETS, "runs": seeds["runs"], "verdict": seed_verdict},
        "temporal_split": {"halves": halves, "verdict": temporal_verdict},
        "verdict": verdict, "lesson": lesson,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "hypothesis": "sim2_v3_lineup_composite_conditioner_REPLICATION", "sport": "nba",
            "atomic_unit": "possession_state_cell", "method": "sim2_cond_composite_v1",
            "season": "original_fold_multiseed+temporal_split",
            "seed_verdict_pass": seed_verdict["pass"], "temporal_verdict_pass": temporal_verdict["pass"],
            "verdict": verdict, "lesson": lesson, "edge_claimed": False,
        }) + "\n")
    return doc


def _main() -> int:
    doc = run()
    print("REPLICATION [%s]" % doc["verdict"])
    print("  cross_season_fold_check:", doc["cross_season_fold_check"])
    for k, v in doc["multi_seed"]["verdict"]["per_bucket"].items():
        print("  seed  %-6s improved %d/%d seeds -> pass=%s" % (
            k, v["seeds_improved"], doc["multi_seed"]["seed_offsets"].__len__(), v["pass"]))
    print("  seed pooled_within_tol=%s" % doc["multi_seed"]["verdict"]["pooled_within_tol"])
    for k, v in doc["temporal_split"]["verdict"]["per_bucket"].items():
        print("  half  %-6s first=%s second=%s -> pass=%s" % (
            k, v["first_half_improved"], v["second_half_improved"], v["pass"]))
    print("  temporal pooled_within_tol=%s" % doc["temporal_split"]["verdict"]["pooled_within_tol"])
    print("  lesson:", doc["lesson"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
