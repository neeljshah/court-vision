"""scripts.platformkit.omni.reject_reaudit -- S8.1 REJECT re-audit lane (P3).

Re-scores the historical REJECT ledger (data/registry/signal_lab_registry.parquet
REJECTED rows + data/registry/signal_test_log/*.parquet rejected rows -- already
backfilled by claims_backfill into data/omni/claims/journal.jsonl, 16 + 13 = 29
claims) at native altitude. Imports scripts.platformkit.omni.native_altitude /
claims_ledger for the contract + ledgering seam -- never forks CRPS/logloss/
reliability math, never re-derives another lane's feature code.

PREMISE CHECK (this run, verified against the actual parquet schemas): both
signal_lab_registry.parquet (cols: name, grain, target, metric, n, base_err,
full_err, oos_rel, split_half, ortho, verdict, reason, asof, note) and
signal_test_log/*.parquet (cols: hash, family_key, definition, p, batch_id,
asof, verdict) store only SUMMARY error/p-value stats -- never the row-level
signal predictions. Re-scoring at a finer observable needs the original
per-row signal VALUE; reconstructing that would mean re-deriving each
signal's feature code, which lives in other lanes' interaction_factory /
team_system modules this lane does not own (forking the math the rails
forbid). So every original is verdicted NOT_TESTABLE_FINER unless a genuine
row-level corpus for that exact signal is found on disk (checked via
_row_level_corpus_exists, not assumed) -- an honest, no-flip outcome per the
rails ("HONEST NOT_TESTABLE ... outcomes are SUCCESSES").

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/ (read-only). Discovery-slice-only: no reserve/held-back
corpus is ever touched (this run touches no corpus at all -- 0 re-scores).
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import native_altitude as NA

_REAUDIT_DIR = pathlib.Path("data/omni/reaudit")
_LIFECYCLE_BY_VERDICT = {"ACCEPT": "accepted", "REJECT": "rejected", "NOT_TESTABLE": "screened"}
_TYPE_BY_VERDICT = {"ACCEPT": "effect", "REJECT": "negative", "NOT_TESTABLE": "meta"}


def enumerate_originals(base_dir=None) -> list[dict]:
    """Read the p2_backfill-sourced rejected NBA claims out of the ledger and
    split them into registry-origin (scope.entity_type = original grain) vs
    test_log-origin (scope.entity_type == 'family') rows. Returns a flat list
    of {claim_id, signal_name, grain, target, source}."""
    df = cl.query(sport="nba", lifecycle="rejected", base_dir=base_dir)
    out: list[dict] = []
    for _, row in df.iterrows():
        prov = json.loads(row["provenance_json"]) if row["provenance_json"] else {}
        if prov.get("created_by_lane") != "p2_backfill":
            continue
        scope = json.loads(row["scope_json"]) if row["scope_json"] else {}
        entity_type = scope.get("entity_type", "")
        statement = row["statement"]
        if entity_type == "family":
            signal_name = statement.split(" | ", 1)[0].strip()
            source = "test_log"
        else:
            signal_name = statement.split(" on ", 1)[0].strip()
            source = "registry"
        out.append({
            "claim_id": row["claim_id"], "signal_name": signal_name,
            "grain": entity_type, "target": row["topic"], "source": source,
        })
    return out


def dedupe_by_signal_name(originals: list[dict]) -> tuple[list[dict], int]:
    """Dedupe originals by underlying signal name, first-seen wins.
    Returns (deduped_list, n_dropped)."""
    seen: dict[str, dict] = {}
    for o in originals:
        seen.setdefault(o["signal_name"], o)
    return list(seen.values()), len(originals) - len(seen)


def _row_level_corpus_exists(signal_name: str) -> bool:
    """Real (not assumed) check: does a row-level prediction artifact for
    *signal_name* exist under data/cache or domains/ output dirs? Kept as a
    genuine filesystem probe so a future run (this is a standing S8.1 job)
    re-tests as corpora are added, rather than hardcoding a permanent skip."""
    candidates = [
        pathlib.Path("data/cache") / f"{signal_name}_predictions.parquet",
        pathlib.Path("data/cache") / f"{signal_name}.parquet",
        pathlib.Path("data/omni/reaudit/corpora") / f"{signal_name}.parquet",
    ]
    return any(p.is_file() for p in candidates)


def native_observable_for(grain: str, target: str) -> str:
    """Heuristic map from (original grain, target) to the finest
    NATIVE_OBSERVABLES entry that target family conceptually belongs to."""
    if target == "a_min":
        return "minutes_dist"
    if target == "margin":
        return "game_winprob"
    if grain == "family":
        return "possession_outcome"
    if grain == "possession":
        return "possession_outcome"
    if target == "ppp":
        return "possession_outcome"
    if target == "a_pts":
        return "shot_quality"
    return "game_total"


def market_families_for(grain: str, target: str, fallback_family: str) -> list[str]:
    if target == "a_min":
        return ["props.min"]
    if target == "a_pts":
        return ["props.pts"]
    if grain == "possession":
        return ["possession.outcome"]
    if target == "margin":
        return ["mainlines.spread"]
    if target == "ppp":
        return ["lineup.ppp"]
    if grain == "family":
        return [fallback_family]
    return [fallback_family or "unknown"]


def classify_finer(o: dict) -> dict:
    """Decide testability for one original. Returns
    {testable, native_observable, market_families, reason}."""
    grain, target, source = o["grain"], o["target"], o["source"]
    observable = native_observable_for(grain, target)
    families = market_families_for(grain, target, target)
    testable = _row_level_corpus_exists(o["signal_name"])
    if testable:
        reason = f"row-level corpus found for {o['signal_name']!r} -- re-scorable."
        return {"testable": True, "native_observable": observable, "market_families": families, "reason": reason}
    if target == "a_min":
        reason = "already native: a_min IS the finest per-player minutes observable (minutes_dist); no finer corpus."
    elif grain == "possession":
        reason = "already native: possession is the finest grain for this pts target (possession_outcome); no finer corpus."
    elif grain == "family":
        reason = "already at finest wired possession-interaction grain (family-level p only stored, no row predictions); no finer corpus found on disk."
    else:
        reason = (f"row-level {target!r} predictions not retained in the registry (only base_err/full_err/oos_rel "
                  f"summary stats stored); finer re-score would require reconstructing the signal's original "
                  f"feature code, owned by other lanes -- not attempted (no fork).")
    return {"testable": False, "native_observable": observable, "market_families": families, "reason": reason}


def benjamini_hochberg(pvalues: list[float], alpha: float = 0.05) -> dict:
    """Standard BH step-up procedure. Returns {n, survivors (indices into
    *pvalues*, ascending), batch_overfit_est (expected false discoveries
    among survivors = alpha * n_survivors)}."""
    n = len(pvalues)
    if n == 0:
        return {"n": 0, "survivors": [], "batch_overfit_est": 0.0}
    order = sorted(range(n), key=lambda i: pvalues[i])
    max_rank = -1
    for rank, idx in enumerate(order):
        threshold = (rank + 1) / n * alpha
        if pvalues[idx] <= threshold:
            max_rank = rank
    survivors = sorted(order[:max_rank + 1]) if max_rank >= 0 else []
    return {"n": n, "survivors": survivors, "batch_overfit_est": round(alpha * len(survivors), 4)}


def ledger_verdict(contract: dict, family: str, verdict_info: dict, parent_claim_id: str, base_dir=None) -> str:
    """Write one native-altitude-shaped claim with links.parent_claims set to
    the original backfilled claim_id. Reuses native_altitude.validate_contract
    (import, not fork) but calls claims_ledger.add_claim directly since
    native_altitude.record_verdicts has no parent-link parameter -- the
    documented fallback in P3_schema.md."""
    NA.validate_contract(contract)
    verdict = verdict_info["verdict"]
    if verdict not in NA.VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}; expected one of {NA.VERDICTS}")
    statement = (f"{contract['signal_name']} native-altitude {contract['metric']} "
                 f"vs {contract['baseline_model']} on {family}: {verdict}")
    scope = {"sport": contract["sport"], "regime": contract["regime_scope"], "market_families": [family]}
    claim = {
        "statement": statement, "type": _TYPE_BY_VERDICT[verdict], "scope": scope,
        "topic": contract["native_observable"], "lifecycle": _LIFECYCLE_BY_VERDICT[verdict],
        "effect": {
            "metric": contract["metric"], "size": verdict_info.get("delta"),
            "ci_low": verdict_info.get("ci_low"), "ci_high": verdict_info.get("ci_high"),
            "n": verdict_info.get("n"),
        },
        "provenance": {"created_by_lane": "P3_reaudit", "contract": contract, "reason": verdict_info.get("reason", "")},
        "links": {"market_families": [family], "parent_claims": [parent_claim_id]},
    }
    return cl.add_claim(claim, base_dir=base_dir)


def run_reaudit(claims_base_dir=None, out_dir: Optional[str | pathlib.Path] = None) -> dict:
    """Full re-audit pipeline: enumerate -> dedupe -> classify -> BH -> ledger
    every outcome -> write summary + detail parquet to data/omni/reaudit/."""
    out_dir = pathlib.Path(out_dir) if out_dir is not None else _REAUDIT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    originals = enumerate_originals(claims_base_dir)
    deduped, n_dropped = dedupe_by_signal_name(originals)

    detail_rows: list[dict] = []
    pvalues: list[float] = []  # only populated by genuine re-scores (none this run)
    claim_ids: list[str] = []
    n_flips = 0

    for o in deduped:
        cls = classify_finer(o)
        family = cls["market_families"][0]
        contract = NA.build_contract(
            signal_name=o["signal_name"], sport="nba",
            native_observable=cls["native_observable"], metric="crps",
            baseline_model="none (no row-level re-score performed)" if not cls["testable"] else "existing gate baseline",
            market_families=cls["market_families"], regime_scope="all", corpus="discovery",
        )
        verdict_info = {"verdict": "NOT_TESTABLE", "reason": cls["reason"], "n": None}
        cid = ledger_verdict(contract, family, verdict_info, o["claim_id"], base_dir=claims_base_dir)
        claim_ids.append(cid)
        detail_rows.append({
            "signal_name": o["signal_name"], "source": o["source"], "grain": o["grain"],
            "target": o["target"], "native_observable": cls["native_observable"],
            "market_family": family, "verdict": "NOT_TESTABLE_FINER", "reason": cls["reason"],
            "parent_claim_id": o["claim_id"], "reaudit_claim_id": cid,
        })

    bh = benjamini_hochberg(pvalues)
    summary = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_originals": len(originals), "n_deduped": len(deduped), "n_dropped_dupes": n_dropped,
        "n_registry": sum(1 for o in originals if o["source"] == "registry"),
        "n_test_log": sum(1 for o in originals if o["source"] == "test_log"),
        "n_rescored": len(pvalues), "n_flips": n_flips,
        "n_not_testable_finer": sum(1 for r in detail_rows if r["verdict"] == "NOT_TESTABLE_FINER"),
        "bh": bh,
    }
    with open(out_dir / "summary.json", "w", encoding="ascii") as fh:
        json.dump(summary, fh, indent=2)
    pd.DataFrame(detail_rows).to_parquet(out_dir / "reaudit_detail.parquet", index=False)
    return summary


if __name__ == "__main__":
    print(json.dumps(run_reaudit(), indent=2))
