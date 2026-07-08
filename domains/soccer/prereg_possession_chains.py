"""domains.soccer.prereg_possession_chains -- PREREGISTERED (K=1, alpha=0.05,
declared before running) soccer counter-attack premium test on the statsbomb
400-match corpus (data/cache/statsbomb/events + matches -- same load pattern
as claims_formation.build_source, reused via _load_match_lookup).

H1: possessions with play_pattern='From Counter' produce higher xG per
possession than 'Regular Play' possessions, CONTROLLING for team strength via
team fixed effects (a possession-tier pairing died under a match-level
strength control in an earlier check -- H1 counts ONLY with the control in).
Unit = possession (xg = sum of shot statsbomb_xg in that possession, 0 for
shotless possessions -- never dropped). METHOD (declared): OLS on xg,
"xg ~ is_counter" (raw) and "xg ~ is_counter + C(team_id)" (controlled, team
FE), cluster-robust SEs by match_id. DECISION uses the controlled p-value
only; raw is reported alongside for comparison, never as the verdict basis.

REPLICATION: year-disjoint split declared before running (<=2018 vs >=2019 --
this corpus's only fault line; no second source exists, so a within-corpus
split is the honest best available, labelled accordingly in the ledger).
REPLICATED = same sign AND p<0.05 in BOTH halves. n=0 in a half ->
NOT_TESTABLE (an un-run test, not a failed one).

Also emits DESCRIPTIVE soccer_possession_chain_claims.jsonl (data/cache/
intel_claims/): per team with >=30 matches in corpus, xG-per-possession by
play_pattern group (counter/regular/set_piece_derived -- everything besides
From Counter/Regular Play is bucketed as set_piece_derived) + counter share
of possessions, both floored on team_matches>=30 (ponytail: reuses
claims_formation's group_by-as-precomputed-column + min_sample-on-a-derived-
column pattern verbatim -- no new validator feature). Validated via the
existing streaming validate_store machinery.

CLI: python -m domains.soccer.prereg_possession_chains
Per-file test: python -m pytest domains/soccer/test_prereg_possession_chains.py -q
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import statsmodels.formula.api as smf

from domains.basketball_nba.prereg.stats_common import LEDGER_PATH, append_ledger
from domains.soccer.claims_formation import _load_match_lookup
from scripts.platformkit.intel_validation.validate_store import validate_and_write

REPO_ROOT = Path(__file__).resolve().parents[2]
_EVENTS_DIR = REPO_ROOT / "data" / "cache" / "statsbomb" / "events"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_SOURCE_PATH = _OUT_DIR / "soccer_possession_chain_source.parquet"
_CLAIMS_OUT = _OUT_DIR / "soccer_possession_chain_claims.jsonl"

MIN_MATCHES_PER_TEAM = 30  # descriptive-claim team floor (declared)
ALPHA = 0.05  # K=1, declared before running -- not a multi-hypothesis census
YEAR_SPLIT = 2019  # <=2018 vs >=2019, declared before running
METHOD = "soccer_possession_chains_v1"
HYPOTHESIS = "counter_attack_xg_premium"


def _pattern_group(name: Optional[str]) -> str:
    if name == "From Counter":
        return "counter"
    if name == "Regular Play":
        return "regular"
    return "set_piece_derived"  # From Corner/Free Kick/Throw In/Goal Kick/Keeper/Kick Off/Other


def build_possessions(events_dir: Path = _EVENTS_DIR, match_lookup: Optional[dict] = None) -> pd.DataFrame:
    """One row per (match_id, possession): team owning it, play_pattern, and
    summed shot xG (0 if no shot in the possession -- shotless possessions
    are rows, never dropped)."""
    lookup = match_lookup if match_lookup is not None else _load_match_lookup()
    rows: List[dict] = []
    for fn in os.listdir(events_dir):
        match_id = int(fn.replace(".json", ""))
        meta = lookup.get(match_id)
        if meta is None:
            continue
        date = meta.get("match_date")
        year = int(date[:4]) if date else None
        with open(events_dir / fn, encoding="utf-8") as f:
            events = json.load(f)
        for poss_id, grp_iter in itertools.groupby(events, key=lambda e: e.get("possession")):
            if poss_id is None:
                continue
            grp = list(grp_iter)
            team = grp[0].get("possession_team") or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            pattern = (grp[0].get("play_pattern") or {}).get("name")
            xg = sum(
                (e.get("shot") or {}).get("statsbomb_xg") or 0.0
                for e in grp if e.get("type", {}).get("name") == "Shot"
            )
            rows.append({
                "match_id": match_id, "possession": poss_id, "team_id": team_id,
                "team_name": team.get("name"), "play_pattern": pattern, "xg": float(xg), "year": year,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["pattern_group"] = df["play_pattern"].map(_pattern_group)
    df["is_counter"] = (df["pattern_group"] == "counter").astype(int)
    df["team_pattern_key"] = df["team_name"] + "::" + df["pattern_group"]
    df["team_matches"] = df.groupby("team_id")["match_id"].transform("nunique")
    return df


def fit_h1(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """OLS xg~is_counter (raw) and xg~is_counter+C(team_id) (controlled,
    team fixed effects for strength), cluster-robust SEs by match_id --
    both declared before running. None (NOT_TESTABLE) if df has no rows."""
    if len(df) == 0:
        return None
    groups = df["match_id"]
    raw = smf.ols("xg ~ is_counter", data=df).fit(cov_type="cluster", cov_kwds={"groups": groups})
    ctrl = smf.ols("xg ~ is_counter + C(team_id)", data=df).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return {
        "n": int(len(df)),
        "effect_raw": float(raw.params["is_counter"]), "p_raw": float(raw.pvalues["is_counter"]),
        "effect_controlled": float(ctrl.params["is_counter"]), "p_controlled": float(ctrl.pvalues["is_counter"]),
    }


def _h1_subset(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["play_pattern"].isin(["From Counter", "Regular Play"])].copy()


def _ledger_row(split: str, fit: Optional[Dict[str, Any]], note: str = "") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    base = {"hypothesis": HYPOTHESIS, "sport": "soccer", "atomic_unit": "possession",
            "method": METHOD, "split": split, "alpha": ALPHA, "edge_claimed": False, "computed_at": now}
    if fit is None:
        return {**base, "n": 0, "effect": None, "effect_raw": None, "p": None, "p_raw": None,
                "verdict": "NOT_TESTABLE", "note": note or "n=0: no possessions in this split"}
    verdict = "SURVIVES_PREREG" if fit["p_controlled"] < ALPHA else "NULL"
    return {**base, "n": fit["n"], "effect": fit["effect_controlled"], "effect_raw": fit["effect_raw"],
            "p": fit["p_controlled"], "p_raw": fit["p_raw"], "verdict": verdict, "note": note}


def _replication_row(fit1: Optional[Dict[str, Any]], fit2: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    note = "within-corpus year-split replication (<=2018 vs >=2019, no second source available)"
    if fit1 is None or fit2 is None:
        verdict, note = "NOT_TESTABLE", "n=0 in at least one year-split half"
    else:
        same_sign = (fit1["effect_controlled"] > 0) == (fit2["effect_controlled"] > 0)
        both_sig = fit1["p_controlled"] < ALPHA and fit2["p_controlled"] < ALPHA
        verdict = "REPLICATED" if (same_sign and both_sig) else "FAILED_REPLICATION"
    return {"hypothesis": HYPOTHESIS, "sport": "soccer", "atomic_unit": "possession", "method": METHOD,
            "split": "replication_verdict", "n": None, "effect": None, "effect_raw": None, "p": None,
            "p_raw": None, "alpha": ALPHA, "verdict": verdict, "note": note, "edge_claimed": False,
            "computed_at": datetime.now(timezone.utc).isoformat()}


def run_h1(source: pd.DataFrame) -> List[Dict[str, Any]]:
    sub = _h1_subset(source)
    full_fit = fit_h1(sub)
    half1 = sub[sub["year"] <= YEAR_SPLIT - 1]
    half2 = sub[sub["year"] >= YEAR_SPLIT]
    fit1, fit2 = fit_h1(half1), fit_h1(half2)
    rows = [
        _ledger_row("full_corpus", full_fit),
        _ledger_row("year_le_2018", fit1),
        _ledger_row("year_ge_2019", fit2),
        _replication_row(fit1, fit2),
    ]
    append_ledger(rows)
    return rows


# Descriptive claims (kind="ranking", validator-recomputable)
def _ranking_claim(claim_id: str, question: str, metric: str, group_by: str, value_col: str,
                    n_col_expr: str, src_path: Path, table: pd.DataFrame, min_sample: dict,
                    caveats: List[str]) -> Dict[str, Any]:
    qualifiers = table.copy()
    for col, floor in min_sample.items():
        qualifiers = qualifiers[qualifiers[col] >= floor]
    qualifiers = qualifiers.sort_values("_value", ascending=False).reset_index(drop=True)
    ranking = [
        {"rank": i, group_by: row[group_by], "value": round(float(row["_value"]), 4), "n": int(row["n"])}
        for i, row in enumerate(qualifiers.to_dict("records"), start=1)
    ]
    return {
        "claim_id": claim_id, "kind": "ranking", "question": question,
        "criteria": {
            "metric": metric, "formula": f"mean({value_col})",
            "aggregate": {"group_by": group_by, "derived": {"n": n_col_expr, "team_matches": "mean(team_matches)"}},
            "window": "statsbomb_400_match_corpus", "min_sample": min_sample,
            "direction": "desc", "value_precision": 4, "entity_key": group_by,
        },
        "ranking": ranking, "source_files": [_rel(src_path)],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "n_considered": len(table), "n_excluded_below_floor": len(table) - len(qualifiers),
        "edge_claimed": False, "caveats": caveats,
    }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


_CAVEATS = [
    f"team floor: only teams with team_matches>={MIN_MATCHES_PER_TEAM} in the corpus are ranked; "
    "pattern_group='set_piece_derived' buckets everything besides From Counter/Regular Play "
    "(Corner/Free Kick/Throw In/Goal Kick/Keeper/Kick Off/Other) -- a simplification, not a strict taxonomy.",
    "DESCRIPTIVE only -- not causal (see the preregistered H1 test in this module for the strength-"
    "controlled inferential result). No market/$ edge claimed.",
]


def build_claims(source: pd.DataFrame, out_dir: Path = _OUT_DIR) -> List[Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / _SOURCE_PATH.name
    source.to_parquet(src_path, index=False)
    min_sample = {"team_matches": MIN_MATCHES_PER_TEAM}

    xg_table = source.groupby("team_pattern_key").agg(
        _value=("xg", "mean"), n=("xg", "count"), team_matches=("team_matches", "mean"),
    ).reset_index()
    claim1 = _ranking_claim(
        "soccer_possession_chain_xg_per_possession",
        "Which team x play-pattern-group cells have the highest xG per possession (statsbomb 400-match corpus)?",
        "xg_per_possession", "team_pattern_key", "xg", "count(xg)", src_path, xg_table, min_sample, _CAVEATS,
    )

    counter_table = source.groupby("team_name").agg(
        _value=("is_counter", "mean"), n=("is_counter", "count"), team_matches=("team_matches", "mean"),
    ).reset_index()
    claim2 = _ranking_claim(
        "soccer_possession_chain_counter_share",
        "Which teams have the highest share of possessions from counter-attacks (statsbomb 400-match corpus)?",
        "counter_share", "team_name", "is_counter", "count(is_counter)", src_path, counter_table, min_sample, _CAVEATS,
    )
    return [claim1, claim2]


def write_claims(claims: List[Dict[str, Any]], out_path: Path = _CLAIMS_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="ascii", errors="strict") as f:
        for claim in claims:
            f.write(json.dumps(claim) + "\n")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Soccer possession-chain prereg H1 + descriptive claims")
    parser.parse_args(argv)

    source = build_possessions()
    print(f"possessions built: {len(source)} rows, {source['team_id'].nunique() if len(source) else 0} teams")
    ledger_rows = run_h1(source)
    print(f"K=1 alpha={ALPHA} (soccer counter-attack xG premium)")
    for r in ledger_rows:
        print(f"  [{r['verdict']:>18}] split={r['split']}: n={r['n']} effect={r['effect']} "
              f"effect_raw={r.get('effect_raw')} p={r['p']} p_raw={r.get('p_raw')}")
    print(f"appended {len(ledger_rows)} rows -> {LEDGER_PATH}")

    claims = build_claims(source)
    out_path = write_claims(claims)
    print(f"wrote {len(claims)} claims -> {out_path}")
    for claim in claims:
        print(f"{claim['claim_id']}: n_considered={claim['n_considered']} "
              f"n_excluded={claim['n_excluded_below_floor']} n_ranked={len(claim['ranking'])}")
    result = validate_and_write(str(_CLAIMS_OUT))
    print(f"validate_store: {result['n_verified']}/{result['n_claims']} verified, "
          f"{result['n_mismatch']} mismatch, {result['n_unverifiable']} unverifiable -> {result['out']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
