"""scripts.platformkit.improve.prop_history_meta -- read-only META-AGGREGATOR over the
accumulated historical prop-calibration folds.

WHY: each prop_history fold (NBA + the MLB/tennis/soccer multisport folds) is ONE leak-free
calibration verdict from a FRESH random player sample. A single fold's SHIP can be a
selection artifact (the "single-fold lifts are artifacts; need >= 2 independent corpora"
discipline). This module reads every source=history row in prop_improve_ledger.jsonl, groups
them by (sport, stat) and reports the REPLICATED verdict -- a verdict that only counts as
SHIP-worthy when it holds across >= 2 independent folds with NO reject and NO planted-null
leak. The overnight loop accrues folds; this report sharpens with them.

DO-NO-HARM / honesty: this is READ-ONLY -- it never recalibrates, never serves, never arms
a flag, never writes a corpus or data/registry/. It only summarizes the ledger to a read
surface (prop_history_meta.json). A SHIP_REPLICATED is a calibration verdict, NOT a $ edge
or a market-beating claim (calibration != edge). Any fold whose planted null shipped, or any
REJECT in a group, blocks the whole group from SHIP_REPLICATED. Build only under
scripts/platformkit/; <=300 LOC; ASCII.
CLI: python -m scripts.platformkit.improve.prop_history_meta
Per-file test: scripts/platformkit/improve/test_prop_history_meta.py
"""
from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("prop_history_meta")

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
DEFAULT_LEDGER = _REPO / "data" / "frontend" / "prop_improve_ledger.jsonl"
DEFAULT_OUT = _REPO / "data" / "frontend" / "prop_history_meta.json"

MIN_REPLICATION = 2  # >= 2 independent folds before a SHIP counts as replicated (not artifact)
CALIBRATION_NOTE = ("calibration != edge: a replicated SHIP means better-calibrated "
                    "probabilities across folds, NOT beating the market close or any $ edge")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with Path(path).open(encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return out


def load_history_folds(ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every source=history fold record in the prop improve ledger."""
    rows = _read_jsonl(Path(ledger_path) if ledger_path else DEFAULT_LEDGER)
    return [r for r in rows if str(r.get("source", "")) == "history"]


def _group_key(rec: Dict[str, Any]) -> tuple:
    return (str(rec.get("sport", "?")).lower(), str(rec.get("stat", "ALL")).lower())


def _replicated_verdict(verdicts: Sequence[str], ship_n: int,
                        any_null_leak: bool) -> str:
    """Conservative, do-no-harm replication rule.

    - any REJECT or any planted-null leak in the group -> REJECT (blocks SHIP).
    - >= MIN_REPLICATION SHIPs and no reject -> SHIP_REPLICATED.
    - exactly one SHIP -> SHIP_SINGLE_FOLD (artifact-suspect; NOT shippable).
    - any HOLD and no ship -> HOLD.
    - otherwise (all insufficient/empty) -> INSUFFICIENT_DATA.
    """
    if any_null_leak or any(v == "REJECT" for v in verdicts):
        return "REJECT"
    if ship_n >= MIN_REPLICATION:
        return "SHIP_REPLICATED"
    if ship_n == 1:
        return "SHIP_SINGLE_FOLD"
    if any(v == "HOLD" for v in verdicts):
        return "HOLD"
    return "INSUFFICIENT_DATA"


def aggregate(folds: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group folds by (sport, stat) and compute the replicated verdict per group."""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in folds:
        groups.setdefault(_group_key(rec), []).append(rec)
    out: List[Dict[str, Any]] = []
    for (sport, stat), recs in sorted(groups.items()):
        verdicts = [str(r.get("verdict", r.get("status", "?"))) for r in recs]
        ship_n = sum(1 for v in verdicts if v == "SHIP")
        deltas = [r["delta_brier"] for r in recs
                  if isinstance(r.get("delta_brier"), (int, float))]
        any_null_leak = any(r.get("null_shipped") is True for r in recs)
        vc: Dict[str, int] = {}
        for v in verdicts:
            vc[v] = vc.get(v, 0) + 1
        out.append({
            "sport": sport,
            "stat": stat,
            "n_folds": len(recs),
            "verdict_counts": vc,
            "ship_folds": ship_n,
            "median_delta_brier": (round(statistics.median(deltas), 6) if deltas else None),
            "any_planted_null_leak": any_null_leak,
            "replicated_verdict": _replicated_verdict(verdicts, ship_n, any_null_leak),
        })
    return out


def build_report(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    folds = load_history_folds(ledger_path)
    groups = aggregate(folds)
    return {
        "schema_version": "1.0.0",
        "n_history_folds": len(folds),
        "n_groups": len(groups),
        "min_replication": MIN_REPLICATION,
        "groups": groups,
        "note": CALIBRATION_NOTE,
        "honest": "READ-ONLY; PROPOSE/RECORD only; no serving armed; no $; single-fold=artifact",
    }


def write_report(report: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    out_path = Path(out_path) if out_path else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path


def _print_report(report: Dict[str, Any]) -> None:
    print()
    print("PROP HISTORY META -- replicated calibration verdict per (sport, stat)")
    print("-" * 78)
    print("history_folds=%s groups=%s min_replication=%s"
          % (report["n_history_folds"], report["n_groups"], report["min_replication"]))
    hdr = "%-8s%-12s%6s%7s  %-18s%s" % (
        "sport", "stat", "folds", "ships", "replicated", "med_dBrier")
    print(hdr)
    for g in report["groups"]:
        print("%-8s%-12s%6s%7s  %-18s%s" % (
            g["sport"], g["stat"], g["n_folds"], g["ship_folds"],
            g["replicated_verdict"], g["median_delta_brier"]))
    print(report["note"])


def run(ledger_path: Optional[Path] = None,
        out_path: Optional[Path] = None, write: bool = True) -> Dict[str, Any]:
    report = build_report(ledger_path)
    if write:
        try:
            write_report(report, out_path)
        except Exception as exc:  # noqa: BLE001 -- a read surface write must never raise out
            logger.debug("meta report write failed: %s", exc)
    return report


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Read-only meta-aggregator over history folds.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    report = run(write=not a.no_write)
    _print_report(report)
    return 0


__all__ = [
    "load_history_folds", "aggregate", "build_report", "write_report", "run",
    "MIN_REPLICATION", "DEFAULT_LEDGER", "DEFAULT_OUT",
]


if __name__ == "__main__":
    raise SystemExit(_main())
