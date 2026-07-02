"""data_registry.inventory -- scan per-sport corpora, persist census, detect drift.

Metadata-only scan of data/domains/<sport>/*.parquet (reads parquet footers, never
row data). Produces data_registry/_INVENTORY.json and a fail-closed health check
that blocks on 0-row corpora, vanished corpora, removed columns, or row regression
versus a stored baseline.

CLI:
  python -m data_registry.inventory scan            # build + write baseline, print summary
  python -m data_registry.inventory check           # build, diff vs baseline, exit 2 if blocked

Pure offline. No src/kernel/api imports. ASCII only. NEVER writes data/registry/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import pyarrow.parquet as pq

from data_registry.schema import (
    SEV_BLOCK,
    SEV_WARN,
    CensusRow,
    DriftFinding,
    make_census_row,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ROOT = "data/domains"
_DEFAULT_OUT = "data_registry/_INVENTORY.json"
_ROW_REGRESSION_TOL = 0.10  # >10% fewer rows than baseline -> block


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def _arrow_columns(path: Path) -> Dict[str, str]:
    schema = pq.ParquetFile(str(path)).schema_arrow
    return {name: str(schema.field(name).type) for name in schema.names}


def _num_rows(path: Path) -> int:
    return int(pq.ParquetFile(str(path)).metadata.num_rows)


def scan_corpora(root: str = _DEFAULT_ROOT, sports: Optional[List[str]] = None) -> List[CensusRow]:
    """Scan ``root``/<sport>/*.parquet via parquet footers; return one row per file.

    A file whose footer cannot be read is recorded as an empty (0-row) corpus so the
    fail-closed gate flags it rather than silently dropping it.
    """
    base = (_REPO_ROOT / root) if not os.path.isabs(root) else Path(root)
    rows: List[CensusRow] = []
    if not base.exists():
        return rows
    for sport_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        sport = sport_dir.name
        if sports is not None and sport not in sports:
            continue
        for pq_path in sorted(sport_dir.glob("*.parquet")):
            try:
                rel = pq_path.relative_to(_REPO_ROOT).as_posix()
            except ValueError:  # root outside the repo (e.g. a tmp dir in tests)
                rel = pq_path.as_posix()
            try:
                cols = _arrow_columns(pq_path)
                nrows = _num_rows(pq_path)
            except Exception as exc:  # unreadable footer -> treat as empty, flagged later
                rows.append(make_census_row(sport, pq_path.stem, rel, 0, {"_unreadable": str(exc)[:40]}))
                continue
            rows.append(make_census_row(sport, pq_path.stem, rel, nrows, cols))
    return rows


def build_inventory(root: str = _DEFAULT_ROOT, sports: Optional[List[str]] = None) -> dict:
    rows = scan_corpora(root, sports)
    sport_set = sorted({r.sport for r in rows})
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "root": root,
        "n_corpora": len(rows),
        "sports": sport_set,
        "rows": [r.to_dict() for r in rows],
    }


# --------------------------------------------------------------------------- #
# Persist (atomic) / load
# --------------------------------------------------------------------------- #
def write_inventory(inv: dict, path: str = _DEFAULT_OUT) -> Path:
    dest = (_REPO_ROOT / path) if not os.path.isabs(path) else Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            json.dump(inv, fh, indent=2, sort_keys=True, ensure_ascii=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dest


def load_inventory(path: str = _DEFAULT_OUT) -> Optional[dict]:
    src = (_REPO_ROOT / path) if not os.path.isabs(path) else Path(path)
    if not src.exists():
        return None
    with open(src, "r", encoding="ascii") as fh:
        return json.load(fh)


def _rows_from_inventory(inv: dict) -> Dict[tuple, CensusRow]:
    return {(r["sport"], r["name"]): CensusRow.from_dict(r) for r in inv.get("rows", [])}


# --------------------------------------------------------------------------- #
# Drift + fail-closed
# --------------------------------------------------------------------------- #
def check_drift(current: List[CensusRow], baseline: Optional[dict]) -> List[DriftFinding]:
    """Return findings: 0-row (block), and vs baseline missing/removed-cols/row-regression."""
    findings: List[DriftFinding] = []
    for r in current:
        if r.is_empty:
            findings.append(DriftFinding(r.sport, r.name, "zero_rows", SEV_BLOCK,
                                         "corpus has 0 rows"))
    if baseline is None:
        return findings

    base = _rows_from_inventory(baseline)
    cur = {(r.sport, r.name): r for r in current}
    for key, b in base.items():
        c = cur.get(key)
        if c is None:
            findings.append(DriftFinding(key[0], key[1], "missing_corpus", SEV_BLOCK,
                                         "present in baseline, absent now"))
            continue
        removed = [col for col in b.columns if col not in c.columns]
        if removed:
            findings.append(DriftFinding(key[0], key[1], "removed_columns", SEV_BLOCK,
                                         "dropped: " + ",".join(sorted(removed))))
        elif c.schema_hash != b.schema_hash:
            findings.append(DriftFinding(key[0], key[1], "schema_change", SEV_WARN,
                                         "columns added / dtype changed"))
        if b.n_rows > 0 and c.n_rows < b.n_rows * (1.0 - _ROW_REGRESSION_TOL):
            findings.append(DriftFinding(key[0], key[1], "row_regression", SEV_BLOCK,
                                         f"rows {c.n_rows} < {b.n_rows} (baseline) by >{int(_ROW_REGRESSION_TOL*100)}%"))
    return findings


def fail_closed(
    root: str = _DEFAULT_ROOT,
    baseline_path: str = _DEFAULT_OUT,
    sports: Optional[List[str]] = None,
) -> tuple:
    """Return (ok, findings). ok is False if any BLOCK-severity finding exists."""
    current = scan_corpora(root, sports)
    baseline = load_inventory(baseline_path)
    findings = check_drift(current, baseline)
    ok = not any(f.severity == SEV_BLOCK for f in findings)
    return ok, findings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="per-sport data census + drift gate")
    ap.add_argument("cmd", choices=["scan", "check"])
    ap.add_argument("--root", default=_DEFAULT_ROOT)
    ap.add_argument("--out", default=_DEFAULT_OUT)
    ap.add_argument("--sport", action="append", default=None)
    args = ap.parse_args(argv)

    if args.cmd == "scan":
        inv = build_inventory(args.root, args.sport)
        dest = write_inventory(inv, args.out)
        empties = [r["name"] for r in inv["rows"] if r["is_empty"]]
        print(f"census: {inv['n_corpora']} corpora across {len(inv['sports'])} sports -> {dest}")
        print(f"sports: {','.join(inv['sports'])}")
        if empties:
            print(f"WARNING: {len(empties)} empty corpora: {','.join(empties)}")
        return 0

    ok, findings = fail_closed(args.root, args.out, args.sport)
    if not findings:
        print("drift check: OK (no findings)")
        return 0
    for f in findings:
        print(str(f))
    blocks = sum(1 for f in findings if f.severity == SEV_BLOCK)
    print(f"drift check: {'OK' if ok else 'FAIL'} ({blocks} blocking, {len(findings)-blocks} warn)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(_cli())
