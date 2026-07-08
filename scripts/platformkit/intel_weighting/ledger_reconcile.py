"""ledger_reconcile -- mark stale MATTERS_PROVISIONAL rows SUPERSEDED once an
independent-corpus replication of the SAME (family, metric) came back NULL/
UNTESTABLE. weight_ledger.append_results upserts by (family, metric, method),
so a *_replication_* run (a DIFFERENT method) never overwrites the original
walkforward row -- both rows sit in the ledger forever, and the original keeps
advertising MATTERS_PROVISIONAL even after its own replication failed. This
script closes that honesty gap without deleting anything: it only rewrites
the ORIGINAL row's verdict field + adds a note naming the replication row.

Append-only discipline: no row is ever deleted. Atomic tmp-file replace, same
pattern as weight_ledger.append_results / third_season_2023_24's
_append_v2_claim_weights. Reads the ledger FRESH at call time -- other lanes
may append rows to it concurrently.

CLI: python -m scripts.platformkit.intel_weighting.ledger_reconcile
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from scripts.platformkit.intel_weighting.weight_ledger import LEDGER, read_ledger

# a replication run that did NOT reconfirm the original single-fold hit
_FAILED_REPLICATION_VERDICTS = {"NULL", "UNTESTABLE"}
_SUPERSEDED = "MATTERS_PROVISIONAL_SUPERSEDED"


def find_supersessions(rows: List[dict]) -> List[Tuple[dict, dict]]:
    """(original_row, replication_row) pairs where original is still a live
    MATTERS_PROVISIONAL and a same-(family,metric) *_replication_* method row
    came back NULL/UNTESTABLE. Rows are the SAME dict objects passed in (the
    caller mutates them in place after this call)."""
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for r in rows:
        groups.setdefault((r.get("family"), r.get("metric")), []).append(r)

    pairs: List[Tuple[dict, dict]] = []
    for grp in groups.values():
        originals = [r for r in grp if r.get("verdict") == "MATTERS_PROVISIONAL"
                     and "_replication_" not in str(r.get("method", ""))]
        replications = [r for r in grp if "_replication_" in str(r.get("method", ""))
                         and r.get("verdict") in _FAILED_REPLICATION_VERDICTS]
        if not (originals and replications):
            continue
        for orig in originals:
            pairs.append((orig, replications[0]))
    return pairs


def reconcile(ledger: Path | None = None) -> List[dict]:
    """Rewrite superseded rows in place, atomic-replace the ledger file if
    anything changed. Returns the list of rows that were rewritten."""
    ledger = ledger or LEDGER
    rows = read_ledger(ledger)  # fresh read -- other lanes may be appending
    pairs = find_supersessions(rows)
    changed: List[dict] = []
    for orig, repl in pairs:
        orig["verdict"] = _SUPERSEDED
        orig["note"] = (
            f"superseded by method={repl.get('method')} verdict={repl.get('verdict')} "
            f"dm_p={repl.get('dm_p')} (independent-corpus replication of the same "
            f"family/metric did not reconfirm this single-fold MATTERS_PROVISIONAL hit)"
        )
        changed.append(orig)

    if changed:
        tmp = ledger.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="ascii", errors="strict") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        tmp.replace(ledger)
    return changed


def main() -> int:
    changed = reconcile()
    if not changed:
        print("ledger_reconcile: no stale MATTERS_PROVISIONAL rows found -- nothing to supersede")
        return 0
    for r in changed:
        print(f"SUPERSEDED  family={r['family']:<20} metric={r['metric']:<24} "
              f"method={r['method']}  -- {r['note']}")
    print(f"rewrote {len(changed)} row(s) -> {LEDGER}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
