"""scripts.platformkit.gap_ledger -- where are we measured, and where are we blind?

The beat-the-close scoreboard answers "how good are the cells we measure?". This answers
the prior question: "which cells exist at all, and which have never been scored?" Absence
is the thing a scoreboard structurally cannot show, so it is declared by hand in
`gap_ledger_cells.tsv` and classified here.

Status is DERIVED, never stored:
  MEASURED       harness declared and present on disk
  HARNESS-MISSING  harness declared but the file is gone (drift/typo -- fix it)
  QUEUED         benchmark named, no harness yet -> the research queue
  NO-BENCHMARK   no benchmark defined -> cannot be scored; define one first

A cell with no benchmark is not a modelling problem, it is a measurement-design problem.
Naming that distinction is the whole point of this file.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; calibration/accuracy only, no $ edge.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
_CELLS = Path(__file__).with_name("gap_ledger_cells.tsv")

MEASURED = "MEASURED"
HARNESS_MISSING = "HARNESS-MISSING"
QUEUED = "QUEUED"
NO_BENCHMARK = "NO-BENCHMARK"

_ORDER = (MEASURED, HARNESS_MISSING, QUEUED, NO_BENCHMARK)


def load_cells(path: Path = None) -> List[Dict[str, str]]:
    """Read the declarative TSV, skipping the leading '>' comment block."""
    src = path or _CELLS
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith(">")]
    return list(csv.DictReader(lines, delimiter="\t"))


def classify(cell: Dict[str, str], repo: Path = None) -> str:
    """Derive status from what the cell declares and what is actually on disk."""
    root = repo or _REPO
    harness = (cell.get("harness") or "").strip()
    kind = (cell.get("benchmark_kind") or "none").strip().lower()
    if harness:
        return MEASURED if (root / harness).exists() else HARNESS_MISSING
    return NO_BENCHMARK if kind == "none" else QUEUED


def build(path: Path = None, repo: Path = None) -> List[Dict[str, str]]:
    rows = load_cells(path)
    for r in rows:
        r["status"] = classify(r, repo)
    return rows


def counts(rows: List[Dict[str, str]]) -> Dict[str, int]:
    return {s: sum(1 for r in rows if r["status"] == s) for s in _ORDER}


def render_markdown(rows: List[Dict[str, str]]) -> str:
    c = counts(rows)
    L = ["# Gap Ledger -- coverage of the prediction surface", "",
         "> Which (sport x question x regime) cells exist, and which have never been scored. "
         "MEASURED cells get their numbers from the beat-the-close scoreboard and the crps_market "
         "benchmarks; this table is about COVERAGE, not accuracy. A NO-BENCHMARK cell cannot be "
         "scored until a benchmark is defined -- that is measurement design, not modelling.", "",
         f"**{c[MEASURED]} measured | {c[QUEUED]} queued | {c[NO_BENCHMARK]} need a benchmark"
         f" | {c[HARNESS_MISSING]} broken**", "",
         "| Sport | Question | Regime | Status | Benchmark | Note |", "|---|---|---|---|---|---|"]
    rank = {s: i for i, s in enumerate(_ORDER)}
    for r in sorted(rows, key=lambda x: (rank[x["status"]], x["sport"], x["question"])):
        bench = r.get("benchmark") or ("--" if r["status"] == NO_BENCHMARK else "")
        L.append(f"| {r['sport']} | {r['question']} | {r['regime']} | {r['status']} | "
                 f"{bench} | {r.get('note','')} |")
    L += ["", "**How to use it:** QUEUED cells are the research queue -- each needs a harness "
          "before any claim about it counts. NO-BENCHMARK cells are the deeper gap: pick a "
          "benchmark kind (baseline, published, or a specified null) before spending model time, "
          "or the result will be ungradeable. HARNESS-MISSING means this file drifted from the "
          "repo and should be fixed now."]
    return "\n".join(L)


def _main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="Gap ledger (coverage of the prediction surface).")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any declared harness path is missing from the repo")
    args = ap.parse_args(argv)
    rows = build()
    print(render_markdown(rows))
    if args.check:
        broken = [r for r in rows if r["status"] == HARNESS_MISSING]
        for r in broken:
            print(f"MISSING HARNESS: {r['sport']} / {r['question']} -> {r['harness']}")
        return 1 if broken else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
