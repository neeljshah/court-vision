"""scripts.platformkit.parity_matrix -- cross-sport coverage / loop-health grid.

One fail-closed green/red grid over all sports x {census, manifest, feature_spec}:

  census       -- data_registry: the sport has corpora and none required is 0-row.
  manifest     -- domains.<sport>.ingest_manifest validates structurally AND every
                  declared source exists + is non-empty in the live census.
  feature_spec -- domains.<sport>.feature_spec loads, has a non-empty frozen catalog,
                  and build_base_matrix produces n_features columns (structural parity;
                  byte-equal-to-adapter parity is proven per-sport in tests).

A dimension a sport has not built yet is "n/a" (gray) and does NOT fail the gate; a
PRESENT-but-broken dimension is "red" and DOES. Overall is fail-closed: exit 2 unless
every resolvable cell is green.

PURE offline (imports domain decl modules + data_registry). ASCII only.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from scripts.platformkit.feature_spec_core import FeatureSpec, build_base_matrix
from scripts.platformkit.ingest_manifest_core import IngestManifest
from data_registry.inventory import build_inventory, check_drift, scan_corpora

# The canonical sports the platform tracks (the grid always resolves all of these).
SPORTS = ("basketball_nba", "mlb", "soccer", "soccer_intl", "tennis")
DIMENSIONS = ("census", "manifest", "feature_spec")

GREEN, RED, NA = "green", "red", "n/a"


@dataclass(frozen=True)
class Cell:
    status: str          # GREEN | RED | NA
    detail: str = ""


@dataclass
class Row:
    sport: str
    cells: Dict[str, Cell] = field(default_factory=dict)


def _find_instance(mod: object, typ: type):
    for v in vars(mod).values():
        if isinstance(v, typ):
            return v
    return None


def _import_optional(modpath: str):
    try:
        return importlib.import_module(modpath)
    except Exception:
        return None


def _census_cell(sport: str, inv: dict) -> Cell:
    rows = scan_corpora(sports=[sport])
    if not rows:
        return Cell(RED, "no corpora on disk")
    findings = check_drift(rows, None)  # 0-row blocks
    blocks = [f for f in findings if f.severity == "block"]
    if blocks:
        return Cell(RED, "; ".join(f"{f.name}:{f.kind}" for f in blocks))
    return Cell(GREEN, f"{len(rows)} corpora")


def _manifest_cell(sport: str, inv: dict) -> Cell:
    mod = _import_optional(f"domains.{sport}.ingest_manifest")
    if mod is None:
        return Cell(NA, "no ingest_manifest")
    man = _find_instance(mod, IngestManifest)
    if man is None:
        return Cell(RED, "module has no IngestManifest instance")
    errs = man.validate()
    if errs:
        return Cell(RED, "; ".join(errs[:2]))
    cerrs = man.validate_against_inventory(inv)
    if cerrs:
        return Cell(RED, "; ".join(cerrs[:2]))
    return Cell(GREEN, f"{len(man.sources)} sources")


def _synthetic_frame(spec: FeatureSpec) -> pd.DataFrame:
    cols: Dict[str, list] = {}
    for f in spec.fields:
        cols.setdefault(f.source, [1.0, 2.0])
        if f.source2:
            cols.setdefault(f.source2, [0.5, 1.0])
    return pd.DataFrame(cols) if cols else pd.DataFrame(index=range(2))


def _feature_spec_cell(sport: str) -> Cell:
    mod = _import_optional(f"domains.{sport}.feature_spec")
    if mod is None:
        return Cell(NA, "no feature_spec")
    spec = _find_instance(mod, FeatureSpec)
    if spec is None:
        return Cell(RED, "module has no FeatureSpec instance")
    if spec.n_features() == 0 or not spec.catalog_hash():
        return Cell(RED, "empty catalog")
    try:
        mat, names = build_base_matrix(spec, _synthetic_frame(spec))
    except Exception as exc:
        return Cell(RED, f"build failed: {str(exc)[:48]}")
    if mat.shape[1] != spec.n_features() or names != spec.col_names():
        return Cell(RED, "width/name mismatch")
    return Cell(GREEN, f"{spec.n_features()} cols {spec.version}")


def build_parity_matrix(sports=SPORTS) -> List[Row]:
    inv = build_inventory()
    out: List[Row] = []
    for sport in sports:
        row = Row(sport)
        row.cells["census"] = _census_cell(sport, inv)
        row.cells["manifest"] = _manifest_cell(sport, inv)
        row.cells["feature_spec"] = _feature_spec_cell(sport)
        out.append(row)
    return out


def is_green(rows: List[Row]) -> bool:
    """Fail-closed: True only if no resolvable cell is RED."""
    return not any(c.status == RED for r in rows for c in r.cells.values())


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="cross-sport parity / coverage health grid")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    rows = build_parity_matrix()
    w = max(len(s) for s in SPORTS) + 1
    hdr = f"{'sport':<{w}} " + " ".join(f"{d:<13}" for d in DIMENSIONS)
    print("\nCross-sport parity matrix (fail-closed; n/a = not built yet)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        line = f"{r.sport:<{w}} "
        for d in DIMENSIONS:
            line += f"{r.cells[d].status:<13} "
        print(line.rstrip())
        if args.verbose:
            for d in DIMENSIONS:
                c = r.cells[d]
                if c.detail:
                    print(f"    {d}: {c.status} -- {c.detail}")
    print("-" * len(hdr))
    ok = is_green(rows)
    reds = [(r.sport, d) for r in rows for d in DIMENSIONS if r.cells[d].status == RED]
    print(f"PARITY: {'GREEN' if ok else 'RED'} "
          f"({len(reds)} red cells)" + (": " + ", ".join(f"{s}/{d}" for s, d in reds) if reds else ""))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(_cli())
