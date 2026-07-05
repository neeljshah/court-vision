"""Coverage scoreboard over every VERIFIED claim ask() can currently answer
from -- per sport x dimension: rows, entities, floor, excluded-below-floor,
store file, mtime; plus totals per sport and a grand total.

This is a READ-ONLY report over ask.load_verified_claims()'s existing
discovery (scripts.platformkit.intel_query.ask), which itself glob-discovers
every (validation-summary, producer-claims) pair under
data/cache/intel_claims/*.jsonl. Nothing here re-implements or second-guesses
the independent claims_validator -- a claim_id absent here is either not
VERIFIED yet or has no ranking/verdict content to summarize, exactly as
ask() itself would report it (honest UNANSWERABLE), never silently treated
as passing.

sport is the claim_id's leading token (e.g. "nba_..." -> "nba",
"tennis_..." -> "tennis") -- the same convention every producer module in
this lane already follows for claim_id naming.

dimension is:
  - ranking claims: criteria.metric (the descriptive quantity ranked)
  - verdict claims: gate_module (the gate/hypothesis this verdict covers)
so two different windows of the SAME metric (e.g. hold_pct_asof for ATP vs
WTA) are reported as separate ROWS under one dimension, matching how ask()
itself treats them (two distinct VERIFIED claim_ids, same metric).

rows = len(claim["ranking"]) -- what ask() can ACTUALLY return a ranking
       entry for today (a store may cap at top-N even when more entities
       clear the floor, e.g. the legacy *_top50_* claims).
entities = n_considered - n_excluded_below_floor -- the full population that
       cleared the claim's own min_sample floor (may exceed `rows` under a
       top-N cap; the gap is never silently hidden, both numbers print).

CLI:
    python -m scripts.platformkit.intel_query.claims_coverage_report
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit.intel_query.ask import (
    CLAIM_SOURCE_PAIRS,
    REPO_ROOT,
    _display_path,
    load_verified_claims,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "cache" / "intel_claims" / "coverage_report.json"


def _sport_of(claim_id: str) -> str:
    """Leading snake_case token of claim_id -- e.g. 'nba_fit_..' -> 'nba'.
    Falls back to the full claim_id if it has no underscore (never crashes
    on a malformed/unexpected id -- degrades to its own one-row 'sport')."""
    return claim_id.split("_", 1)[0] if "_" in claim_id else claim_id


def _dimension_of(row: dict[str, Any]) -> str:
    """ranking claims key off criteria.metric; verdict claims (no metric)
    key off gate_module; anything else falls back to claim_kind:kind so it
    still gets its own bucket rather than silently merging into another
    dimension."""
    if row.get("kind") == "ranking":
        metric = row.get("criteria", {}).get("metric")
        if metric:
            return str(metric)
    if row.get("kind") == "verdict":
        gate_module = row.get("gate_module")
        if gate_module:
            return str(gate_module)
    return f"claim_kind:{row.get('kind')}"


def _mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def build_coverage_report() -> dict[str, Any]:
    """One row per VERIFIED claim_id, grouped sport -> dimension -> rows,
    plus a per-sport and grand total. Every claim currently visible to
    ask() appears exactly once; nothing here filters claims ask() itself
    would answer from."""
    verified = load_verified_claims()

    # store_file -> mtime, resolved once (a claim's _producer_source is a
    # repo-relative string; re-resolve it against REPO_ROOT for stat()).
    producer_paths = {c for _v, c in CLAIM_SOURCE_PAIRS}
    mtime_by_display: dict[str, str | None] = {
        _display_path(p): _mtime_iso(p) for p in producer_paths
    }

    sports: dict[str, dict[str, Any]] = {}
    for claim_id, row in sorted(verified.items()):
        sport = _sport_of(claim_id)
        dimension = _dimension_of(row)
        n_considered = row.get("n_considered")
        n_excluded = row.get("n_excluded_below_floor")
        entities = (
            n_considered - n_excluded
            if isinstance(n_considered, int) and isinstance(n_excluded, int)
            else None
        )
        rows_emitted = len(row.get("ranking", [])) if row.get("kind") == "ranking" else None
        store_file = row.get("_producer_source")

        claim_entry = {
            "claim_id": claim_id,
            "kind": row.get("kind"),
            "rows": rows_emitted,
            "entities": entities,
            "n_considered": n_considered,
            "excluded_below_floor": n_excluded,
            "floor": row.get("criteria", {}).get("min_sample") if row.get("kind") == "ranking" else None,
            "store_file": store_file,
            "store_mtime": mtime_by_display.get(store_file),
            "validator_source": row.get("_validator_source"),
        }

        sport_bucket = sports.setdefault(
            sport, {"dimensions": {}, "totals": {"rows": 0, "entities": 0, "excluded_below_floor": 0, "n_claims": 0}}
        )
        dim_bucket = sport_bucket["dimensions"].setdefault(dimension, {"claims": []})
        dim_bucket["claims"].append(claim_entry)

        sport_bucket["totals"]["n_claims"] += 1
        sport_bucket["totals"]["rows"] += rows_emitted or 0
        sport_bucket["totals"]["entities"] += entities or 0
        sport_bucket["totals"]["excluded_below_floor"] += n_excluded or 0

    grand_total = {
        "n_sports": len(sports),
        "n_claims": sum(s["totals"]["n_claims"] for s in sports.values()),
        "rows": sum(s["totals"]["rows"] for s in sports.values()),
        "entities": sum(s["totals"]["entities"] for s in sports.values()),
        "excluded_below_floor": sum(s["totals"]["excluded_below_floor"] for s in sports.values()),
        "n_claim_source_pairs_discovered": len(CLAIM_SOURCE_PAIRS),
    }

    return {
        "component": "claims_coverage_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sports": sports,
        "grand_total": grand_total,
    }


def write_report(report: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="ascii", errors="strict") as f:
        json.dump(report, f, indent=2)


def print_summary(report: dict[str, Any]) -> None:
    """ASCII CLI summary -- one line per sport x dimension, then totals."""
    print(f"claims_coverage_report generated_at={report['generated_at']}")
    for sport in sorted(report["sports"]):
        bucket = report["sports"][sport]
        totals = bucket["totals"]
        print(
            f"[{sport}] n_claims={totals['n_claims']} rows={totals['rows']} "
            f"entities={totals['entities']} excluded_below_floor={totals['excluded_below_floor']}"
        )
        for dimension in sorted(bucket["dimensions"]):
            for claim in bucket["dimensions"][dimension]["claims"]:
                print(
                    f"    {dimension} :: {claim['claim_id']} "
                    f"rows={claim['rows']} entities={claim['entities']} "
                    f"floor={claim['floor']} store={claim['store_file']} mtime={claim['store_mtime']}"
                )
    gt = report["grand_total"]
    print(
        f"GRAND TOTAL: n_sports={gt['n_sports']} n_claims={gt['n_claims']} rows={gt['rows']} "
        f"entities={gt['entities']} excluded_below_floor={gt['excluded_below_floor']} "
        f"n_claim_source_pairs_discovered={gt['n_claim_source_pairs_discovered']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-sport x dimension VERIFIED-claims coverage report")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    report = build_coverage_report()
    write_report(report, Path(args.output))
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
