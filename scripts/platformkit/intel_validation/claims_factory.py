"""Claims factory core (spec sec 2 BATCH EMISSION + sec 5 HONESTY,
CLAIMS_FACTORY_SPEC_2026-07-06.md, Fable rulings R1-R5, LANE L-A).

Reads a per-sport `GRID` dict (domains/<sport>/claims_grid.py -- pure DATA,
never imported here) and walks families x dims x windows x context_splits,
materializing one snapshot parquet per (family,window[,split]) and one
contract claim row per (entity,metric,window[,split]) -- the
context_shooting_claims.py precedent (snapshot + plain-aggregate criteria)
at n-dim scale instead of hand-written per dim.

CONTRACT: every row is the EXISTING shared claims contract verbatim
(kind="ranking", criteria{metric,formula,aggregate,min_sample,direction,
value_precision,entity_key}, ranking[], source_files, computed_at,
n_considered, n_excluded_below_floor, edge_claimed:false, caveats[]) -- a
batch PRODUCER only, zero contract changes. `criteria.formula =
f"({num})/({den})"` evaluates under safe_formula's AGGREGATE grammar;
`criteria.aggregate.group_by = entity_key` is exactly what
claims_validator.recompute_aggregate already independently re-derives.

FLOORS FAIL-CLOSED (spec sec 5 + R2/self-critique A): a window classifies
into a TYPE (season | career | split); the grid's `floors[type]` dict is
REQUIRED for every type the family uses, else FactoryError (no artifact).
Floor counts reuse safe_formula's `count_distinct`, never a hand groupby.

HONESTY POST-CHECKS (spec sec 5, binding): runs (a) the retracted-number/
token/key lint (governance.honesty_linter.lint_obj) on the pre-explosion
(dim,window) claims -- every per-entity exploded copy shares byte-identical
caveats/question/ranking, so linting post-explosion would re-scan the same
content N times for nothing -- and (b) an edge_claimed:false check on every
exploded row. EITHER trip ABORTS: no jsonl written.

CAVEATS auto-derived: R3 Fable-ruling VERBATIM caveat, window-coverage
line, floor line, fixed descriptive-only line (precedent at
context_shooting_claims.py:193). NO index building (L-D owns that). NO
gate fits, NO predictive claims, NO $/ROI language, NO registry writes.

CLI: python -m scripts.platformkit.intel_validation.claims_factory --sport basketball_nba
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from governance.honesty_linter import lint_obj
from scripts.platformkit.intel_validation.basketball_claims_io import atomic_write_parquet
from scripts.platformkit.intel_validation.safe_formula import (
    FormulaError,
    evaluate_group_formula,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUT_DIR = REPO_ROOT / "data" / "cache" / "intel_claims"
_VALUE_PRECISION = 4
_R3_CAVEAT = (
    "machine-verified-recompute; semantic adjudication at family-config "
    "review, not per claim"
)


class FactoryError(ValueError):
    """Fail-closed: missing floor, bad formula, or tripped honesty check; no artifact is written."""


def _to_source_ref(path: Path) -> str:
    """Repo-relative POSIX string under REPO_ROOT; absolute otherwise (tmp
    test out_dir) -- validator's `REPO_ROOT / rel` resolves either form."""
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _window_type(window: dict[str, Any], split: dict[str, Any] | None) -> str:
    """Floor-lookup TYPE: a split always wins (spec sec 1); else season/career by name."""
    if split is not None:
        return "split"
    if window["name"].startswith("career"):
        return "career"
    return "season"


def _window_name(window: dict[str, Any], split: dict[str, Any] | None) -> str:
    if split is None:
        return window["name"]
    return f"{window['name']}_{split['name']}"


def _slice_rows(df: pd.DataFrame, window: dict[str, Any], split: dict[str, Any] | None) -> pd.DataFrame:
    out = df
    for col, val in (window.get("filter") or {}).items():
        if col not in out.columns:
            raise FactoryError(f"window filter column not present: {col!r}")
        out = out[out[col] == val]
    if split is not None:
        col = split["col"]
        if col not in out.columns:
            raise FactoryError(f"split column not present: {col!r}")
        out = out[out[col] == split["eq"]]
    return out


def _floor_for(family: dict[str, Any], win_type: str) -> dict[str, Any]:
    floors = family.get("floors") or {}
    if win_type not in floors:
        raise FactoryError(f"family {family['family']!r}: no floors[{win_type!r}] -- fail-closed, no artifact written")
    return floors[win_type]


def _build_dim_claim(
    family: dict[str, Any], dim: dict[str, Any], window: dict[str, Any],
    split: dict[str, Any] | None, rows: pd.DataFrame, snapshot_rel: str,
    computed_at: str,
) -> dict[str, Any]:
    entity_key = family["entity_key"]
    if isinstance(entity_key, list):
        raise FactoryError("pair-keyed entity_key not yet supported by generate_family")
    group_by, name_col, metric = entity_key, family.get("entity_name_col"), dim["metric"]
    formula = f"({dim['agg']['num']})/({dim['agg']['den']})"
    win_name = _window_name(window, split)
    min_sample = _floor_for(family, _window_type(window, split))

    try:
        value_s = evaluate_group_formula(formula, rows, group_by)
        floor_cols = {col: evaluate_group_formula(f"count_distinct({col})", rows, group_by) for col in min_sample}
    except FormulaError as e:
        raise FactoryError(f"{family['family']}/{metric}/{win_name}: {e}") from e

    n_considered = int(value_s.index.nunique())
    mask = pd.Series(True, index=value_s.index)
    for col, floor in min_sample.items():
        mask &= floor_cols[col] >= floor
    # Zero (or non-finite) denominator entities (e.g. ast_to_tov for a
    # zero-turnover sample) must never reach the ranking as NaN/inf -- same
    # honest-exclusion idiom as the floor mask above, folded into the same
    # n_excluded count rather than a second bucket.
    mask &= np.isfinite(value_s.astype(float))
    ids_kept = value_s.index[mask]
    n_excluded = n_considered - len(ids_kept)

    names_map: dict[Any, str] = {}
    if name_col == group_by:
        names_map = {v: v for v in value_s.index}
    elif name_col and name_col in rows.columns:
        names_map = dict(rows.drop_duplicates(subset=[group_by]).set_index(group_by)[name_col])

    kept_s = value_s.loc[ids_kept]
    if family["family"].startswith("tennis_"):
        # TENNIS-ONLY tie-break: value DESC (declared direction), THEN
        # entity_key ASC, stable sort -- matches claims_validator.py's
        # validate_claim tie-break (gated on claim_id.startswith("tennis_"))
        # so grid-factory-produced tennis families (tennis_p1_match_context /
        # tennis_p2_match_context) resolve tied metric values identically to
        # the independent recompute, same fix class as tennis_ranking_
        # claims.py's 2026-07-18 fix (see claims_validator.py:192-209).
        tie_df = kept_s.rename("value").rename_axis(entity_key).reset_index()
        tie_df = tie_df.sort_values(["value", entity_key], ascending=[False, True], kind="mergesort")
        ranked = tie_df.set_index(entity_key)["value"]
    else:
        ranked = kept_s.sort_values(ascending=False)
    ranking = []
    for i, (eid, val) in enumerate(ranked.items(), start=1):
        entry: dict[str, Any] = {
            "rank": i,
            entity_key: eid.item() if hasattr(eid, "item") else eid,
            "value": round(float(val), _VALUE_PRECISION),
            "n": int(floor_cols[next(iter(min_sample))].loc[eid]) if min_sample else 0,
        }
        if name_col:
            entry[name_col] = names_map.get(eid, str(eid))
        ranking.append(entry)

    caveats = [
        f"window={win_name}, source rows={len(rows)}",
        f"floor: {min_sample} ({len(ids_kept)}/{n_considered} qualify, {n_excluded} below floor)",
        _R3_CAVEAT,
        "DESCRIPTIVE ranking only -- no forecasting/market/$ edge claimed.",
    ]

    claim = {
        "claim_id": None,  # per-ENTITY (spec sec 2); overwritten by _explode_per_entity, never read as-is
        "kind": "ranking",
        "question": f"{family['family']} {metric} leaderboard ({win_name})?",
        "criteria": {
            "metric": metric,
            "formula": formula,
            "aggregate": {"group_by": group_by, "derived": {c: f"count_distinct({c})" for c in min_sample}},
            "window": win_name,
            "min_sample": min_sample,
            "direction": "desc",
            "value_precision": _VALUE_PRECISION,
            "entity_key": entity_key,
        },
        "ranking": ranking,
        "source_files": [snapshot_rel],
        "computed_at": computed_at,
        "n_considered": n_considered,
        "n_excluded_below_floor": n_excluded,
        "edge_claimed": False,
        "caveats": caveats,
    }
    return claim


def _explode_per_entity(claim: dict[str, Any], family: str) -> list[dict[str, Any]]:
    """claim_id is PER ENTITY (spec sec 2) but recompute is one shared
    ranking -- explode into one row per surviving entity, each keeping the
    FULL ranking list (validator's rank-by-rank compare still works)."""
    entity_key, metric, window = (claim["criteria"][k] for k in ("entity_key", "metric", "window"))
    out = []
    for row in claim["ranking"]:
        exploded = dict(claim)
        exploded["claim_id"] = f"{family}__{row[entity_key]}__{metric}__{window}"
        out.append(exploded)
    return out


def generate_family(
    sport: str, family: str, grid: dict[str, Any], out_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize one (sport,family)'s claims jsonl; returns a summary dict.
    Raises FactoryError (NO artifact written) -- see module docstring."""
    fam_cfg = next((f for f in grid["families"] if f["family"] == family), None)
    if fam_cfg is None:
        raise FactoryError(f"family {family!r} not found in grid for sport {sport!r}")

    out_dir = out_dir or _DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    src_path = REPO_ROOT / fam_cfg["source"] if not Path(fam_cfg["source"]).is_absolute() else Path(fam_cfg["source"])
    df = pd.read_parquet(src_path)
    computed_at = datetime.now(timezone.utc).isoformat()

    splits: list[dict[str, Any] | None] = [None] + list(fam_cfg.get("context_splits") or [])
    all_claims: list[dict[str, Any]] = []
    dim_claims: list[dict[str, Any]] = []  # ONE pre-explosion claim per (dim,window) -- lint target
    n_excluded_total = 0

    for window in fam_cfg["windows"]:
        for split in splits:
            win_name = _window_name(window, split)
            rows = _slice_rows(df, window, split)
            if rows.empty:
                continue
            snap_path = out_dir / f"{family}__{win_name}_snapshot.parquet"
            atomic_write_parquet(pa.Table.from_pandas(rows, preserve_index=False), snap_path)
            snap_rel = _to_source_ref(snap_path)

            for dim in fam_cfg["dims"]:
                claim = _build_dim_claim(fam_cfg, dim, window, split, rows, snap_rel, computed_at)
                n_excluded_total += claim["n_excluded_below_floor"]
                dim_claims.append(claim)
                all_claims.extend(_explode_per_entity(claim, family))

    # Lint pre-explosion dim_claims, not all_claims -- see module docstring.
    _assert_edge_claimed_false(all_claims, family)
    lint_result = lint_obj(dim_claims)
    if not lint_result["clean"]:
        raise FactoryError(f"family {family!r} tripped honesty lint, ABORTED: {lint_result['violations']}")

    out_path = out_dir / f"{family}.jsonl"
    tmp_path = out_path.with_name(f"{out_path.stem}.{uuid.uuid4().hex}.tmp{out_path.suffix}")
    with open(tmp_path, "w", encoding="ascii", errors="strict") as f:
        for row in all_claims:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp_path, out_path)

    return {
        "sport": sport,
        "family": family,
        "n_claims": len(all_claims),
        "n_excluded_below_floor": n_excluded_total,
        "out_path": str(out_path),
    }


def _assert_edge_claimed_false(claims: list[dict[str, Any]], family: str) -> None:
    for c in claims:
        if c.get("edge_claimed") is not False:
            raise FactoryError(f"family {family!r}: claim_id={c.get('claim_id')!r} missing/true edge_claimed")


def generate_sport(sport: str, grid: dict[str, Any], out_dir: Path | None = None) -> list[dict[str, Any]]:
    # Fail-closed: a FactoryError here is NOT caught, so one bad family aborts the whole sport.
    return [generate_family(sport, fam["family"], grid, out_dir) for fam in grid["families"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claims factory: grid -> batch claims jsonl")
    parser.add_argument("--sport", required=True, help="e.g. basketball_nba")
    parser.add_argument("--family", default=None, help="single family; default = all in the grid")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args(argv)

    grid_module = __import__(f"domains.{args.sport}.claims_grid", fromlist=["GRID"])
    grid = grid_module.GRID
    out_dir = Path(args.out_dir) if args.out_dir else None

    if args.family:
        results = [generate_family(args.sport, args.family, grid, out_dir)]
    else:
        results = generate_sport(args.sport, grid, out_dir)

    for r in results:
        print(f"{r['family']}: n_claims={r['n_claims']} n_excluded_below_floor={r['n_excluded_below_floor']} -> {r['out_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
