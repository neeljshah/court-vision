"""predictions-validate-intelligence seam (report-only).

Enumerates (sport, attribute, family) triples whose attribute_registry declares
a weight_ledger_family, then reports which families already have a row in the
weight ledger (data/cache/intel_claims/claim_weights.jsonl) and which are
UNWEIGHTED -- the queue for future gate runs. Runs NO gates.
"""
from __future__ import annotations

import argparse
import json
import os

from scripts.platformkit.profiles.ask import SPORTS, load_registry

LEDGER_PATH = os.path.join("data", "cache", "intel_claims", "claim_weights.jsonl")


def profile_families(sports=None) -> list[tuple[str, str, str]]:
    """(sport, attribute, weight_ledger_family) for every registered attribute
    that declares a weight_ledger_family."""
    out = []
    for sport in (sports or SPORTS):
        for attr, spec in load_registry(sport).items():
            fam = spec.get("weight_ledger_family")
            if fam:
                out.append((sport, attr, fam))
    return out


def ledger_families(path: str = LEDGER_PATH) -> set[str]:
    fams: set[str] = set()
    if not os.path.exists(path):
        return fams
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                fam = json.loads(line).get("family")
            except Exception:
                continue
            if fam:
                fams.add(fam)
    return fams


def coverage(sports=None, ledger_path: str = LEDGER_PATH):
    """Return (weighted, unweighted) lists of (sport, attribute, family)."""
    have = ledger_families(ledger_path)
    weighted, unweighted = [], []
    for row in profile_families(sports):
        (weighted if row[2] in have else unweighted).append(row)
    return weighted, unweighted


def report(sports=None, ledger_path: str = LEDGER_PATH) -> str:
    weighted, unweighted = coverage(sports, ledger_path)
    total = len(weighted) + len(unweighted)
    L = [f"Weight-ledger coverage: {len(weighted)}/{total} registered families weighted",
         "", "WEIGHTED (has a claim_weights row):"]
    L += [f"  [{s}] {a} -> {f}" for s, a, f in weighted] or ["  (none)"]
    L += ["", "UNWEIGHTED (queue for future gate runs):"]
    L += [f"  [{s}] {a} -> {f}" for s, a, f in unweighted] or ["  (none)"]
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description="Report weight-ledger coverage of registered profile families (report-only).")
    p.add_argument("--sport")
    p.add_argument("--ledger", default=LEDGER_PATH)
    a = p.parse_args(argv)
    print(report([a.sport] if a.sport else None, a.ledger))


if __name__ == "__main__":
    main()
