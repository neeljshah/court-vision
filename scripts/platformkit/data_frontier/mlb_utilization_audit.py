"""scripts.platformkit.data_frontier.mlb_utilization_audit -- MLB stat-utilization
census: every column on disk (statcast, leaderboards, in-game states, domains/mlb
derived corpora) vs whether domains/mlb or scripts/platformkit actually reference
its name anywhere (git grep, word-boundary match). USED_IN lists the matching
files; everything else is UNUSED (not proof of no value -- just no consumer yet).

Cheap by construction: parquet schemas read via pyarrow metadata (never a full
table load); CSVs sampled with nrows; jsonl sampled first N lines. Corpus list
below is a snapshot from the 2026-07-09 audit -- add new paths as new corpora
land; this script does not discover them on its own (ponytail: a real crawler
would double the LOC for a one-a-quarter task).

Output: data/frontend/ops/mlb_stat_utilization.json (local-only, gitignored).
CLI: python -m scripts.platformkit.data_frontier.mlb_utilization_audit
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyarrow.parquet as pq

_REPO = Path(__file__).resolve().parents[3]
_OUT_FP = _REPO / "data" / "frontend" / "ops" / "mlb_stat_utilization.json"
_SEARCH_ROOTS = ["domains/mlb", "scripts/platformkit"]

# (path relative to repo root, kind) -- kind picks the cheap-read strategy.
# Representative file per corpus family; sibling year-files share a schema.
CORPORA: List[Tuple[str, str]] = [
    ("data/cache/statcast/savant_full__2024.parquet", "parquet"),
    ("data/cache/statcast/savant_hitcoords__2024.parquet", "parquet"),
    ("data/cache/statcast/statcast_fuller__2023.parquet", "parquet"),
    ("data/cache/statcast/starter_table__2023.parquet", "parquet"),
    ("data/cache/statcast/leaderboards/bat_tracking_consolidated.parquet", "parquet"),
    ("data/cache/statcast/leaderboards/catch_probability_consolidated.parquet", "parquet"),
    ("data/cache/statcast/leaderboards/outs_above_average_consolidated.parquet", "parquet"),
    ("data/cache/ingame/mlb_pitch_states__2026.parquet", "parquet"),
    ("data/cache/ingame/mlb_atbat_states__2023.parquet", "parquet"),
    ("data/cache/ingame/mlb_states__2024.parquet", "parquet"),
    ("data/cache/combo/gate_corpus_mlb.parquet", "parquet"),
    ("data/domains/mlb/probables.parquet", "parquet"),
    ("data/domains/mlb/umpire_zone_index.parquet", "parquet"),
    ("data/domains/mlb/umpire_totals_gate_rows.parquet", "parquet"),
    ("data/domains/mlb/travel_scouting.parquet", "parquet"),
    ("data/domains/mlb/sp_velo_states.parquet", "parquet"),
    ("data/domains/mlb/platoon_split_index.parquet", "parquet"),
    ("data/domains/mlb/postmortem.parquet", "parquet"),
    ("data/domains/mlb/asof_features.parquet", "parquet"),
    ("data/domains/mlb/asof_park_savant_local.parquet", "parquet"),
    ("data/domains/mlb/gumbo_live", "jsonl_dir"),
    ("data/cache/mlb_lineups", "jsonl_dir"),
    ("data/cache/edge_engine/injury_facts_mlb.jsonl", "jsonl"),
    ("data/cache/edge_engine/news_facts_mlb.jsonl", "jsonl"),
]


def _parquet_schema(path: Path) -> List[Tuple[str, str, float]]:
    pf = pq.ParquetFile(path)
    batch = next(pf.iter_batches(batch_size=5000), None)
    df = batch.to_pandas() if batch is not None else pd.DataFrame()
    out = []
    for name, dtype in zip(pf.schema_arrow.names, pf.schema_arrow.types):
        cov = round((1 - df[name].isnull().mean()) * 100, 1) if name in df.columns and len(df) else None
        out.append((name, str(dtype), cov))
    return out


def _jsonl_fields(path: Path, n: int = 10) -> List[Tuple[str, str, Optional[float]]]:
    fields: Dict[str, int] = {}
    total = 0
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= n:
                break
            rec = json.loads(line)
            total += 1
            for k, v in rec.items():
                if v is not None:
                    fields[k] = fields.get(k, 0) + 1
    return [(k, "jsonl_field", round(100 * cnt / total, 1) if total else None) for k, cnt in fields.items()]


def _jsonl_dir_fields(dirpath: Path, n_files: int = 3, n_lines: int = 10) -> List[Tuple[str, str, Optional[float]]]:
    files = sorted(dirpath.glob("*.jsonl"))
    if not files:
        return []
    sample = [files[0], files[len(files) // 2], files[-1]][:min(n_files, len(files))]
    fields: Dict[str, int] = {}
    total = 0
    for fp in sample:
        for name, _, _ in _jsonl_fields(fp, n=n_lines):
            fields[name] = fields.get(name, 0) + 1
        with open(fp, "r", encoding="utf-8") as fh:
            total += sum(1 for _, __ in zip(fh, range(n_lines)))
    return [(k, "jsonl_field", None) for k in fields]


def schema_for(rel_path: str, kind: str) -> List[Tuple[str, str, Optional[float]]]:
    path = _REPO / rel_path
    if not path.exists():
        return []
    if kind == "parquet":
        return _parquet_schema(path)
    if kind == "jsonl":
        return _jsonl_fields(path)
    if kind == "jsonl_dir":
        return _jsonl_dir_fields(path)
    raise ValueError(f"unknown kind {kind}")


def consumers_for(column: str, roots: List[str] = _SEARCH_ROOTS, cap: int = 5) -> List[str]:
    """git grep -n -w <column> under each root; capped file:line hit list."""
    hits: List[str] = []
    for root in roots:
        try:
            res = subprocess.run(
                ["git", "grep", "-n", "-w", column, "--", root],
                cwd=_REPO, capture_output=True, text=True, timeout=30,
            )
        except Exception:  # noqa: BLE001 -- grep unavailable is a data gap, not a crash
            continue
        if res.returncode == 0:
            hits.extend(res.stdout.strip().splitlines())
        if len(hits) >= cap:
            break
    return hits[:cap]


def build_inventory() -> List[Dict[str, object]]:
    seen: Dict[str, Dict[str, object]] = {}
    for rel_path, kind in CORPORA:
        for name, dtype, cov in schema_for(rel_path, kind):
            row = seen.setdefault(name, {"column": name, "dtype": dtype, "corpora": [], "coverage_pct_sample": cov})
            row["corpora"].append(rel_path)
    rows = []
    for name, row in sorted(seen.items()):
        hits = consumers_for(name)
        row["used_in"] = hits
        row["status"] = "USED" if hits else "UNUSED"
        rows.append(row)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="MLB stat-utilization census (schema + consumption).")
    ap.add_argument("--out", default=str(_OUT_FP))
    a = ap.parse_args(argv)
    rows = build_inventory()
    out_fp = Path(a.out)
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    out_fp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    used = sum(1 for r in rows if r["status"] == "USED")
    print(json.dumps({"total_columns": len(rows), "used": used, "unused": len(rows) - used, "out": str(out_fp)}, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["schema_for", "consumers_for", "build_inventory", "main", "CORPORA"]
